import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# File Paths
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
    """Get setting with priority: Env Var > Config File > Default."""
    # 1. Environment Variable
    env_val = os.getenv(key)
    if env_val:
        return env_val

    # 2. Config File
    config = load_config()
    if key in config:
        return str(config[key])

    # 3. Default
    return default


def is_env_shadowed(key: str) -> bool:
    """Return True if an environment variable is overriding the stored config value for `key`."""
    return bool(os.getenv(key))


def is_first_run() -> bool:
    """Check if this is the first time Forbin is being run."""
    return not CONFIG_FILE.exists()


def validate_config() -> bool:
    """Validate required configuration. Returns True if valid, False otherwise."""
    if not MCP_SERVER_URL:
        return False
    if not MCP_TOKEN:
        return False
    return True


def reload_config():
    """Reload module-level config variables from settings."""
    global MCP_SERVER_URL, MCP_TOKEN, MCP_HEALTH_URL, VERBOSE
    MCP_SERVER_URL = get_setting("MCP_SERVER_URL")
    MCP_TOKEN = get_setting("MCP_TOKEN")
    MCP_HEALTH_URL = get_setting("MCP_HEALTH_URL") or None
    VERBOSE = get_setting("VERBOSE").lower() in ("true", "1", "yes")


def run_first_time_setup():
    """Interactive first-time setup wizard."""
    from .display import console

    console.print()
    console.print("[bold cyan]First-time setup[/bold cyan]")
    console.print()
    console.print("No configuration found. Let's set up your MCP server connection.")
    console.print()

    # MCP_SERVER_URL (required)
    console.print("[bold]MCP Server URL[/bold] [dim](required)[/dim]")
    console.print("  The URL of your MCP server endpoint (e.g. https://example.com/mcp)")
    while True:
        server_url = input("  MCP Server URL: ").strip()
        if server_url:
            break
        console.print("  [red]This field is required.[/red]")

    # MCP_TOKEN (required)
    console.print()
    console.print("[bold]MCP Token[/bold] [dim](required)[/dim]")
    console.print("  Bearer token for authentication")
    while True:
        token = input("  MCP Token: ").strip()
        if token:
            break
        console.print("  [red]This field is required.[/red]")

    # MCP_HEALTH_URL (optional)
    console.print()
    console.print("[bold]Health Check URL[/bold] [dim](optional)[/dim]")
    console.print("  For waking up suspended services (e.g. Fly.io)")
    health_url = input("  Health URL (press Enter to skip): ").strip()

    # Build config
    config = {
        "MCP_SERVER_URL": server_url,
        "MCP_TOKEN": token,
    }
    if health_url:
        config["MCP_HEALTH_URL"] = health_url

    # Save
    if save_config(config):
        console.print()
        console.print(f"[green]Configuration saved to {CONFIG_FILE}[/green]")
        console.print(
            "[dim]You can change settings anytime with 'c' in the menu or 'forbin --config'[/dim]"
        )
        console.print()
        reload_config()
    else:
        console.print("[red]Failed to save configuration.[/red]")
        console.print()


# Initialize Configuration
MCP_SERVER_URL: Optional[str] = get_setting("MCP_SERVER_URL") or None
MCP_HEALTH_URL: Optional[str] = get_setting("MCP_HEALTH_URL") or None
MCP_TOKEN: Optional[str] = get_setting("MCP_TOKEN") or None

# Runtime flags
VERBOSE: bool = get_setting("VERBOSE").lower() in ("true", "1", "yes")
