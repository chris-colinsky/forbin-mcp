import asyncio
import time
from typing import Optional
import httpx
from fastmcp.client import Client
from fastmcp.client.auth import BearerAuth

from . import config
from .display import console
from .verbose import vlog, vlog_json, vlog_timing, vtimer


class MCPSession:
    """Wrapper to hold both the client and session for proper lifecycle management."""

    def __init__(self, client: Client, session):
        self.client = client
        self.session = session

    async def list_tools(self):
        """List available tools from the MCP server."""
        vlog("Requesting tool list...")
        async with vtimer("list_tools"):
            tools = await self.session.list_tools()
        vlog(f"Received [bold cyan]{len(tools)}[/bold cyan] tools")
        return tools

    async def call_tool(self, name: str, arguments: dict):
        """Call a tool with the given arguments."""
        vlog(f"MCP call_tool: [bold]{name}[/bold]")
        vlog_json("Request Arguments", arguments)
        async with vtimer("Tool execution time"):
            result = await self.session.call_tool(name, arguments)
        vlog(
            f"Response: is_error={result.is_error}, "
            f"content_blocks={len(result.content) if result.content else 0}"
        )
        if config.VERBOSE and result.content:
            for i, block in enumerate(result.content):
                text = getattr(block, "text", None)
                if text:
                    vlog_json(f"Raw Response Block {i}", text)
        return result

    async def cleanup(self):
        """Close the MCP session."""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
            except Exception:
                # FastMCP's stream teardown can emit a "Session termination
                # failed: 400" — harmless and unavoidable, so swallow it.
                pass


async def wake_up_server(health_url: str, max_attempts: int = 6, wait_seconds: float = 5) -> bool:
    """
    Wake up a suspended server by calling the health endpoint.
    Useful for Fly.io and other platforms that suspend inactive services.

    Args:
        health_url: The health endpoint URL
        max_attempts: Maximum number of health check attempts
        wait_seconds: Seconds to wait between attempts

    Returns:
        True if server is awake, False otherwise
    """
    vlog(f"Wake-up target: [bold]{health_url}[/bold]")
    wake_start = time.monotonic()

    # Generous per-request timeout because cold starts on Fly.io can take
    # 20-30s before the health endpoint even begins responding.
    async with httpx.AsyncClient(timeout=30.0) as client:
        with console.status("  [dim]Polling health endpoint...[/dim]", spinner="dots") as status:
            for attempt in range(1, max_attempts + 1):
                try:
                    status.update(f"  [dim]Attempt {attempt}/{max_attempts}...[/dim]")
                    attempt_start = time.monotonic()
                    response = await client.get(health_url)
                    attempt_elapsed = time.monotonic() - attempt_start

                    vlog(
                        f"Attempt {attempt}/{max_attempts}: "
                        f"HTTP {response.status_code} ({attempt_elapsed * 1000:.0f}ms)"
                    )

                    # 200 = server is awake; bail out early.
                    if response.status_code == 200:
                        vlog_timing("Total wake-up time", time.monotonic() - wake_start)
                        return True
                    else:
                        # Only surface non-200 once we've exhausted retries.
                        if attempt == max_attempts:
                            console.print(
                                f"  [yellow]Server responded with status {response.status_code}[/yellow]"
                            )

                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    # Expected during cold start — log noisily only on the
                    # last attempt or when verbose mode is on.
                    vlog(f"Attempt {attempt}/{max_attempts}: {type(e).__name__}")
                    if config.VERBOSE or attempt == max_attempts:
                        error_msg = f"  [yellow]Connection failed: {type(e).__name__}[/yellow]"
                        if config.VERBOSE:
                            error_msg += f" [dim]({str(e)})[/dim]"
                        console.print(error_msg)
                except Exception as e:
                    vlog(f"Attempt {attempt}/{max_attempts}: {type(e).__name__}: {e}")
                    if config.VERBOSE or attempt == max_attempts:
                        console.print(f"  [red]Unexpected error: {e}[/red]")

                # Skip the sleep on the last iteration — there's no next attempt.
                if attempt < max_attempts:
                    await asyncio.sleep(wait_seconds)

    vlog_timing("Total wake-up time (failed)", time.monotonic() - wake_start)
    return False


