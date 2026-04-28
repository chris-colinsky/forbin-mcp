import asyncio
import json
import sys
import time
from typing import Any, Dict, List, TYPE_CHECKING
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax

from .display import console
from .utils import copy_to_clipboard, read_single_key
from .verbose import vlog_json, vlog_timing

if TYPE_CHECKING:
    from .client import MCPSession


async def list_tools(mcp_session: "MCPSession") -> List[Any]:
    """
    List all available tools from the MCP server.

    Args:
        mcp_session: Connected MCPSession

    Returns:
        List of tool objects
    """
    with console.status("  [dim]Retrieving tool manifest...[/dim]", spinner="dots"):
        tools = await asyncio.wait_for(mcp_session.list_tools(), timeout=15.0)

    return tools


def parse_parameter_value(value_str: str, param_type: str) -> Any:
    """Parse a string input into the appropriate type."""
    # Empty input means "skip" — caller decides whether that's allowed.
    if not value_str.strip():
        return None

    if param_type == "boolean":
        return value_str.lower() in ("true", "t", "yes", "y", "1")
    elif param_type == "integer":
        # Bare conversions: ValueError / JSONDecodeError propagate to the
        # input loop in get_tool_parameters, which reprompts.
        return int(value_str)
    elif param_type == "number":
        return float(value_str)
    elif param_type in ("object", "array"):
        return json.loads(value_str)
    else:  # string (or any unknown type — pass through verbatim)
        return value_str


def get_tool_parameters(tool: Any) -> Dict[str, Any]:
    """Interactively collect parameters for a tool."""
    params: dict[str, Any] = {}

    if not tool.inputSchema or not isinstance(tool.inputSchema, dict):
        return params

    properties = tool.inputSchema.get("properties", {})
    required = tool.inputSchema.get("required", [])

    if not properties:
        return params

    console.print()
    console.rule("[bold cyan]ENTER PARAMETERS[/bold cyan]")
    console.print("Enter parameter values (press [bold]Enter[/bold] to skip optional parameters)\n")

    for param_name, param_info in properties.items():
        param_type = param_info.get("type", "string")
        param_desc = param_info.get("description", "")
        is_required = param_name in required

        # Header line: name, type, required/optional badge.
        req_str = "[red](required)[/red]" if is_required else "[green](optional)[/green]"
        console.print(f"[bold cyan]{param_name}[/bold cyan] ({param_type}) {req_str}")
        if param_desc:
            console.print(f"  [dim]{param_desc}[/dim]")

        if "enum" in param_info:
            console.print(f"  Allowed values: {', '.join(str(v) for v in param_info['enum'])}")

        # Reprompt loop: keep asking until we either parse the value or accept
        # the user's empty-input "skip" for an optional field.
        while True:
            try:
                # Plain Prompt (not IntPrompt/etc) so we can handle skipping
                # and the wider set of MCP types ourselves.
                value_str = Prompt.ask("  ->", default="", show_default=False)

                if not value_str:
                    if is_required:
                        console.print(
                            "  [red]This parameter is required. Please enter a value.[/red]"
                        )
                        continue
                    else:
                        break

                value = parse_parameter_value(value_str, param_type)
                params[param_name] = value
                break

            except (ValueError, json.JSONDecodeError) as e:
                console.print(f"  [red]Invalid value for type {param_type}:[/red] {e}")
                console.print("  Please try again.")

        console.print()

    return params


async def _wait_for_escape():
    """Listen for an ESC key press in the background. Returns when ESC is detected."""
    # All three early-return branches below fall back to "wait forever":
    # the parent uses asyncio.wait(FIRST_COMPLETED), so the tool task will
    # win the race instead. We just need this coroutine to never resolve
    # on its own when ESC isn't actually monitorable.
    try:
        import termios
        import tty
        import select
    except ImportError:
        await asyncio.Event().wait()
        return

    try:
        fd = sys.stdin.fileno()
    except (AttributeError, OSError):
        # stdin is redirected (e.g. in pytest); no fd to read from.
        await asyncio.Event().wait()
        return
    if not sys.stdin.isatty():
        await asyncio.Event().wait()
        return

    # Switch the terminal to cbreak so single keypresses arrive without Enter.
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            # Non-blocking poll: 100ms is short enough to feel responsive
            # and long enough to keep CPU near zero.
            if select.select([sys.stdin], [], [], 0.1)[0]:
                char = sys.stdin.read(1)
                if char == "\x1b":  # ESC key
                    return
            await asyncio.sleep(0.1)
    finally:
        # Always restore the terminal, even if the task is cancelled.
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


