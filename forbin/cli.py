import argparse
import asyncio
import contextlib
import os
import sys
import time
from typing import Optional

from rich.prompt import Prompt

from . import config
from . import profiles
from .config import (
    validate_config,
    is_first_run,
    is_env_shadowed,
    run_first_time_setup,
    reload_config,
    migrate_legacy_config_if_needed,
)
from .picker import pick_profile_and_environment
from .utils import setup_logging, listen_for_toggle, UserQuit
from .client import MCPSession, connect_and_list_tools, wake_up_server
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
    # Flip the in-memory flag, then mirror it to globals in profiles.json.
    config.VERBOSE = not config.VERBOSE
    doc = profiles.load_profiles()
    profiles.set_global(doc, "VERBOSE", str(config.VERBOSE).lower())
    profiles.save_profiles(doc)
    # Drop any env-var shadow so the new value sticks for the rest of this session.
    os.environ.pop("VERBOSE", None)
    status = "[bold green]ON[/bold green]" if config.VERBOSE else "[bold red]OFF[/bold red]"
    console.print(f"\n[bold cyan]Verbose logging toggled {status}[/bold cyan]\n")


_PER_ENV_FIELD_LABELS = {
    "MCP_SERVER_URL": ("MCP Server URL", ""),
    "MCP_HEALTH_URL": (
        "Health Check URL",
        "[dim](optional — enables wake-up for suspended servers)[/dim]",
    ),
    "MCP_TOKEN": ("MCP Token", ""),
}

_GLOBAL_FIELD_LABELS = {
    "MCP_TOOL_TIMEOUT": (
        "Tool timeout (seconds)",
        "[dim](max time to wait for a tool call to complete)[/dim]",
    ),
}


def handle_config_command() -> bool:
    """Show the current config and allow interactive editing.

    Per-environment fields (1-3) write to the active environment in
    profiles.json. Globals (VERBOSE toggle, MCP_TOOL_TIMEOUT) write to
    the globals slot. ``p`` opens the picker for switch / CRUD.

    Returns True if a change happened that warrants reconnecting (any
    per-environment field edited, or the active profile/environment
    switched). Globals-only changes return False — the running session
    can absorb them without a fresh connection.
    """
    needs_reconnect = False

    while True:
        doc = profiles.load_profiles()
        try:
            env_dict = profiles.get_active_environment(doc)
        except Exception:
            env_dict = {}

        active_profile, active_env = profiles.get_active(doc)
        token = env_dict.get("MCP_TOKEN") or ""
        token_display = token[:8] + "..." if len(token) > 8 else token or "[dim]Not set[/dim]"
        verbose_display = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"

        def _env_tag(name: str) -> str:
            # Per-env fields are never shadowed under v0.1.5+; this tag
            # only renders for global keys when an env var overrides them.
            return " [yellow](env)[/yellow]" if is_env_shadowed(name) else ""

        any_global_shadowed = any(is_env_shadowed(k) for k in profiles.GLOBAL_FIELDS)

        console.print()
        console.print("[bold underline]Configuration[/bold underline]")
        console.print()
        console.print(
            f"  [bold]Active:[/bold] [cyan]{active_profile}[/cyan] / [cyan]{active_env}[/cyan]"
        )
        console.print()
        console.print(
            f"  [bold]Per-environment settings[/bold] [dim]({active_profile} / {active_env})[/dim]"
        )
        console.print(
            f"  [bold cyan]1.[/bold cyan] MCP_SERVER_URL:    "
            f"{env_dict.get('MCP_SERVER_URL') or '[dim]Not set[/dim]'}"
        )
        console.print(
            f"  [bold cyan]2.[/bold cyan] MCP_HEALTH_URL:    "
            f"{env_dict.get('MCP_HEALTH_URL') or '[dim]Not set[/dim]'} "
            f"{_PER_ENV_FIELD_LABELS['MCP_HEALTH_URL'][1]}"
        )
        console.print(f"  [bold cyan]3.[/bold cyan] MCP_TOKEN:         {token_display}")
        console.print()
        console.print("  [bold]Globals[/bold]")
        console.print(
            f"  [bold cyan]4.[/bold cyan] VERBOSE:           {verbose_display}{_env_tag('VERBOSE')}"
        )
        console.print(
            f"  [bold cyan]5.[/bold cyan] MCP_TOOL_TIMEOUT:  "
            f"{config.MCP_TOOL_TIMEOUT:g}s{_env_tag('MCP_TOOL_TIMEOUT')} "
            f"{_GLOBAL_FIELD_LABELS['MCP_TOOL_TIMEOUT'][1]}"
        )
        console.print()
        console.print(f"  [dim]Profiles file: {profiles.PROFILES_FILE}[/dim]")
        if any_global_shadowed:
            console.print(
                "  [dim][yellow](env)[/yellow] = overridden by environment / .env "
                "(globals only — connection fields come from the active profile)[/dim]"
            )
        console.print()

        display_commands(
            [
                ("number", "Edit field"),
                ("p", "Switch / manage profiles & environments"),
                ("b", "Back"),
                ("q", "Quit"),
            ]
        )

        choice = Prompt.ask("Choice").strip().lower()
        if choice in ("", "b", "back"):
            return needs_reconnect
        if choice in ("q", "quit", "exit"):
            raise UserQuit

        if choice == "p":
            result = pick_profile_and_environment()
            if result is not None:
                old = (active_profile, active_env)
                if result != old:
                    reload_config()
                    needs_reconnect = True
                    console.print(f"[green]  Switched to {result[0]}/{result[1]}.[/green]")
            continue

        # Field 4 (VERBOSE) is a toggle, not an editable string.
        if choice == "4":
            _toggle_verbose()
            continue

        if choice in ("1", "2", "3"):
            key = ["MCP_SERVER_URL", "MCP_HEALTH_URL", "MCP_TOKEN"][int(choice) - 1]
            if _edit_per_env_field(key):
                needs_reconnect = True
            continue

        if choice == "5":
            _edit_global_field("MCP_TOOL_TIMEOUT")
            # Timeout change applies on the next tool call without a
            # reconnect — module-level constant is read each call.
            continue

        console.print("[red]Invalid choice.[/red]")


