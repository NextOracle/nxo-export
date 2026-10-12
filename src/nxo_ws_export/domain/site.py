"""The built Writerside site as a value: its table of contents and topic selection."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import ExportError


@dataclass(frozen=True, slots=True)
class TocNode:
    id: str
    title: str
    url: str | None
    """Relative page URL; None for pure section nodes (a tree <toc-element> with only a title)."""
    level: int
    children: tuple[TocNode, ...] = ()

    def walk(self) -> Iterator[TocNode]:
        yield self
        for c in self.children:
            yield from c.walk()

    @property
    def slug(self) -> str:
        return (self.url or self.id).removesuffix(".html")

    def matches(self, pattern: str) -> bool:
        p = pattern.lower()
        return any(fnmatch.fnmatch(k.lower(), p) for k in (self.id, self.slug, self.url or ""))


@dataclass(frozen=True, slots=True)
class Site:
    root: Path
    toc: tuple[TocNode, ...]
    product_name: str
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def product_id(self) -> str:
        return str(self.config.get("productId") or self.root.name)

    def topics(self) -> list[TocNode]:
        """Pages in reading order (depth-first through the TOC), de-duplicated."""
        seen: set[str] = set()
        out: list[TocNode] = []
        for top in self.toc:
            for n in top.walk():
                if n.url and n.url not in seen:
                    seen.add(n.url)
                    out.append(n)
        return out

    def select(self, patterns: tuple[str, ...] = ()) -> list[TocNode]:
        """Topics matching any id/slug/url glob (all topics when no pattern is given)."""
        topics = self.topics()
        if not patterns:
            return topics
        keep = [t for t in topics if any(t.matches(p) for p in patterns)]
        if not keep:
            raise ExportError(f"no topic matches {', '.join(patterns)}")
        return keep

    def subset(self, urls: set[str | None]) -> Site:
        """The same TOC pruned to `urls`; ancestors of kept topics stay as sections (url=None)."""

        def prune(n: TocNode) -> TocNode | None:
            kids = tuple(c for c in (prune(c) for c in n.children) if c)
            if n.url in urls or kids:
                return TocNode(n.id, n.title, n.url if n.url in urls else None, n.level, kids)
            return None

        return Site(self.root, tuple(t for t in (prune(n) for n in self.toc) if t), self.product_name, self.config)

    def outline(self, depth: int) -> list[TocNode]:
        """TOC nodes above `depth` in reading order (for a printed table of contents)."""
        out: list[TocNode] = []

        def visit(n: TocNode) -> None:
            if n.level < depth:
                out.append(n)
                for c in n.children:
                    visit(c)

        for top in self.toc:
            visit(top)
        return out
