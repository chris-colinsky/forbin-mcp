import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from cwd (or up the tree) before reading any settings — so
# environment shadowing of the JSON config behaves predictably.
load_dotenv()

# File Paths — both overridable via env so tests and CI can sandbox them.
FORBIN_DIR = Path(os.getenv("FORBIN_DIR", str(Path.home() / ".forbin")))
CONFIG_FILE = Path(os.getenv("FORBIN_CONFIG_FILE", str(FORBIN_DIR / "config.json")))


def ensure_forbin_dir():
    """Ensure the forbin storage directory exists."""
    if not FORBIN_DIR.exists():
        try:
            FORBIN_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            from .display import console

            console.print(f"[yellow]Warning: Could not create directory {FORBIN_DIR}: {e}[/yellow]")


def load_config() -> dict:
    """Load configuration from JSON file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception as e:
            from .display import console

            console.print(f"[yellow]Warning: Could not load config file: {e}[/yellow]")
    return {}


def save_config(config: dict) -> bool:
    """Save configuration to JSON file."""
    try:
        ensure_forbin_dir()
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        from .display import console

        console.print(f"[red]Error saving config file: {e}[/red]")
        return False


def get_setting(key: str, default: str = "") -> str:
    """Resolve a setting from the right storage slot.

    Per-environment fields (server URL, health URL, token) come from the
    active environment in ``profiles.json``; environment variables
    deliberately do **not** shadow these — picking a profile means the
    profile's values are authoritative.

    Global fields (``VERBOSE``, ``MCP_TOOL_TIMEOUT``) keep the original
    env-shadow semantics so a shell-level toggle still wins.
    """
    from . import profiles  # lazy: avoids circular import on module load

    if key in profiles.PER_ENV_FIELDS:
        try:
            doc = profiles.load_profiles()
            env_dict = profiles.get_active_environment(doc)
        except (profiles.ProfileError, KeyError):
            return default
        val = env_dict.get(key)
        return str(val) if val else default

    # Global key path: env > profiles.globals > default
    env_val = os.getenv(key)
    if env_val:
        return env_val
    try:
        doc = profiles.load_profiles()
        val = profiles.get_global(doc, key)
    except (profiles.ProfileError, KeyError):
        val = None
    return val if val else default


def is_env_shadowed(key: str) -> bool:
    """True when an env var is currently overriding the stored value.

    Per-environment fields are never shadowed under v0.1.5+ — profiles win.
    The (env) tag in the editor only renders for global keys now.
    """
    from . import profiles  # lazy

    if key in profiles.PER_ENV_FIELDS:
        return False
    return bool(os.getenv(key))


def is_first_run() -> bool:
    """True when Forbin has no profiles.json yet — wizard should run.

    Migration runs *before* this check, so by the time we get here a
    legacy ``config.json`` or a ``.env`` with connection fields would
    already have produced a ``profiles.json``.
    """
    from . import profiles  # lazy

    return not profiles.PROFILES_FILE.exists()


def validate_config() -> bool:
    """Validate required configuration. Returns True if valid, False otherwise."""
    if not MCP_SERVER_URL:
        return False
    if not MCP_TOKEN:
        return False
    return True


# Default tool-call timeout (seconds). Long-running MCP tools — agentic
# workflows, batch jobs, etc. — can exceed this; bump MCP_TOOL_TIMEOUT in
# .env or via the in-app editor to extend.
DEFAULT_TOOL_TIMEOUT = 600.0


def _parse_tool_timeout(raw: str) -> float:
    """Parse the MCP_TOOL_TIMEOUT setting. Falls back to the default on
    empty/invalid input rather than crashing — bad config shouldn't break
    the CLI's startup."""
    if not raw:
        return DEFAULT_TOOL_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TOOL_TIMEOUT
    if value <= 0:
        return DEFAULT_TOOL_TIMEOUT
    return value


# Optional overrides set by --profile / --env CLI flags. When set, they
# bypass the on-disk active pointer for the lifetime of the process —
# CI invocations shouldn't mutate persistent state.
_OVERRIDE_PROFILE: Optional[str] = None
_OVERRIDE_ENV: Optional[str] = None


def set_active_override(profile: Optional[str], env: Optional[str]) -> None:
    """Pin reload_config() to a specific profile/environment for this
    process, ignoring whatever's stored as active in profiles.json.

    Used by ``--profile`` / ``--env`` CLI flags so a scripted run lands
    in a known config without overwriting the user's last manual choice.
    Pass ``None`` for both to clear the override.
    """
    global _OVERRIDE_PROFILE, _OVERRIDE_ENV
    _OVERRIDE_PROFILE = profile
    _OVERRIDE_ENV = env


