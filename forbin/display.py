import json
from typing import List, Any
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.control import Control
from rich.segment import ControlType

# Global console instance with constrained width for better readability
console = Console(width=100)


def display_logo():
    """Display the Forbin ASCII logo."""
    # Lazy import: __version__ is set in forbin/__init__.py at import time, but
    # importing it at module top would create a partial-import risk during the
    # parent package's own initialisation chain.
    from . import __version__

    logo = f"""
[bold cyan]
  ███████╗ ██████╗ ██████╗ ██████╗ ██╗███╗   ██╗
  ██╔════╝██╔═══██╗██╔══██╗██╔══██╗██║████╗  ██║
  █████╗  ██║   ██║██████╔╝██████╔╝██║██╔██╗ ██║
  ██╔══╝  ██║   ██║██╔══██╗██╔══██╗██║██║╚██╗██║
  ██║     ╚██████╔╝██║  ██║██████╔╝██║██║ ╚████║
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝╚═╝  ╚═══╝[/bold cyan]
[dim]         MCP Remote Tool Tester v{__version__}[/dim]
[italic dim]    "This is the voice of world control..."[/italic dim]
"""
    console.print(logo)


def display_config_panel():
    """Display all configuration values in a panel.

    Reads directly from the live `config` module so callers don't need to
    thread the ever-growing list of settings through every call site.
    """
    from . import config

    config_table = Table.grid(padding=(0, 2))
    config_table.add_column(style="bold cyan", justify="right")
    config_table.add_column(style="white")

    not_set = "[dim]Not configured[/dim]"

    config_table.add_row("Profile:", config.ACTIVE_PROFILE)
    config_table.add_row("Environment:", config.ACTIVE_ENV)
    config_table.add_row("Server URL:", config.MCP_SERVER_URL or not_set)
    config_table.add_row("Health URL:", config.MCP_HEALTH_URL or not_set)

    # Mask the token — show enough to identify it without leaking the secret.
    if config.MCP_TOKEN:
        token_display = (
            config.MCP_TOKEN[:8] + "..." if len(config.MCP_TOKEN) > 8 else "[dim]hidden[/dim]"
        )
    else:
        token_display = not_set
    config_table.add_row("Token:", token_display)

    verbose_display = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"
    config_table.add_row("Verbose:", verbose_display)
    config_table.add_row("Tool Timeout:", f"{config.MCP_TOOL_TIMEOUT:g}s")

    console.print()
    console.print(
        Panel(
            config_table,
            title="[bold]Configuration[/bold]",
            title_align="left",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()


def display_step(
    step_num: int, total_steps: int, title: str, status: str = "in_progress", update: bool = False
):
    """Display a step indicator with status.

    Args:
        step_num: Current step number
        total_steps: Total number of steps
        title: Step title
        status: One of 'in_progress', 'success', 'skip'
        update: If True, updates the previous line instead of creating a new one
    """
    icons = {"in_progress": ">", "success": "+", "skip": "-"}

    colors = {"in_progress": "yellow", "success": "green", "skip": "dim"}

    icon = icons.get(status, "*")
    color = colors.get(status, "white")

    step_text = f"[{color}]{icon} Step {step_num}/{total_steps}:[/{color}] [bold {color}]{title}[/bold {color}]"

    if update:
        # In-place update: rewind one line and clear it, so a "Step 1: ✓"
        # success replaces the earlier "Step 1: ⏳ in progress" line.
        console.control(Control((ControlType.CURSOR_UP, 1), (ControlType.ERASE_IN_LINE, 2)))
        console.print(step_text)
    else:
        console.print(step_text)


def display_tools(tools: List[Any]):
    """Display a compact list of available tools."""
    if not tools:
        console.print(
            Panel(
                "No tools available on this server.", title="Available Tools", border_style="yellow"
            )
        )
        return

    console.print()
    console.print("[bold underline]Available Tools[/bold underline]")
    console.print()

    for i, tool in enumerate(tools, 1):
        description = tool.description.strip() if tool.description else "No description"
        # Truncate to keep each tool on a single 100-col line.
        if len(description) > 60:
            description = description[:57] + "..."
        console.print(
            f"  [bold cyan]{i:2}[/bold cyan]. [white]{tool.name}[/white] [dim]- {description}[/dim]"
        )

    console.print()


def display_tool_header(tool: Any):
    """Display a simple header for the tool view."""
    console.print()
    console.rule(f"[bold cyan]{tool.name}[/bold cyan]")
    console.print()


def display_commands(items: List[tuple]):
    """Render a uniform 'Commands:' block.

    Args:
        items: list of (key_label, description) tuples. Use 'Enter' as the
        key_label for the Enter key (it will be rendered as [Enter]).
    """
    console.print("[bold underline]Commands:[/bold underline]")
    # Pad each key to the widest label so all the descriptions line up vertically.
    max_visible = max(len(f"[{k}]") for k, _ in items)
    for key, desc in items:
        pad = " " * (max_visible - len(f"[{key}]"))
        console.print(f"  [bold cyan]\\[{key}][/bold cyan]{pad} - {desc}")
    console.print()


def display_tool_menu():
    """Display the tool view menu options.

    Reads `config.VERBOSE` at render time so the displayed state reflects
    the current value after a toggle, without the caller having to thread
    it through.
    """
    from . import config

    verbose_state = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"
    display_commands(
        [
            ("d", "View details"),
            ("r", "Run tool"),
            ("v", f"Toggle verbose logging (currently: {verbose_state})"),
            ("c", "Change configuration"),
            ("p", "Switch profile / environment"),
            ("b", "Back to tool list"),
            ("q", "Quit"),
        ]
    )


def _parse_description_with_code_blocks(description: str) -> List[Any]:
    """Parse description and extract code blocks for syntax highlighting."""
    import re

    content: List[Any] = []

    # Pattern to match ```json ... ``` or ``` ... ``` code blocks
    code_block_pattern = r"```(\w*)\n(.*?)```"

    last_end = 0
    for match in re.finditer(code_block_pattern, description, re.DOTALL):
        # Add text before the code block
        before_text = description[last_end : match.start()].strip()
        if before_text:
            content.append(Text(before_text))
            content.append(Text(""))

        # Get language and code
        lang = match.group(1) or "json"
        code = match.group(2).strip()

        # Add syntax-highlighted code block
        content.append(Syntax(code, lang, theme="monokai", line_numbers=False))
        content.append(Text(""))

        last_end = match.end()

    # Add any remaining text after the last code block
    remaining = description[last_end:].strip()
    if remaining:
        content.append(Text(remaining))

    return content


def display_tool_schema(tool: Any):
    """Display detailed schema for a specific tool with syntax-highlighted JSON."""

    content: List[Any] = []

    # Description with parsed code blocks
    if tool.description:
        parsed_content = _parse_description_with_code_blocks(tool.description)
        content.extend(parsed_content)
        if parsed_content:
            content.append(Text(""))

    # Input Schema as syntax-highlighted JSON
    if tool.inputSchema:
        content.append(Text("Input Schema:", style="bold underline"))
        content.append(Text(""))
        json_str = json.dumps(tool.inputSchema, indent=2)
        content.append(Syntax(json_str, "json", theme="monokai", line_numbers=False))
    else:
        content.append(Text("No input parameters required.", style="dim"))

    # Combine all content
    panel_content = Group(*content)

    console.print()
    console.print(
        Panel(
            panel_content,
            title=f"[bold]{tool.name}[/bold] - Details",
            border_style="blue",
            expand=False,
        )
    )
    console.print()
