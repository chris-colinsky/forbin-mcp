# Installation Guide

This guide covers all methods for installing Forbin.

**Requirements:** Python 3.13 or higher

> **Note:** Forbin's distribution name on PyPI is `forbin-mcp`, but the import name and CLI command are both `forbin`. Use `forbin-mcp` everywhere you'd write a package name (`pip install`, `pipx install`, `uv tool install`); use `forbin` to run the tool.

## Homebrew (macOS/Linux - Recommended)

The easiest way to install Forbin on macOS or Linux:

```bash
# Add the tap
brew tap chris-colinsky/forbin-mcp

# Install
brew install forbin-mcp

# Verify installation
forbin --help
```

### Upgrading

```bash
brew upgrade forbin-mcp
```

### Uninstalling

```bash
brew uninstall forbin-mcp
```

## pipx (All Platforms - Recommended)

[pipx](https://pipx.pypa.io/) installs Python applications in isolated environments, preventing dependency conflicts:

```bash
# Install pipx if you don't have it
brew install pipx       # macOS/Linux
# or: pip install pipx  # Any platform

# Install forbin (PyPI distribution name is `forbin-mcp`)
pipx install forbin-mcp

# Verify installation
forbin --help
```

### Upgrading

```bash
pipx upgrade forbin-mcp
```

### Uninstalling

```bash
pipx uninstall forbin-mcp
```

## pip (All Platforms)

Standard Python package installation:

```bash
# Install (PyPI distribution name is `forbin-mcp`)
pip install forbin-mcp

# Verify installation
forbin --help
```

### Upgrading

```bash
pip install --upgrade forbin-mcp
```

### Uninstalling

```bash
pip uninstall forbin-mcp
```

## uv (For Developers)

Using the modern [uv](https://github.com/astral-sh/uv) package manager:

```bash
# Install globally
uv tool install forbin-mcp

# Or run without installing (ephemeral)
uvx --from forbin-mcp forbin

# Verify installation
forbin --help
```

### Upgrading

```bash
uv tool upgrade forbin-mcp
```

### Uninstalling

```bash
uv tool uninstall forbin-mcp
```

## From Source (Development)

For contributing or development:

```bash
# Clone the repository
git clone https://github.com/chris-colinsky/forbin-mcp.git
cd forbin-mcp

# Install dependencies
uv sync

# Run from source
uv run forbin

# Or activate venv and run directly
source .venv/bin/activate
forbin
```

See [Development Guide](../CONTRIBUTING.md) for more details on contributing.

## Windows Users

Forbin runs on Windows via [WSL (Windows Subsystem for Linux)](https://learn.microsoft.com/en-us/windows/wsl/install):

1. Install WSL: `wsl --install`
2. Open your Linux distribution
3. Follow the pip or pipx installation instructions above

> **Why WSL?** Forbin's single-key shortcuts (`v` to toggle verbose, `c` for config/clipboard, `ESC` to cancel a running tool) depend on POSIX `termios`/`tty`, which isn't available on native Windows. The CLI itself will install and run on native Windows, but those shortcuts silently no-op there. See [Terminal Compatibility](USAGE.md#terminal-compatibility) for details.

## Verification

After installation, verify Forbin is working:

```bash
forbin --help
```

You should see the help output with available options.

## Configuration

Forbin requires a `.env` file for MCP server configuration. After installation:

1. Create your configuration file:
   ```bash
   # If you have .env.example from the repo
   cp .env.example .env

   # Or create manually
   touch .env
   ```

2. Edit `.env` with your MCP server details:
   ```bash
   MCP_SERVER_URL=https://your-server.example.com/mcp
   MCP_TOKEN=your-bearer-token
   MCP_HEALTH_URL=https://your-server.example.com/health  # Optional
   ```

## Uninstalling Completely

To completely remove Forbin:

```bash
# Uninstall (use your installation method)
pipx uninstall forbin-mcp   # or pip, brew, uv tool uninstall, etc.

# Remove configuration (if created)
rm .env
rm -rf ~/.forbin    # persisted JSON config from the first-run wizard
```

## Next Steps

After installation:

- Run `forbin --test` to test connectivity to your MCP server
- Run `forbin` to start the interactive tool browser
- See the [README](../README.md) for usage details
