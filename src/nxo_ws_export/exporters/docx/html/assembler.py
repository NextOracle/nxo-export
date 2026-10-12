"""Pandoc input documents: one topic, or every topic in TOC order with section headings."""

from __future__ import annotations

import re
from collections.abc import Mapping

from ....domain.site import Site, TocNode
from ..topic import TopicHtml
from .links import LinkResolver

_ID = re.compile(r'(\sid="|\shref="#)([^"]+)"')
_HREF = re.compile(r'\shref="#([^"]+)"')
_EMPTY_SPAN = re.compile(r'<span id="([^"]+)"></span>')
_HEADING = re.compile(r"<(/?)h([1-6])\b")
KEPT_IDS = ("nxo-t-", "nxo-callout-")
"""Table/callout tags read by the OOXML passes."""


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def shift_headings(html: str, shift: int) -> str:
    """Demote headings by `shift` levels (capped at h6): a nested topic's h1 becomes a chapter sub-heading."""
    if shift <= 0:
        return html
    return _HEADING.sub(lambda m: f"<{m.group(1)}h{min(6, int(m.group(2)) + shift)}", html)


def short_ids(html: str) -> str:
    """Word ignores bookmarks longer than 40 characters, and Pandoc hashes names it considers invalid.
    Heading ids and link targets get a short name ``nxoaN`` (hidden later in post-processing); ids nothing
    links to are dropped, so they do not litter the document with bookmarks. Table/callout tags are kept."""
    targets = set(_HREF.findall(html))
    names: dict[str, str] = {}

    def sub(m: re.Match[str]) -> str:
        attr, ident = m.groups()
        if ident.startswith(KEPT_IDS):
            return m.group(0)
        short = names.setdefault(ident, f"nxoa{len(names) + 1}")
        return f'{attr}{short}"'

    def drop(m: re.Match[str]) -> str:
        return "" if m.group(1) not in targets else m.group(0)

    html = _EMPTY_SPAN.sub(drop, html)
    return _ID.sub(sub, html)


def html_document(title: str | None, body: str) -> str:
    # A <title> becomes a Word "Title" paragraph; per-topic documents already start with the topic h1.
    head = f"<title>{esc(title)}</title>" if title else ""
    return f'<!DOCTYPE html><html><head><meta charset="utf-8">{head}</head><body>{short_ids(body)}</body></html>'


class HtmlAssembler:
    def __init__(self, topics: Mapping[str, TopicHtml], link_base_url: str | None):
        self.topics = topics
        self.links = LinkResolver(topics, link_base_url)

    def topic(self, t: TopicHtml) -> str:
        """A per-topic document: only links into the topic itself stay internal."""
        body = self.links.resolve(t.html, current=t, internal=lambda u: u == t.node.url)
        return html_document(None, body)

    def combined(self, site: Site, title: str) -> str:
        """Every topic in TOC order, headings shifted by TOC depth; title-only TOC nodes become headings."""
        parts: list[str] = []
        emitted: set[str] = set()

        def visit(n: TocNode) -> None:
            if n.url and n.url in self.topics and n.url not in emitted:
                emitted.add(n.url)
                t = self.topics[n.url]
                html = shift_headings(t.html, t.node.level)
                parts.append(self.links.resolve(html, current=t, internal=lambda u: u in self.topics))
            elif not n.url and self._has_selected(n):
                lvl = min(6, n.level + 1)
                parts.append(f'<h{lvl} id="group-{len(parts)}">{esc(n.title)}</h{lvl}>')
            for c in n.children:
                visit(c)

        for top in site.toc:
            visit(top)
        return html_document(title, "\n".join(parts))

    def _has_selected(self, n: TocNode) -> bool:
        return any((c.url in self.topics) or self._has_selected(c) for c in n.children)
