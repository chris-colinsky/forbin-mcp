import asyncio
import os
import sys
import time

from rich.prompt import Prompt

from . import config
from .config import (
    validate_config,
    is_first_run,
    is_env_shadowed,
    run_first_time_setup,
    reload_config,
    load_config,
    save_config,
    CONFIG_FILE,
)
from .utils import setup_logging, listen_for_toggle
from .client import connect_and_list_tools, wake_up_server
from .tools import get_tool_parameters, call_tool
from .verbose import vlog_timing
from .display import (
    display_tools,
    display_tool_header,
    display_tool_menu,
    display_tool_schema,
    display_logo,
    display_config_panel,
    display_step,
    console,
)


def _toggle_verbose():
    """Toggle verbose mode and persist the setting."""
    config.VERBOSE = not config.VERBOSE
    # Persist to config file
    cfg = load_config()
    cfg["VERBOSE"] = str(config.VERBOSE).lower()
    save_config(cfg)
    # Drop any env-var shadow so the new value sticks for the rest of this session.
    os.environ.pop("VERBOSE", None)
    status = "[bold green]ON[/bold green]" if config.VERBOSE else "[bold red]OFF[/bold red]"
    console.print(f"\n[bold cyan]Verbose logging toggled {status}[/bold cyan]\n")


def handle_config_command():
    """Show current config and allow interactive editing. Loops until user exits. Returns True if any setting changed."""
    changed = False

    while True:
        token_display = (
            config.MCP_TOKEN[:8] + "..."
            if config.MCP_TOKEN and len(config.MCP_TOKEN) > 8
            else config.MCP_TOKEN or "[dim]Not set[/dim]"
        )
        verbose_display = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"

        def _env_tag(key: str) -> str:
            return " [yellow](env)[/yellow]" if is_env_shadowed(key) else ""

        any_shadowed = any(
            is_env_shadowed(k) for k in ("MCP_SERVER_URL", "MCP_TOKEN", "MCP_HEALTH_URL", "VERBOSE")
        )

        console.print()
        console.print("[bold underline]Configuration[/bold underline]")
        console.print()
        console.print(
            f"  [bold cyan]1.[/bold cyan] MCP_SERVER_URL:  "
            f"{config.MCP_SERVER_URL or '[dim]Not set[/dim]'}{_env_tag('MCP_SERVER_URL')}"
        )
        console.print(
            f"  [bold cyan]2.[/bold cyan] MCP_HEALTH_URL:  "
            f"{config.MCP_HEALTH_URL or '[dim]Not set[/dim]'}{_env_tag('MCP_HEALTH_URL')} "
            f"[dim](optional — enables wake-up for suspended servers)[/dim]"
        )
        console.print(
            f"  [bold cyan]3.[/bold cyan] MCP_TOKEN:       {token_display}{_env_tag('MCP_TOKEN')}"
        )
        console.print(
            f"  [bold cyan]4.[/bold cyan] VERBOSE:         {verbose_display}{_env_tag('VERBOSE')}"
        )
        console.print()
        console.print(f"  [dim]Config file: {CONFIG_FILE}[/dim]")
        if any_shadowed:
            console.print(
                "  [dim][yellow](env)[/yellow] = overridden by environment / .env "
                "(edits apply this session, but env still wins on next launch)[/dim]"
            )
        console.print()

        choice = Prompt.ask("Edit setting (1-4) or press Enter to go back").strip()
        if not choice:
            return changed

        if choice == "4":
            _toggle_verbose()
            continue

        keys = {
            "1": ("MCP_SERVER_URL", "MCP Server URL"),
            "2": ("MCP_HEALTH_URL", "Health Check URL"),
            "3": ("MCP_TOKEN", "MCP Token"),
        }

        if choice not in keys:
            console.print("[red]Invalid choice.[/red]")
            continue

        key, label = keys[choice]
        current = config.get_setting(key) or ""

        console.print()
        if current:
            display = current[:40] + ("..." if len(current) > 40 else "")
            console.print(f"  [dim]Current: {display}[/dim]")
        console.print("  [dim]Enter new value, 'clear' to remove, or Enter to keep current[/dim]")
        new_value = input(f"  {label}: ").strip()

        if not new_value:
            console.print("[dim]  No change.[/dim]")
            continue

        cfg = load_config()
        if new_value.lower() == "clear":
            cfg.pop(key, None)
        else:
            cfg[key] = new_value

        if save_config(cfg):
            # Drop any env-var shadow so the just-saved value applies this session.
            # The .env file (if any) still wins on next launch.
            os.environ.pop(key, None)
            reload_config()
            console.print(f"[green]  Updated {key}.[/green]")
            changed = True
        else:
            console.print("[red]  Failed to save setting.[/red]")


