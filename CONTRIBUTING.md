# Contributing to Forbin

Thank you for your interest in contributing to Forbin! This document provides guidelines and information for contributors.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/yourusername/forbin.git
   cd forbin
   ```
3. **Install dependencies**:
   ```bash
   uv sync
   # or
   pip install -r requirements.txt
   ```
4. **Set up your environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your test MCP server details
   ```

## Development Workflow

1. **Create a branch** for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style guidelines below

3. **Test your changes**:
   ```bash
   # Test connectivity
   uv run forbin --test

   # Test interactive mode
   uv run forbin
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add feature: description of your changes"
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request** on GitHub

## Code Style Guidelines

- **Python version**: Target Python 3.13+
- **Line length**: 100 characters (configured in `pyproject.toml`)
- **Formatting**: We use Black for code formatting
  ```bash
  make format
  ```
- **Linting**: We use Ruff for linting
  ```bash
  make lint
  ```
- **Type hints**: Use type hints where appropriate
- **Docstrings**: Use docstrings for functions, following Google style

## What to Contribute

### Good First Issues

- Improve error messages
- Add support for new parameter types
- Enhance display formatting
- Update documentation

### Feature Ideas

- Support for environment variable expansion in parameters
- Save/load parameter presets for frequent tool calls
- Export tool call results to file
- Batch tool calling
- Non-interactive mode for scripting

### Bug Reports

When reporting bugs, please include:
- Your Python version (`python --version`)
- Your operating system
- Steps to reproduce the issue
- Expected vs actual behavior
- Relevant error messages

## Testing

We have comprehensive automated testing with pytest:

**Run all tests:**
```bash
make test
```

**Run specific test types:**
```bash
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-coverage      # With coverage report
```

**Writing tests:**
- Add unit tests to `tests/test_main.py`
- Add integration tests to `tests/test_integration.py`
- Use fixtures from `tests/conftest.py`
- Mark async tests with `@pytest.mark.asyncio`

**Example test:**
```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_new_feature(mock_mcp_client):
    """Test description."""
    result = await your_function()
    assert result == expected
```

**Manual testing:**
1. Set up a test MCP server (local or remote)
2. Test connectivity with `make run-test`
3. Test interactive mode with `make run`
4. Verify new features work as expected

**Coverage requirements:**
- New code should maintain or improve coverage
- Check coverage with `make test-coverage`
- View HTML report: `open htmlcov/index.html`

## Documentation

When adding features:
- Update `README.md` with usage examples
- Update `CLAUDE.md` with implementation details
- Add comments for complex logic
- Update `--help` text if adding CLI arguments

## Pull Request Guidelines

- **Keep PRs focused**: One feature or bugfix per PR
- **Write clear commit messages**: Explain what and why, not just how
- **Update documentation**: Keep docs in sync with code changes
- **Test thoroughly**: Verify your changes don't break existing functionality
- **Respond to feedback**: Be open to suggestions and iteration

## Questions or Need Help?

- Open an issue on GitHub
- Check existing issues and PRs for similar topics
- Review the `CLAUDE.md` file for implementation guidance

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing to Forbin!
