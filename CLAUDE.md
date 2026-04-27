# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Forbin** is an interactive CLI tool for testing remote MCP (Model Context Protocol) servers and their tools. Named after Dr. Charles Forbin from "Colossus: The Forbin Project" (1970), where two computers learn to communicate — a perfect parallel to MCP enabling systems to communicate.

It's designed for developers building agentic workflows and testing FastAPI/FastMCP-based remote tools. The tool specializes in handling suspended services (like Fly.io) with automatic wake-up functionality.

## Key Features

- Interactive tool browser with parameter input
- Automatic server wake-up for suspended services
- Cold-start resilient connection logic
- Type-safe parameter parsing
- Connectivity testing mode
- Clipboard copy for tool responses
- ESC-to-cancel for in-flight tool calls
- First-run setup wizard with persistent JSON config

## Running the Tool

The package installs a `forbin` console script (see `pyproject.toml` `[project.scripts]`).

### Interactive Mode

```bash
forbin
```

Equivalent: `python -m forbin` or `uv run forbin` from a source checkout.

The interactive flow:
1. Show current configuration; let the user confirm or edit before connecting.
2. Wake up the server if `MCP_HEALTH_URL` is configured (otherwise skip).
3. Connect to the MCP server and list its tools in a single retry attempt.
4. Enter the two-level interactive browser (tool list → tool view).

### Connectivity Test Mode

```bash
forbin --test
```

Tests server connectivity (wake-up + connect + list tools) without entering the browser.

### First-time Setup Wizard

```bash
forbin --config
```

Forces the first-run setup wizard to re-run.

### Help

```bash
forbin --help
```

## Configuration

Settings live in two places:

1. **`.env` file or environment variables** — highest priority.
2. **`~/.forbin/config.json`** — written by the first-run wizard and the in-app config editor.

Required:
- `MCP_SERVER_URL` — MCP server endpoint
- `MCP_TOKEN` — Bearer token for authentication

Optional:
- `MCP_HEALTH_URL` — Health endpoint for availability check / wake-up
- `VERBOSE` — `true`/`false` (also persisted when toggled with `v` in the UI)

Precedence is `env > config.json > default`. The config editor flags env-shadowed fields with an `(env)` tag so the user knows their edit won't survive the next launch.

## Architecture

### Package Layout

```
forbin/
  __init__.py        # Package exports + __version__ from importlib.metadata
  __main__.py        # python -m forbin entry point
  cli.py             # Argument dispatch + interactive_session / test_connectivity
  client.py          # MCPSession wrapper, wake_up_server, connect_and_list_tools
  config.py          # Config load/save, env shadowing, first-run wizard
  display.py         # Rich-based UI primitives (panels, step indicators, logo)
  tools.py           # parse/get parameters, call_tool with ESC-cancel + clipboard
  utils.py           # FilteredStderr, verbose-aware logging, key listeners
  verbose.py         # vlog / vlog_json / vlog_timing / vtimer helpers
```

### Health Endpoint Strategy

When `MCP_HEALTH_URL` is set, Forbin probes the health endpoint before connecting. The probe does two things at once:

1. **Availability check** — confirms the server is reachable, like hitting an LLM provider's `/models` endpoint before issuing real requests.
2. **Wake-up trigger** — on Fly.io / Railway / Render and similar suspend-on-idle platforms, the same probe rouses the instance.

If `MCP_HEALTH_URL` is unset, Forbin skips wake-up entirely and connects directly. That path is appropriate for always-on servers and local development.

### Wake-Up Sequence

For configured health URLs, the flow is:

1. **Health probe** (`client.wake_up_server`) — 6 attempts × 5s waits, 30s per-request httpx timeout.
2. **Initialization pause** — 5s `asyncio.sleep` after the first 200 to let the MCP server's inner services finish booting.
3. **Connect + list tools** (`client.connect_and_list_tools`) — `init_timeout=30s`, `timeout=600s`, 3 retries with 5s between.

Connect and list_tools are bundled inside the same retry attempt because a session can expire between them; retrying connect alone wouldn't recover.

### Error Handling

**`utils.FilteredStderr`** — proxies `sys.stderr` and suppresses harmless FastMCP teardown noise (e.g. "Session termination failed: 400", post_writer 400 tracebacks). Suppression is bypassed when `VERBOSE` is on so the user can opt back into the noise.

