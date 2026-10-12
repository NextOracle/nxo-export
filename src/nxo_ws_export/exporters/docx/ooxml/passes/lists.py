"""List rhythm: the space after the last item of a list, as on the rendered page."""

from __future__ import annotations

from collections import Counter

from docx.document import Document
from docx.oxml.ns import qn

from .....domain.units import twips
from ...theme import GAP
from .. import xml as ox
from ..context import PassContext
from .base import DocumentPass


def _is_item(p) -> bool:
    return p.find(qn("w:pPr") + "/" + qn("w:numPr")) is not None


class ListSpacingPass(DocumentPass):
    name = "lists"

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        for p in doc.element.body.iter(qn("w:p")):
            if not _is_item(p):
                continue
            nxt = p.getnext()
            if nxt is not None and ox.local(nxt) == "p" and _is_item(nxt):
                continue
            in_cell = ox.local(p.getparent()) == "tc"
            ox.spacing(p, after=0 if (in_cell and nxt is None) else twips(GAP["list_end"]))
