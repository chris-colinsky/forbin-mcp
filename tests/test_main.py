"""Unit tests for forbin.py."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from io import StringIO

# Import the module to test
# Import the modules to test
import forbin.tools
import forbin.display
import forbin.client
import forbin.utils
import forbin.cli
import forbin.config


class TestParameterParsing:
    """Test parameter value parsing."""

    def test_parse_string(self):
        """Test parsing string values."""
        result = forbin.tools.parse_parameter_value("hello", "string")
        assert result == "hello"

    def test_parse_integer(self):
        """Test parsing integer values."""
        result = forbin.tools.parse_parameter_value("42", "integer")
        assert result == 42
        assert isinstance(result, int)

    def test_parse_number(self):
        """Test parsing float values."""
        result = forbin.tools.parse_parameter_value("3.14", "number")
        assert result == 3.14
        assert isinstance(result, float)

    def test_parse_boolean_true(self):
        """Test parsing boolean true values."""
        for value in ["true", "True", "t", "yes", "y", "1"]:
            result = forbin.tools.parse_parameter_value(value, "boolean")
            assert result is True

    def test_parse_boolean_false(self):
        """Test parsing boolean false values."""
        for value in ["false", "False", "f", "no", "n", "0"]:
            result = forbin.tools.parse_parameter_value(value, "boolean")
            assert result is False

    def test_parse_object(self):
        """Test parsing JSON object."""
        json_str = '{"key": "value", "number": 42}'
        result = forbin.tools.parse_parameter_value(json_str, "object")
        assert result == {"key": "value", "number": 42}

    def test_parse_array(self):
        """Test parsing JSON array."""
        json_str = '[1, 2, 3, "four"]'
        result = forbin.tools.parse_parameter_value(json_str, "array")
        assert result == [1, 2, 3, "four"]

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = forbin.tools.parse_parameter_value("", "string")
        assert result is None

    def test_parse_whitespace(self):
        """Test parsing whitespace."""
        result = forbin.tools.parse_parameter_value("   ", "string")
        assert result is None


class TestDisplayFunctions:
    """Test display and formatting functions."""

    def test_display_tools_with_tools(self, mock_tool_list, capsys):
        """Test displaying tools list."""
        forbin.display.display_tools(mock_tool_list)
        captured = capsys.readouterr()
        assert "Available Tools" in captured.out
        assert "test_tool" in captured.out
        assert "simple_tool" in captured.out

    def test_display_tools_empty(self, capsys):
        """Test displaying empty tools list."""
        forbin.display.display_tools([])
        captured = capsys.readouterr()
        assert "No tools available" in captured.out

    def test_display_tool_schema_with_params(self, mock_tool, capsys):
        """Test displaying tool schema with parameters."""
        forbin.display.display_tool_schema(mock_tool)
        captured = capsys.readouterr()
        assert "test_tool" in captured.out
        assert "param1" in captured.out
        assert "param2" in captured.out
        assert "required" in captured.out
        assert "optional" in captured.out

    def test_display_tool_schema_no_params(self, mock_tool_no_params, capsys):
        """Test displaying tool schema without parameters."""
        forbin.display.display_tool_schema(mock_tool_no_params)
        captured = capsys.readouterr()
        assert "simple_tool" in captured.out
        assert "No input parameters required" in captured.out


class TestWakeUpServer:
    """Test server wake-up functionality."""

    @pytest.mark.asyncio
    async def test_wake_up_server_success(self, mock_httpx_client):
        """Test successful server wake-up."""
        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            result = await forbin.client.wake_up_server(
                "http://test.local/health", max_attempts=3, wait_seconds=0.1
            )
            assert result is True
            mock_httpx_client.get.assert_called()

    @pytest.mark.asyncio
    async def test_wake_up_server_retry_then_success(self):
        """Test server wake-up with retry."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # First call fails, second succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 503

        mock_response_success = Mock()
        mock_response_success.status_code = 200

        mock_client.get = AsyncMock(side_effect=[mock_response_fail, mock_response_success])

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await forbin.client.wake_up_server(
                "http://test.local/health", max_attempts=3, wait_seconds=0.1
            )
            assert result is True
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_wake_up_server_failure(self):
        """Test server wake-up failure after all attempts."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # Always return error
        mock_response = Mock()
        mock_response.status_code = 503
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await forbin.client.wake_up_server(
                "http://test.local/health", max_attempts=2, wait_seconds=0.1
            )
            assert result is False
            assert mock_client.get.call_count == 2


class TestConnectToMCPServer:
    """Test MCP server connection."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_mcp_client):
        """Test successful connection to MCP server."""
        with (
            patch("forbin.config.MCP_SERVER_URL", "http://test.local/mcp"),
            patch("forbin.config.MCP_TOKEN", "test-token"),
            patch("forbin.client.Client", return_value=mock_mcp_client),
        ):
            client = await forbin.client.connect_to_mcp_server(max_attempts=3, wait_seconds=0.1)

            assert client is not None
            mock_mcp_client.__aenter__.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_retry_then_success(self):
        """Test connection with retry."""
        # First attempt fails, second succeeds
        mock_client_fail = AsyncMock()
        mock_client_fail.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))

        mock_client_success = AsyncMock()
        mock_client_success.__aenter__ = AsyncMock(return_value=mock_client_success)
        mock_client_success.__aexit__ = AsyncMock(return_value=None)
        mock_client_success.initialize_result = {}

        with (
            patch("forbin.config.MCP_SERVER_URL", "http://test.local/mcp"),
            patch("forbin.config.MCP_TOKEN", "test-token"),
            patch("forbin.client.Client", side_effect=[mock_client_fail, mock_client_success]),
        ):
            client = await forbin.client.connect_to_mcp_server(max_attempts=2, wait_seconds=0.1)

            assert client is not None

    @pytest.mark.asyncio
    async def test_connect_timeout(self):
        """Test connection timeout."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError)

        with (
            patch("forbin.config.MCP_SERVER_URL", "http://test.local/mcp"),
            patch("forbin.config.MCP_TOKEN", "test-token"),
            patch("forbin.client.Client", return_value=mock_client),
        ):
            client = await forbin.client.connect_to_mcp_server(max_attempts=2, wait_seconds=0.1)

            assert client is None


class TestListTools:
    """Test tool listing functionality."""

    @pytest.mark.asyncio
    async def test_list_tools_success(self, mock_mcp_client):
        """Test successful tool listing."""
        tools = await forbin.tools.list_tools(mock_mcp_client)

        assert len(tools) > 0
        assert tools[0].name == "test_tool"
        mock_mcp_client.list_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tools_timeout(self):
        """Test tool listing timeout."""
        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(side_effect=asyncio.TimeoutError("Timeout"))

        with pytest.raises(asyncio.TimeoutError):
            await forbin.tools.list_tools(mock_client)


class TestCallTool:
    """Test tool calling functionality."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self, mock_mcp_client, mock_tool, capsys):
        """Test successful tool call."""
        params = {"param": "value"}

        await forbin.tools.call_tool(mock_mcp_client, mock_tool, params)

        captured = capsys.readouterr()
        assert "CALLING TOOL" in captured.out
        assert "test_tool" in captured.out
        assert "Tool executed successfully" in captured.out

        mock_mcp_client.call_tool.assert_called_once_with("test_tool", params)

    @pytest.mark.asyncio
    async def test_call_tool_failure(self, mock_mcp_client, mock_tool, capsys):
        """Test tool call failure."""
        mock_mcp_client.call_tool = AsyncMock(side_effect=Exception("Tool execution failed"))
        params = {"param": "value"}

        await forbin.tools.call_tool(mock_mcp_client, mock_tool, params)

        captured = capsys.readouterr()
        assert "Tool execution failed" in captured.out


