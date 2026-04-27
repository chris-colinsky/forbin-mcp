# Usage Guide

This guide covers how to use Forbin to test MCP servers and their tools.

## Quick Start

```bash
# Test connectivity to your MCP server
forbin --test

# Start interactive tool browser
forbin

# Re-run the first-time setup wizard
forbin --config

# Show help
forbin --help
```

## Modes

### Interactive Mode (Default)

Run without arguments to start the interactive tool browser:

```bash
forbin
```

The tool will:
1. Show the current configuration and let you confirm or edit before connecting
2. Wake up your server (if `MCP_HEALTH_URL` is configured — otherwise this step is skipped)
3. Connect to the MCP server
4. List all available tools
5. Enter the interactive browser

### Connectivity Test Mode

Test server connectivity without entering interactive mode:

```bash
forbin --test
```

Useful for:
- Verifying server is reachable
- Checking health endpoint configuration
- Validating authentication tokens
- CI/CD health checks

`--test` exits with status `0` on success and a non-zero status on failure (failed wake-up, failed connection, or user-cancellation at the config gate), so it's safe to use as a CI step. See [Using `--test` in CI/CD](#using---test-in-cicd) below for a concrete example.

### Config Wizard Mode

Re-run the first-time setup wizard to (re)write `~/.forbin/config.json`:

```bash
forbin --config
```

## Interactive Navigation

Forbin uses a two-level navigation system for a cleaner experience.

### Tool List View

After connecting, you'll see a compact list of available tools:

```
Available Tools

   1. generate_report - Generate a monthly summary report...
   2. get_user_stats - Retrieves user statistics for a given...

Commands:
  number - Select a tool
  v      - Toggle verbose logging (current: OFF)
  q      - Quit

Select tool:
```

Enter a number to select a tool, `v` to toggle verbose logging, or `q` to quit.

### Tool View

After selecting a tool, you enter the tool view with these options:

```
─────────────────────────── generate_report ───────────────────────────

Options:
  d - View details
  r - Run tool
  b - Back to tool list
  q - Quit

Choose option:
```

**Options:**
- **d** - View the full tool schema with syntax-highlighted JSON
- **r** - Run the tool (prompts for parameters)
- **b** - Go back to the tool list
- **q** - Quit the application

### Viewing Tool Details

Press `d` to see the complete tool schema, including:
- Description
- Response examples (syntax-highlighted JSON)
- Output schemas
- Input parameters

Example output:
```
╭──────────────────────── generate_report - Details ────────────────────────╮
│ Generate Report                                                           │
│                                                                           │
│ ### Responses:                                                            │
│                                                                           │
│ **200**: Successful Response                                              │
│                                                                           │
│ {                                                                         │
│   "success": true,                                                        │
│   "message": "Report generated successfully",                             │
│   "report_month": "2025-06"                                               │
│ }                                                                         │
│                                                                           │
│ Input Schema:                                                             │
│                                                                           │
│ {                                                                         │
│   "type": "object",                                                       │
│   "properties": {                                                         │
│     "report_month": {                                                     │
│       "type": "string",                                                   │
│       "description": "Report month in YYYY-MM format"                     │
│     }                                                                     │
│   },                                                                      │
│   "required": ["report_month"]                                            │
│ }                                                                         │
╰───────────────────────────────────────────────────────────────────────────╯
```

### Running a Tool

Press `r` to run the tool. You'll be prompted for each parameter:

```
──────────────────────────── ENTER PARAMETERS ─────────────────────────────
Enter parameter values (press Enter to skip optional parameters)

report_month (string) (required)
  Report month in YYYY-MM format (e.g., '2025-06')
  -> 2025-06

use_preview_db (boolean) (optional)
  Whether to use preview database instead of production
  -> false
```

After entering parameters, the tool executes and displays the result:

```
───────────────────────────── CALLING TOOL ────────────────────────────────
Tool: generate_report

╭─ Parameters ─────────────────────────────────────────────────────────────╮
│ {                                                                        │
│   "report_month": "2025-06",                                             │
│   "use_preview_db": false                                                │
│ }                                                                        │
╰──────────────────────────────────────────────────────────────────────────╯

Executing...

Tool execution completed!

────────────────────────────── RESULT ─────────────────────────────────────

╭─ Response ───────────────────────────────────────────────────────────────╮
│ {                                                                        │
│   "success": true,                                                       │
│   "message": "Monthly report generated successfully",                    │
│   "report_month": "2025-06",                                             │
│   "generated_at": "2025-02-04T15:30:00Z"                                 │
│ }                                                                        │
╰──────────────────────────────────────────────────────────────────────────╯
```

After the result is displayed, you return to the tool view where you can:
- Run the tool again with different parameters
- View details
- Go back to the tool list
- Quit

### Cancelling a Running Tool

While a tool call is in flight, press **`ESC`** to cancel it. Useful when a tool is hung or taking longer than you're willing to wait — you stay in the tool view instead of having to ctrl-C the whole CLI.

### Copying a Tool Response

Immediately after a tool call completes, Forbin offers a single-key prompt:

```
Press c to copy response to clipboard, any other key to continue...
```