def reload_config():
    """Refresh module-level globals from the current profiles.json state.

    Called after the user edits config in the CLI or switches profile/env
    so the change applies to the rest of the session without restarting.
    Reads the file once and pulls every setting from the same snapshot to
    avoid getting a torn read across keys.
    """
    from . import profiles  # lazy

    global MCP_SERVER_URL, MCP_TOKEN, MCP_HEALTH_URL, VERBOSE, MCP_TOOL_TIMEOUT
    global ACTIVE_PROFILE, ACTIVE_ENV

    try:
        doc = profiles.load_profiles()
        if _OVERRIDE_PROFILE and _OVERRIDE_ENV:
            active_profile, active_env = _OVERRIDE_PROFILE, _OVERRIDE_ENV
        else:
            active_profile, active_env = profiles.get_active(doc)
        env_dict = doc["profiles"][active_profile]["environments"][active_env]
        ACTIVE_PROFILE, ACTIVE_ENV = active_profile, active_env
    except (profiles.ProfileError, KeyError):
        env_dict = {}
        doc = profiles.default_profiles_doc()
        ACTIVE_PROFILE, ACTIVE_ENV = ("default", "default")

    MCP_SERVER_URL = (env_dict.get("MCP_SERVER_URL") or "") or None
    MCP_TOKEN = (env_dict.get("MCP_TOKEN") or "") or None
    MCP_HEALTH_URL = (env_dict.get("MCP_HEALTH_URL") or "") or None

    # Globals: env still wins for these. Pull from profiles.globals as
    # the second tier so a session-level shell override (e.g. VERBOSE=true
    # forbin) keeps working without touching the stored config.
    verbose_raw = os.getenv("VERBOSE") or profiles.get_global(doc, "VERBOSE") or ""
    VERBOSE = verbose_raw.lower() in ("true", "1", "yes")

    timeout_raw = (
        os.getenv("MCP_TOOL_TIMEOUT") or profiles.get_global(doc, "MCP_TOOL_TIMEOUT") or ""
    )
    MCP_TOOL_TIMEOUT = _parse_tool_timeout(timeout_raw)


def migrate_legacy_config_if_needed() -> bool:
    """Import a pre-v0.1.5 ``config.json`` (or a bare ``.env``) into the
    new ``profiles.json`` store.

    Runs at every launch but is idempotent — once ``profiles.json`` exists
    we return immediately. Returns True if a migration actually ran (so
    the caller can suppress the wizard); False otherwise.

    Three branches, in priority order:
      1. Legacy ``config.json`` present → import its connection fields
         into ``default/default`` and globals into the globals slot.
         Rename the old file to ``config.json.bak``.
      2. No legacy file but ``.env`` defines a connection field →
         seed ``default/default`` from whatever's present. The wizard
         still fills in any required fields the .env didn't provide.
      3. Neither → return False; caller runs the wizard.
    """
    from . import profiles  # lazy to avoid circular import on module load

    if profiles.PROFILES_FILE.exists():
        return False

    from .display import console

    legacy_present = CONFIG_FILE.exists()
    if legacy_present:
        legacy = load_config()
        doc = profiles.default_profiles_doc()
        env = doc["profiles"]["default"]["environments"]["default"]
        for key in profiles.PER_ENV_FIELDS:
            if key in legacy and legacy[key]:
                env[key] = str(legacy[key])
        for key in profiles.GLOBAL_FIELDS:
            if key in legacy and legacy[key] != "":
                doc["globals"][key] = str(legacy[key])

        if profiles.save_profiles(doc):
            backup = CONFIG_FILE.with_suffix(CONFIG_FILE.suffix + ".bak")
            try:
                os.replace(CONFIG_FILE, backup)
            except Exception as e:
                console.print(f"[yellow]Warning: could not back up legacy config: {e}[/yellow]")
            console.print(
                f"[green]Migrated legacy config to {profiles.PROFILES_FILE}[/green] "
                f"[dim](backup at {backup})[/dim]"
            )
            _warn_about_env_shadow(console)
            return True
        return False

    # No legacy file. If .env supplied any per-env value, seed from it so
    # the user doesn't have to retype values the wizard already saw via
    # the environment.
    env_seed = {k: os.getenv(k, "") for k in profiles.PER_ENV_FIELDS}
    has_any = any(v for v in env_seed.values())
    if has_any:
        doc = profiles.default_profiles_doc()
        target = doc["profiles"]["default"]["environments"]["default"]
        for k, v in env_seed.items():
            if v:
                target[k] = v
        if profiles.save_profiles(doc):
            console.print(
                f"[green]Seeded default profile from .env at {profiles.PROFILES_FILE}[/green]"
            )
            _warn_about_env_shadow(console)
            return True
    return False