async def connect_to_mcp_server(
    max_attempts: int = 3, wait_seconds: float = 5
) -> Optional[MCPSession]:
    """
    Connect to the MCP server with retry logic.

    Args:
        max_attempts: Maximum connection attempts
        wait_seconds: Seconds to wait between attempts

    Returns:
        MCPSession instance or None if failed
    """
    server_url = config.MCP_SERVER_URL or ""
    token = config.MCP_TOKEN or ""

    vlog(f"Connecting to: [bold]{server_url}[/bold]")

    with console.status("  [dim]Establishing connection...[/dim]", spinner="dots") as status:
        for attempt in range(1, max_attempts + 1):
            # Track the client so the except blocks can tear it down on failure.
            client = None
            try:
                status.update(f"  [dim]Attempt {attempt}/{max_attempts}...[/dim]")
                attempt_start = time.monotonic()

                client = Client(
                    server_url,
                    auth=BearerAuth(token=token),
                    init_timeout=30.0,  # Extended timeout for cold starts
                    timeout=600.0,  # Wait up to 10 minutes for tool operations
                )

                # Manually enter the async context so we can hold the session
                # open beyond this function — MCPSession.cleanup() exits it later.
                session = await client.__aenter__()

                vlog_timing(f"Connection attempt {attempt}", time.monotonic() - attempt_start)
                return MCPSession(client, session)

            except asyncio.TimeoutError:
                vlog(f"Attempt {attempt}/{max_attempts}: Timeout")
                if config.VERBOSE or attempt == max_attempts:
                    console.print("  [red]Timeout (server not responding)[/red]")
                # Tear down whatever the client got mid-handshake before retrying.
                if client:
                    try:
                        await client.__aexit__(None, None, None)
                    except Exception:
                        pass
                if attempt < max_attempts:
                    await asyncio.sleep(wait_seconds)
            except Exception as e:
                error_name = type(e).__name__
                vlog(f"Attempt {attempt}/{max_attempts}: {error_name}: {e}")
                if config.VERBOSE or attempt == max_attempts:
                    # Broken/Closed resource errors are the typical "server
                    # is still booting" signature — soften the message.
                    if "BrokenResourceError" in error_name or "ClosedResourceError" in error_name:
                        console.print("  [yellow]Connection error (server not ready)[/yellow]")
                    else:
                        console.print(f"  [red]{error_name}: {e}[/red]")

                    # Skip the traceback for the noisy expected errors above.
                    if config.VERBOSE and not (
                        "BrokenResourceError" in error_name or "ClosedResourceError" in error_name
                    ):
                        import traceback

                        console.print(f"[dim]{traceback.format_exc()}[/dim]")

                if client:
                    try:
                        await client.__aexit__(None, None, None)
                    except Exception:
                        pass

                if attempt < max_attempts:
                    await asyncio.sleep(wait_seconds)

    return None


async def connect_and_list_tools(
    max_attempts: int = 3, wait_seconds: float = 5
) -> tuple[Optional[MCPSession], list]:
    """
    Connect to MCP server AND list tools in a single retry loop.

    This combines connection and tool listing to avoid session expiry
    between the two operations.

    Args:
        max_attempts: Maximum connection attempts
        wait_seconds: Seconds to wait between attempts

    Returns:
        Tuple of (MCPSession instance or None, list of tools)
    """
    server_url = config.MCP_SERVER_URL or ""
    token = config.MCP_TOKEN or ""

    vlog(f"Connecting to: [bold]{server_url}[/bold]")
    total_start = time.monotonic()

    with console.status("  [dim]Establishing connection...[/dim]", spinner="dots") as status:
        for attempt in range(1, max_attempts + 1):
            client = None
            try:
                status.update(f"  [dim]Attempt {attempt}/{max_attempts}...[/dim]")
                attempt_start = time.monotonic()

                client = Client(
                    server_url,
                    auth=BearerAuth(token=token),
                    init_timeout=30.0,  # Extended timeout for cold starts
                    timeout=600.0,  # Wait up to 10 minutes for tool operations
                )

                # Hold the context open — MCPSession.cleanup() exits it later.
                session = await client.__aenter__()
                mcp_session = MCPSession(client, session)

                vlog_timing(f"Connection attempt {attempt}", time.monotonic() - attempt_start)

                # List tools inside the same retry attempt: if the session
                # expires between connect and list_tools, retrying connect
                # alone wouldn't help. Bundling them keeps the retry honest.
                status.update(
                    f"  [dim]Retrieving tools (attempt {attempt}/{max_attempts})...[/dim]"
                )
                list_start = time.monotonic()
                tools = await asyncio.wait_for(mcp_session.session.list_tools(), timeout=15.0)
                vlog_timing("Tool listing", time.monotonic() - list_start)
                vlog(f"Received [bold cyan]{len(tools)}[/bold cyan] tools")
                vlog_timing("Total connect+list", time.monotonic() - total_start)

                return mcp_session, tools

            except asyncio.TimeoutError:
                vlog(f"Attempt {attempt}/{max_attempts}: Timeout")
                if config.VERBOSE or attempt == max_attempts:
                    console.print("  [red]Timeout (server not responding)[/red]")
                # Clean up partial connection
                if client:
                    try:
                        await client.__aexit__(None, None, None)
                    except Exception:
                        pass
                if attempt < max_attempts:
                    await asyncio.sleep(wait_seconds)
            except Exception as e:
                error_name = type(e).__name__
                vlog(f"Attempt {attempt}/{max_attempts}: {error_name}: {e}")
                if config.VERBOSE or attempt == max_attempts:
                    if "BrokenResourceError" in error_name or "ClosedResourceError" in error_name:
                        console.print("  [yellow]Connection error (server not ready)[/yellow]")
                    else:
                        console.print(f"  [red]{error_name}: {e}[/red]")

                    if config.VERBOSE and not (
                        "BrokenResourceError" in error_name or "ClosedResourceError" in error_name
                    ):
                        import traceback

                        console.print(f"[dim]{traceback.format_exc()}[/dim]")

                # Clean up partial connection
                if client:
                    try:
                        await client.__aexit__(None, None, None)
                    except Exception:
                        pass

                if attempt < max_attempts:
                    await asyncio.sleep(wait_seconds)

    return None, []
