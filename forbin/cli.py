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
    display_commands,
    display_step,
    console,
)


def _toggle_verbose():
    """Toggle verbose mode and persist the setting."""
    # Flip the in-memory flag, then mirror it to the on-disk config.
    config.VERBOSE = not config.VERBOSE
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

    # Outer loop: re-render the config menu after each edit until the user exits.
    while True:
        # Mask the token so we never echo a full secret to the terminal.
        token_display = (
            config.MCP_TOKEN[:8] + "..."
            if config.MCP_TOKEN and len(config.MCP_TOKEN) > 8
            else config.MCP_TOKEN or "[dim]Not set[/dim]"
        )
        verbose_display = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"

        # An (env) tag warns the user that .env / environment is overriding the
        # stored value — useful because edits won't survive the next launch.
        def _env_tag(key: str) -> str:
            return " [yellow](env)[/yellow]" if is_env_shadowed(key) else ""

        any_shadowed = any(
            is_env_shadowed(k)
            for k in (
                "MCP_SERVER_URL",
                "MCP_TOKEN",
                "MCP_HEALTH_URL",
                "VERBOSE",
                "MCP_TOOL_TIMEOUT",
            )
        )

        console.print()
        console.print("[bold underline]Configuration[/bold underline]")
        console.print()
        console.print(
            f"  [bold cyan]1.[/bold cyan] MCP_SERVER_URL:    "
            f"{config.MCP_SERVER_URL or '[dim]Not set[/dim]'}{_env_tag('MCP_SERVER_URL')}"
        )
        console.print(
            f"  [bold cyan]2.[/bold cyan] MCP_HEALTH_URL:    "
            f"{config.MCP_HEALTH_URL or '[dim]Not set[/dim]'}{_env_tag('MCP_HEALTH_URL')} "
            f"[dim](optional — enables wake-up for suspended servers)[/dim]"
        )
        console.print(
            f"  [bold cyan]3.[/bold cyan] MCP_TOKEN:         {token_display}{_env_tag('MCP_TOKEN')}"
        )
        console.print(
            f"  [bold cyan]4.[/bold cyan] VERBOSE:           {verbose_display}{_env_tag('VERBOSE')}"
        )
        console.print(
            f"  [bold cyan]5.[/bold cyan] MCP_TOOL_TIMEOUT:  "
            f"{config.MCP_TOOL_TIMEOUT:g}s{_env_tag('MCP_TOOL_TIMEOUT')} "
            f"[dim](max time to wait for a tool call to complete)[/dim]"
        )
        console.print()
        console.print(f"  [dim]Config file: {CONFIG_FILE}[/dim]")
        if any_shadowed:
            console.print(
                "  [dim][yellow](env)[/yellow] = overridden by environment / .env "
                "(edits apply this session, but env still wins on next launch)[/dim]"
            )
        console.print()

        display_commands(
            [
                ("number", "Edit field"),
                ("b", "Back"),
            ]
        )

        choice = Prompt.ask("Choice").strip().lower()
        if choice in ("", "b", "back"):
            return changed

        # Field 4 (VERBOSE) is a toggle, not an editable string.
        if choice == "4":
            _toggle_verbose()
            continue

        # Map menu numbers to (env-var key, human label).
        # Field 4 (VERBOSE) is handled above as a toggle.
        keys = {
            "1": ("MCP_SERVER_URL", "MCP Server URL"),
            "2": ("MCP_HEALTH_URL", "Health Check URL"),
            "3": ("MCP_TOKEN", "MCP Token"),
            "5": ("MCP_TOOL_TIMEOUT", "Tool timeout (seconds)"),
        }

        if choice not in keys:
            console.print("[red]Invalid choice.[/red]")
            continue

        # Inner sub-menu: edit a single field (set / clear / back).
        key, label = keys[choice]
        current = config.get_setting(key) or ""

        console.print()
        console.print(f"[bold]Editing {key}[/bold]")
        if current:
            display = current[:60] + ("..." if len(current) > 60 else "")
            console.print(f"  [dim]Current: {display}[/dim]")
        else:
            console.print("  [dim]Current: [italic]not set[/italic][/dim]")
        console.print()

        sub_commands = [("Enter", "Set a new value")]
        if current:
            sub_commands.append(("x", "Clear"))
        sub_commands.append(("b", "Back"))
        display_commands(sub_commands)

        action = Prompt.ask("Choice").strip().lower()

        if action in ("b", "back"):
            console.print("[dim]  No change.[/dim]")
            continue

        if action == "":
            new_value = input(f"  {label}: ").strip()
            if not new_value:
                console.print("[dim]  No change.[/dim]")
                continue
            # Numeric fields validate at edit time so the user sees the
            # error immediately, instead of silently falling back to the
            # default at parse time after they save.
            if key == "MCP_TOOL_TIMEOUT":
                try:
                    parsed = float(new_value)
                except ValueError:
                    console.print(f"[red]  Invalid number: {new_value}[/red]")
                    continue
                if parsed <= 0:
                    console.print("[red]  Tool timeout must be greater than zero.[/red]")
                    continue
            cfg = load_config()
            cfg[key] = new_value
        elif action == "x" and current:
            cfg = load_config()
            cfg.pop(key, None)
        else:
            console.print("[red]  Invalid choice.[/red]")
            continue

        if save_config(cfg):
            # Drop any env-var shadow so the just-saved value applies this session.
            # The .env file (if any) still wins on next launch.
            os.environ.pop(key, None)
            reload_config()
            console.print(f"[green]  Updated {key}.[/green]")
            changed = True  # Caller uses this to decide whether to reconnect.
        else:
            console.print("[red]  Failed to save setting.[/red]")


