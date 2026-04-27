# Forbin Architecture

Technical reference for how Forbin is organized internally, how it talks to MCP servers, and how its UI is wired up. For the user-facing wake-up strategy and timeout knobs, see [CONFIGURATION.md](CONFIGURATION.md#health-url-behavior).

## Package Layout

```
forbin/
  __init__.py        # Package exports + __version__ from importlib.metadata
  __main__.py        # `python -m forbin` entry point
  cli.py             # Argument dispatch + interactive_session / test_connectivity
  client.py          # MCPSession wrapper, wake_up_server, connect_and_list_tools
  config.py          # Config load/save, env shadowing, first-run wizard
  display.py         # Rich-based UI primitives (panels, step indicators, logo)
  tools.py           # Parameter parsing, get_tool_parameters, call_tool
  utils.py           # FilteredStderr, verbose-aware logging, key listeners
  verbose.py         # vlog / vlog_json / vlog_timing / vtimer helpers
```

## Connection Flow

The wake-up sequence (health probe → init pause → connect+list) and its timeout values are documented in [CONFIGURATION.md](CONFIGURATION.md#health-url-behavior). This section covers the *implementation* details below that user-facing description.

### `MCPSession` wrapper (`forbin/client.py`)

`MCPSession` holds both the FastMCP `Client` and its underlying session so the async context can outlive the function that opened it. Connect functions enter the client context manually (`await client.__aenter__()`) and `MCPSession.cleanup()` exits it later. This is what allows the interactive loop to hold a connection open across multiple tool calls.

### `connect_and_list_tools` bundling

Connection and tool listing are bundled inside a single retry attempt rather than treated as two independent steps. Reason: an MCP session can expire between connect and `list_tools`. If they were separate, retrying connect alone wouldn't recover from a session that died after a successful handshake. Bundling them keeps the retry honest — each attempt is a fresh client.

### Cold-start error softening

`BrokenResourceError` and `ClosedResourceError` raised during connect are the typical cold-start signature on Fly.io and similar platforms. They're surfaced to the user as a softer "Connection error (server not ready)" message rather than a raw traceback. Other exceptions fall through to a normal error message + traceback when verbose mode is on.

## User Interface

### Step Indicators

During the connect sequence Forbin shows in-place step status:

| Color | Icon | Meaning |
|-------|------|---------|
| **Yellow** | `>` | **In Progress** — current action is running |
| **Green** | `+` | **Success** — step completed |
| **Dim/Grey** | `-` | **Skip** — step skipped (e.g. no health URL) |

The "in progress" → "success" transition is rendered as an in-place line update via Rich's `Control` cursor sequences, so the terminal isn't filled with stale status lines.

### Anytime Logging Toggle

A background asyncio task (`utils.listen_for_toggle`) reads stdin in cbreak mode and watches for `v`. Because it runs concurrently with the connect/list/tool-call work, the user can toggle verbose mid-flight — useful for surfacing the underlying error on a hanging connection without restarting the CLI.

When verbose flips on, two things change immediately:
1. `FilteredStderr` (see below) stops swallowing FastMCP teardown noise and shows full tracebacks.
2. The verbose-gated `httpx` and `mcp.client.streamable_http` logging handlers begin emitting through `vlog()`.

This listener requires a TTY and POSIX `termios`; it silently no-ops on native Windows or piped stdin. See [USAGE.md → Terminal Compatibility](USAGE.md#terminal-compatibility).

### Interactive Tool Browser

Two-level navigation:

1. **Tool List View** — numbered list of tools, with a `Commands:` block underneath for `v`/`c`/`q`/numeric selection.
2. **Tool View** — header rule + per-tool menu (`d` details, `r` run, `b` back, `q` quit, plus the global `v`/`c`).

Parameter collection is type-aware (`tools.parse_parameter_value`):
- **string** — verbatim
- **boolean** — `true`/`false`/`y`/`n`/`1`/`0`
- **integer**, **number** — `int()` / `float()`
- **object**, **array** — `json.loads()`

Invalid input reprompts; required vs. optional is enforced.

### ESC-to-Cancel

`tools.call_tool` races the actual MCP call against `_wait_for_escape` using `asyncio.wait(FIRST_COMPLETED)`. If ESC wins, the tool task is cancelled and the user returns to the tool view without disturbing the open MCP session. Same TTY/POSIX requirements as the verbose listener.

## Error Handling

### `FilteredStderr` (`forbin/utils.py`)

Replaces `sys.stderr` with a proxy that suppresses known-noisy FastMCP teardown output — most prominently the `Session termination failed: 400` warning emitted when a streamable-HTTP session is closed. It works by pattern-matching against substrings (`Session termination failed`, `Error in post_writer`, traceback frame markers, etc.) and swallowing up to 10 follow-up lines or until a blank line.

Bypassed entirely when `VERBOSE` is on, so the user can opt back into the noise for debugging.

### Verbose-gated library logging

The MCP library's logging handlers may hold a reference to the original (unfiltered) stderr captured at import time, bypassing `FilteredStderr`. To plug that gap, `utils.setup_logging` adds a `_MCPVerboseGate` filter to `mcp.client.streamable_http` that drops records unless `VERBOSE` is on, and routes `httpx` + MCP transport logs through `vlog()` so they appear only when the user opts in.

### Connection retry semantics

- `BrokenResourceError` / `ClosedResourceError` → softened message, no traceback even in verbose
- `asyncio.TimeoutError` → "Timeout (server not responding)"
- Anything else → exception name + message; full traceback in verbose mode
- Each retry creates a fresh `Client` — there's no resurrecting a partially-handshaken session

## Configuration Resolution (`forbin/config.py`)

Settings are read with priority `env > ~/.forbin/config.json > default` (see [CONFIGURATION.md](CONFIGURATION.md#environment-variables)). The implementation:

- `load_dotenv()` runs at module import to populate `os.environ` from `.env` in CWD (or up the tree).
- `get_setting(key)` checks `os.environ` first, then the JSON file, then returns the default.
- Module-level `MCP_SERVER_URL`, `MCP_TOKEN`, `MCP_HEALTH_URL`, `VERBOSE` are populated at import.
- `reload_config()` re-runs `get_setting` for each, used after the in-app config editor saves a change so the new values apply mid-session without a restart.
- `is_env_shadowed(key)` drives the `(env)` tag in the editor — warns the user that their JSON edit will be invisible on next launch unless they also clear the env var.

## Versioning

`pyproject.toml` is the single source of truth. `forbin.__version__` resolves it via `importlib.metadata.version("forbin-mcp")` at import time, with a `0.0.0+local` fallback for editable checkouts where the package metadata isn't installed yet. `tests/test_version.py` fails CI if `__version__` and `pyproject.toml` ever drift.

## Related Documentation

- [USAGE.md](USAGE.md) — user-facing CLI guide
- [CONFIGURATION.md](CONFIGURATION.md) — settings, health-URL strategy, troubleshooting
- [DEVELOPMENT.md](DEVELOPMENT.md) — testing, linting, dev workflow
- [RELEASING.md](RELEASING.md) — release process and Homebrew bottle build
