"""A post-processing pass: one concern, applied to the whole document."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from typing import ClassVar

from docx.document import Document
from docx.oxml.ns import qn

from .. import xml as ox
from ..context import PassContext

MIN_CELL_CONTENT = 200
"""Twips; narrower cells still get this much room for nested content."""


class DocumentPass(ABC):
    name: ClassVar[str]

    def applies(self, ctx: PassContext) -> bool:
        return True

    @abstractmethod
    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None: ...


def containers(body):
    """The body and every table cell, outermost first: the places block content (p, tbl) lives in."""
    yield body
    yield from body.iter(qn("w:tc"))


def content_width(container, text_width: int) -> int:
    """Usable width (twips) in a container: the text column, or a cell's width minus its table's cell margins
    (set by TableLayoutPass)."""
    if ox.local(container) != "tc":
        return text_width
    w = container.find(qn("w:tcPr") + "/" + qn("w:tcW"))
    if w is None:
        return text_width
    tbl = next(a for a in container.iterancestors() if ox.local(a) == "tbl")
    pad = 0
    mar = tbl.find(qn("w:tblPr") + "/" + qn("w:tblCellMar"))
    if mar is not None:
        pad = sum(int(s.get(qn("w:w"))) for s in mar if ox.local(s) in ("left", "right"))
    return max(MIN_CELL_CONTENT, int(w.get(qn("w:w"))) - pad)
