"""Text diagrams (box-drawing art from plain code blocks, one "Text Diagram" paragraph per line): keep a diagram
on one page, end it with the code-block gap, and shrink the font when the longest line is wider than the column
(box art must never wrap)."""

from __future__ import annotations

from collections import Counter

from docx.document import Document
from docx.oxml.ns import qn

from .....domain.units import half_points, twips
from ...theme import GAP
from .. import xml as ox
from ..context import PassContext
from .base import DocumentPass

STYLE_ID = "TextDiagram"
MONO_ADVANCE = 0.6           # JetBrains Mono / Consolas glyph advance, in em
DIAGRAM_KEEP_MAX_LINES = 60  # longer listings may break across pages


class TextDiagramPass(DocumentPass):
    name = "text_diagrams"

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        groups = _groups(doc.element.body)
        for g in groups:
            self._fit(g, ctx)
        stats["text_diagrams"] += len(groups)

    @staticmethod
    def _fit(g: list, ctx: PassContext) -> None:
        size_px = ctx.theme.code.size_px
        longest = max(len(ox.text_of(p)) for p in g)
        avail = ctx.text_width
        cell = g[0].getparent()
        if ox.local(cell) == "tc":
            w = cell.find(qn("w:tcPr") + "/" + qn("w:tcW"))
            avail = int(w.get(qn("w:w"))) if w is not None else avail
        need = twips(longest * MONO_ADVANCE * size_px)
        sz = half_points(size_px * avail / need) if need > avail else None
        for i, p in enumerate(g):
            if i < len(g) - 1 and len(g) <= DIAGRAM_KEEP_MAX_LINES:
                ox.put(ox.child(p, "pPr"), "keepNext", val=1)
            if sz:
                for r in p.findall(qn("w:r")):
                    rpr = ox.child(r, "rPr")
                    ox.put(rpr, "sz", val=sz)
                    ox.put(rpr, "szCs", val=sz)
        ox.spacing(g[-1], after=twips(GAP["code"]))


def _groups(body) -> list[list]:
    """Runs of consecutive Text Diagram paragraphs."""
    groups, seen = [], set()
    for p in body.iter(qn("w:p")):
        if id(p) in seen or ox.pstyle(p) != STYLE_ID:
            continue
        g = [p]
        nxt = p.getnext()
        while nxt is not None and ox.local(nxt) == "p" and ox.pstyle(nxt) == STYLE_ID:
            g.append(nxt)
            nxt = nxt.getnext()
        seen.update(id(x) for x in g)
        groups.append(g)
    return groups