def confirm_or_edit_config() -> bool:
    """Show current config and prompt to connect, edit, or quit.

    If required fields are missing, only edit/quit are allowed.
    Returns True to proceed with connection, False to quit.
    """
    while True:
        display_config_panel(config.MCP_SERVER_URL, config.MCP_HEALTH_URL)

        if not validate_config():
            console.print("[yellow]MCP_SERVER_URL and MCP_TOKEN are required to connect.[/yellow]")
            choice = (
                Prompt.ask(
                    "Press [bold cyan]Enter[/bold cyan] / [bold cyan]c[/bold cyan] to edit, "
                    "[bold cyan]q[/bold cyan] to quit"
                )
                .strip()
                .lower()
            )
            if choice in ("", "c"):
                handle_config_command()
                continue
            if choice in ("q", "quit", "exit"):
                console.print("\n[bold yellow]Exiting...[/bold yellow]")
                return False
            console.print("[red]Invalid choice.[/red]")
            continue

        choice = (
            Prompt.ask(
                "Press [bold cyan]Enter[/bold cyan] to connect, "
                "[bold cyan]c[/bold cyan] to change configuration, "
                "[bold cyan]q[/bold cyan] to quit"
            )
            .strip()
            .lower()
        )

        if choice in ("", "y", "yes"):
            return True
        if choice in ("q", "quit", "exit"):
            console.print("\n[bold yellow]Exiting...[/bold yellow]")
            return False
        if choice == "c":
            handle_config_command()
            continue
        console.print("[red]Invalid choice.[/red]")


async def reconnect(old_session):
    """Clean up old session and establish a new connection. Returns (mcp_session, tools) or (None, None)."""
    console.print("[bold cyan]Reconnecting...[/bold cyan]")
    display_config_panel(config.MCP_SERVER_URL, config.MCP_HEALTH_URL)
    overall_start = time.monotonic()

    if old_session:
        try:
            await old_session.cleanup()
        except Exception:
            pass

    # Determine total steps
    total_steps = 2 if config.MCP_HEALTH_URL else 1
    current_step = 1

    # Step 1: Wake up server if health URL is configured
    if config.MCP_HEALTH_URL:
        display_step(current_step, total_steps, "WAKING UP SERVER", "in_progress")
        wake_start = time.monotonic()
        is_awake = await wake_up_server(config.MCP_HEALTH_URL, max_attempts=6, wait_seconds=5)

        if not is_awake:
            console.print("[bold red]  Failed to wake up server[/bold red]\n")
            return None, None

        display_step(current_step, total_steps, "WAKING UP SERVER", "success", update=True)
        vlog_timing("Wake-up step", time.monotonic() - wake_start)

        with console.status(
            "  [dim]Waiting for server initialization (5s)...[/dim]", spinner="dots"
        ):
            await asyncio.sleep(5)

        console.print()
        current_step += 1

    # Step 2: Connect and list tools
    display_step(current_step, total_steps, "CONNECTING AND LISTING TOOLS", "in_progress")
    connect_start = time.monotonic()
    mcp_session, tools = await connect_and_list_tools(max_attempts=3, wait_seconds=5)

    if not mcp_session:
        console.print("[bold red]  Failed to connect to MCP server[/bold red]\n")
        return None, None

    display_step(current_step, total_steps, "CONNECTING AND LISTING TOOLS", "success", update=True)
    vlog_timing("Connect+list step", time.monotonic() - connect_start)
    vlog_timing("Total reconnect", time.monotonic() - overall_start)
    console.print()
    console.print(
        f"[bold green]Connected![/bold green] Server has [bold cyan]{len(tools)}[/bold cyan] tools available"
    )
    console.print()
    return mcp_session, tools


