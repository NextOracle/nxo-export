"""Shared type aliases."""

from __future__ import annotations

from collections.abc import Callable

Log = Callable[[str], None]
"""Progress sink (one human-readable line per call); the CLI writes to stderr."""