Press **`c`** to copy the rendered response (formatted JSON when applicable) to the system clipboard. On Linux this requires `xclip` or `xsel` to be installed.

## Verbose Logging

Toggle verbose logging at any time by pressing `v`:
- Shows detailed connection information
- Displays retry attempts and errors
- Useful for debugging connection issues

```
Verbose logging toggled ON
```

## Parameter Types

Forbin automatically parses parameter values based on their schema type:

| Type | Example Input | Parsed Value |
|------|--------------|--------------|
| string | `hello world` | `"hello world"` |
| boolean | `true`, `yes`, `1` | `true` |
| boolean | `false`, `no`, `0` | `false` |
| integer | `42` | `42` |
| number | `3.14` | `3.14` |
| object | `{"key": "value"}` | `{"key": "value"}` |
| array | `[1, 2, 3]` | `[1, 2, 3]` |

For objects and arrays, enter valid JSON.

## Step Indicators

During startup, Forbin shows progress with colored indicators:

- **> Yellow** - In progress
- **+ Green** - Completed successfully
- **- Dim** - Skipped

Example:
```
> Step 1/2: WAKING UP SERVER
+ Step 1/2: WAKING UP SERVER

> Step 2/2: CONNECTING AND LISTING TOOLS
+ Step 2/2: CONNECTING AND LISTING TOOLS

Test complete! Server has 3 tools available
```

## Keyboard Shortcuts Summary

| Key | Context | Action |
|-----|---------|--------|
| `1-9` | Tool List | Select tool by number |
| `v` | Any | Toggle verbose logging |
| `c` | Tool List / Tool View | Change configuration |
| `c` | Post-tool-call prompt | Copy last response to clipboard |
| `q` | Any | Quit application |
| `d` | Tool View | View tool details |
| `r` | Tool View | Run tool |
| `b` | Tool View | Back to tool list |
| `ESC` | During tool execution | Cancel the running tool call |

## Command Line Options

```
forbin              Run interactive session
forbin --test       Test connectivity only
forbin --config     Re-run the first-time setup wizard
forbin --help       Show help message
```

## Using `--test` in CI/CD

`forbin --test` is designed for non-interactive contexts: it loads configuration from environment variables, runs the same wake-up + connect + list-tools sequence as the interactive mode, and exits with status `0` on success or non-zero on any failure.

### GitHub Actions example

```yaml
# .github/workflows/mcp-smoke.yml
name: MCP smoke test

on:
  schedule:
    - cron: "0 */6 * * *"   # every 6 hours
  workflow_dispatch:

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install Forbin
        run: pip install forbin-mcp

      - name: Probe MCP server
        env:
          MCP_SERVER_URL: ${{ secrets.MCP_SERVER_URL }}
          MCP_TOKEN: ${{ secrets.MCP_TOKEN }}
          MCP_HEALTH_URL: ${{ secrets.MCP_HEALTH_URL }}
        run: forbin --test
```

### Notes for CI

- **No TTY:** CI runners don't have an interactive terminal. The `v` keypress listener and post-call clipboard prompt are skipped automatically — `forbin --test` is the only mode that's appropriate here.
- **Verbose output:** set `VERBOSE=true` in the step's `env` to get full traces of every retry. Useful when debugging a flaky workflow.
- **Health URL is your friend:** if your MCP server is on a suspend-on-idle platform (Fly.io scale-to-zero, etc.), set `MCP_HEALTH_URL`. The cron schedule above will both wake the server and verify it's alive.
- **Secrets handling:** never commit `MCP_TOKEN`. Use the platform's secret store (`secrets.*` in GitHub Actions, `${VARIABLE}` in GitLab CI, etc.).
- **Timeouts:** the default ceiling for a full run is roughly 30s (health probe) + 5s (init pause) + 90s (3 connect retries × 30s init timeout) ≈ 2 minutes. Bump your CI step timeout above that.

## Terminal Compatibility

The single-key shortcuts in the table above (`v`, `c`, `ESC`, and the post-call clipboard prompt) rely on POSIX `termios`/`tty` to read keypresses without requiring Enter. Behavior by environment:

| Environment | Status | Notes |
|-------------|--------|-------|
| macOS, Linux (TTY) | Fully supported | All shortcuts work in any modern terminal |
| Native Windows (cmd / PowerShell) | Degraded | Numbered selection and prompts still work; `v`, `c`, `ESC`, and the clipboard prompt silently no-op. **Use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) for the full experience.** |
| Piped / non-TTY stdin | Degraded | Background `v` listener and post-call clipboard prompt are skipped. Use `forbin --test` for non-interactive contexts. |

### Linux Clipboard

The `c` shortcut after a tool call uses `pyperclip`, which requires either `xclip` or `xsel` to be installed:

```bash
# Debian/Ubuntu
sudo apt install xclip      # or: sudo apt install xsel

# Fedora
sudo dnf install xclip
```

Without one of these, Forbin will print a "could not access clipboard" message and continue — the rest of the workflow is unaffected.

## Next Steps

- See [Configuration Guide](CONFIGURATION.md) for setting up your MCP server connection
- See [Installation Guide](INSTALLATION.md) for installation options
- See [Development Guide](DEVELOPMENT.md) for contributing