async def test_connectivity():
    """Test connectivity to the MCP server."""
    # Start background listener for 'v' key toggle
    listener_task = asyncio.create_task(listen_for_toggle())
    mcp_session = None
    try:
        display_logo()
        if is_first_run():
            run_first_time_setup()
        if not confirm_or_edit_config():
            return
        overall_start = time.monotonic()

        # Determine total steps
        total_steps = 2 if config.MCP_HEALTH_URL else 1
        current_step = 1

        # Step 1: Wake up server if health URL is configured
        if config.MCP_HEALTH_URL:
            display_step(current_step, total_steps, "WAKING UP SERVER", "in_progress")
            wake_start = time.monotonic()
            is_awake = await wake_up_server(config.MCP_HEALTH_URL, max_attempts=6, wait_seconds=5)

            if not is_awake:
                console.print("[bold red]  Failed to wake up server[/bold red]\n")
                return

            display_step(current_step, total_steps, "WAKING UP SERVER", "success", update=True)
            vlog_timing("Wake-up step", time.monotonic() - wake_start)

            # Wait for MCP server to initialize (shorter wait like working example)
            with console.status(
                "  [dim]Waiting for server initialization (5s)...[/dim]", spinner="dots"
            ):
                await asyncio.sleep(5)

            console.print()
            current_step += 1

        # Step 2: Connect to MCP server AND list tools in one operation
        # (This avoids session expiry between connect and list_tools)
        display_step(current_step, total_steps, "CONNECTING AND LISTING TOOLS", "in_progress")
        connect_start = time.monotonic()
        mcp_session, tools = await connect_and_list_tools(max_attempts=3, wait_seconds=5)

        if not mcp_session:
            console.print("[bold red]  Failed to connect to MCP server[/bold red]\n")
            console.print("[yellow]This may indicate:[/yellow]")
            console.print("  - The MCP server is not properly configured")
            console.print("  - The server endpoint URL is incorrect")
            console.print("  - The server is returning errors for MCP requests")
            return

        display_step(
            current_step, total_steps, "CONNECTING AND LISTING TOOLS", "success", update=True
        )
        vlog_timing("Connect+list step", time.monotonic() - connect_start)
        vlog_timing("Total test time", time.monotonic() - overall_start)
        console.print()
        console.print(
            f"[bold green]Test complete![/bold green] Server has [bold cyan]{len(tools)}[/bold cyan] tools available"
        )
        console.print()

    finally:
        # Cancel the listener task when exiting
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
        # Clean up MCP session
        if mcp_session:
            await mcp_session.cleanup()