class TestClipboard:
    """Test clipboard copy helpers and the post-result prompt branch."""

    def test_copy_to_clipboard_success(self):
        with patch("pyperclip.copy") as mock_copy:
            assert forbin.utils.copy_to_clipboard("hello") is True
            mock_copy.assert_called_once_with("hello")

    def test_copy_to_clipboard_failure(self):
        with patch("pyperclip.copy", side_effect=RuntimeError("no backend")):
            assert forbin.utils.copy_to_clipboard("hello") is False

    @pytest.mark.asyncio
    async def test_call_tool_copies_on_c(self, mock_mcp_client, mock_tool, capsys):
        # Swap in a JSON response so we can also assert the copied text is
        # the formatted JSON the user just saw rather than the raw string.
        mock_result = Mock()
        content = Mock()
        content.text = '{"answer":42}'
        mock_result.content = [content]
        mock_mcp_client.call_tool = AsyncMock(return_value=mock_result)

        with (
            patch("forbin.tools.read_single_key", return_value="c"),
            patch("forbin.tools.copy_to_clipboard", return_value=True) as mock_copy,
        ):
            await forbin.tools.call_tool(mock_mcp_client, mock_tool, {"param": "v"})

        captured = capsys.readouterr()
        assert "Copied to clipboard" in captured.out
        mock_copy.assert_called_once()
        copied_text = mock_copy.call_args[0][0]
        # Formatted JSON has indentation, which the raw response does not.
        assert '"answer": 42' in copied_text

    @pytest.mark.asyncio
    async def test_call_tool_skips_on_other_key(self, mock_mcp_client, mock_tool, capsys):
        with (
            patch("forbin.tools.read_single_key", return_value=""),
            patch("forbin.tools.copy_to_clipboard") as mock_copy,
        ):
            await forbin.tools.call_tool(mock_mcp_client, mock_tool, {"param": "v"})

        mock_copy.assert_not_called()
        captured = capsys.readouterr()
        assert "Copied to clipboard" not in captured.out

    @pytest.mark.asyncio
    async def test_call_tool_skips_on_non_tty(self, mock_mcp_client, mock_tool, capsys):
        # read_single_key returns None when stdin isn't a TTY — the prompt
        # branch must early-out without invoking the clipboard.
        with (
            patch("forbin.tools.read_single_key", return_value=None),
            patch("forbin.tools.copy_to_clipboard") as mock_copy,
        ):
            await forbin.tools.call_tool(mock_mcp_client, mock_tool, {"param": "v"})

        mock_copy.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_tool_copy_failure_message(self, mock_mcp_client, mock_tool, capsys):
        with (
            patch("forbin.tools.read_single_key", return_value="c"),
            patch("forbin.tools.copy_to_clipboard", return_value=False),
        ):
            await forbin.tools.call_tool(mock_mcp_client, mock_tool, {"param": "v"})

        captured = capsys.readouterr()
        assert "Could not access clipboard" in captured.out


