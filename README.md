<p align="left">
  <img src="https://raw.githubusercontent.com/chris-colinsky/forbin-mcp/main/img/forbin_avatar.jpg" alt="Forbin Logo" width="200">
</p>

[![CI](https://github.com/chris-colinsky/forbin-mcp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/chris-colinsky/forbin-mcp/actions)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Forbin

> *"This is the voice of world control..."*
> Inspired by **Colossus: The Forbin Project**, where two computers learn to communicate - just like MCP enables systems to talk to each other.

An interactive CLI tool for testing remote MCP (Model Context Protocol) servers and their tools. Specifically designed for developing agentic workflows with support for suspended services (like Fly.io) that need automatic wake-up.

## Name Origin

**Forbin** is named after Dr. Charles Forbin from the 1970 film *Colossus: The Forbin Project*. In the movie, two supercomputers (American "Colossus" and Soviet "Guardian") learn to communicate with each other, establishing their own protocol and sharing information - a perfect parallel to the Model Context Protocol enabling AI systems and tools to communicate seamlessly.

## Table of Contents

- [Features](#features)
- [Use Cases](#use-cases)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Interactive CLI** - Browse and test MCP tools with an intuitive command-line interface
- **Automatic Wake-up** - Handles suspended services (Fly.io, etc.) with health check probing
- **Cold-Start Resilient** - Built-in retry logic and extended timeouts for slow-starting servers
- **Schema Inspection** - View detailed tool schemas including parameters and types
- **Generic Tool Calling** - Test any MCP tool with interactive parameter input
- **Type-Safe Parameter Parsing** - Automatic conversion of strings, booleans, numbers, and JSON objects
- **Connectivity Testing** - Verify server connectivity without running tools
- **Clipboard Copy** - Press `c` after any tool response to copy it to the system clipboard

## Use Cases

- **Development** - Test your FastAPI/FastMCP server tools during development
- **Debugging** - Verify tool schemas and responses in real-time
- **Agentic Workflows** - Validate tools before integrating them into AI agents
- **CI/CD** - Run connectivity tests as part of deployment pipelines
- **Documentation** - Explore available tools on any MCP server

## Installation

**Requirements:** Python 3.13 or higher (handled automatically when installing with Homebrew).

### End-User Installation

#### Homebrew (macOS — recommended)

```bash
brew tap chris-colinsky/forbin-mcp
brew install forbin-mcp
```

Prebuilt bottles are published for Apple Silicon (Sequoia, Tahoe). On other platforms, Homebrew falls back to building from source.

#### pipx (cross-platform)

[pipx](https://pipx.pypa.io/) installs Python applications in isolated environments:

```bash
pipx install forbin-mcp
```

#### pip

```bash
pip install forbin-mcp
```

After any of the above:

```bash
forbin --help
```

For upgrade, uninstall, and platform-specific notes (including Windows/WSL), see [docs/INSTALLATION.md](docs/INSTALLATION.md).

### Developer Installation

Clone and install in editable mode using [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/chris-colinsky/forbin-mcp.git
cd forbin-mcp
uv sync
```

Then run from source:

```bash
uv run forbin
```

For dev dependencies, testing, linting, and pre-commit hooks, see [CONTRIBUTING.md](CONTRIBUTING.md) and the [Development](#development) section below.

## Configuration

Forbin reads its settings from environment variables (or a `.env` file) and from `~/.forbin/config.json`. **Environment wins** when both are set. You have two ways to set up:

**Option 1 — First-run wizard (easiest):** just run `forbin`. If no config exists, you'll be prompted for the required values and they'll be saved to `~/.forbin/config.json`. Re-run anytime with `forbin --config`.

**Option 2 — `.env` file (best for CI/CD or scripted setups):**

```bash
cp .env.example .env
```

Edit `.env` with your MCP server details:

```env
# Required: Your MCP server endpoint
MCP_SERVER_URL=https://your-server.fly.dev/mcp

# Required: Authentication token
MCP_TOKEN=your-secret-token

# Optional: Health check endpoint. Forbin uses this to verify availability
# (like an LLM provider's /models) and to wake up suspended services.
# Leave unset (or remove) to skip the wake-up step entirely.
MCP_HEALTH_URL=https://your-server.fly.dev/health
```

For full details on configuration precedence, the JSON config file, and platform-specific examples, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Configuration Examples

**Local Development:**
```env
MCP_SERVER_URL=http://localhost:8000/mcp
MCP_TOKEN=test-token-123
```

**Fly.io Production:**
```env
MCP_SERVER_URL=https://my-app.fly.dev/mcp
MCP_HEALTH_URL=https://my-app.fly.dev/health
MCP_TOKEN=prod-token-xyz
```

## Usage

### Interactive Mode (Default)

Run the interactive tool browser:

```bash
forbin
```

This will:
1. Show the current configuration and let you confirm or edit it before connecting
2. Wake up your server (only if `MCP_HEALTH_URL` is configured — otherwise this step is skipped)
3. Connect to the MCP server
4. List all available tools
5. Enter the two-level interactive browser

**Tool List View:**
```
Available Tools

   1. generate_report - Generates a monthly summary report...
   2. get_user_stats - Retrieves user statistics for a given...

Commands:
  number - Select a tool
  v      - Toggle verbose logging (current: OFF)
  q      - Quit

Select tool: 1
```

**Tool View:**
```
─────────────────────────── generate_report ───────────────────────────

Options:
  d - View details
  r - Run tool
  b - Back to tool list
  q - Quit

Choose option:
```

From the tool view you can:
- **d** - View full schema with syntax-highlighted JSON
- **r** - Run the tool with interactive parameter input
- **b** - Go back to the tool list
- **q** - Quit

After running a tool, you stay in the tool view to run again with different parameters or navigate elsewhere.

For detailed usage instructions, see the [Usage Guide](docs/USAGE.md).

### Connectivity Test Mode

Test server connectivity without entering interactive mode:

```bash
forbin --test
```

This is useful for:
- Verifying server is reachable
- Checking health endpoint configuration
- Validating authentication tokens
- CI/CD health checks

### Config Wizard

Re-run the first-time setup wizard at any time:

```bash
forbin --config
```

### Help

```bash
forbin --help
```

## How It Works

Forbin is designed to handle the complexities of remote MCP servers, especially those on serverless or suspended platforms.

### Health Endpoint Strategy

When `MCP_HEALTH_URL` is configured, Forbin probes the health endpoint before opening the MCP connection. The probe does two things at once:

- **Availability check** — confirms the server is reachable, similar to hitting an LLM provider's `/models` endpoint to verify the API is up before issuing real requests.
- **Wake-up trigger** — on platforms that suspend or stop idle instances (Fly.io scale-to-zero, Railway, Render, etc.), the same request rouses the service.

If you don't configure a health URL, Forbin skips the probe and connects directly — the right choice for always-on servers and local development.

### Step Output Colors

During operation, Forbin shows its progress using colored step indicators:

- **[yellow]> Yellow[/yellow]**: **In Progress** - The current action is being performed.
- **[green]+ Green[/green]**: **Success** - The step completed successfully.
- **[dim]- Dim[/dim]**: **Skip** - Step was skipped (e.g., wake-up not needed).

### Interactive Toggle

At any time during the connection process or while in the tool menu, you can press **`v`** to toggle verbose logging on or off. This is useful for debugging connection issues in real-time without restarting the tool.

### Cancelling a Running Tool

While a tool call is in flight, press **`ESC`** to cancel it. You stay in the tool view instead of having to ctrl-C the whole CLI — handy for tools that hang or take longer than you're willing to wait.

### Terminal Compatibility

Forbin's single-key shortcuts (`v`, `c`, `ESC`-to-cancel, post-call clipboard prompt) rely on POSIX `termios`/`tty` to read keypresses without requiring Enter. That has a few practical implications:

- **macOS and Linux** — fully supported in any modern terminal (Terminal.app, iTerm2, Alacritty, GNOME Terminal, Konsole, etc.).
- **Native Windows** — `termios` isn't available, so the single-key shortcuts silently no-op. Numbered tool selection, prompts, and tool execution still work, but you won't be able to toggle verbose mid-run, cancel a hanging tool with `ESC`, or use the one-key clipboard prompt. **Run Forbin under [WSL](https://learn.microsoft.com/en-us/windows/wsl/install)** for the full experience.
- **Piped or non-TTY stdin** (e.g. `forbin < script.txt`, some CI runners) — the shortcuts and the post-call clipboard prompt are skipped automatically. `forbin --test` is the right mode for non-interactive contexts.
- **Linux clipboard copy** — the `c` shortcut after a tool call requires `xclip` or `xsel` to be installed (`pyperclip` uses them as backends). Without one, Forbin tells you it couldn't access the clipboard and continues.

### Detailed Documentation

- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — full health-URL strategy, timeout knobs, and troubleshooting tables.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — internal package layout, connection lifecycle, and error-handling plumbing.
- [docs/](docs/) — index of all long-form documentation.

## Development

### Project Structure

```
forbin/
 forbin/              # Package directory
   __init__.py
   __main__.py        # python -m forbin entry point
   cli.py             # Main CLI application
   client.py          # MCP connection + wake-up
   config.py          # Configuration + first-run wizard
   display.py         # Rich-based UI primitives
   tools.py           # Parameter parsing + tool calls
   utils.py           # FilteredStderr + key listeners
   verbose.py         # vlog helpers (gated on VERBOSE flag)
 pyproject.toml       # Python project configuration
 uv.lock              # Dependency lock file
 .env.example         # Example environment configuration
 .env                 # Your environment configuration (not committed)
 CLAUDE.md            # AI assistant guidance
 README.md            # This file
```

### Dependencies

- **fastmcp** - MCP client library for Python
- **httpx** - Async HTTP client for health checks
- **python-dotenv** - Environment variable management
- **pyperclip** - Clipboard copy for tool responses
- **rich** - Terminal UI rendering

### Running Tests

```bash
# Test connectivity only
python -m forbin --test

# Run interactive session with your test server
python -m forbin
```

## FastAPI/FastMCP Server Compatibility

This tool is designed to work with FastAPI servers using the FastMCP library. Your server should:

1. Expose an MCP endpoint (typically `/mcp`)
2. Implement bearer token authentication
3. Optionally expose a `/health` endpoint for wake-up detection
4. Follow the MCP protocol specification

**Example FastAPI/FastMCP server:**
```python
from fastapi import FastAPI
from fastmcp import FastMCP

app = FastAPI()
mcp = FastMCP("My Tools")

@mcp.tool()
def my_tool(param: str) -> str:
    """A sample tool"""
    return f"Result: {param}"

# Mount MCP at /mcp endpoint
app.include_router(mcp.get_router(), prefix="/mcp")

@app.get("/health")
def health():
    return {"status": "ok"}
```

## Troubleshooting

### "Failed to wake up server" or "Failed to list tools: TimeoutError"

- Verify your `MCP_HEALTH_URL` is correct
- Check if the health endpoint is accessible
- Try removing `MCP_HEALTH_URL` if your server doesn't suspend
- For `TimeoutError` during listing, check if your server is extremely slow or overloaded

### "Connection error (server not ready)"

- Increase the initialization wait time (edit `forbin/client.py`)
- Check your `MCP_SERVER_URL` is correct
- Verify your `MCP_TOKEN` is valid

### "Session termination failed: 400"

- This is a harmless error from the FastMCP library
- Already suppressed in the tool output
- Safe to ignore

## Development

For detailed development instructions, testing, and automation, see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

**Quick commands:**

```bash
make install-dev      # Install dev dependencies
make test             # Run tests
make check            # Run all checks (format + lint + test)
make help             # Show all available commands
```

**Testing:**

We have comprehensive test coverage with unit and integration tests:

```bash
make test             # Run all tests
make test-coverage    # Run with coverage report
make lint             # Check code quality
make format           # Format code
```

**Pre-commit hooks:**

Automatically run checks before each commit:

```bash
make pre-commit-install
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for complete details on testing, CI/CD, and contributing.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

**Quick start:**

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Install dev dependencies (`make install-dev`)
4. Make your changes and add tests
5. Run checks (`make check`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

All pull requests must:
- Pass all tests (`make test`)
- Pass linting (`make lint`)
- Maintain or improve code coverage
- Include appropriate documentation

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## Acknowledgments

- **Name inspiration**: [Colossus: The Forbin Project](https://en.wikipedia.org/wiki/Colossus:_The_Forbin_Project) (1970)
- Built with [FastMCP](https://github.com/jlowin/fastmcp) - FastAPI integration for MCP
- Developed for better MCP tool testing during agentic workflow development

## Links

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
