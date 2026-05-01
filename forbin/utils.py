import sys
import asyncio
import contextlib
import logging
import select
from . import config


class UserQuit(Exception):
    """Raised from any prompt to exit the app cleanly. Caught at the top
    level so finally blocks (MCP session cleanup, listener cancellation)
    still run."""


# Stderr proxy that hides known-noisy MCP library output (e.g. the harmless
# "Session termination failed: 400" warning) without losing genuine errors.
class FilteredStderr:
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
        # Substring matches — any line containing one of these triggers
        # suppression of itself plus the lines that typically follow it
        # (the rest of a traceback or the stack frames around `raise`/`await`).
        self.suppress_patterns = [
            "Error in post_writer",
            "Session termination failed",
            "httpx.HTTPStatusError",
            "streamable_http.py",
            "Traceback (most recent call last)",
            "File ",  # File paths in tracebacks
            "raise ",
            "await ",
            "BrokenResourceError",
            "ClosedResourceError",
            "raise_for_status",
            "handle_request_async",
            "_handle_post_request",
        ]
        self.suppressing = False
        # When suppressing, swallow up to this many follow-up lines unless
        # we hit a blank line first (which signals end-of-traceback).
        self.suppress_depth = 0

    def write(self, text):
        # Verbose mode is the user opting back in to the noise.
        if config.VERBOSE:
            self.original_stderr.write(text)
            return

        # New suppressible block — start swallowing.
        if any(pattern in text for pattern in self.suppress_patterns):
            self.suppressing = True
            self.suppress_depth = 10
            return

        # Mid-suppression: blank line ends it, anything else burns one slot.
        if self.suppressing:
            if text.strip() == "":
                self.suppressing = False
                self.suppress_depth = 0
            else:
                self.suppress_depth -= 1
                if self.suppress_depth <= 0:
                    self.suppressing = False
                    return

            return

        self.original_stderr.write(text)

    def flush(self):
        self.original_stderr.flush()


class _VerboseLogHandler(logging.Handler):
    """Logging handler that routes messages through vlog() when verbose is on."""

    def __init__(self, prefix: str):
        super().__init__()
        self.prefix = prefix

    def emit(self, record):
        if not config.VERBOSE:
            return
        # A logging handler must never crash the caller — drop the line
        # silently if anything goes wrong while formatting/printing it.
        with contextlib.suppress(Exception):
            from .verbose import vlog

            msg = self.format(record)
            # Truncate very long messages
            if len(msg) > 500:
                msg = msg[:497] + "..."
            vlog(f"[dim]\\[{self.prefix}][/dim] {msg}")


_logging_setup = False


def setup_logging():
    """Replace stderr with a filtered version and suppress noisy MCP library logging."""
    # Idempotent — the CLI calls this exactly once but we guard anyway so
    # double-imports in tests don't stack handlers or proxies.
    global _logging_setup
    if _logging_setup:
        return
    _logging_setup = True

    sys.stderr = FilteredStderr(sys.stderr)

    # The MCP library's logging handlers may hold a reference to the original
    # stderr (captured at import time), bypassing FilteredStderr. Suppress the
    # noisy "Error in post_writer" 400 errors directly via the logging system.
    class _MCPVerboseGate(logging.Filter):
        def filter(self, record):
            return config.VERBOSE

    logging.getLogger("mcp.client.streamable_http").addFilter(_MCPVerboseGate())

    # Route httpx + MCP transport logs through vlog() so they only show
    # when the user toggles verbose mode on.
    httpx_handler = _VerboseLogHandler("httpx")
    httpx_handler.setLevel(logging.DEBUG)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.addHandler(httpx_handler)
    httpx_logger.setLevel(logging.DEBUG)

    mcp_handler = _VerboseLogHandler("mcp")
    mcp_handler.setLevel(logging.DEBUG)
    mcp_logger = logging.getLogger("mcp.client.streamable_http")
    mcp_logger.addHandler(mcp_handler)
    mcp_logger.setLevel(logging.DEBUG)


def read_single_key() -> str | None:
    """
    Block until the user presses one key, then return it lowercased.
    Returns None when stdin isn't a TTY (e.g., pytest capture, piped input)
    or when termios/tty aren't importable (Windows) — callers treat this as
    "skip the prompt" rather than a hard failure.
    """
    try:
        import termios
        import tty
    except ImportError:
        return None

    try:
        fd = sys.stdin.fileno()
    except (AttributeError, OSError):
        return None
    if not sys.stdin.isatty():
        return None

    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        char = sys.stdin.read(1)
        return char.lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard. Returns False if the platform
    backend isn't available (e.g., headless Linux without xclip/xsel)."""
    # noinspection PyBroadException
    try:
        # Lazy import: a missing native backend on the user's machine should
        # only break the copy path, not forbin's overall importability.
        import pyperclip  # type: ignore[import-untyped]

        pyperclip.copy(text)
        return True
    except Exception:
        # pyperclip raises PyperclipException, but the package's own import
        # can also fail in unusual environments — broad catch keeps the
        # CLI from crashing on a copy attempt regardless of the cause.
        return False


async def listen_for_toggle():
    """
    Background task to listen for 'v' key to toggle verbose logging.
    Uses non-blocking stdin read.
    """
    # termios/tty are POSIX-only; bail silently on Windows so the CLI still works.
    try:
        import termios
        import tty
    except ImportError:
        return

    fd = sys.stdin.fileno()
    # Skip if stdin isn't a tty (e.g. piped input, CI, pytest capture).
    if not sys.stdin.isatty():
        return

    # Switch to a raw single-character mode so keypresses arrive without
    # Enter, and always restore on exit so the user's shell isn't left
    # in raw mode.
    old_settings = termios.tcgetattr(fd)
    try:
        # Terminal manipulation can fail in odd environments — don't take
        # down the whole CLI just because the toggle key stopped working.
        with contextlib.suppress(Exception):
            tty.setcbreak(fd)
            while True:
                # 100ms poll keeps CPU near zero while still feeling responsive.
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    char = sys.stdin.read(1).lower()
                    if char == "v":
                        config.VERBOSE = not config.VERBOSE
                        from .display import console

                        status = (
                            "[bold green]ON[/bold green]"
                            if config.VERBOSE
                            else "[bold red]OFF[/bold red]"
                        )
                        console.print(f"\n[bold cyan]Verbose logging toggled {status}[/bold cyan]")

                await asyncio.sleep(0.1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
