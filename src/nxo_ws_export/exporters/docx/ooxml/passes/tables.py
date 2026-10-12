"""Tables: data tables in the Writerside grid, callouts as shaded boxes (Strategy per table kind).

Data tables -> fixed layout at 100 % text width, measured column widths in absolute twips, Writerside grid and
header shading as direct formatting too (LibreOffice/Google Docs ignore conditional table styles), rows that do
not split across pages, cell text in "Table Text", wide tables scaled like the PDF.
Callouts -> borderless shaded one-cell tables, text in "Callout <Kind>"."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterator

from docx.document import Document
from docx.oxml.ns import qn

from .....domain.units import half_points, twips
from ...theme import GAP
from .. import xml as ox
from ..context import PassContext
from .base import MIN_CELL_CONTENT, DocumentPass

BODY_LIKE = {None, "BodyText", "FirstParagraph", "Compact", "Normal"}
ALL_BORDERS = ("top", "left", "bottom", "right", "insideH", "insideV")
CANT_SPLIT_MAX_CHARS = 900
"""Rows longer than this may split across pages (otherwise Word pushes a page-tall row to the next page)."""
CALLOUT_TAG = "nxo-callout-"


class TableLayoutPass(DocumentPass):
    name = "tables"

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        TableLayout(ctx, stats, _style_space_before(doc)).layout(doc.element.body, ctx.text_width)


class TableLayout:
    """One run over one document. Recursive, because a cell's width is only known once its table is laid out."""

    def __init__(self, ctx: PassContext, stats: Counter[str], before: dict[str, int]):
        self.ctx = ctx
        self.stats = stats
        self.before = before

    def layout(self, container, avail: int) -> None:
        for el in list(container):
            if ox.local(el) != "tbl":
                continue
            names = _bookmark_names(el)
            kind = next((n.split("-")[2] for n in names if n.startswith(CALLOUT_TAG)), None)
            fmt: TableFormatter
            if kind:
                fmt = CalloutFormatter(self, kind)
            else:
                scale = next((self.ctx.table_scales[n] for n in names if n in self.ctx.table_scales), 1.0)
                fmt = DataTableFormatter(self, max(self.ctx.min_scale, min(1.0, scale)))
            fmt.format(el, avail)
            self.stats[fmt.stat] += 1
            _space_after_table(el, self.before)


class TableFormatter(ABC):
    stat: str

    def __init__(self, owner: TableLayout):
        self.owner = owner
        self.theme = owner.ctx.theme

    @abstractmethod
    def format(self, tbl, avail: int) -> None: ...

    def cells(self, tbl, avail: int) -> Iterator[tuple[object, object, int]]:
        """(tr, tc, width) with the grid stretched to `avail` and every tcW in absolute twips."""
        widths = _grid(tbl, avail)
        for tr in tbl.findall(qn("w:tr")):
            col = 0
            for tc in tr.findall(qn("w:tc")):
                tcpr = ox.child(tc, "tcPr")
                span_el = tcpr.find(qn("w:gridSpan"))
                span = int(span_el.get(qn("w:val"))) if span_el is not None else 1
                w = sum(widths[col:col + span]) or widths[-1]
                ox.put(tcpr, "tcW", w=w, type="dxa")
                yield tr, tc, w
                col += span

    def cell_text(self, tc, style_id: str) -> None:
        paras = [c for c in tc if ox.local(c) == "p"]
        for p in paras:
            if ox.pstyle(p) in BODY_LIKE:
                ox.set_pstyle(p, style_id)
        if paras:
            ox.spacing(paras[-1], after=0)


class DataTableFormatter(TableFormatter):
    stat = "tables"

    def __init__(self, owner: TableLayout, scale: float):
        super().__init__(owner)
        self.k = scale

    def format(self, tbl, avail: int) -> None:
        t, k = self.theme, self.k
        tblpr = ox.child(tbl, "tblPr")
        ox.put(tblpr, "tblStyle", val="Table")
        ox.put(tblpr, "tblW", w=avail, type="dxa")
        ox.borders(tblpr, "tblBorders", ALL_BORDERS, t.table_border, 6)
        ox.put(tblpr, "tblLayout", type="fixed")
        pad_y, pad_x = twips(t.cell_pad_y_px * k), twips(t.cell_pad_x_px * k)
        ox.margins(tblpr, "tblCellMar", pad_y, pad_x, pad_y, pad_x)
        for tr, tc, w in self.cells(tbl, avail):
            trpr = tr.find(qn("w:trPr"))
            if trpr is not None and trpr.find(qn("w:tblHeader")) is not None:
                ox.shade(ox.child(tc, "tcPr"), t.table_header_fill)
            self.cell_text(tc, "TableText")
            self.owner.layout(tc, max(MIN_CELL_CONTENT, w - 2 * pad_x))
        for tr in tbl.findall(qn("w:tr")):
            if (tr.find(".//" + qn("w:drawing")) is None and tr.find(".//" + qn("w:tbl")) is None
                    and ox.text_len(tr) < CANT_SPLIT_MAX_CHARS):
                trpr = ox.child(tr, "trPr")
                if trpr.find(qn("w:cantSplit")) is None:
                    trpr.insert(0, ox.make("cantSplit"))
        if k < 0.999:
            self._scale_runs(tbl)

    def _scale_runs(self, tbl) -> None:
        t = self.theme
        for p in tbl.iter(qn("w:p")):
            code = ox.pstyle(p) == "SourceCode"
            for r in p.iter(qn("w:r")):
                rpr = ox.child(r, "rPr")
                rs = rpr.find(qn("w:rStyle"))
                sid = rs.get(qn("w:val")) if rs is not None else ""
                base = t.code.size_px if code else t.inline_code_px if sid == "VerbatimChar" else t.body.size_px
                ox.put(rpr, "sz", val=half_points(base * self.k))
                ox.put(rpr, "szCs", val=half_points(base * self.k))