def _warn_about_env_shadow(console) -> None:
    """One-time heads-up that .env no longer shadows per-environment fields.

    Triggered from the migration code path, so the user only sees it on
    the launch where they're moving to v0.1.5.
    """
    shadowed = [k for k in ("MCP_SERVER_URL", "MCP_HEALTH_URL", "MCP_TOKEN") if os.getenv(k)]
    if not shadowed:
        return
    console.print(
        f"[yellow]Note: {', '.join(shadowed)} from your environment / .env "
        f"are no longer used for the active profile.[/yellow] "
        f"[dim]Manage connection fields with 'forbin --config' or the "
        f"in-app editor.[/dim]"
    )


def run_first_time_setup():
    """Interactive first-time setup wizard.

    Writes into the ``default/default`` slot of ``profiles.json``. If
    migration pre-seeded any field from ``.env``, only re-prompt for
    required fields that are still empty (fill-in-the-blanks mode).
    """
    from . import profiles  # lazy
    from .display import console

    doc = profiles.load_profiles()
    if not doc["profiles"]:
        # load_profiles() returned a doc that's missing the default
        # profile (shouldn't normally happen — default_profiles_doc
        # creates one). Reset to default to avoid downstream KeyErrors.
        doc = profiles.default_profiles_doc()

    profile_name, env_name = profiles.get_active(doc)
    env_dict = doc["profiles"][profile_name]["environments"][env_name]

    console.print()
    console.print("[bold cyan]First-time setup[/bold cyan]")
    console.print()
    if any(env_dict.get(k) for k in profiles.PER_ENV_FIELDS):
        console.print(
            "Some values were seeded from your environment. "
            "Fill in any missing required fields below."
        )
    else:
        console.print("Let's set up your MCP server connection.")
    console.print()

    if not env_dict.get("MCP_SERVER_URL"):
        console.print("[bold]MCP Server URL[/bold] [dim](required)[/dim]")
        console.print("  The URL of your MCP server endpoint (e.g. https://example.com/mcp)")
        while True:
            server_url = input("  MCP Server URL: ").strip()
            if server_url:
                env_dict["MCP_SERVER_URL"] = server_url
                break
            console.print("  [red]This field is required.[/red]")

    if not env_dict.get("MCP_TOKEN"):
        console.print()
        console.print("[bold]MCP Token[/bold] [dim](required)[/dim]")
        console.print("  Bearer token for authentication")
        while True:
            token = input("  MCP Token: ").strip()
            if token:
                env_dict["MCP_TOKEN"] = token
                break
            console.print("  [red]This field is required.[/red]")

    # Health URL is optional — only prompt if the seed didn't supply one.
    if not env_dict.get("MCP_HEALTH_URL"):
        console.print()
        console.print("[bold]Health Check URL[/bold] [dim](optional)[/dim]")
        console.print("  For waking up suspended services (e.g. Fly.io)")
        health_url = input("  Health URL (press Enter to skip): ").strip()
        if health_url:
            env_dict["MCP_HEALTH_URL"] = health_url

    if profiles.save_profiles(doc):
        console.print()
        console.print(f"[green]Configuration saved to {profiles.PROFILES_FILE}[/green]")
        console.print(
            "[dim]You can change settings anytime with 'c' in the menu or 'forbin --config'[/dim]"
        )
        console.print()
        reload_config()
    else:
        console.print("[red]Failed to save configuration.[/red]")
        console.print()


# Module-level snapshot of the config — populated at import. reload_config()
# updates these in-place after the user edits values via the CLI or
# switches profile/environment.
MCP_SERVER_URL: Optional[str] = get_setting("MCP_SERVER_URL") or None
MCP_HEALTH_URL: Optional[str] = get_setting("MCP_HEALTH_URL") or None
MCP_TOKEN: Optional[str] = get_setting("MCP_TOKEN") or None

# Runtime flags
VERBOSE: bool = get_setting("VERBOSE").lower() in ("true", "1", "yes")
MCP_TOOL_TIMEOUT: float = _parse_tool_timeout(get_setting("MCP_TOOL_TIMEOUT"))

# Currently selected profile / environment — surfaced in the panel and
# the config editor header. Populated by reload_config(); the import-time
# value is a best-effort read so first-launch displays don't crash.
ACTIVE_PROFILE: str = "default"
ACTIVE_ENV: str = "default"
