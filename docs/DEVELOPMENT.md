# Development Guide

This guide covers testing, automation, and contributing to the Forbin.

## Quick Start for Developers

```bash
# Complete setup with one command
make install-all

# This will:
# 1. Install all dependencies
# 2. Create .env from .env.example
# 3. Set up pre-commit hooks
```

Or run steps individually:

```bash
make install-dev        # Install dev dependencies
make setup-env          # Create .env from example
make pre-commit-install # Set up git hooks
```

## Project Structure

```
forbin/
├── forbin/                      # Main package
│   ├── __init__.py             # Package exports + __version__
│   ├── __main__.py             # `python -m forbin` entry point
│   ├── cli.py                  # Argument dispatch + interactive session
│   ├── client.py               # MCP connection + wake-up
│   ├── config.py               # Config load/save + first-run wizard
│   ├── display.py              # Rich-based UI primitives
│   ├── tools.py                # Parameter parsing + tool calls
│   ├── utils.py                # FilteredStderr + key listeners
│   └── verbose.py              # vlog / vlog_json / vlog_timing
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── test_main.py            # Unit tests
│   ├── test_integration.py     # Integration tests
│   └── test_version.py         # Version-drift guard
├── docs/                        # Long-form documentation
├── .github/
│   └── workflows/
│       └── ci.yml              # CI/CD pipeline
├── pyproject.toml              # Python project configuration
├── Makefile                    # Development commands
├── .pre-commit-config.yaml     # Pre-commit hooks
├── .env.example                # Example environment config
├── CLAUDE.md                   # AI assistant guidance
├── CONTRIBUTING.md             # Contribution guidelines
├── DOCS.md                     # Technical deep-dive
└── README.md                   # Main documentation
```

## Testing

### Test Framework

We use **pytest** with comprehensive unit and integration tests:

- **Unit tests** (`test_main.py`) - Test individual functions in isolation
- **Integration tests** (`test_integration.py`) - Test complete workflows
- **Version guard** (`test_version.py`) - Fails CI if `__version__` drifts from `pyproject.toml`
- **Fixtures** (`conftest.py`) - Reusable test components

### Running Tests

```bash
# Run all tests
make test

# Run with coverage report (opens HTML report)
make test-coverage

# Run only unit tests
make test-unit

# Run only integration tests
make test-integration

# Run tests in watch mode (auto-rerun on changes)
make test-watch

# Quick test without coverage
make quick-test
```

### Writing Tests

Tests use `pytest` with async support:

```python
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.mark.asyncio
async def test_something(mock_mcp_client):
    """Test description."""
    result = await some_async_function()
    assert result == expected_value
```

**Available fixtures** (see `conftest.py`):
- `mock_tool` - Mock MCP tool with parameters
- `mock_tool_no_params` - Mock tool without parameters
- `mock_mcp_client` - Mock MCP client
- `mock_httpx_client` - Mock HTTP client
- `env_vars` - Set up environment variables

### Test Coverage

We aim for >80% test coverage:

```bash
# Generate coverage report
make test-coverage

# View HTML report
open htmlcov/index.html
```

Coverage is automatically uploaded to Codecov on CI runs.

## Code Quality

### Formatting with Black

Black is our code formatter (100 character line length):

```bash
# Format all code
make format

# Check formatting without changes
make format-check
```

**Configuration** (in `pyproject.toml`):
```toml
[tool.black]
line-length = 100
target-version = ["py313"]
```

### Linting with Ruff

Ruff is a fast Python linter:

```bash
# Run linter
make lint

# Ruff will check for:
# - Code style issues
# - Common bugs
# - Performance issues
# - Security problems
```

### All Checks

Run all quality checks at once:

```bash
make check  # Runs: format-check + lint + test
```

## Makefile Commands

The `Makefile` provides shortcuts for common tasks:

### Setup Commands

```bash
make install          # Install production dependencies
make install-dev      # Install dev dependencies
make install-all      # Complete setup (deps + env + hooks)
make setup-env        # Create .env from .env.example
```

### Testing Commands