def confirm_or_edit_config() -> bool:
    """Show current config and prompt to connect, edit, or quit.

    If required fields are missing, only edit/quit are allowed.
    Returns True to proceed with connection, False to quit.
    """
    while True:
        display_config_panel()
        verbose_state = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"

        # Branch A: required fields missing — restrict the menu to edit-or-quit
        # so the user can't try to connect with a broken config.
        if not validate_config():
            console.print("[yellow]MCP_SERVER_URL and MCP_TOKEN are required to connect.[/yellow]")
            console.print()
            display_commands(
                [
                    ("Enter", "Edit configuration"),
                    ("v", f"Toggle verbose logging (currently: {verbose_state})"),
                    ("q", "Quit"),
                ]
            )
            choice = Prompt.ask("Choice").strip().lower()
            if choice == "":
                handle_config_command()
                continue
            if choice == "v":
                _toggle_verbose()
                continue
            if choice in ("q", "quit", "exit"):
                console.print("\n[bold yellow]Exiting...[/bold yellow]")
                return False
            console.print("[red]Invalid choice.[/red]")
            continue

        # Branch B: config is valid — offer connect / change / quit.
        display_commands(
            [
                ("Enter", "Connect"),
                ("v", f"Toggle verbose logging (currently: {verbose_state})"),
                ("c", "Change configuration"),
                ("q", "Quit"),
            ]
        )
        choice = Prompt.ask("Choice").strip().lower()

        if choice == "":
            return True
        if choice in ("q", "quit", "exit"):
            console.print("\n[bold yellow]Exiting...[/bold yellow]")
            return False
        if choice == "v":
            _toggle_verbose()
            continue
        if choice == "c":
            handle_config_command()
            continue
        console.print("[red]Invalid choice.[/red]")


async def reconnect(old_session):
    """Clean up old session and establish a new connection. Returns (mcp_session, tools) or (None, None)."""
    console.print("[bold cyan]Reconnecting...[/bold cyan]")
    display_config_panel()
    overall_start = time.monotonic()

    # Tear down the existing session first; swallow errors because cleanup is
    # best-effort and shouldn't block the new connection.
    if old_session:
        try:
            await old_session.cleanup()
        except Exception:
            pass

    # Skip the wake-up step entirely when no health URL is configured.
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


async def test_connectivity() -> bool:
    """Test connectivity to the MCP server. Returns True on success, False otherwise.

    The bool return drives the process exit code in `main()` so CI pipelines
    can fail loudly when the server is unreachable. User-cancellation at the
    config gate is treated as a non-success outcome (False) — the test didn't
    actually run, so it shouldn't be reported as passing.
    """
    # Background listener lets the user toggle verbose mode mid-run with 'v'.
    listener_task = asyncio.create_task(listen_for_toggle())
    mcp_session = None
    try:
        display_logo()
        # First-time setup before the gate so a fresh user has values to confirm.
        if is_first_run():
            run_first_time_setup()
        if not confirm_or_edit_config():
            return False
        overall_start = time.monotonic()

        # Wake-up step is skipped entirely when no health URL is set.
        total_steps = 2 if config.MCP_HEALTH_URL else 1
        current_step = 1

        # Step 1: Wake up server if health URL is configured
        if config.MCP_HEALTH_URL:
            display_step(current_step, total_steps, "WAKING UP SERVER", "in_progress")
            wake_start = time.monotonic()
            is_awake = await wake_up_server(config.MCP_HEALTH_URL, max_attempts=6, wait_seconds=5)

            if not is_awake:
                console.print("[bold red]  Failed to wake up server[/bold red]\n")
                return False

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
            return False

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
        return True

    finally:
        # Always cancel the listener and tear down the session, even on error.
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
        if mcp_session:
            await mcp_session.cleanup()


