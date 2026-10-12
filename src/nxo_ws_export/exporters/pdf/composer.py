"""PDF documents from printed topics: one per topic, or one combined book (cover, TOC, outline, numbering)."""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from ..._types import Log
from ...domain.site import Site, TocNode
from .footer import PageNumberStamper
from .pages import FRONT_CSS, CoverPage, TocPage, first_page
from .printer import PagePrinter, TopicPdf, page_count

PRODUCER = "nxo-ws-export"
TOC_CONVERGE_ROUNDS = 3


def _append(writer: PdfWriter, data: bytes) -> None:
    writer.append(PdfReader(io.BytesIO(data)), import_outline=False)


def _save(writer: PdfWriter, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        writer.write(fh)


def start_pages(rendered: Sequence[TopicPdf], offset: int) -> dict[str, int]:
    """Topic url -> 1-based first page, after `offset` front pages."""
    start, page = {}, offset + 1
    for t in rendered:
        if t.node.url:
            start[t.node.url] = page
        page += t.pages
    return start


class TopicPdfWriter:
    def __init__(self, stamper: PageNumberStamper, page_numbers: bool):
        self.stamper = stamper
        self.page_numbers = page_numbers

    def write(self, rendered: Sequence[TopicPdf], out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for idx, t in enumerate(rendered, 1):
            w = PdfWriter()
            _append(w, t.data)
            if self.page_numbers:
                self.stamper.stamp(w, [f"Page {i} of {t.pages}" for i in range(1, t.pages + 1)])
            w.add_metadata({"/Title": t.node.title, "/Producer": PRODUCER})
            p = out_dir / f"{idx:03d}-{t.node.slug}.pdf"
            _save(w, p)
            paths.append(p)
        return paths


class CombinedPdfComposer:
    def __init__(self, printer: PagePrinter, stamper: PageNumberStamper, log: Log):
        self.printer = printer
        self.stamper = stamper
        self.cfg = printer.session.cfg
        self.log = log

    def compose(self, site: Site, rendered: Sequence[TopicPdf], out: Path, title: str) -> Path:
        cfg = self.cfg
        front: list[bytes] = []
        if cfg.cover.enabled:
            cover = CoverPage(cfg.cover.title or title, cfg.cover.subtitle)
            front.append(self.printer.blank(cover.html(), FRONT_CSS))
        front_pages = sum(page_count(b) for b in front)
        toc_data = self._toc(site, rendered, front_pages) if cfg.toc.enabled else b""
        toc_pages = page_count(toc_data) if toc_data else 0
        start = start_pages(rendered, front_pages + toc_pages)

        w = PdfWriter()
        for b in front:
            _append(w, b)
        if toc_data:
            _append(w, toc_data)
        for t in rendered:
            _append(w, t.data)

        total = len(w.pages)
        if cfg.page_numbers:
            self.stamper.stamp(w, [None if i < front_pages else f"Page {i + 1} of {total}" for i in range(total)])
        if toc_data:
            w.add_outline_item(cfg.toc.title, front_pages)
        for top in site.toc:
            self._outline(w, top, start)
        w.page_mode = "/UseOutlines"
        w.add_metadata({"/Title": title, "/Producer": PRODUCER})
        _save(w, out)
        self.log(f"combined PDF: {out} ({total} pages)")
        return out

    def _toc(self, site: Site, rendered: Sequence[TopicPdf], front_pages: int) -> bytes:
        """Two-pass TOC: page numbers can change the TOC length, so render until the length converges."""
        page = TocPage(self.cfg.toc.title, tuple(site.outline(self.cfg.toc.depth)))
        toc_pages = page_count(self.printer.blank(page.html(None), FRONT_CSS))
        data = b""
        for _ in range(TOC_CONVERGE_ROUNDS):
            data = self.printer.blank(page.html(start_pages(rendered, front_pages + toc_pages)), FRONT_CSS)
            n = page_count(data)
            if n == toc_pages:
                break
            toc_pages = n
        return data

    def _outline(self, w: PdfWriter, node: TocNode, start: dict[str, int], parent: Any = None) -> None:
        first = first_page(node, start)
        if first is None:
            return
        item = w.add_outline_item(node.title, first - 1, parent=parent)
        for c in node.children:
            self._outline(w, c, start, item)