```bash
make test             # Run all tests
make test-unit        # Unit tests only
make test-integration # Integration tests only
make test-coverage    # Tests with coverage report
make test-watch       # Auto-rerun tests on changes
make quick-test       # Fast test without coverage
```

### Code Quality Commands

```bash
make format           # Format code with Black
make format-check     # Check formatting
make lint             # Run Ruff linter
make check            # All checks (format + lint + test)
make validate         # Validate Python syntax
```

### Running Commands

```bash
make run              # Run interactive mode
make run-test         # Run connectivity test
make run-help         # Show help
```

### Utilities

```bash
make clean            # Remove generated files
make pre-commit-install   # Install git hooks
make pre-commit-run       # Run hooks manually
make ci               # Run CI checks locally
make help             # Show all commands
```

## Pre-commit Hooks

Pre-commit hooks automatically check your code before each commit.

### Installation

```bash
make pre-commit-install
```

### What Gets Checked

The hooks will:
1. [x] Trim trailing whitespace
2. [x] Fix end of file newlines
3. [x] Validate YAML, JSON, TOML syntax
4. [x] Check for large files
5. [x] Detect private keys
6. [x] Validate Python syntax
7. [x] Format code with Black
8. [x] Lint with Ruff
9. [x] Run full test suite

### Manual Execution

```bash
# Run hooks on all files
make pre-commit-run

# Skip hooks for a specific commit (not recommended)
git commit --no-verify
```

### Configuration

See `.pre-commit-config.yaml` for hook configuration.

## Continuous Integration (CI)

### GitHub Actions Workflows

#### CI Workflow (`.github/workflows/ci.yml`)

Runs on every push and pull request:

- **Test Job** - Runs tests on Python 3.13
- **Lint Job** - Checks formatting and linting
- **Validate Job** - Validates project structure
- **Security Job** - Runs security scans
- **Build Job** - Builds the package

### Running CI Locally

Test what CI will do before pushing:

```bash
make ci  # Runs: lint + format-check + test
```

### CI Status

Check CI status:
- GitHub Actions tab in your repository
- Badge in README (add after setting up)

## Making Changes

### Development Workflow

1. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make your changes** and test:
   ```bash
   make test
   ```

3. **Check code quality**:
   ```bash
   make check
   ```

4. **Commit** (hooks will run automatically):
   ```bash
   git add .
   git commit -m "Add feature: description"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature
   ```

### Tips

- Run `make check` before committing to catch issues early
- Use `make test-watch` during development for instant feedback
- Check coverage with `make test-coverage` for new code
- Format code with `make format` before committing

## Debugging Tests

### Run Specific Tests

```bash
# Specific test file
pytest tests/test_main.py -v

# Specific test class
pytest tests/test_main.py::TestParameterParsing -v

# Specific test function
pytest tests/test_main.py::TestParameterParsing::test_parse_string -v

# Tests matching a pattern
pytest -k "test_parse" -v
```

### Verbose Output

```bash
# Show print statements
pytest tests/ -v -s

# Show locals on failures
pytest tests/ -v -l

# Stop on first failure
pytest tests/ -x

# Drop into debugger on failure
pytest tests/ --pdb
```

### Common Issues

**Tests hang:**
- Check for missing `@pytest.mark.asyncio` on async tests
- Verify mocks are properly configured

**Import errors:**
- Make sure you're in the project root
- Check that dependencies are installed: `make install-dev`

**Coverage not generated:**
- Install pytest-cov: `uv pip install pytest-cov`
- Use `make test-coverage` instead of plain `pytest`

## Release Process

Releases are automated. See [RELEASING.md](RELEASING.md) for the full flow — bump version in `pyproject.toml`, commit, push a `v*.*.*` tag, and the release workflow handles PyPI publishing, GitHub Release creation, and Homebrew tap updates (including the two-stage bottle build).

## Getting Help

- Check [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines
- Review existing tests in `tests/` for examples
- Open an issue on GitHub for questions
- Check [CLAUDE.md](CLAUDE.md) for implementation details

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Black documentation](https://black.readthedocs.io/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [pre-commit documentation](https://pre-commit.com/)
- [GitHub Actions documentation](https://docs.github.com/en/actions)