async def interactive_session():
    """Run an interactive session to explore and test MCP tools."""
    # Listener handles 'v' for verbose toggle during the setup phase only;
    # the main loop below takes over input handling once we're connected.
    listener_task = asyncio.create_task(listen_for_toggle())
    mcp_session = None

    try:
        display_logo()

        # First run: kick off the setup wizard so the user has somewhere to start.
        if is_first_run():
            run_first_time_setup()

        # Always show the config gate so the user can confirm or edit before connecting.
        # The gate blocks "connect" when required fields are missing.
        if not confirm_or_edit_config():
            return

        # Initial connection (no prior session to clean up).
        mcp_session, tools = await reconnect(None)

        if not mcp_session:
            return

        if not tools:
            console.print("[yellow]No tools available on this server.[/yellow]")
            return

        # Hand off keyboard input to the interactive loop below — it has its
        # own 'v' shortcut and shouldn't compete with the background listener.
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

        # Main interaction loop — Tool List View. `running` is the outer escape
        # hatch so a quit from the inner Tool View also exits the outer loop.
        running = True
        while running:
            display_tools(tools)

            verbose_state = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"
            display_commands(
                [
                    ("number", "Select a tool"),
                    ("v", f"Toggle verbose logging (currently: {verbose_state})"),
                    ("c", "Change configuration"),
                    ("q", "Quit"),
                ]
            )

            choice = Prompt.ask("Choice").strip().lower()

            if choice in ("quit", "q", "exit"):
                console.print("\n[bold yellow]Exiting...[/bold yellow]")
                break

            if choice == "v":
                _toggle_verbose()
                continue

            if choice == "c":
                # Only force a reconnect if something actually changed —
                # otherwise we'd disconnect for nothing.
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

            # Anything else: treat as a 1-indexed tool selection.
            try:
                tool_num = int(choice)
                if 1 <= tool_num <= len(tools):
                    selected_tool = tools[tool_num - 1]

                    # Inner Tool View loop — details / run / back / quit.
                    while True:
                        display_tool_header(selected_tool)
                        display_tool_menu()

                        tool_choice = Prompt.ask("Choice").strip().lower()

                        if tool_choice in ("d", "details"):
                            # View details
                            display_tool_schema(selected_tool)

                        elif tool_choice in ("r", "run"):
                            # Run tool
                            params = get_tool_parameters(selected_tool)
                            await call_tool(mcp_session, selected_tool, params)

                        elif tool_choice in ("b", "back", ""):
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
                                # Drop back to the tool list — the tool set
                                # may have changed under the new connection.
                                break

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
        # The listener may already be cancelled (we cancel it after setup);
        # only cancel again if we exited the try block before that point.
        if not listener_task.done():
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

        if mcp_session:
            await mcp_session.cleanup()


async def async_main() -> int:
    """Async main entry point. Returns the process exit code.

    Only `--test` propagates a non-zero status today (so CI pipelines can
    detect a dead server). Interactive mode and `--config` always return 0
    — there's no machine-readable failure signal those modes need to emit.
    """
    # Install the stderr filter and verbose-aware logging handlers once,
    # before any subcommand can produce output.
    setup_logging()

    try:
        # Subcommand dispatch: --test, --config, --help, or fall through to interactive.
        if len(sys.argv) > 1:
            if sys.argv[1] in ("--test", "-t"):
                ok = await test_connectivity()
                return 0 if ok else 1
            elif sys.argv[1] in ("--config", "-c"):
                display_logo()
                run_first_time_setup()
                return 0
            elif sys.argv[1] in ("--help", "-h"):
                display_logo()
                console.print("\n[bold]Usage:[/bold]")
                console.print("  forbin            Run interactive session")
                console.print(
                    "  forbin --test     Test connectivity only (exits non-zero on failure)"
                )
                console.print("  forbin --config   Run configuration wizard")
                console.print("  forbin --help     Show this help message")
                console.print("\n[bold]Configuration:[/bold]")
                console.print(f"  Config file: {CONFIG_FILE}")
                console.print("  Settings can also be set via .env file or environment variables")
                console.print("  Priority: .env / environment > ~/.forbin/config.json")
                console.print("\n[bold]Interactive Shortcuts:[/bold]")
                console.print("  [bold cyan]'v'[/bold cyan]   - Toggle verbose logging at any time")
                console.print(
                    "  [bold cyan]'c'[/bold cyan]   - View/update configuration (in menu) or copy last response (after a tool call)"
                )
                console.print("  [bold cyan]ESC[/bold cyan]   - Cancel a running tool call")
                return 0

        # Run interactive session by default
        await interactive_session()
        return 0
    except asyncio.CancelledError:
        return 0


def main():
    """Synchronous entry point for CLI."""
    sys.exit(asyncio.run(async_main()))
