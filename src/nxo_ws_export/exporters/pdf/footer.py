"""Page numbers stamped as an overlay, in the Writerside @page footer style, continuous across documents."""

from __future__ import annotations

import html
import io

from pypdf import PdfReader, PdfWriter

from ...browser import BrowserSession

# Mirrors the Writerside @page footer (app.css: overline style, "Page n of N"), so numbering looks native but
# can run continuously across a combined document.
FOOTER_CSS = """
.nxo-footer { position: absolute; left: 0; right: 0; text-align: center;
  letter-spacing: .1em; text-transform: uppercase; color: var(--nxo-fg, #19191c); opacity: .75;
  font-family: var(--rs-font-family-ui, var(--rs-font-family-jb-sans, "JetBrains Sans", Inter, system-ui, sans-serif));
  font-size: var(--rs-overline-font-size, 13px); font-weight: var(--rs-font-weight-semi-bold, 530);
  line-height: var(--rs-overline-line-height, 18px); }
"""


class PageNumberStamper:
    def __init__(self, session: BrowserSession):
        self.session = session

    def stamp(self, writer: PdfWriter, labels: list[str | None]) -> None:
        """Overlay footer labels (None = no label) on the pages of `writer`."""
        if not any(labels):
            return
        box = writer.pages[0].mediabox
        w, h = float(box.width), float(box.height)
        bottom = f"calc(({self.session.cfg.page.margin_bottom}) / 2 - 9px)"
        sheets = "".join(
            f'<div class="nxo-sheet"><div class="nxo-footer" style="bottom:{bottom}">{html.escape(lbl or "")}</div></div>'
            for lbl in labels
        )
        css = FOOTER_CSS + (
            f"html, body {{ background: transparent !important; margin: 0 !important; }}"
            f".nxo-sheet {{ position: relative; width: {w}pt; height: {h}pt; break-after: page; overflow: hidden; }}"
        )
        page = self.session.open_blank(sheets, css)
        try:
            # open_blank pins the theme background inline (!important beats the stylesheet); the overlay must be
            # transparent, otherwise Chromium paints an opaque sheet over the first page.
            page.evaluate(
                "for (const e of [document.documentElement, document.body]) e.style.removeProperty('background')")
            page.add_style_tag(content=f"@page {{ size: {w}pt {h}pt; margin: 0; @bottom-center {{ content: none; }} }}")
            overlay = PdfReader(io.BytesIO(page.pdf(print_background=False, prefer_css_page_size=True)))
        finally:
            page.close()
        for i, target in enumerate(writer.pages):
            if i < len(overlay.pages) and labels[i]:
                target.merge_page(overlay.pages[i])