class CalloutFormatter(TableFormatter):
    stat = "callouts"

    def __init__(self, owner: TableLayout, kind: str):
        super().__init__(owner)
        self.kind = kind

    def format(self, tbl, avail: int) -> None:
        t = self.theme
        c = t.callout(self.kind)
        tblpr = ox.child(tbl, "tblPr")
        for old in tblpr.findall(qn("w:tblStyle")):
            tblpr.remove(old)
        ox.put(tblpr, "tblW", w=avail, type="dxa")
        ox.borders(tblpr, "tblBorders", ALL_BORDERS, "auto", 0, val="nil")
        ox.shade(tblpr, c.fill)
        ox.put(tblpr, "tblLayout", type="fixed")
        pad = twips(t.callout_pad_px)
        ox.margins(tblpr, "tblCellMar", pad, pad, pad, pad)
        ox.put(tblpr, "tblLook", val="0000", firstRow=0, lastRow=0, firstColumn=0, lastColumn=0, noHBand=1,
               noVBand=1)
        style = f"Callout{self.kind.title()}"
        for tr, tc, w in self.cells(tbl, avail):
            trpr = tr.find(qn("w:trPr"))
            if trpr is not None:
                for h in trpr.findall(qn("w:tblHeader")):
                    trpr.remove(h)
            ox.shade(ox.child(tc, "tcPr"), c.fill)
            self.cell_text(tc, style)
            self.owner.layout(tc, max(MIN_CELL_CONTENT, w - 2 * pad))


# --------------------------------------------------------------------------- helpers


def _style_space_before(doc: Document) -> dict[str, int]:
    """style id -> effective space-before (twips), following basedOn."""
    styles = {s.get(qn("w:styleId")): s for s in doc.styles.element.findall(qn("w:style"))}

    def before(sid: str | None, depth: int = 0) -> int:
        s = styles.get(sid or "Normal")
        if s is None or depth > 10:
            return 0
        sp = s.find(qn("w:pPr") + "/" + qn("w:spacing"))
        if sp is not None and sp.get(qn("w:before")) is not None:
            return int(sp.get(qn("w:before")))
        base = s.find(qn("w:basedOn"))
        return before(base.get(qn("w:val")), depth + 1) if base is not None else 0

    return {sid: before(sid) for sid in styles}


def _bookmark_names(tbl) -> list[str]:
    """Pandoc puts the bookmark of an id'd table just before it."""
    names = []
    prev = tbl.getprevious()
    while prev is not None and ox.local(prev) in ("bookmarkStart", "bookmarkEnd"):
        if ox.local(prev) == "bookmarkStart":
            names.append(prev.get(qn("w:name")))
        prev = prev.getprevious()
    return names


def _grid(tbl, avail: int) -> list[int]:
    grid = tbl.find(qn("w:tblGrid"))
    cols = [int(g.get(qn("w:w")) or 0) for g in grid.findall(qn("w:gridCol"))] if grid is not None else []
    total = sum(cols) or 1
    widths = [max(1, round(avail * c / total)) for c in cols] if cols else [avail]
    widths[-1] += avail - sum(widths)
    if grid is not None:
        for g, w in zip(grid.findall(qn("w:gridCol")), widths, strict=False):
            g.set(qn("w:w"), str(w))
    return widths


def _space_after_table(tbl, before: dict[str, int]) -> None:
    nxt = tbl.getnext()
    while nxt is not None and ox.local(nxt) in ("bookmarkStart", "bookmarkEnd"):
        nxt = nxt.getnext()
    if nxt is None:
        return
    if ox.local(nxt) == "tbl":  # adjacent tables would merge into one in Word
        spacer = ox.make("p")
        ox.spacing(spacer, before=0, after=twips(GAP["after_table"]), line=20, lineRule="exact")
        tbl.addnext(spacer)
        return
    if ox.local(nxt) == "p":
        sid = ox.pstyle(nxt) or "Normal"
        cur = nxt.find(qn("w:pPr") + "/" + qn("w:spacing"))
        base = int(cur.get(qn("w:before"))) if cur is not None and cur.get(qn("w:before")) else before.get(sid, 0)
        ox.spacing(nxt, before=base + twips(GAP["after_table"]))
