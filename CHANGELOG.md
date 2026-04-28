# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-05

### Added

- **Interactive CLI** - Two-level tool browser for exploring and testing MCP tools
- **Automatic server wake-up** - Health check polling for suspended services (Fly.io, etc.)
- **Cold-start resilient connections** - Retry logic with extended timeouts for slow-starting servers
- **Tool schema inspection** - View detailed tool schemas with syntax-highlighted JSON
- **Interactive parameter input** - Type-safe parsing for strings, booleans, numbers, and JSON objects
- **Connectivity test mode** - `forbin --test` for verifying server connectivity
- **Verbose logging toggle** - Press `v` at any time to toggle debug output
- **Modular package structure** - Organized into cli, client, tools, display, and utils modules
- **Comprehensive documentation** - README, CLAUDE.md, docs/ARCHITECTURE.md, docs/USAGE.md, docs/DEVELOPMENT.md, CONTRIBUTING.md
- **CI/CD pipeline** - GitHub Actions workflow for testing and linting
- **Pre-commit hooks** - Automated code quality checks
- **Makefile automation** - Common development tasks (`make test`, `make check`, etc.)

### Technical Details

- Python 3.13+ required
- Built with fastmcp, httpx, python-dotenv, pyperclip, and rich
- MIT licensed

[0.1.0]: https://github.com/chris-colinsky/forbin-mcp/releases/tag/v0.1.0