async def call_tool(mcp_session: "MCPSession", tool: Any, params: Dict[str, Any]):
    """Call a tool with the given parameters."""
    console.print()
    console.rule("[bold magenta]CALLING TOOL[/bold magenta]")
    console.print(f"Tool: [bold]{tool.name}[/bold]")
    console.print()

    if tool.inputSchema:
        vlog_json("Tool Input Schema", tool.inputSchema)

    # Echo the parameters back as syntax-highlighted JSON so the user can
    # confirm what's actually being sent before we await the response.
    if params:
        json_str = json.dumps(params, indent=2)
        console.print(
            Panel(
                Syntax(json_str, "json", theme="monokai", line_numbers=False),
                title="[bold]Parameters[/bold]",
                title_align="left",
                border_style="cyan",
            )
        )
    else:
        console.print("[dim]No parameters[/dim]")

    console.print("\n[bold]Executing...[/bold] [dim](press ESC to cancel)[/dim]")

    try:
        call_start = time.monotonic()
        # Race the tool call against an ESC-key listener so the user can
        # cancel a hanging tool without ctrl+C-ing the whole CLI.
        tool_task = asyncio.create_task(mcp_session.call_tool(tool.name, params))
        esc_task = asyncio.create_task(_wait_for_escape())

        with console.status("Waiting for response...", spinner="dots"):
            done, pending = await asyncio.wait(
                {tool_task, esc_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

        # Cancel whichever task lost the race so it doesn't leak.
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if esc_task in done:
            console.print("\n[bold yellow]Cancelled by user[/bold yellow]\n")
            return

        result = tool_task.result()
        vlog_timing("Full round-trip", time.monotonic() - call_start)

        console.print("\n[bold green]Tool execution completed![/bold green]\n")
        console.rule("[bold green]RESULT[/bold green]")
        console.print()

        # Extract and display result. We accumulate `copyable_blocks` in
        # parallel with rendering so the post-result clipboard prompt has
        # access to the exact text the user just saw — including the
        # JSON-formatted version when parsing succeeded.
        copyable_blocks: list[str] = []
        if result.content:
            for item in result.content:
                # Explicit annotation pulls the type out of `Any` so PyCharm
                # narrows it cleanly on the None-check below — without it,
                # the .strip() call gets a "could be None" warning.
                text: str | None = getattr(item, "text", None)
                if text is not None:
                    # Cheap shape check before paying for json.loads — only
                    # try to parse if the text actually looks like a JSON
                    # object/array. Falls through to plain text on any miss.
                    text_stripped = text.strip()
                    if text_stripped.startswith(("{", "[")) and text_stripped.endswith(("}", "]")):
                        try:
                            parsed = json.loads(text_stripped)
                            formatted = json.dumps(parsed, indent=2)
                            console.print(
                                Panel(
                                    Syntax(formatted, "json", theme="monokai", line_numbers=False),
                                    border_style="green",
                                    title="[bold]Response[/bold]",
                                    title_align="left",
                                )
                            )
                            copyable_blocks.append(formatted)
                            continue
                        except json.JSONDecodeError:
                            pass

                    # For non-JSON text responses
                    console.print(
                        Panel(
                            text_stripped,
                            border_style="green",
                            title="[bold]Response[/bold]",
                            title_align="left",
                        )
                    )
                    copyable_blocks.append(text_stripped)
                else:
                    rendered = str(item)
                    console.print(rendered)
                    copyable_blocks.append(rendered)
        else:
            console.print("[dim]No content returned[/dim]")

        console.print()
        console.rule()
        console.print()

        if copyable_blocks:
            _prompt_copy_to_clipboard("\n\n".join(copyable_blocks))

    except Exception as e:
        console.print(f"[bold red]Tool execution failed:[/bold red] {type(e).__name__}")
        console.print(f"   Error: {e}\n")


def _prompt_copy_to_clipboard(text: str) -> None:
    """Offer a single-key 'c' shortcut to copy `text` to the clipboard.
    No-op when stdin isn't a TTY (read_single_key returns None there)."""
    console.print(
        "[dim]Press [bold cyan]c[/bold cyan] to copy response to clipboard, "
        "any other key to continue...[/dim]"
    )
    key = read_single_key()
    if key is None:
        return
    # Echo a newline so subsequent menu output starts on a fresh line —
    # the keystroke itself isn't echoed back to the terminal.
    console.print()
    if key == "c":
        if copy_to_clipboard(text):
            console.print("[green]+ Copied to clipboard[/green]\n")
        else:
            console.print(
                "[yellow]- Could not access clipboard "
                "(install xclip/xsel on Linux, or check pyperclip docs)[/yellow]\n"
            )
