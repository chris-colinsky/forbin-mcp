# Configuration Guide

Forbin reads its settings from two places, in this priority order:

1. **Environment variables** (including those loaded from a `.env` file in the current directory) — highest priority.
2. **`~/.forbin/config.json`** — written by the first-run setup wizard and the in-app config editor.

Whichever source provides a value wins. The in-app config editor flags any field overridden by an environment variable with an `(env)` tag so you know your edit won't survive the next launch unless you also clear the env var.

## Quick Setup

The easiest path is the first-run wizard — just run Forbin once:

```bash
forbin
```

If no config file exists yet, Forbin will prompt for the required values and save them to `~/.forbin/config.json`. You can re-run the wizard anytime with:

```bash
forbin --config
```

If you prefer environment variables (useful for CI/CD or containers), create a `.env` file:

```bash
cp .env.example .env
# then edit .env with your settings
```

> **Where Forbin looks for `.env`:** the file is loaded from the **current working directory** (or up the directory tree) at startup. If you run `forbin` from `~/Desktop` while your `.env` is in `~/projects/myapp`, it will not be picked up. Either `cd` into the project directory first, set the variables in your shell environment, or use the `~/.forbin/config.json` route instead — that file is read regardless of where you run `forbin` from.

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `MCP_SERVER_URL` | Full URL to your MCP server endpoint | `https://my-app.fly.dev/mcp` |
| `MCP_TOKEN` | Bearer token for authentication | `your-secret-token` |

### Optional

| Variable | Description | Example |
|----------|-------------|---------|
| `MCP_HEALTH_URL` | Health check endpoint for wake-up | `https://my-app.fly.dev/health` |

## Configuration Examples

### Local Development

For testing against a local MCP server:

```env
MCP_SERVER_URL=http://localhost:8000/mcp
MCP_TOKEN=dev-token-123
```

No health URL needed for local servers that don't suspend.

### Fly.io Production

For Fly.io apps that may suspend when idle:

```env
MCP_SERVER_URL=https://my-app.fly.dev/mcp
MCP_HEALTH_URL=https://my-app.fly.dev/health
MCP_TOKEN=prod-token-xyz
```

The health URL enables automatic wake-up for suspended services.

### Railway / Render

Similar to Fly.io, for platforms with cold starts:

```env
MCP_SERVER_URL=https://my-app.railway.app/mcp
MCP_HEALTH_URL=https://my-app.railway.app/health
MCP_TOKEN=your-token
```

### Always-On Server

For servers that don't suspend (dedicated VPS, always-on containers):

```env
MCP_SERVER_URL=https://api.example.com/mcp
MCP_TOKEN=your-token
# No MCP_HEALTH_URL needed
```

## Health URL Behavior

`MCP_HEALTH_URL` does double duty: it's both an **availability check** (similar to hitting an LLM provider's `/models` endpoint to confirm the API is reachable before issuing real requests) and a **wake-up trigger** for platforms that suspend or stop idle instances (Fly.io scale-to-zero, Railway, Render, etc.). The same probe that verifies "is it up?" is what *makes* it come up.

When `MCP_HEALTH_URL` is configured:

1. Forbin polls the health endpoint before connecting
2. Waits for HTTP 200 response (up to 6 attempts, 5 seconds apart; per-request timeout is 30s)
3. Pauses 5 seconds to let the MCP server inside the container finish booting
4. Then connects to the MCP endpoint with retry logic

When `MCP_HEALTH_URL` is NOT configured:

1. Forbin skips the wake-up step entirely
2. Connects directly to the MCP endpoint with retry logic
3. Suitable for always-on servers and local development

## Server Requirements

Your MCP server should:

### Implement MCP Endpoint

Expose an MCP-compatible endpoint (typically `/mcp`):

```python
from fastapi import FastAPI
from fastmcp import FastMCP

app = FastAPI()
mcp = FastMCP("My Tools")

@mcp.tool()
def my_tool(param: str) -> str:
    """Tool description"""
    return f"Result: {param}"

app.include_router(mcp.get_router(), prefix="/mcp")
```

### Implement Bearer Authentication

The MCP endpoint should validate the bearer token:

```python
from fastmcp.server.auth import BearerAuthProvider

auth = BearerAuthProvider(token="your-secret-token")
mcp = FastMCP("My Tools", auth=auth)
```

### Implement Health Endpoint (Optional)

For suspended services, add a simple health check:

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

This endpoint should:
- Return HTTP 200 when the server is ready
- Be lightweight (no database queries)
- Not require authentication

## Timeouts and Retries

Forbin uses these defaults for resilience:

| Setting | Value | Description |
|---------|-------|-------------|
| Health check attempts | 6 | Number of wake-up attempts |
| Health check interval | 5s | Wait between health checks |
| Health check per-request timeout | 30s | httpx timeout for each probe |
| Post-wake initialization | 5s | Wait after health check succeeds |
| Connection retry attempts | 3 | Connect + list_tools retries |
| Connection init timeout | 30s | MCP init timeout for cold starts |
| Tool operation timeout | 600s | Max time for tool execution |
| Tool listing timeout | 15s | Timeout for retrieving tool list |

