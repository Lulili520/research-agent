"""Deterministic UTF-8 standard streams for command-line entry points."""
from __future__ import annotations

import sys


def configure_utf8_stdio() -> None:
    """Keep CLI output usable when the Windows console locale is not UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                # Embedded hosts may expose a stream that cannot be reconfigured.
                pass
