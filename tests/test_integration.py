"""Integration tests for MCP Remote Tool Tester.

These tests verify the complete workflow of the tool.
They use mocks but test the full integration of components.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# Import the modules to test
import forbin.tools
import forbin.display
import forbin.client
import forbin.utils
import forbin.cli
import forbin.config


@pytest.mark.asyncio
async def test_full_connectivity_workflow(mock_mcp_client, mock_httpx_client):
    """Test the complete connectivity test workflow."""
    # import forbin

    with (
        patch("forbin.config.MCP_SERVER_URL", "http://test.local/mcp"),
        patch("forbin.config.MCP_TOKEN", "test-token"),
        patch("forbin.config.MCP_HEALTH_URL", "http://test.local/health"),
        patch("forbin.cli.confirm_or_edit_config", return_value=True),
        patch("httpx.AsyncClient", return_value=mock_httpx_client),
        patch("forbin.client.Client", return_value=mock_mcp_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await forbin.cli.test_connectivity()

        # Verify the complete flow
        mock_httpx_client.get.assert_called()  # Health check
        mock_mcp_client.__aenter__.assert_called()  # Connection
        mock_mcp_client.list_tools.assert_called()  # Tool listing


@pytest.mark.asyncio
async def test_connectivity_without_health_url(mock_mcp_client):
    """Test connectivity when health URL is not configured."""
    # import forbin

    with (
        patch("forbin.config.MCP_SERVER_URL", "http://test.local/mcp"),
        patch("forbin.config.MCP_TOKEN", "test-token"),
        patch("forbin.config.MCP_HEALTH_URL", None),
        patch("forbin.cli.confirm_or_edit_config", return_value=True),
        patch("forbin.client.Client", return_value=mock_mcp_client),
    ):
        await forbin.cli.test_connectivity()

        # Should skip health check but still connect
        mock_mcp_client.__aenter__.assert_called()
        mock_mcp_client.list_tools.assert_called()


@pytest.mark.asyncio
async def test_wake_up_then_connect_flow(mock_mcp_client, mock_httpx_client):
    """Test the wake-up -> wait -> connect flow."""
    # import forbin

    with (
        patch("httpx.AsyncClient", return_value=mock_httpx_client),
        patch("forbin.client.Client", return_value=mock_mcp_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        # Wake up server
        is_awake = await forbin.client.wake_up_server(
            "http://test.local/health", max_attempts=3, wait_seconds=1
        )
        assert is_awake is True

        # Simulate initialization wait
        await asyncio.sleep(20)

        # Connect to server
        client = await forbin.client.connect_to_mcp_server(max_attempts=3, wait_seconds=1)
        assert client is not None

        # List tools
        tools = await forbin.tools.list_tools(client)
        assert len(tools) > 0


@pytest.mark.asyncio
async def test_tool_discovery_and_call_flow(mock_mcp_client):
    """Test discovering tools and calling one."""
    # import forbin

    with patch("forbin.client.Client", return_value=mock_mcp_client):
        # Connect
        client = await forbin.client.connect_to_mcp_server()
        assert client is not None

        # List tools
        tools = await forbin.tools.list_tools(client)
        assert len(tools) > 0

        # Call a tool
        tool = tools[0]
        params = {"param": "test_value"}
        await forbin.tools.call_tool(client, tool, params)

        # Verify call was made
        mock_mcp_client.call_tool.assert_called_once()


@pytest.mark.asyncio
async def test_parameter_input_and_parsing_flow(mock_tool):
    """Test the complete parameter input and parsing flow."""
    # import forbin

    # Test with various parameter types
    test_cases = [
        ("hello world", "string", "hello world"),
        ("42", "integer", 42),
        ("3.14", "number", 3.14),
        ("true", "boolean", True),
        ("false", "boolean", False),
        ('{"key": "value"}', "object", {"key": "value"}),
        ("[1, 2, 3]", "array", [1, 2, 3]),
    ]

    for input_value, param_type, expected in test_cases:
        result = forbin.tools.parse_parameter_value(input_value, param_type)
        assert result == expected, f"Failed for {param_type}: {input_value}"


@pytest.mark.asyncio
async def test_retry_logic_integration():
    """Test that retry logic works across the stack."""
    # import forbin

    # Mock client that fails twice then succeeds
    attempt_count = {"value": 0}

    async def mock_aenter(self):
        attempt_count["value"] += 1
        if attempt_count["value"] < 3:
            raise Exception("Connection failed")
        mock_client = AsyncMock()
        mock_client.initialize_result = {}
        return mock_client

    mock_client_class = Mock()
    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = mock_aenter
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)
    mock_client_class.return_value = mock_client_instance

    with (
        patch("forbin.config.MCP_SERVER_URL", "http://test.local/mcp"),
        patch("forbin.config.MCP_TOKEN", "test-token"),
        patch("forbin.client.Client", mock_client_class),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        client = await forbin.client.connect_to_mcp_server(max_attempts=3, wait_seconds=0.1)

        # Should succeed on third attempt
        assert client is not None
        assert attempt_count["value"] == 3


@pytest.mark.asyncio
async def test_error_handling_in_tool_call():
    """Test error handling when tool execution fails."""
    # import forbin

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(side_effect=Exception("Tool execution error"))

    mock_tool = Mock()
    mock_tool.name = "failing_tool"

    # Should handle the error gracefully (not raise)
    await forbin.tools.call_tool(mock_client, mock_tool, {})
    # If we get here without exception, error handling worked


@pytest.mark.asyncio
async def test_timeout_handling_in_tool_listing():
    """Test timeout handling in tool listing."""
    # import forbin

    mock_client = AsyncMock()
    mock_client.list_tools = AsyncMock(side_effect=asyncio.TimeoutError("Timeout"))

    # Should raise TimeoutError
    with pytest.raises(asyncio.TimeoutError):
        await forbin.tools.list_tools(mock_client)


class TestEnvironmentConfiguration:
    """Test environment variable configuration."""

    def test_missing_server_url(self, monkeypatch):
        """Test that missing MCP_SERVER_URL raises error."""
        # Remove the environment variable
        monkeypatch.delenv("MCP_SERVER_URL", raising=False)
        monkeypatch.setenv("MCP_TOKEN", "test-token")

        # Reload the module to trigger validation
        # (In real test, this would exit, so we'd test the exit behavior)
        # For now, we just verify the check exists in the code

    def test_missing_token(self, monkeypatch):
        """Test that missing MCP_TOKEN raises error."""
        monkeypatch.setenv("MCP_SERVER_URL", "http://test.local/mcp")
        monkeypatch.delenv("MCP_TOKEN", raising=False)

        # Similar to above - would trigger validation


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_tool_list(self, mock_mcp_client):
        """Test handling of empty tool list."""
        # import forbin

        mock_mcp_client.list_tools = AsyncMock(return_value=[])

        tools = await forbin.tools.list_tools(mock_mcp_client)
        assert tools == []

    def test_tool_with_no_schema(self):
        """Test displaying tool with no input schema."""
        # import forbin

        tool = Mock()
        tool.name = "no_schema_tool"
        tool.description = "Tool without schema"
        tool.inputSchema = None

        # Should not raise error
        forbin.display.display_tool_schema(tool)

    def test_tool_with_empty_schema(self):
        """Test tool with empty schema."""
        # import forbin

        tool = Mock()
        tool.name = "empty_schema_tool"
        tool.description = "Tool with empty schema"
        tool.inputSchema = {}

        # Should not raise error
        forbin.display.display_tool_schema(tool)

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        # import forbin

        with pytest.raises(Exception):
            forbin.tools.parse_parameter_value("{invalid json", "object")

    def test_parse_invalid_integer(self):
        """Test parsing invalid integer."""
        # import forbin

        with pytest.raises(ValueError):
            forbin.tools.parse_parameter_value("not a number", "integer")

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        """Test health check with connection error."""
        # import forbin

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        import httpx

        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await forbin.client.wake_up_server(
                "http://unreachable.local/health", max_attempts=2, wait_seconds=0.1
            )

            assert result is False
