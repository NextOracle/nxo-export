"""Chromium printing with the configured page box."""

from __future__ import annotations

import io
from dataclasses import dataclass

from playwright.sync_api import Page
from pypdf import PdfReader

from ...browser import BrowserSession
from ...config import RenderCfg
from ...domain.site import TocNode


def page_css(cfg: RenderCfg, background: str | None = None) -> str:
    p = cfg.page
    # Chromium paints margins with the colour-scheme canvas, not the root background; @page background fixes it.
    bg = f" background: {background};" if background else ""
    return (
        f"@page {{ size: {p.size}; margin: {p.margin_top} {p.margin_x} {p.margin_bottom} {p.margin_x};{bg}"
        " @bottom-center { content: none; } }"
    )


def page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


@dataclass(frozen=True, slots=True)
class TopicPdf:
    node: TocNode
    data: bytes
    pages: int


class PagePrinter:
    """Prints topic pages and synthetic pages (cover, TOC) with the Writerside theme of the session."""

    def __init__(self, session: BrowserSession):
        self.session = session

    def print(self, page: Page, transparent: bool = False) -> bytes:
        bg = None if transparent else page.evaluate("getComputedStyle(document.documentElement).backgroundColor")
        page.add_style_tag(content=page_css(self.session.cfg, bg))
        return page.pdf(print_background=not transparent, prefer_css_page_size=True)

    def topic(self, node: TocNode) -> TopicPdf:
        page, _ = self.session.open_topic(node)
        try:
            data = self.print(page)
        finally:
            page.close()
        return TopicPdf(node, data, page_count(data))

    def blank(self, body: str, css: str = "") -> bytes:
        page = self.session.open_blank(body, css)
        try:
            return self.print(page)
        finally:
            page.close()
