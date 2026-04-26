# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Forbin** is an interactive CLI tool for testing remote MCP (Model Context Protocol) servers and their tools. Named after Dr. Charles Forbin from "Colossus: The Forbin Project" (1970), where two computers learn to communicate - a perfect parallel to MCP enabling systems to communicate.

It's designed for developers building agentic workflows and testing FastAPI/FastMCP-based remote tools. The tool specializes in handling suspended services (like Fly.io) with automatic wake-up functionality.

## Key Features

- Interactive tool browser with parameter input
- Automatic server wake-up for suspended services
- Cold-start resilient connection logic
- Type-safe parameter parsing
- Connectivity testing mode

## Running the Tool

### Interactive Mode

```bash
python forbin.py
```

This launches the interactive tool browser that:
1. Wakes up suspended servers (if health URL configured)
2. Connects to the MCP server
3. Lists all available tools
4. Allows interactive tool selection and calling

### Connectivity Test Mode

```bash
python forbin.py --test
```

Tests server connectivity without running tools.

### Help

```bash
python forbin.py --help
```

## Configuration

Configuration is via `.env` file:

- `MCP_SERVER_URL` (required) - MCP server endpoint
- `MCP_TOKEN` (required) - Bearer token for authentication
- `MCP_HEALTH_URL` (optional) - Health endpoint for wake-up

Create from template:
```bash
cp .env.example .env
```

## Architecture

### Main Components

**`forbin.py`** - Single-file CLI application with these key functions:

1. **wake_up_server()** (lines 72-111)
   - Polls health endpoint until server responds
   - 6 attempts with 5-second waits
   - Returns True if server is awake

2. **connect_to_mcp_server()** (lines 114-161)
   - Establishes MCP connection with retry logic
   - Uses `init_timeout=30.0` for cold starts
   - 3 attempts with 5-second waits
   - Returns connected Client or None

3. **list_tools()** (lines 164-177)
   - Retrieves tool manifest from server
   - 15-second timeout for the list operation

4. **interactive_session()** (lines 394-476)
   - Main interactive loop
   - Handles tool selection and parameter input
   - Displays results

5. **test_connectivity()** (lines 348-391)
   - Connectivity-only testing mode
   - Useful for CI/CD health checks

### Wake-Up Process

Three-step approach for suspended services:

1. **Health Check Wake-Up** - Polls `/health` endpoint until 200 response
2. **Initialization Wait** - Waits 20 seconds for MCP server to fully initialize
3. **Connection with Retry** - Connects with extended timeout and retry logic

This is critical for Fly.io and similar platforms that suspend inactive services.

### Error Handling

**FilteredStderr class** (lines 18-51):
- Suppresses harmless MCP session termination errors
- Filters stderr output for cleaner user experience
- Specifically suppresses "Session termination failed: 400" warnings

**Connection retry logic**:
- Handles `BrokenResourceError`, `ClosedResourceError`, `TimeoutError`
- Creates fresh client on each retry attempt
- Provides clear feedback on connection status

### Parameter Handling

**parse_parameter_value()** (lines 236-250):
- Converts string input to appropriate types
- Supports: boolean, integer, number, string, object, array
- Handles JSON parsing for complex types

**get_tool_parameters()** (lines 253-310):
- Interactive parameter collection
- Validates required vs optional parameters
- Shows enum values when available
- Retry loop for invalid inputs

## Development Notes

### Dependencies

- **fastmcp** - MCP client library (requires >=2.0.0)
- **httpx** - Async HTTP for health checks
- **python-dotenv** - Environment variable management

### Package Management

Uses `uv` for dependency management:
```bash
uv sync
```

Python 3.11+ required.

### CLI Entry Point

Configured in `pyproject.toml`:
```toml
[project.scripts]
mcp-test = "main:main"
```

After installation, users can run `mcp-test` directly.

### Making Changes

When modifying the tool:

1. **Connection logic** - Edit `connect_to_mcp_server()` and adjust timeouts/retries
2. **Wake-up behavior** - Edit `wake_up_server()` and the 20-second sleep in `interactive_session()`
3. **Display formatting** - Edit `display_tools()` and `display_tool_schema()`
4. **Parameter parsing** - Edit `parse_parameter_value()` for new type support
5. **Error suppression** - Edit `FilteredStderr` class patterns

### Important Constants

- **Health check**: 6 attempts x 5 seconds = 30 seconds max
- **Initialization wait**: 20 seconds after health check
- **Connection retry**: 3 attempts with 30-second init timeout each
- **Tool listing timeout**: 15 seconds

These are tuned for Fly.io cold starts but can be adjusted for other platforms.

## Testing

The tool itself is used for testing MCP servers. To test the tester:

1. Set up a local MCP server or use a remote one
2. Configure `.env` with server details
3. Run `python forbin.py --test` to verify connectivity
4. Run `python forbin.py` to test interactive mode

## FastAPI/FastMCP Server Compatibility

This tool expects servers to:
- Expose an MCP endpoint (e.g., `/mcp`)
- Implement bearer token authentication
- Optionally provide `/health` endpoint for wake-up detection
- Follow MCP protocol specification

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
- Check `MCP_HEALTH_URL` is correct and accessible
- Try increasing retry attempts in `wake_up_server()`
- Remove `MCP_HEALTH_URL` if server doesn't suspend

### "Connection error (server not ready)"
- Increase initialization wait time (line 410: `await asyncio.sleep(20)`)
- Verify `MCP_SERVER_URL` and `MCP_TOKEN` are correct
- Check server logs for initialization issues

### "Session termination failed: 400"
- This is harmless and automatically suppressed
- Occurs during FastMCP library cleanup
- No action needed