def _edit_per_env_field(key: str) -> bool:
    """Edit a per-environment field on the active environment. Returns
    True if the value actually changed."""
    label, _hint = _PER_ENV_FIELD_LABELS[key]
    doc = profiles.load_profiles()
    try:
        env_dict = profiles.get_active_environment(doc)
    except (profiles.ProfileError, KeyError):
        console.print("[red]  No active environment.[/red]")
        return False
    current = env_dict.get(key) or ""

    console.print()
    console.print(f"[bold]Editing {key}[/bold]")
    if current:
        display = current[:60] + ("..." if len(current) > 60 else "")
        console.print(f"  [dim]Current: {display}[/dim]")
    else:
        console.print("  [dim]Current: [italic]not set[/italic][/dim]")
    console.print()

    if not current:
        # No current value — the [Enter]/[x]/[b] sub-menu would have only
        # one meaningful choice. Go straight to the value prompt; empty
        # input there is the cancel path.
        new_value = input(f"  {label} (Enter to cancel): ").strip()
        if not new_value:
            console.print("[dim]  No change.[/dim]")
            return False
        env_dict[key] = new_value
    else:
        display_commands(
            [
                ("Enter", "Set a new value"),
                ("x", "Clear"),
                ("b", "Back"),
                ("q", "Quit"),
            ]
        )
        action = Prompt.ask("Choice").strip().lower()
        if action in ("b", "back"):
            console.print("[dim]  No change.[/dim]")
            return False
        if action in ("q", "quit", "exit"):
            raise UserQuit
        if action == "":
            new_value = input(f"  {label}: ").strip()
            if not new_value:
                console.print("[dim]  No change.[/dim]")
                return False
            env_dict[key] = new_value
        elif action == "x":
            env_dict.pop(key, None)
        else:
            console.print("[red]  Invalid choice.[/red]")
            return False

    if profiles.save_profiles(doc):
        reload_config()
        console.print(f"[green]  Updated {key}.[/green]")
        return True
    return False


