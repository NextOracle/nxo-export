"""A topic extracted from the rendered page, ready for Pandoc."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from ...domain.site import TocNode


@dataclass(frozen=True)
class TopicHtml:
    node: TocNode
    html: str
    figures: int
    anchor: str | None = None
    """Id of the topic's first heading (target for links to the topic itself)."""
    ids: frozenset[str] = frozenset()
    tables: dict[str, float] = field(default_factory=dict)
    """Table tag -> zoom measured in the browser."""
    prism: dict[str, dict[str, Any]] = field(default_factory=dict)

    def with_html(self, html: str) -> TopicHtml:
        return replace(self, html=html)