**Connection retry logic** — `BrokenResourceError` and `ClosedResourceError` are softened to "Connection error (server not ready)" because they're the typical cold-start signature. Other exceptions fall through to a normal error message + traceback in verbose mode.

**ESC-to-cancel** — `tools.call_tool` races the tool task against an `_wait_for_escape` listener so a hanging tool call can be aborted without ctrl-C-ing the whole CLI.

### Parameter Handling

**`tools.parse_parameter_value`** — converts string input to the right type for the MCP schema: `boolean`, `integer`, `number`, `string`, `object`, `array` (last two via `json.loads`).

**`tools.get_tool_parameters`** — interactive collection loop with required/optional badges, enum hints, and reprompt-on-parse-failure.

## Development Notes

### Dependencies

- `fastmcp>=2.0.0` — MCP client library
- `httpx>=0.24.0` — async HTTP for health checks
- `python-dotenv>=1.0.0` — env-var loading
- `pyperclip>=1.8.0` — clipboard copy for tool responses
- `rich>=13.0.0` — terminal UI

### Package Management

Uses `uv`:

```bash
uv sync
```

Python **3.13+** is required (see `pyproject.toml`). The distributed package on PyPI is `forbin-mcp`; the import name and console script are `forbin`.

### Versioning

`pyproject.toml` is the single source of truth for the version. `forbin.__version__` resolves it via `importlib.metadata`, and `tests/test_version.py` fails CI if anything drifts. Do not hardcode the version anywhere else. See `docs/RELEASING.md` for the release flow.

### Making Changes

- **Connection logic** — `forbin/client.py` (`connect_and_list_tools`, `connect_to_mcp_server`, `MCPSession`)
- **Wake-up behavior** — `forbin/client.py` `wake_up_server`, plus the 5s init `asyncio.sleep` in `forbin/cli.py` (`reconnect`, `test_connectivity`)
- **Display formatting** — `forbin/display.py`
- **Parameter parsing** — `forbin/tools.py` `parse_parameter_value` / `get_tool_parameters`
- **Error suppression** — `forbin/utils.py` `FilteredStderr.suppress_patterns`

### Important Constants

- **Health probe**: 6 attempts × 5s inter-attempt wait, 30s per-request timeout
- **Post-wake initialization pause**: 5s
- **Connection retry**: 3 attempts with `init_timeout=30s` each
- **Tool listing timeout**: 15s
- **Tool execution timeout**: 600s

These are tuned for Fly.io cold starts but can be adjusted for other platforms.

## Testing

Tests live in `tests/`:

- `tests/test_main.py` — unit tests
- `tests/test_integration.py` — integration tests
- `tests/test_version.py` — version-drift guard
- `tests/conftest.py` — fixtures (`mock_tool`, `mock_mcp_client`, `mock_httpx_client`, etc.)

Run with `make test` or `uv run pytest`.

To exercise the tool against a real server:
1. Configure `.env` or run `forbin --config`.
2. `forbin --test` for connectivity-only.
3. `forbin` for the full interactive session.

## FastAPI/FastMCP Server Compatibility

Forbin expects servers to:
- Expose an MCP endpoint (typically `/mcp`)
- Implement bearer token authentication
- Optionally provide a `/health` endpoint that returns 200 when the server is ready (lightweight, no auth, no DB queries)
- Follow the MCP protocol specification

Example compatible server:

```python
from fastapi import FastAPI
from fastmcp import FastMCP

app = FastAPI()
mcp = FastMCP("My Tools")

@mcp.tool()
def my_tool(param: str) -> str:
    return f"Result: {param}"

app.include_router(mcp.get_router(), prefix="/mcp")

@app.get("/health")
def health():
    return {"status": "ok"}
```

## Common Issues

### "Failed to wake up server"
- Check `MCP_HEALTH_URL` is correct and accessible (try it in a browser).
- Increase retries via `wake_up_server`'s `max_attempts` argument if your platform has very long cold-starts.
- Remove `MCP_HEALTH_URL` if your server doesn't suspend.

### "Connection error (server not ready)"
- Increase the post-wake initialization pause in `forbin/cli.py` (currently `asyncio.sleep(5)` in `reconnect` and `test_connectivity`).
- Verify `MCP_SERVER_URL` and `MCP_TOKEN` are correct.
- Toggle verbose with `v` to see the underlying exception.

### "Session termination failed: 400"
- Harmless FastMCP teardown noise; already suppressed by `FilteredStderr`.
- No action needed.
