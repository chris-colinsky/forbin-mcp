# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.5] - 2026-04-28

### Added

- **Profiles + environments.** Forbin now stores connection details in `~/.forbin/profiles.json`. A profile is a named bundle of named environments (e.g. `staging/us-east`, `staging/eu-west`); each environment carries its own `MCP_SERVER_URL`, `MCP_HEALTH_URL`, and `MCP_TOKEN`. Multi-server users can switch contexts without editing `.env` files.
- **Profile/environment picker** at launch when more than one profile or environment exists. Single-profile users see no UX change.
- **`p` shortcut** in the config gate, the main tool list, and the tool view to switch profile or environment mid-session. Triggers a reconnect when the active selection changes.
- **CRUD for profiles and environments** inside the picker — create, rename, delete from the UI. Refusal logic prevents deleting the only profile or the only environment in a profile.
- **`--profile NAME --env NAME` flags** for scripted / CI use. The override applies for the lifetime of the process and does not persist as the new active selection. Validation lists available names on typo, and `--profile` without `--env` is required to disambiguate when the chosen profile has multiple environments.
- **Default values for optional tool parameters.** When a tool's input schema declares a `default` for an optional parameter, Forbin renders it under the description so the user knows what value the server will substitute if they skip the prompt.

### Changed

- **Configuration storage moved** from the flat `~/.forbin/config.json` to `~/.forbin/profiles.json` with a versioned schema. The first launch on v0.1.5 migrates legacy `config.json` into a `default/default` profile and renames the old file to `config.json.bak`. Migration also seeds a default profile from `.env` connection fields when no legacy file exists.
- **Environment-variable shadowing semantics.** `MCP_SERVER_URL`, `MCP_HEALTH_URL`, and `MCP_TOKEN` from `.env` or the shell are *no longer* used to override the active profile's connection fields — picking a profile means the profile's values are authoritative. Globals (`VERBOSE`, `MCP_TOOL_TIMEOUT`) keep their existing env-shadow precedence. The `(env)` tag in the editor only renders for globals now, and a one-time migration warning surfaces this when the change first applies.
- **`forbin --config`** opens the in-app editor at the active environment instead of re-running the wizard. Use the picker (`p`) to add fresh profiles; the wizard still runs automatically on a brand-new install.
- **Startup config panel** shows `Profile:` and `Environment:` rows above the connection details so the active selection is always visible.

### Fixed

- Malformed `profiles.json` is renamed to `profiles.json.malformed.<timestamp>.bak` and replaced with a fresh default doc instead of crashing the CLI. A stale `active` pointer (e.g. from a hand-edit) auto-recovers to the alphabetically-first profile and environment.

## [0.1.4] - 2026-04-28

### Security

- Pin nine transitive dependencies (`authlib`, `cryptography`, `pygments`, `python-multipart`, `requests`, `starlette`, `urllib3`, `filelock`, `virtualenv`) to clear 19 CVEs flagged by `pip-audit`. Inline comments call out which CVE each pin addresses.

### Added

- Configurable tool-call timeout via `MCP_TOOL_TIMEOUT` (env var or `~/.forbin/config.json`). Default unchanged at 600 seconds; long-running agentic / batch tools can extend without code changes.
- `v` (verbose toggle) and `c` (change configuration) shortcuts now appear in the Tool View and the startup config gate menus, with the current verbose state shown inline. The handlers existed already — only the discoverability was missing.

### Changed

- Project rename: `chris-colinsky/Forbin` → `chris-colinsky/forbin-mcp`, Homebrew tap `homebrew-forbin` → `homebrew-forbin-mcp`, formula `forbin.rb` → `forbin-mcp.rb`. Install command is now `brew install forbin-mcp` (was `brew install forbin`). The on-disk binary is still `forbin`.
- README CI badge points at `main` instead of the stale `release/v1.0.0` branch reference.

### Fixed

- `forbin --test` now exits with status `1` on connection failure or user-cancellation at the config gate. Previously CI smoke tests passed silently against dead servers.
- `MCPSession`, `reconnect`, and several utility functions now have proper type annotations and use `contextlib.suppress` for cleanup paths instead of bare `except: pass`. PyCharm and mypy are clean across the package.

## [0.1.3] - 2026-04-27

### Added

- Interactive config-confirmation gate at CLI startup with a panel showing every setting (server URL, health URL, masked token, verbose state).
- Clipboard copy for tool responses — press `c` after a tool call to copy the rendered output.
- Homebrew bottle build pipeline. Releases now publish prebuilt bottles for macOS Tahoe and Sequoia; `brew install` pours a binary instead of compiling Rust extensions.
- First-run setup wizard plus `forbin --config` to re-run it. Configuration persists to `~/.forbin/config.json`.
- Health-endpoint strategy framing in docs (availability check + wake-up trigger), terminal-compatibility notes for Windows / non-TTY / Linux clipboard, GitHub Actions CI recipe for `forbin --test`, expanded troubleshooting tables in `docs/CONFIGURATION.md`.

### Changed

- Project layout split from a single `forbin.py` into a proper package (`cli`, `client`, `config`, `display`, `tools`, `utils`, `verbose`).
- Docs reorganized: `DOCS.md` → `docs/ARCHITECTURE.md`, new `docs/README.md` index, all long-form docs now live under `docs/`.
- Menu styling unified across the CLI; verbose state shown inline in command lists.
- Test suite now isolates from local user state; `is_first_run` is stubbed so CI runners without `~/.forbin/config.json` don't trip the interactive wizard.
- Version display reads from `pyproject.toml` via `importlib.metadata` (with a `test_version.py` guard against drift).

### Removed

- Unused `tenacity` dependency.
- Dead code across the `forbin` package.

### Fixed

- GitHub Actions versions bumped to Node 24-compatible majors.

## [0.1.2] - 2026-02-11

### Added

- Verbose logging mode and a configuration-management subsystem (env vars, `.env` loading, persisted JSON config).
- Automated Homebrew formula updates on release — the `release.yml` workflow now pushes the new formula to the tap repo after PyPI publishes.

### Changed

- Release workflow tag pattern restricted to strict semver (`v[0-9]*.[0-9]*.[0-9]*`).

### Fixed

- `_wait_for_escape` no longer hangs on stdin when not running in a TTY (e.g. piped input, pytest capture).

## [0.1.1] - 2026-02-05

### Fixed

- Logo URL on PyPI now resolves to the GitHub-hosted image instead of a relative path.

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

[0.1.4]: https://github.com/chris-colinsky/forbin-mcp/releases/tag/v0.1.4
[0.1.3]: https://github.com/chris-colinsky/forbin-mcp/releases/tag/v0.1.3
[0.1.2]: https://github.com/chris-colinsky/forbin-mcp/releases/tag/v0.1.2
[0.1.1]: https://github.com/chris-colinsky/forbin-mcp/releases/tag/v0.1.1
[0.1.0]: https://github.com/chris-colinsky/forbin-mcp/releases/tag/v0.1.0