class TestFilteredStderr:
    """Test stderr filtering."""

    @pytest.fixture(autouse=True)
    def _disable_verbose(self, monkeypatch):
        # FilteredStderr is a no-op when VERBOSE is True; force it off so the
        # filter logic actually runs regardless of the user's local config file.
        monkeypatch.setattr(forbin.config, "VERBOSE", False)

    def test_filter_suppressed_pattern(self):
        """Test that suppressed patterns are filtered."""
        original_stderr = StringIO()
        filtered = forbin.utils.FilteredStderr(original_stderr)

        filtered.write("Error in post_writer\n")
        filtered.write("Session termination failed\n")

        assert original_stderr.getvalue() == ""

    def test_filter_normal_output(self):
        """Test that normal output passes through."""
        original_stderr = StringIO()
        filtered = forbin.utils.FilteredStderr(original_stderr)

        filtered.write("Normal error message\n")

        assert "Normal error message" in original_stderr.getvalue()

    def test_filter_suppression_ends_on_blank_line(self):
        """Test that suppression ends on blank line."""
        original_stderr = StringIO()
        filtered = forbin.utils.FilteredStderr(original_stderr)

        filtered.write("Error in post_writer\n")
        filtered.write("traceback details\n")
        filtered.write("\n")  # Blank line
        filtered.write("New message\n")

        assert "New message" in original_stderr.getvalue()
        assert "post_writer" not in original_stderr.getvalue()


class TestMainFunction:
    """Test main entry point."""

    @pytest.mark.asyncio
    async def test_main_help(self, capsys):
        """Test help flag."""
        with patch("sys.argv", ["forbin.py", "--help"]):
            await forbin.cli.async_main()

            captured = capsys.readouterr()
            assert "MCP Remote Tool Tester" in captured.out
            assert "Usage:" in captured.out

    @pytest.mark.asyncio
    async def test_main_test_mode(self, mock_mcp_client, mock_httpx_client):
        """Test connectivity test mode."""
        with (
            patch("sys.argv", ["forbin.py", "--test"]),
            patch("forbin.config.MCP_SERVER_URL", "http://test.local/mcp"),
            patch("forbin.config.MCP_TOKEN", "test-token"),
            patch("forbin.config.MCP_HEALTH_URL", "http://test.local/health"),
            patch("forbin.cli.confirm_or_edit_config", return_value=True),
            patch("httpx.AsyncClient", return_value=mock_httpx_client),
            patch("forbin.client.Client", return_value=mock_mcp_client),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await forbin.cli.async_main()

            # Should have attempted to wake up server and connect
            mock_httpx_client.get.assert_called()
            mock_mcp_client.__aenter__.assert_called()
