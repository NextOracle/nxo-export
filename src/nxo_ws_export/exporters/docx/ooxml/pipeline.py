"""Pandoc's DOCX -> the Writerside look: an ordered chain of single-purpose OOXML passes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from docx import Document

from .context import PassContext
from .passes import (
    BookmarkPass,
    ChapterBreakPass,
    CorePropertiesPass,
    DocumentPass,
    FigurePass,
    ListSpacingPass,
    TableLayoutPass,
    TextDiagramPass,
    TocPass,
)

DEFAULT_PASSES: tuple[DocumentPass, ...] = (
    TableLayoutPass(),   # data tables + callouts (reads the nxo-* bookmarks, so before BookmarkPass)
    FigurePass(),        # needs the cell widths set by TableLayoutPass
    ListSpacingPass(),
    TextDiagramPass(),   # needs the cell widths set by TableLayoutPass
    BookmarkPass(),
    ChapterBreakPass(),
    TocPass(),
    CorePropertiesPass(),
)


class PostProcessor:
    def __init__(self, passes: Sequence[DocumentPass] = DEFAULT_PASSES):
        self.passes = tuple(passes)

    def run(self, path: Path, ctx: PassContext) -> Counter[str]:
        """Rewrite the DOCX at `path` in place; returns counters (tables, callouts, figures, text_diagrams)."""
        doc = Document(str(path))
        stats: Counter[str] = Counter()
        for p in self.passes:
            if p.applies(ctx):
                p.run(doc, ctx, stats)
        doc.save(str(path))
        return stats
