"""Input of the post-processing passes for one output document."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..theme import Theme


@dataclass(frozen=True)
class PassContext:
    theme: Theme
    text_width: int
    """Text column width in twips."""
    text_height: int = 0
    """Text column height in twips (0: figures are only clamped to the width)."""
    table_scales: Mapping[str, float] = field(default_factory=dict)
    """Table tag (nxo-t-*) -> zoom measured in the browser for tables wider than the page."""
    min_scale: float = 0.75
    combined: bool = False
    toc_depth: int | None = None
    title: str | None = None
    subject: str | None = None
