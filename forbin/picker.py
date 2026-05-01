"""Profile + environment picker UI.

The picker is invoked at launch (when the user has more than one
profile/env to choose between) and on the ``p`` shortcut mid-session.
It also serves as the CRUD UI for adding, renaming, and deleting
profiles and environments — keeping that logic out of the main config
editor so the editor stays focused on field edits.

Returns ``(profile, environment)`` when the user makes a selection, or
``None`` if they back out without picking. CRUD operations save to disk
incrementally so a mid-flow cancel doesn't lose work.
"""

from typing import Optional

from rich.prompt import Prompt

from . import profiles
from .display import console, display_commands
from .utils import UserQuit


def pick_profile_and_environment() -> Optional[tuple[str, str]]:
    """Top-level picker. Always renders even with a single profile/env —
    the launch-flow caller decides when to skip rendering entirely."""
    while True:
        doc = profiles.load_profiles()
        chosen_profile = _pick_profile(doc)
        if chosen_profile is None:
            return None

        # Always drop into the env picker — even for single-env profiles —
        # so the user can rename, add, or delete environments. The earlier
        # auto-skip optimisation made env CRUD undiscoverable for any
        # profile with only one environment. The launch path still skips
        # the picker entirely when there's nothing to choose between (see
        # _launch_setup), so this only adds a keystroke for users who
        # genuinely have multiple profiles or environments to navigate.
        doc = profiles.load_profiles()
        picked = _pick_environment(doc, chosen_profile)
        if picked is None:
            # User backed out of env picker — go back to profile list.
            continue
        chosen_env = picked

        # Persist active pointer.
        doc = profiles.load_profiles()
        profiles.set_active(doc, chosen_profile, chosen_env)
        profiles.save_profiles(doc)
        return chosen_profile, chosen_env


def _pick_profile(doc: dict) -> Optional[str]:
    while True:
        active_profile, active_env = profiles.get_active(doc)
        names = profiles.list_profiles(doc)

        console.print()
        console.print("[bold underline]Profile[/bold underline]")
        console.print()
        for i, name in enumerate(names, start=1):
            n_envs = len(profiles.list_environments(doc, name))
            badge = " [bold green]*active*[/bold green]" if name == active_profile else ""
            envs_label = f"{n_envs} environment{'s' if n_envs != 1 else ''}"
            console.print(
                f"  [bold cyan]{i}.[/bold cyan] {name:<20} [dim]({envs_label})[/dim]{badge}"
            )
        console.print()

        display_commands(
            [
                ("number", "Select a profile"),
                ("n", "New profile"),
                ("r", "Rename a profile"),
                ("d", "Delete a profile"),
                ("b", "Back / cancel"),
                ("q", "Quit"),
            ]
        )

        choice = Prompt.ask("Choice").strip().lower()
        if choice in ("", "b", "back"):
            return None
        if choice in ("q", "quit", "exit"):
            raise UserQuit

        if choice == "n":
            new_name = _create_profile(doc)
            if new_name:
                doc = profiles.load_profiles()
            continue

        if choice == "r":
            if _rename_profile_flow(doc):
                doc = profiles.load_profiles()
            continue

        if choice == "d":
            if _delete_profile_flow(doc):
                doc = profiles.load_profiles()
            continue

        try:
            idx = int(choice)
        except ValueError:
            console.print("[red]Invalid choice.[/red]")
            continue
        if 1 <= idx <= len(names):
            return names[idx - 1]
        console.print(f"[red]Choose a number between 1 and {len(names)}.[/red]")


def _pick_environment(doc: dict, profile: str) -> Optional[str]:
    while True:
        active_profile, active_env = profiles.get_active(doc)
        names = profiles.list_environments(doc, profile)

        console.print()
        console.print(f"[bold underline]Environment — {profile}[/bold underline]")
        console.print()
        for i, name in enumerate(names, start=1):
            badge = (
                " [bold green]*active*[/bold green]"
                if profile == active_profile and name == active_env
                else ""
            )
            console.print(f"  [bold cyan]{i}.[/bold cyan] {name}{badge}")
        console.print()

        display_commands(
            [
                ("number", "Select an environment"),
                ("n", "New environment"),
                ("r", "Rename an environment"),
                ("d", "Delete an environment"),
                ("b", "Back to profiles"),
                ("q", "Quit"),
            ]
        )

        choice = Prompt.ask("Choice").strip().lower()
        if choice in ("", "b", "back"):
            return None
        if choice in ("q", "quit", "exit"):
            raise UserQuit

        if choice == "n":
            if _create_environment(doc, profile):
                doc = profiles.load_profiles()
            continue

        if choice == "r":
            if _rename_environment_flow(doc, profile):
                doc = profiles.load_profiles()
            continue

        if choice == "d":
            if _delete_environment_flow(doc, profile):
                doc = profiles.load_profiles()
            continue

        try:
            idx = int(choice)
        except ValueError:
            console.print("[red]Invalid choice.[/red]")
            continue
        if 1 <= idx <= len(names):
            return names[idx - 1]
        console.print(f"[red]Choose a number between 1 and {len(names)}.[/red]")


# ---------------------------------------------------------------------------
# CRUD flows — each prompts for input and persists, returning True on success
# so the caller can reload the in-memory doc.
# ---------------------------------------------------------------------------


_RESERVED_MENU_SHORTCUTS = {"n", "r", "d", "b", "q"}


