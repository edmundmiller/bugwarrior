"""
Shared console output utilities for bugwarrior.

This module provides a unified interface for console output using Rich,
separating pretty console output from file-based logging.

Usage:
    from bugwarrior.console import console, info, warn, error, hint, success

    info("Processing 5 tasks")
    warn("Task diverged from upstream")
    error("Failed to connect")
    hint("Run bugwarrior-uda to see UDA definitions")
    success("Sync complete")
"""

from rich.console import Console

# Main console instance - writes to stderr to keep stdout clean for data
console = Console(stderr=True)

# Verbosity state - controlled by command.py based on CLI flags
_quiet = False
_verbose = False


def set_verbosity(quiet: bool = False, verbose: bool = False):
    """Set global verbosity levels."""
    global _quiet, _verbose
    _quiet = quiet
    _verbose = verbose


def is_quiet() -> bool:
    """Check if quiet mode is enabled."""
    return _quiet


def is_verbose() -> bool:
    """Check if verbose mode is enabled."""
    return _verbose


def info(message: str, quiet_ok: bool = False):
    """Print an informational message.

    Args:
        message: The message to display
        quiet_ok: If True, suppress in quiet mode (default: False)
    """
    if _quiet and quiet_ok:
        return
    console.print(message)


def warn(message: str):
    """Print a warning message (yellow, with ⚠ prefix)."""
    console.print(f"[yellow]⚠ {message}[/yellow]")


def error(message: str):
    """Print an error message (red, with ✗ prefix)."""
    console.print(f"[red]✗ {message}[/red]")


def hint(message: str):
    """Print a hint/suggestion (dim, subtle)."""
    if _quiet:
        return
    console.print(f"[dim]{message}[/dim]")


def success(message: str):
    """Print a success message (green, with ✓ prefix)."""
    console.print(f"[green]✓ {message}[/green]")


def detail(message: str):
    """Print a detail message (only shown in verbose mode)."""
    if not _verbose:
        return
    console.print(f"  [dim]{message}[/dim]")


def status(label: str, value: str, style: str = ""):
    """Print a labeled status line.

    Args:
        label: The label (e.g., "Adding")
        value: The value (e.g., "5 tasks")
        style: Optional Rich style for the value
    """
    if _quiet:
        return
    if style:
        console.print(f"{label}: [{style}]{value}[/{style}]")
    else:
        console.print(f"{label}: {value}")