def _edit_global_field(key: str) -> bool:
    """Edit a global field. Returns True if the value changed."""
    label, _hint = _GLOBAL_FIELD_LABELS[key]
    doc = profiles.load_profiles()
    current = profiles.get_global(doc, key) or ""

    console.print()
    console.print(f"[bold]Editing {key}[/bold]")
    if current:
        console.print(f"  [dim]Current: {current}[/dim]")
    else:
        console.print("  [dim]Current: [italic]not set (using default)[/italic][/dim]")
    console.print()

    if not current:
        # No stored value — skip the sub-menu and go straight to input.
        # Empty input cancels.
        new_value = input(f"  {label} (Enter to cancel): ").strip()
        if not new_value:
            console.print("[dim]  No change.[/dim]")
            return False
        if not _validate_global_value(key, new_value):
            return False
        profiles.set_global(doc, key, new_value)
    else:
        display_commands(
            [
                ("Enter", "Set a new value"),
                ("x", "Clear (revert to default)"),
                ("b", "Back"),
                ("q", "Quit"),
            ]
        )
        action = Prompt.ask("Choice").strip().lower()
        if action in ("b", "back"):
            console.print("[dim]  No change.[/dim]")
            return False
        if action in ("q", "quit", "exit"):
            raise UserQuit
        if action == "":
            new_value = input(f"  {label}: ").strip()
            if not new_value:
                console.print("[dim]  No change.[/dim]")
                return False
            if not _validate_global_value(key, new_value):
                return False
            profiles.set_global(doc, key, new_value)
        elif action == "x":
            profiles.set_global(doc, key, None)
        else:
            console.print("[red]  Invalid choice.[/red]")
            return False

    if profiles.save_profiles(doc):
        os.environ.pop(key, None)
        reload_config()
        console.print(f"[green]  Updated {key}.[/green]")
        return True
    return False


def _validate_global_value(key: str, value: str) -> bool:
    """Inline validation for global fields. Prints an error and returns
    False on failure."""
    if key == "MCP_TOOL_TIMEOUT":
        try:
            parsed = float(value)
        except ValueError:
            console.print(f"[red]  Invalid number: {value}[/red]")
            return False
        if parsed <= 0:
            console.print("[red]  Tool timeout must be greater than zero.[/red]")
            return False
    return True