def _prompt_name(label: str) -> Optional[str]:
    """Prompt for a name, validating against the schema's name regex.
    Returns None if the user enters an empty name (treated as cancel)."""
    raw = Prompt.ask(f"  {label}").strip()
    if not raw:
        console.print("[dim]  No change.[/dim]")
        return None
    if raw.lower() in _RESERVED_MENU_SHORTCUTS:
        # The picker dispatches single letters as menu actions, so a
        # name like "n" is almost certainly a fat-finger. Refuse it
        # rather than silently saving a confusing identifier.
        console.print(f"[red]  {raw!r} is a menu shortcut — pick a longer or different name.[/red]")
        return None
    if not profiles.is_valid_name(raw):
        console.print("[red]  Invalid name. Use letters, digits, underscore, dot, or hyphen.[/red]")
        return None
    return raw


def _create_profile(doc: dict) -> Optional[str]:
    name = _prompt_name("New profile name:")
    if not name:
        return None
    seed_env = Prompt.ask("  Seed environment name", default="default").strip() or "default"
    if not profiles.is_valid_name(seed_env):
        console.print("[red]  Invalid environment name.[/red]")
        return None
    try:
        profiles.add_profile(doc, name, seed_env_name=seed_env)
    except profiles.ProfileError as e:
        console.print(f"[red]  {e}[/red]")
        return None
    if profiles.save_profiles(doc):
        console.print(f"[green]  Created profile {name!r} with environment {seed_env!r}.[/green]")
        return name
    return None


def _rename_profile_flow(doc: dict) -> bool:
    names = profiles.list_profiles(doc)
    if not names:
        return False
    target = _select_from_list(names, "Rename which profile?")
    if not target:
        return False
    new_name = _prompt_name(f"New name for {target!r}:")
    if not new_name:
        return False
    try:
        profiles.rename_profile(doc, target, new_name)
    except profiles.ProfileError as e:
        console.print(f"[red]  {e}[/red]")
        return False
    if profiles.save_profiles(doc):
        console.print(f"[green]  Renamed {target!r} -> {new_name!r}.[/green]")
        return True
    return False


def _delete_profile_flow(doc: dict) -> bool:
    names = profiles.list_profiles(doc)
    if len(names) <= 1:
        console.print("[yellow]  Cannot delete the only profile.[/yellow]")
        return False
    target = _select_from_list(names, "Delete which profile?")
    if not target:
        return False
    confirm = Prompt.ask(f"  Type {target!r} to confirm deletion", default="").strip()
    if confirm != target:
        console.print("[dim]  Deletion cancelled.[/dim]")
        return False
    try:
        profiles.delete_profile(doc, target)
    except profiles.ProfileError as e:
        console.print(f"[red]  {e}[/red]")
        return False
    if profiles.save_profiles(doc):
        console.print(f"[green]  Deleted profile {target!r}.[/green]")
        return True
    return False


def _create_environment(doc: dict, profile: str) -> bool:
    name = _prompt_name("New environment name:")
    if not name:
        return False
    try:
        profiles.add_environment(doc, profile, name)
    except profiles.ProfileError as e:
        console.print(f"[red]  {e}[/red]")
        return False
    if profiles.save_profiles(doc):
        console.print(
            f"[green]  Created environment {profile}/{name!r}. "
            f"Set values via the config editor.[/green]"
        )
        return True
    return False


def _rename_environment_flow(doc: dict, profile: str) -> bool:
    names = profiles.list_environments(doc, profile)
    if not names:
        return False
    target = _select_from_list(names, f"Rename which environment in {profile}?")
    if not target:
        return False
    new_name = _prompt_name(f"New name for {target!r}:")
    if not new_name:
        return False
    try:
        profiles.rename_environment(doc, profile, target, new_name)
    except profiles.ProfileError as e:
        console.print(f"[red]  {e}[/red]")
        return False
    if profiles.save_profiles(doc):
        console.print(f"[green]  Renamed {profile}/{target!r} -> {new_name!r}.[/green]")
        return True
    return False


def _delete_environment_flow(doc: dict, profile: str) -> bool:
    names = profiles.list_environments(doc, profile)
    if len(names) <= 1:
        console.print("[yellow]  Cannot delete the only environment in this profile.[/yellow]")
        return False
    target = _select_from_list(names, f"Delete which environment in {profile}?")
    if not target:
        return False
    confirm = Prompt.ask(f"  Type {target!r} to confirm deletion", default="").strip()
    if confirm != target:
        console.print("[dim]  Deletion cancelled.[/dim]")
        return False
    try:
        profiles.delete_environment(doc, profile, target)
    except profiles.ProfileError as e:
        console.print(f"[red]  {e}[/red]")
        return False
    if profiles.save_profiles(doc):
        console.print(f"[green]  Deleted environment {profile}/{target!r}.[/green]")
        return True
    return False


def _select_from_list(items: list[str], label: str) -> Optional[str]:
    """Mini-prompt: list items by number, return the picked one or None."""
    console.print()
    console.print(f"[bold]{label}[/bold]")
    for i, name in enumerate(items, start=1):
        console.print(f"  [bold cyan]{i}.[/bold cyan] {name}")
    raw = Prompt.ask("  Choice", default="").strip()
    if not raw:
        return None
    try:
        idx = int(raw)
    except ValueError:
        console.print("[red]  Invalid number.[/red]")
        return None
    if 1 <= idx <= len(items):
        return items[idx - 1]
    console.print("[red]  Out of range.[/red]")
    return None
