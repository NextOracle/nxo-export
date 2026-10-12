"""Combined document: title page, TOC, then every top-level chapter on a new page."""

from __future__ import annotations

from collections import Counter

from docx.document import Document
from docx.oxml.ns import qn

from .. import xml as ox
from ..context import PassContext
from .base import DocumentPass


def _page_break_paragraph():
    p = ox.make("p")
    r = ox.make("r")
    r.append(ox.make("br", type="page"))
    p.append(r)
    return p


class ChapterBreakPass(DocumentPass):
    name = "chapters"

    def applies(self, ctx: PassContext) -> bool:
        return ctx.combined

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        h1 = doc.styles.element.find(f"{qn('w:style')}[@{qn('w:styleId')}='Heading1']")
        if h1 is not None:
            ppr = h1.find(qn("w:pPr"))
            if ppr is None:
                ppr = ox.make("pPr")
                h1.append(ppr)
            ox.put(ppr, "pageBreakBefore", val=1)
        sdt = doc.element.body.find(qn("w:sdt"))
        if sdt is not None:
            sdt.addprevious(_page_break_paragraph())
