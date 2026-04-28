"""Verbose logging helpers for Forbin.

All functions are no-ops when config.VERBOSE is False,
so callers don't need to check the flag themselves.
"""

import json
import time
from contextlib import asynccontextmanager

from . import config
from .display import console

from rich.panel import Panel
from rich.syntax import Syntax


def vlog(message: str):
    """Print a [verbose]-prefixed line if verbose mode is on."""
    if not config.VERBOSE:
        return
    console.print(f"  [dim bold]\\[verbose][/dim bold] {message}")


def vlog_json(label: str, data):
    """Print a JSON payload in a compact Rich Panel if verbose mode is on."""
    if not config.VERBOSE:
        return
    # noinspection PyBroadException
    try:
        if isinstance(data, str):
            json_str = data
        else:
            json_str = json.dumps(data, indent=2, default=str)
        console.print(
            Panel(
                Syntax(json_str, "json", theme="monokai", line_numbers=False),
                title=f"[bold]{label}[/bold]",
                title_align="left",
                border_style="dim",
                expand=False,
            )
        )
    except Exception:
        # Intentional catch-all: a verbose helper must never crash the caller.
        # Anything from json.dumps / Rich rendering / console.print falls back
        # to a plain-text dump so the diagnostic info still surfaces.
        console.print(f"  [dim bold]\\[verbose][/dim bold] {label}: {data}")


def vlog_timing(label: str, elapsed: float):
    """Print a timing line, auto-formatted as ms or seconds."""
    if not config.VERBOSE:
        return
    if elapsed < 1.0:
        formatted = f"{elapsed * 1000:.0f}ms"
    else:
        formatted = f"{elapsed:.2f}s"
    console.print(f"  [dim bold]\\[verbose][/dim bold] {label}: [bold cyan]{formatted}[/bold cyan]")


@asynccontextmanager
async def vtimer(label: str):
    """Async context manager that times an await block and vlogs the result."""
    start = time.monotonic()
    yield
    elapsed = time.monotonic() - start
    vlog_timing(label, elapsed)