async def interactive_session():
    """Run an interactive session to explore and test MCP tools."""
    # Start background listener for 'v' key toggle during setup
    listener_task = asyncio.create_task(listen_for_toggle())
    mcp_session = None

    try:
        # Display logo first
        display_logo()

        # First run: kick off the setup wizard so the user has somewhere to start.
        if is_first_run():
            run_first_time_setup()

        # Always show the config gate so the user can confirm or edit before connecting.
        # The gate blocks "connect" when required fields are missing.
        if not confirm_or_edit_config():
            return

        # Initial connection
        mcp_session, tools = await reconnect(None)

        if not mcp_session:
            return

        if not tools:
            console.print("[yellow]No tools available on this server.[/yellow]")
            return

        # Stop background listener before entering interactive loop
        # The interactive loop handles 'v' key itself
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

        # Main interaction loop - Tool List View
        running = True
        while running:
            display_tools(tools)

            console.print("[bold underline]Commands:[/bold underline]")
            console.print("  [bold cyan]number[/bold cyan] - Select a tool")
            console.print(
                "  [bold cyan]v[/bold cyan]      - Toggle verbose logging (current: {})".format(
                    "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"
                )
            )
            console.print("  [bold cyan]c[/bold cyan]      - Configuration settings")
            console.print("  [bold cyan]q[/bold cyan]      - Quit")
            console.print()

            choice = Prompt.ask("Select tool").strip().lower()

            if choice in ("quit", "q", "exit"):
                console.print("\n[bold yellow]Exiting...[/bold yellow]")
                break

            if choice == "v":
                _toggle_verbose()
                continue

            if choice == "c":
                changed = handle_config_command()
                if changed:
                    new_session, new_tools = await reconnect(mcp_session)
                    if new_session:
                        mcp_session = new_session
                        tools = new_tools
                    else:
                        console.print(
                            "[yellow]Reconnection failed. Keeping current connection.[/yellow]\n"
                        )
                continue

            # Try to parse as tool number
            try:
                tool_num = int(choice)
                if 1 <= tool_num <= len(tools):
                    selected_tool = tools[tool_num - 1]

                    # Enter Tool View loop
                    while True:
                        display_tool_header(selected_tool)
                        display_tool_menu()

                        tool_choice = Prompt.ask("Choose option").strip().lower()

                        if tool_choice in ("d", "details", "1"):
                            # View details
                            display_tool_schema(selected_tool)

                        elif tool_choice in ("r", "run", "2"):
                            # Run tool
                            params = get_tool_parameters(selected_tool)
                            await call_tool(mcp_session, selected_tool, params)

                        elif tool_choice in ("b", "back", "3"):
                            # Back to tool list
                            break

                        elif tool_choice in ("q", "quit", "exit"):
                            # Quit entirely
                            console.print("\n[bold yellow]Exiting...[/bold yellow]")
                            running = False
                            break

                        elif tool_choice == "v":
                            _toggle_verbose()

                        elif tool_choice == "c":
                            changed = handle_config_command()
                            if changed:
                                new_session, new_tools = await reconnect(mcp_session)
                                if new_session:
                                    mcp_session = new_session
                                    tools = new_tools
                                else:
                                    console.print(
                                        "[yellow]Reconnection failed. Keeping current connection.[/yellow]\n"
                                    )
                                break  # Back to tool list since tools may have changed

                        else:
                            console.print(
                                "[red]Invalid option. Use 'd' for details, 'r' to run, 'b' to go back, or 'q' to quit.[/red]\n"
                            )
                else:
                    console.print(
                        f"[red]Invalid tool number. Choose between 1 and {len(tools)}[/red]\n"
                    )
            except ValueError:
                console.print("[red]Invalid choice. Enter a tool number or 'q' to quit.[/red]\n")

    finally:
        # Ensure listener is cancelled if we exit early
        if not listener_task.done():
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

        # Clean up MCP session
        if mcp_session:
            await mcp_session.cleanup()


async def async_main():
    """Async main entry point."""
    setup_logging()

    try:
        # Check for command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] in ("--test", "-t"):
                await test_connectivity()
                return
            elif sys.argv[1] in ("--config", "-c"):
                display_logo()
                run_first_time_setup()
                return
            elif sys.argv[1] in ("--help", "-h"):
                display_logo()
                console.print("\n[bold]Usage:[/bold]")
                console.print("  forbin            Run interactive session")
                console.print("  forbin --test     Test connectivity only")
                console.print("  forbin --config   Run configuration wizard")
                console.print("  forbin --help     Show this help message")
                console.print("\n[bold]Configuration:[/bold]")
                console.print(f"  Config file: {CONFIG_FILE}")
                console.print("  Settings can also be set via .env file or environment variables")
                console.print("  Priority: .env / environment > ~/.forbin/config.json")
                console.print("\n[bold]Interactive Shortcuts:[/bold]")
                console.print("  [bold cyan]'v'[/bold cyan]   - Toggle verbose logging at any time")
                console.print("  [bold cyan]'c'[/bold cyan]   - View/update configuration")
                console.print("  [bold cyan]ESC[/bold cyan]   - Cancel a running tool call")
                return

        # Run interactive session by default
        await interactive_session()
    except asyncio.CancelledError:
        pass


def main():
    """Synchronous entry point for CLI."""
    asyncio.run(async_main())