def confirm_or_edit_config() -> bool:
    """Show current config and prompt to connect, edit, or quit.

    If required fields are missing, only edit/quit are allowed.
    Returns True to proceed with connection, False to quit.
    """
    while True:
        display_config_panel()
        verbose_state = "[green]ON[/green]" if config.VERBOSE else "[red]OFF[/red]"

        # Token-but-no-token-needed setups (mock servers, network-gated
        # internal services) are common, so an empty MCP_TOKEN is just a
        # heads-up rather than a blocker. Render the hint regardless of
        # which branch we land in below.
        if not config.MCP_TOKEN:
            console.print(
                "[yellow]No MCP_TOKEN set — connecting without auth. "
                "Servers that require a bearer token will respond with 401.[/yellow]\n"
            )

        # Branch A: required fields missing — restrict the menu to edit-or-quit
        # so the user can't try to connect with a broken config.
        if not validate_config():
            console.print("[yellow]MCP_SERVER_URL is required to connect.[/yellow]")
            console.print()
            display_commands(
                [
                    ("Enter", "Edit configuration"),
                    ("v", f"Toggle verbose logging (currently: {verbose_state})"),
                    ("b", "Back to profile picker"),
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
            if choice in ("b", "back"):
                if pick_profile_and_environment() is not None:
                    reload_config()
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
                ("p", "Switch profile / environment"),
                ("b", "Back to profile picker"),
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
        if choice in ("p", "b", "back"):
            if pick_profile_and_environment() is not None:
                reload_config()
            continue
        console.print("[red]Invalid choice.[/red]")
        # Loops back via while True; the unreachable return below proves
        # to the type checker that no path falls through to an implicit
        # None return, satisfying the `-> bool` annotation.
        continue
    return False  # pragma: no cover - unreachable


async def _reconnect_or_warn(
    old_session: MCPSession | None, old_tools: list
) -> tuple[MCPSession | None, list]:
    """Reconnect after a profile/environment switch, but only if the new
    selection has at least the server URL. Without it we'd produce a
    confusing fastmcp traceback. Keeps the previous session and tells
    the user to press `c` to fill in the gaps and reconnect manually."""
    if not validate_config():
        console.print(
            f"[yellow]Profile [bold]{config.ACTIVE_PROFILE}/{config.ACTIVE_ENV}[/bold] "
            f"is missing MCP_SERVER_URL. Skipping reconnect — "
            f"press [bold]c[/bold] to set it.[/yellow]\n"
        )
        return old_session, old_tools
    new_session, new_tools = await reconnect(old_session)
    if new_session is None:
        console.print("[yellow]Reconnection failed. Keeping current connection.[/yellow]\n")
        return old_session, old_tools
    return new_session, new_tools


async def reconnect(old_session: MCPSession | None) -> tuple[MCPSession | None, list]:
    """Clean up the old session and establish a new connection.

    Returns (mcp_session, tools) on success, or (None, []) on failure.
    """
    console.print("[bold cyan]Reconnecting...[/bold cyan]")
    display_config_panel()
    overall_start = time.monotonic()

    # Tear down the existing session first; swallow errors because cleanup is
    # best-effort and shouldn't block the new connection.
    if old_session:
        with contextlib.suppress(Exception):
            await old_session.cleanup()

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
            return None, []

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
        return None, []

    display_step(current_step, total_steps, "CONNECTING AND LISTING TOOLS", "success", update=True)
    vlog_timing("Connect+list step", time.monotonic() - connect_start)
    vlog_timing("Total reconnect", time.monotonic() - overall_start)
    console.print()
    console.print(
        f"[bold green]Connected![/bold green] Server has [bold cyan]{len(tools)}[/bold cyan] tools available"
    )
    console.print()
    return mcp_session, tools


def _launch_setup() -> bool:
    """Shared launch sequence: migrate legacy config, run wizard if first
    launch, and show the picker when the user has more than one
    profile/environment to choose between.

    Returns False if the user quits the picker; True otherwise. Caller
    falls through to the config gate either way (gate handles the
    True case, returns immediately on False)."""
    migrate_legacy_config_if_needed()
    if is_first_run():
        run_first_time_setup()
    reload_config()

    # --profile / --env flags pin the selection at the async_main layer
    # via set_active_override. Skip the picker so a scripted run doesn't
    # block on a TTY prompt.
    if config._OVERRIDE_PROFILE:
        return True

    # Skip the picker entirely for the single-profile / single-env case
    # so existing users see no UX change. Multi-profile or multi-env
    # users get the picker on every launch.
    doc = profiles.load_profiles()
    profile_count = len(doc.get("profiles", {}))
    env_count = (
        len(profiles.list_environments(doc, profiles.get_active(doc)[0])) if profile_count else 0
    )
    if profile_count > 1 or env_count > 1:
        if pick_profile_and_environment() is None:
            return False
        reload_config()
    return True


async def test_connectivity() -> bool:
    """Test connectivity to the MCP server. Returns True on success, False otherwise.

    The bool return drives the process exit code in `main()` so CI pipelines
    can fail loudly when the server is unreachable. User-cancellation at the
    config gate is treated as a non-success outcome (False) — the test didn't
    actually run, so it shouldn't be reported as passing.
    """
    mcp_session = None
    listener_task: asyncio.Task | None = None
    try:
        display_logo()
        if not _launch_setup():
            return False
        if not confirm_or_edit_config():
            return False

        # Listener is started AFTER the gate / wizard. Both use Prompt.ask /
        # input(), which would race with listen_for_toggle()'s cbreak-mode
        # raw-stdin reads — the listener could swallow the user's `v` before
        # the prompt sees it, leaving Prompt.ask with just `\n` and silently
        # taking the default action. The gate handles `v` itself, so we only
        # need the listener during the connect phase below.
        listener_task = asyncio.create_task(listen_for_toggle())

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
        # listener_task may be None if we exited before the gate completed.
        if listener_task is not None and not listener_task.done():
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
        if mcp_session:
            await mcp_session.cleanup()


async def interactive_session():
    """Run an interactive session to explore and test MCP tools."""
    mcp_session = None
    # Listener gets started after the config gate so its cbreak-mode stdin
    # reads don't race with the wizard / gate's Prompt.ask. Set to None up
    # front so the finally block can handle the case where we exited before
    # creating it.
    listener_task: asyncio.Task | None = None

    try:
        display_logo()
        if not _launch_setup():
            return

        # Loop over (gate -> connect) until we either connect successfully
        # or the user quits at the gate. A failed connect (bad URL, dead
        # server, missing credentials) drops the user back at the gate so
        # they can edit config or switch profile and retry — without
        # killing the app and losing their place.
        while True:
            if not confirm_or_edit_config():
                return

            # Listener starts AFTER the gate so its cbreak-mode raw stdin
            # reads don't race with Prompt.ask. The gate / wizard handle
            # `v` themselves; the listener is only useful during the
            # connect phase (so the user can flip verbose mid-flight to
            # debug a hanging connection). try/finally guarantees we cancel
            # before the next gate iteration if the connect fails.
            listener_task = asyncio.create_task(listen_for_toggle())
            try:
                mcp_session, tools = await reconnect(None)
            finally:
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass
                listener_task = None

            if mcp_session:
                break
            console.print(
                "[yellow]Could not connect with the current configuration. "
                "Press [bold]c[/bold] to edit, [bold]p[/bold] to switch profile, "
                "Enter to retry, or [bold]q[/bold] to quit.[/yellow]\n"
            )

        if not tools:
            console.print("[yellow]No tools available on this server.[/yellow]")
            return

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
                    ("p", "Switch profile / environment"),
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
                    mcp_session, tools = await _reconnect_or_warn(mcp_session, tools)
                continue

            if choice == "p":
                old_active = (config.ACTIVE_PROFILE, config.ACTIVE_ENV)
                if pick_profile_and_environment() is not None:
                    reload_config()
                    if (config.ACTIVE_PROFILE, config.ACTIVE_ENV) != old_active:
                        mcp_session, tools = await _reconnect_or_warn(mcp_session, tools)
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
                                mcp_session, tools = await _reconnect_or_warn(mcp_session, tools)
                                # Drop back to the tool list — the tool set
                                # may have changed under the new connection.
                                break

                        elif tool_choice == "p":
                            old_active = (config.ACTIVE_PROFILE, config.ACTIVE_ENV)
                            if pick_profile_and_environment() is not None:
                                reload_config()
                                if (config.ACTIVE_PROFILE, config.ACTIVE_ENV) != old_active:
                                    mcp_session, tools = await _reconnect_or_warn(
                                        mcp_session, tools
                                    )
                                    # Profile changed; tool set may differ — drop back to list.
                                    break

                        else:
                            console.print(
                                "[red]Invalid option. Use 'd' for details, 'r' to run, 'p' to switch profile, 'b' to go back, or 'q' to quit.[/red]\n"
                            )
                else:
                    console.print(
                        f"[red]Invalid tool number. Choose between 1 and {len(tools)}[/red]\n"
                    )
            except ValueError:
                console.print("[red]Invalid choice. Enter a tool number or 'q' to quit.[/red]\n")

    finally:
        # listener_task may be None (we exited before the gate completed) or
        # already cancelled (we cancel it after setup). Only cancel again if
        # we exited the try block before that point.
        if listener_task is not None and not listener_task.done():
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

        if mcp_session is not None:
            await mcp_session.cleanup()


def _build_arg_parser() -> "argparse.ArgumentParser":
    import argparse as _argparse

    parser = _argparse.ArgumentParser(
        prog="forbin",
        description="Interactive CLI for testing remote MCP servers.",
        add_help=False,  # we render our own help to keep the logo + theming
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test", "-t", action="store_true", help="Test connectivity and exit")
    mode.add_argument("--config", "-c", action="store_true", help="Open the config editor")
    mode.add_argument("--help", "-h", action="store_true", help="Show this help and exit")
    parser.add_argument(
        "--profile",
        metavar="NAME",
        help="Use this profile for the run (does not persist as the active profile)",
    )
    parser.add_argument(
        "--env",
        metavar="NAME",
        help="Use this environment within the chosen profile",
    )
    return parser


def _resolve_flag_overrides(profile_arg: Optional[str], env_arg: Optional[str]) -> Optional[int]:
    """Apply --profile/--env to the in-memory active pointer.

    Returns an exit code on validation failure (so the caller can return
    it directly), or ``None`` if everything checks out and the launch
    sequence should proceed.
    """
    if not profile_arg and not env_arg:
        return None
    if env_arg and not profile_arg:
        console.print("[red]--env requires --profile.[/red]")
        return 2

    doc = profiles.load_profiles()
    available = profiles.list_profiles(doc)
    if profile_arg not in available:
        console.print(
            f"[red]Unknown profile {profile_arg!r}.[/red] "
            f"Available: {', '.join(available) or '(none)'}"
        )
        return 2

    envs = profiles.list_environments(doc, profile_arg)
    if env_arg is None:
        if len(envs) > 1:
            console.print(
                f"[red]--profile {profile_arg!r} has multiple environments "
                f"({', '.join(envs)}); pass --env to disambiguate.[/red]"
            )
            return 2
        env_arg = envs[0]
    elif env_arg not in envs:
        console.print(
            f"[red]Unknown environment {env_arg!r} in profile {profile_arg!r}.[/red] "
            f"Available: {', '.join(envs)}"
        )
        return 2

    config.set_active_override(profile_arg, env_arg)
    reload_config()
    return None


def _print_help() -> None:
    display_logo()
    console.print("\n[bold]Usage:[/bold]")
    console.print("  forbin                       Run interactive session")
    console.print("  forbin --test                Test connectivity (exits non-zero on failure)")
    console.print("  forbin --config              Open the config editor")
    console.print("  forbin --profile X --env Y   Pin profile/environment for this run")
    console.print("  forbin --help                Show this help message")
    console.print("\n[bold]Configuration:[/bold]")
    console.print(f"  Profiles file: {profiles.PROFILES_FILE}")
    console.print("  Connection fields come from the active profile's environment.")
    console.print("  Globals (VERBOSE, MCP_TOOL_TIMEOUT) can still be overridden via env / .env.")
    console.print("\n[bold]Interactive Shortcuts:[/bold]")
    console.print("  [bold cyan]'v'[/bold cyan]   - Toggle verbose logging at any time")
    console.print(
        "  [bold cyan]'c'[/bold cyan]   - View/update configuration (in menu) "
        "or copy last response (after a tool call)"
    )
    console.print("  [bold cyan]'p'[/bold cyan]   - Switch profile / environment")
    console.print("  [bold cyan]ESC[/bold cyan]   - Cancel a running tool call")


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
        parser = _build_arg_parser()
        args = parser.parse_args(sys.argv[1:])

        if args.help:
            _print_help()
            return 0

        # Migration runs before flag validation so --profile can reference
        # a freshly-imported profile from a legacy config.json.
        migrate_legacy_config_if_needed()

        if args.profile or args.env:
            if args.config:
                console.print(
                    "[yellow]--profile / --env are ignored with --config "
                    "(switch from inside the editor instead).[/yellow]"
                )
            else:
                code = _resolve_flag_overrides(args.profile, args.env)
                if code is not None:
                    return code

        if args.test:
            ok = await test_connectivity()
            return 0 if ok else 1
        if args.config:
            display_logo()
            if is_first_run():
                run_first_time_setup()
            else:
                reload_config()
            handle_config_command()
            return 0

        await interactive_session()
        return 0
    except UserQuit:
        # Any prompt anywhere in the app can raise UserQuit to short-
        # circuit out cleanly — finally blocks (MCP cleanup, listener
        # cancellation) still run because we propagate up here instead
        # of calling sys.exit() in-place.
        console.print("\n[bold yellow]Exiting...[/bold yellow]")
        return 0
    except asyncio.CancelledError:
        return 0
    except Exception as e:
        # Last-resort safety net: any uncaught exception lands here so
        # users see a clean Rich-rendered error message instead of a raw
        # Python traceback dumped to stderr by asyncio. Verbose mode
        # additionally prints a colourised traceback so a developer can
        # diagnose without re-running.
        console.print(f"\n[bold red]Unexpected error:[/bold red] [red]{type(e).__name__}[/red] {e}")
        if config.VERBOSE:
            from rich.traceback import Traceback

            console.print(Traceback.from_exception(type(e), e, e.__traceback__))
        else:
            console.print(
                "[dim]Run with VERBOSE=true (or toggle 'v' before the error) "
                "for a detailed traceback.[/dim]"
            )
        return 1


def main():
    """Synchronous entry point for CLI."""
    sys.exit(asyncio.run(async_main()))
