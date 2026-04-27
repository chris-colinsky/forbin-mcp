# Forbin Documentation

This folder contains the long-form documentation for Forbin. For a quick start, see the [project README](../README.md).

## For Users

- **[INSTALLATION.md](INSTALLATION.md)** — install via Homebrew, pipx, pip, or uv; Windows/WSL notes.
- **[CONFIGURATION.md](CONFIGURATION.md)** — environment variables and `~/.forbin/config.json`, the health-URL strategy (availability check + wake-up), timeout knobs, and a troubleshooting reference.
- **[USAGE.md](USAGE.md)** — interactive mode, tool browser, keyboard shortcuts, terminal compatibility, and a GitHub Actions CI recipe for `forbin --test`.

## For Contributors

- **[DEVELOPMENT.md](DEVELOPMENT.md)** — local setup, running tests, linting, pre-commit hooks, CI workflow.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — package layout, MCPSession lifecycle, `FilteredStderr`, the verbose-gated logging plumbing, and configuration resolution.
- **[RELEASING.md](RELEASING.md)** — version bump → tag → automated PyPI publish + two-stage Homebrew bottle build.

## Other Docs in the Repo

- [../README.md](../README.md) — project overview, install, quick start.
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — contribution guidelines.
- [../CHANGELOG.md](../CHANGELOG.md) — release history.
- [../CLAUDE.md](../CLAUDE.md) — guidance for AI agents working in this repo.
