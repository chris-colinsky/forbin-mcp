"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import Mock, AsyncMock


@pytest.fixture(autouse=True)
def _skip_first_run_wizard(monkeypatch):
    """Prevent any test that exercises async_main / test_connectivity from
    triggering the interactive first-run wizard.

    The wizard fires when ~/.forbin/config.json doesn't exist, which is
    typical on CI runners but rare on dev boxes (where the file usually
    exists from running the tool). Without this stub, the wizard calls
    `input()` and pytest's stdin capture raises OSError — making the test
    suite green locally and red on CI."""
    monkeypatch.setattr("forbin.cli.is_first_run", lambda: False)


@pytest.fixture(autouse=True)
def _stub_launch_setup(monkeypatch):
    """Stub the v0.1.5 launch sequence (migration / wizard / picker) so
    tests that patch ``forbin.config.MCP_*`` module globals keep working.

    Without this, ``_launch_setup`` calls ``reload_config()``, which
    re-reads profiles.json and overwrites the patches. Tests that
    explicitly want to exercise the launch sequence can override this
    fixture by patching ``forbin.cli._launch_setup`` directly inside the
    test, or by writing a profiles.json into an isolated ``FORBIN_DIR``."""
    monkeypatch.setattr("forbin.cli._launch_setup", lambda: True)


@pytest.fixture
def mock_tool():
    """Create a mock MCP tool."""
    tool = Mock()
    tool.name = "test_tool"
    tool.description = "A test tool for unit testing"
    tool.inputSchema = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "A string parameter"},
            "param2": {"type": "integer", "description": "An integer parameter"},
            "optional_param": {"type": "boolean", "description": "An optional boolean"},
        },
        "required": ["param1", "param2"],
    }
    return tool


@pytest.fixture
def mock_tool_no_params():
    """Create a mock tool with no parameters."""
    tool = Mock()
    tool.name = "simple_tool"
    tool.description = "A simple tool with no parameters"
    tool.inputSchema = None
    return tool


@pytest.fixture
def mock_tool_list(mock_tool, mock_tool_no_params):
    """Create a list of mock tools."""
    return [mock_tool, mock_tool_no_params]


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP client."""
    client = AsyncMock()
    client.initialize_result = {"capabilities": {}}
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    # Mock list_tools response
    mock_tool1 = Mock()
    mock_tool1.name = "test_tool"
    mock_tool1.description = "Test tool"
    mock_tool1.inputSchema = {
        "type": "object",
        "properties": {"param": {"type": "string", "description": "A parameter"}},
        "required": ["param"],
    }

    client.list_tools = AsyncMock(return_value=[mock_tool1])

    # Mock call_tool response
    mock_result = Mock()
    mock_content = Mock()
    mock_content.text = "Tool executed successfully"
    mock_result.content = [mock_content]
    client.call_tool = AsyncMock(return_value=mock_result)

    return client


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx client for health checks."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    client.get = AsyncMock(return_value=mock_response)

    return client


@pytest.fixture
def env_vars(monkeypatch):
    """Set up environment variables for testing."""
    monkeypatch.setenv("MCP_SERVER_URL", "http://test-server.local/mcp")
    monkeypatch.setenv("MCP_TOKEN", "test-token-123")
    monkeypatch.setenv("MCP_HEALTH_URL", "http://test-server.local/health")


@pytest.fixture
def env_vars_no_health(monkeypatch):
    """Set up environment variables without health URL."""
    monkeypatch.setenv("MCP_SERVER_URL", "http://test-server.local/mcp")
    monkeypatch.setenv("MCP_TOKEN", "test-token-123")
    monkeypatch.delenv("MCP_HEALTH_URL", raising=False)
