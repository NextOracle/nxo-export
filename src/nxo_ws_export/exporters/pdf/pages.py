"""Synthetic pages of the combined PDF, styled as Writerside articles: cover and table of contents."""

from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from ...domain.site import TocNode

FRONT_CSS = """
.nxo-doc { padding: 0; }
.nxo-toc { list-style: none; margin: 1.5em 0 0; padding: 0; }
.nxo-toc li { display: flex; align-items: baseline; gap: .4em; margin: .35em 0; break-inside: avoid; }
.nxo-toc li .t { flex: 0 1 auto; }
.nxo-toc li .d { flex: 1 1 auto; border-bottom: 1px dotted currentColor; opacity: .45; min-width: 1em;
  transform: translateY(-.25em); }
.nxo-toc li .n { flex: 0 0 auto; font-variant-numeric: tabular-nums; }
.nxo-toc li.l0 { font-weight: 600; margin-top: .9em; }
.nxo-cover { padding-top: 70mm; }
.nxo-cover .sub { margin-top: 1em; font-size: 1.25em; opacity: .8; }
.nxo-cover .date { margin-top: 3em; opacity: .6; }
"""

PLACEHOLDER_PAGE = 888
"""Wide enough for any page number, so the first (unnumbered) TOC pass has the final line breaks."""


def first_page(node: TocNode, start: Mapping[str, int]) -> int | None:
    """First page of a TOC node: its own page, else that of its first exported descendant."""
    for n in node.walk():
        if n.url and n.url in start:
            return start[n.url]
    return None


@dataclass(frozen=True, slots=True)
class CoverPage:
    title: str
    subtitle: str | None

    def html(self) -> str:
        sub = f'<div class="sub">{html.escape(self.subtitle)}</div>' if self.subtitle else ""
        return (
            '<div class="app__article"><div class="article nxo-doc nxo-cover">'
            f'<h1 class="title article__h1">{html.escape(self.title)}</h1>{sub}'
            f'<div class="date">{date.today().isoformat()}</div></div></div>'
        )


@dataclass(frozen=True, slots=True)
class TocPage:
    title: str
    entries: tuple[TocNode, ...]

    def html(self, start: Mapping[str, int] | None) -> str:
        items = []
        for n in self.entries:
            num = first_page(n, start) if start is not None else PLACEHOLDER_PAGE
            if num is None:
                continue
            items.append(
                f'<li class="l{n.level}" style="padding-left:{n.level * 1.4}em"><span class="t">{html.escape(n.title)}'
                f'</span><span class="d"></span><span class="n">{num}</span></li>'
            )
        return (
            '<div class="app__article"><div class="article nxo-doc">'
            f'<h1 class="title article__h1">{html.escape(self.title)}</h1><ul class="nxo-toc">{"".join(items)}</ul>'
            '</div></div>'
        )