These are tuned for Fly.io cold starts but work well with most platforms.

## Troubleshooting

For most failures, the fastest diagnostic is **toggling verbose mode with `v`** (or running with `VERBOSE=true forbin`) — it surfaces the underlying httpx/MCP errors that the default output suppresses.

### Connection & networking

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `HTTPStatusError: 401 Unauthorized` | Token mismatch — server doesn't recognize this bearer token | Verify `MCP_TOKEN` against the server's expected value. Check for stray whitespace and case differences. Tokens are case-sensitive. |
| `HTTPStatusError: 403 Forbidden` | Token is valid but lacks permission, or the server requires a different auth scheme | Check the server's auth configuration. Some servers gate tools by scope or require a non-bearer scheme. |
| `HTTPStatusError: 404 Not Found` | URL is missing the MCP mount path (e.g. `/mcp`) | Confirm the full path. `https://my-app.fly.dev` is wrong; `https://my-app.fly.dev/mcp` is right. |
| `ConnectError: [Errno -2] Name or service not known` / `nodename nor servname provided` | DNS lookup failed — typo in hostname, or VPN-only host | Try `curl <MCP_SERVER_URL>` from the same machine. If the host is internal, check your VPN. |
| `ConnectError: [Errno 61] Connection refused` | Nothing listening on that host:port | For local dev: confirm the server is running. For remote: check the URL/port; firewall may be blocking. |
| `SSLError: CERTIFICATE_VERIFY_FAILED` | Self-signed cert, expired cert, or missing intermediate | Fix the cert chain server-side. For local dev only, switch to `http://`. |
| Hangs on connect, no progress | Cold-start in progress on a suspended platform | If you have a `MCP_HEALTH_URL`, Forbin should already be probing — toggle `v` to confirm. If you don't, set one. |

### Wake-up & cold starts

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Failed to wake up server` (after 6 attempts) | Health endpoint not reachable, returns non-200, or the server takes longer than 30s × 6 to start | `curl <MCP_HEALTH_URL>` to check. If it's slow on cold start, increase the retry count in `wake_up_server` or remove `MCP_HEALTH_URL` if the server is always-on. |
| `Connection error (server not ready)` | Health probe succeeded but the MCP server inside the container is still booting | Increase the post-wake `asyncio.sleep(5)` in `forbin/cli.py`. Often resolves on the next retry. |
| `TimeoutError` during tool listing | Server reachable but slow to respond on `list_tools` | Increase the 15s `wait_for` timeout in `forbin/client.py`, or investigate why the server is slow. |

### Tools & MCP behavior

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Connect succeeds, tool list is empty | Server registered no tools, or tool registration is gated behind an env var on the server | Check the server's `@mcp.tool()` decorators load. Run `forbin --test` with `v` on to see if anything was filtered. |
| Tool runs, response is `null` or empty `content` | Tool returns `None` or returns before its decorator wraps the result | Server-side issue; verify the tool function actually returns a value. |
| `Invalid value for type X` when entering parameters | Input doesn't match the declared schema type — e.g. text where a number is expected, or non-JSON for object/array fields | Re-enter using the correct type. For objects/arrays, use valid JSON: `{"key": "value"}` or `[1, 2, 3]`. |

### Configuration

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Changes to `.env` aren't picked up | Forbin loads `.env` from the **current working directory** (or up the tree). If you `cd`'d elsewhere, it won't see your file. | `cd` into the project directory before running `forbin`, or move settings into `~/.forbin/config.json` via `forbin --config`. |
| Edited a value in the in-app config editor but it reverts on next launch | Environment variable is shadowing the JSON config (the editor flags this with an `(env)` tag) | Unset the env var or remove the `.env` line. Env always wins on next launch. |
| `URL Format` issues | Trailing slash, missing protocol, or wrong path | URLs need protocol, full endpoint path, and no trailing slash: `https://my-app.fly.dev/mcp` ✓, `my-app.fly.dev/mcp` ✗, `https://my-app.fly.dev/mcp/` ✗. |
| Token rejected after edit in `.env` | Trailing whitespace, surrounding quotes, or shell-expanded characters | No quotes around the value, no trailing whitespace, escape `$` if literal. |

### Suppressed errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Session termination failed: 400` flashes briefly | Harmless FastMCP teardown noise, normally suppressed | Ignore — it's a known cleanup quirk. If it's showing up anyway, you may have toggled verbose mode on. |
| `Error in post_writer` traceback | Same as above — usually FastMCP cleanup | Verbose-mode artifact. Toggle `v` off to suppress. |

## Security Notes

- Never commit `.env` files to version control
- Use different tokens for development and production
- Rotate tokens periodically
- Consider using environment-specific `.env` files (`.env.local`, `.env.production`)

## Next Steps

- See [Usage Guide](USAGE.md) for how to use Forbin
- See [Installation Guide](INSTALLATION.md) for installation options
