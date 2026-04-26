import json
from typing import List, Any, Optional
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


def display_config_panel(server_url: Optional[str], health_url: Optional[str] = None):
    """Display configuration information in a panel."""

    config_table = Table.grid(padding=(0, 2))
    config_table.add_column(style="bold cyan", justify="right")
    config_table.add_column(style="white")

    server_url_display = server_url or "[dim]Not configured[/dim]"
    config_table.add_row("Server URL:", server_url_display)
    if health_url:
        config_table.add_row("Health URL:", health_url)
    else:
        config_table.add_row("Health URL:", "[dim]Not configured[/dim]")

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


def _highlight_json_in_text(text: str):
    """Highlight JSON content in text with syntax colors.

    Detects JSON objects/arrays and applies basic syntax highlighting.
    Returns a Text object with styled content.
    """
    import re

    # Simple check if text looks like it contains JSON
    if not any(char in text for char in ["{", "[", '":']):
        return text

    # Try to detect and highlight JSON-like patterns
    result = Text()

    # Pattern to match JSON-like content (simple approach)
    # This will highlight common JSON patterns with colors
    current_pos = 0

    # Find JSON strings (simple pattern for "key": "value")
    string_pattern = r'"([^"\\]*(\\.[^"\\]*)*)"'

    for match in re.finditer(string_pattern, text):
        # Add text before match
        if match.start() > current_pos:
            result.append(text[current_pos : match.start()])

        # Add the matched string with color
        matched_text = match.group(0)

        # Check if this looks like a key (followed by :)
        next_char_pos = match.end()
        if next_char_pos < len(text) and text[next_char_pos : next_char_pos + 1].strip().startswith(
            ":"
        ):
            result.append(matched_text, style="bold cyan")  # JSON key
        else:
            result.append(matched_text, style="green")  # JSON value

        current_pos = match.end()

    # Add remaining text
    if current_pos < len(text):
        remaining = text[current_pos:]
        # Trick: insert a zero-width space after each JSON delimiter so we
        # can split on it and style each piece. The U+200B is invisible to
        # the user but gives us a unique split character that won't collide
        # with anything in the JSON itself.
        remaining = remaining.replace("{", "{\u200b")
        remaining = remaining.replace("}", "}\u200b")
        remaining = remaining.replace("[", "[\u200b")
        remaining = remaining.replace("]", "]\u200b")
        remaining = remaining.replace(":", ":\u200b")

        for part in remaining.split("\u200b"):
            if part in ["{", "}", "[", "]"]:
                result.append(part, style="bold yellow")
            elif part == ":":
                result.append(part, style="dim")
            else:
                result.append(part)

    return result if len(result) > 0 else text


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
    """Display the tool view menu options."""
    display_commands(
        [
            ("d", "View details"),
            ("r", "Run tool"),
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
