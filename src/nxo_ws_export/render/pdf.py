"""Stage 2a: PDF. Each topic is printed by Chromium from the real Writerside page, then assembled with pypdf."""

from __future__ import annotations

import html
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from playwright.sync_api import Page
from pypdf import PdfReader, PdfWriter

from ..config import RenderCfg
from ..site import Site, TocNode
from .browser import Session

# Mirrors the Writerside @page footer (app.css: overline style, "Page n of N"), so numbering looks native but
# can run continuously across a combined document.
FOOTER_CSS = """
.nxo-footer { position: absolute; left: 0; right: 0; text-align: center;
  letter-spacing: .1em; text-transform: uppercase; color: var(--nxo-fg, #19191c); opacity: .75;
  font-family: var(--rs-font-family-ui, var(--rs-font-family-jb-sans, "JetBrains Sans", Inter, system-ui, sans-serif));
  font-size: var(--rs-overline-font-size, 13px); font-weight: var(--rs-font-weight-semi-bold, 530);
  line-height: var(--rs-overline-line-height, 18px); }
"""

TOC_CSS = """
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


@dataclass
class TopicPdf:
    node: TocNode
    data: bytes
    pages: int


def page_css(cfg: RenderCfg, background: str | None = None) -> str:
    p = cfg.page
    # Chromium paints margins with the colour-scheme canvas, not the root background; @page background fixes it.
    bg = f" background: {background};" if background else ""
    return (
        f"@page {{ size: {p.size}; margin: {p.margin_top} {p.margin_x} {p.margin_bottom} {p.margin_x};{bg}"
        " @bottom-center { content: none; } }"
    )


def _print(page: Page, cfg: RenderCfg, transparent: bool = False) -> bytes:
    bg = None if transparent else page.evaluate("getComputedStyle(document.documentElement).backgroundColor")
    page.add_style_tag(content=page_css(cfg, bg))
    return page.pdf(print_background=not transparent, prefer_css_page_size=True)


def render_topic(session: Session, node: TocNode) -> TopicPdf:
    page, _ = session.open_topic(node)
    try:
        data = _print(page, session.cfg)
    finally:
        page.close()
    return TopicPdf(node, data, len(PdfReader(io.BytesIO(data)).pages))


def _render_blank(session: Session, body: str, css: str = "", transparent: bool = False) -> bytes:
    page = session.open_blank(body, css)
    try:
        return _print(page, session.cfg, transparent=transparent)
    finally:
        page.close()


def stamp_page_numbers(session: Session, writer: PdfWriter, labels: list[str | None]) -> None:
    """Overlay footer labels (None = no label) rendered with the Writerside footer style."""
    if not any(labels):
        return
    box = writer.pages[0].mediabox
    w, h = float(box.width), float(box.height)
    bottom = f"calc(({session.cfg.page.margin_bottom}) / 2 - 9px)"
    sheets = "".join(
        f'<div class="nxo-sheet"><div class="nxo-footer" style="bottom:{bottom}">{html.escape(lbl or "")}</div></div>'
        for lbl in labels
    )
    css = FOOTER_CSS + (
        f"html, body {{ background: transparent !important; margin: 0 !important; }}"
        f".nxo-sheet {{ position: relative; width: {w}pt; height: {h}pt; break-after: page; overflow: hidden; }}"
    )
    page = session.open_blank(sheets, css)
    try:
        # open_blank pins the theme background inline (!important beats the stylesheet); the overlay must be
        # transparent, otherwise Chromium paints an opaque sheet over the first page.
        page.evaluate("for (const e of [document.documentElement, document.body]) e.style.removeProperty('background')")
        page.add_style_tag(content=f"@page {{ size: {w}pt {h}pt; margin: 0; @bottom-center {{ content: none; }} }}")
        overlay = PdfReader(io.BytesIO(page.pdf(print_background=False, prefer_css_page_size=True)))
    finally:
        page.close()
    for i, target in enumerate(writer.pages):
        if i < len(overlay.pages) and labels[i]:
            target.merge_page(overlay.pages[i])


def _toc_entries(site: Site, depth: int) -> list[TocNode]:
    out: list[TocNode] = []

    def visit(n: TocNode) -> None:
        if n.level < depth:
            out.append(n)
            for c in n.children:
                visit(c)

    for top in site.toc:
        visit(top)
    return out


def _first_page(node: TocNode, start: dict[str, int]) -> int | None:
    for n in node.walk():
        if n.url and n.url in start:
            return start[n.url]
    return None


def _toc_html(title: str, entries: list[TocNode], start: dict[str, int] | None) -> str:
    items = []
    for n in entries:
        num = _first_page(n, start) if start is not None else 888
        if num is None:
            continue
        items.append(
            f'<li class="l{n.level}" style="padding-left:{n.level * 1.4}em"><span class="t">{html.escape(n.title)}'
            f'</span><span class="d"></span><span class="n">{num}</span></li>'
        )
    return (
        '<div class="app__article"><div class="article nxo-doc">'
        f'<h1 class="title article__h1">{html.escape(title)}</h1><ul class="nxo-toc">{"".join(items)}</ul></div></div>'
    )


def _cover_html(title: str, subtitle: str | None) -> str:
    sub = f'<div class="sub">{html.escape(subtitle)}</div>' if subtitle else ""
    return (
        '<div class="app__article"><div class="article nxo-doc nxo-cover">'
        f'<h1 class="title article__h1">{html.escape(title)}</h1>{sub}'
        f'<div class="date">{date.today().isoformat()}</div></div></div>'
    )


def _append(writer: PdfWriter, data: bytes) -> None:
    writer.append(PdfReader(io.BytesIO(data)), import_outline=False)


def write_topic_pdfs(session: Session, rendered: list[TopicPdf], out_dir: Path, page_numbers: bool) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for idx, t in enumerate(rendered, 1):
        w = PdfWriter()
        _append(w, t.data)
        if page_numbers:
            stamp_page_numbers(session, w, [f"Page {i} of {t.pages}" for i in range(1, t.pages + 1)])
        w.add_metadata({"/Title": t.node.title, "/Producer": "nxo-ws-export"})
        p = out_dir / f"{idx:03d}-{t.node.slug}.pdf"
        with p.open("wb") as fh:
            w.write(fh)
        paths.append(p)
    return paths


def write_combined_pdf(
    session: Session, site: Site, rendered: list[TopicPdf], out: Path, title: str, log: Callable[[str], None]
) -> Path:
    cfg = session.cfg
    front: list[bytes] = []
    if cfg.cover.enabled:
        front.append(_render_blank(session, _cover_html(cfg.cover.title or title, cfg.cover.subtitle), TOC_CSS))
    front_pages = sum(len(PdfReader(io.BytesIO(b)).pages) for b in front)

    toc_data = b""
    toc_pages = 0
    start: dict[str, int] = {}
    if cfg.toc.enabled:
        entries = _toc_entries(site, cfg.toc.depth)
        toc_pages = len(PdfReader(io.BytesIO(
            _render_blank(session, _toc_html(cfg.toc.title, entries, None), TOC_CSS))).pages)
        for _ in range(3):  # page numbers can change the TOC length; converge
            start = _start_pages(rendered, front_pages + toc_pages)
            toc_data = _render_blank(session, _toc_html(cfg.toc.title, entries, start), TOC_CSS)
            n = len(PdfReader(io.BytesIO(toc_data)).pages)
            if n == toc_pages:
                break
            toc_pages = n
    start = _start_pages(rendered, front_pages + toc_pages)

    w = PdfWriter()
    for b in front:
        _append(w, b)
    if toc_data:
        _append(w, toc_data)
    for t in rendered:
        _append(w, t.data)

    total = len(w.pages)
    if cfg.page_numbers:
        labels = [None if i < front_pages else f"Page {i + 1} of {total}" for i in range(total)]
        stamp_page_numbers(session, w, labels)

    if toc_data:
        w.add_outline_item(cfg.toc.title, front_pages)

    def outline(node: TocNode, parent=None) -> None:
        first = _first_page(node, start)
        if first is None:
            return
        item = w.add_outline_item(node.title, first - 1, parent=parent)
        for c in node.children:
            outline(c, item)

    for top in site.toc:
        outline(top)
    w.page_mode = "/UseOutlines"
    w.add_metadata({"/Title": title, "/Producer": "nxo-ws-export"})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        w.write(fh)
    log(f"combined PDF: {out} ({total} pages)")
    return out


def _start_pages(rendered: list[TopicPdf], offset: int) -> dict[str, int]:
    start, page = {}, offset + 1
    for t in rendered:
        if t.node.url:
            start[t.node.url] = page
        page += t.pages
    return start
