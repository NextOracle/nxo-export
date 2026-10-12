"""OOXML post-processing of Pandoc's DOCX: the parts of the Writerside look that styles alone cannot express.

* tables    -> fixed layout at 100 % text width, measured column widths in absolute twips, Writerside grid and
               header shading as direct formatting too (LibreOffice/Google Docs ignore conditional table styles),
               rows that do not split across pages, cell text in "Table Text", wide tables scaled like the PDF
* callouts  -> borderless shaded one-cell tables, text in "Callout <Kind>"
* figures   -> own paragraph style, clamped to the available width, Writerside border on bordered screenshots
* rhythm    -> space after tables and lists as on the rendered page
* combined  -> title page, pre-populated TOC (readable before Word refreshes fields), each chapter on a new page
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from . import ooxml as ox
from .reference import GAP, half_pt, tw
from .theme import Theme

EMU_PER_TWIP = 635
FIGURE_HEADROOM_PX = 160  # same as the PDF: room for a heading above a page-tall figure
BODY_LIKE = {None, "BodyText", "FirstParagraph", "Compact", "Normal"}
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
_INTERNAL = re.compile(r"^nxo-(t|callout)-")
_ANCHOR = re.compile(r"^nxoa\d+$")


@dataclass
class PostCtx:
    theme: Theme
    text_width: int
    text_height: int = 0
    table_scales: dict[str, float] = field(default_factory=dict)
    min_scale: float = 0.75
    combined: bool = False
    toc_depth: int | None = None
    title: str | None = None
    subject: str | None = None


def postprocess(path: Path, ctx: PostCtx) -> dict:
    doc = Document(str(path))
    body = doc.element.body
    stats = {"tables": 0, "callouts": 0, "figures": 0}
    before = _style_spacing(doc)
    _layout(body, ctx.text_width, ctx, stats, before)
    _list_ends(body)
    stats["text_diagrams"] = _text_diagrams(body, ctx)
    _drop_internal_bookmarks(body)
    if ctx.combined:
        _chapter_breaks(doc)
    if ctx.toc_depth:
        _populate_toc(doc, ctx.toc_depth, ctx.combined)
        _update_fields_on_open(doc)
    cp = doc.core_properties
    if ctx.title:
        cp.title = ctx.title
    if ctx.subject:
        cp.subject = ctx.subject
    cp.author = cp.author or "nxo-ws-export"
    cp.last_modified_by = "nxo-ws-export"
    now = datetime.now(UTC).replace(microsecond=0)
    cp.created = cp.created or now
    cp.modified = now
    doc.save(str(path))
    return stats


# --------------------------------------------------------------------------- helpers


def _pstyle(p) -> str | None:
    ps = p.find(qn("w:pPr") + "/" + qn("w:pStyle"))
    return ps.get(qn("w:val")) if ps is not None else None


def _set_pstyle(p, style_id: str) -> None:
    ox.put(ox.child(p, "pPr"), "pStyle", val=style_id)


def _spacing(p, **kw) -> None:
    ppr = ox.child(p, "pPr")
    sp = ppr.find(qn("w:spacing"))
    attrs = {k.split("}")[-1]: v for k, v in sp.attrib.items()} if sp is not None else {}
    attrs.update({k: str(v) for k, v in kw.items()})
    ox.put(ppr, "spacing", **attrs)


def _style_spacing(doc) -> dict[str, int]:
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
        return before(base.get(qn("w:val")) if base is not None else None, depth + 1) if base is not None else 0

    return {sid: before(sid) for sid in styles}


def _bookmark_names(tbl) -> list[str]:
    names = []
    prev = tbl.getprevious()
    while prev is not None and ox.local(prev) in ("bookmarkStart", "bookmarkEnd"):
        if ox.local(prev) == "bookmarkStart":
            names.append(prev.get(qn("w:name")))
        prev = prev.getprevious()
    return names


def _cell_paragraphs(tc):
    return [c for c in tc if ox.local(c) == "p"]


def _text_len(el) -> int:
    return sum(len(t.text or "") for t in el.iter(qn("w:t")))


# --------------------------------------------------------------------------- tables, callouts, figures


def _layout(container, avail: int, ctx: PostCtx, stats: dict, before: dict[str, int]) -> None:
    for el in list(container):
        tag = ox.local(el)
        if tag == "p":
            _figure(el, avail, ctx.text_height - tw(FIGURE_HEADROOM_PX) if ctx.text_height else 0, stats)
        elif tag == "tbl":
            names = _bookmark_names(el)
            kind = next((n.split("-")[2] for n in names if n.startswith("nxo-callout-")), None)
            if kind:
                _callout(el, kind, avail, ctx, stats, before)
            else:
                scale = next((ctx.table_scales[n] for n in names if n in ctx.table_scales), 1.0)
                _table(el, max(ctx.min_scale, min(1.0, scale)), avail, ctx, stats, before)
            _space_after_table(el, before)


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


def _cells_with_widths(tbl, widths: list[int]):
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


def _table(tbl, k: float, avail: int, ctx: PostCtx, stats: dict, before: dict[str, int]) -> None:
    t = ctx.theme
    stats["tables"] += 1
    tblpr = ox.child(tbl, "tblPr")
    ox.put(tblpr, "tblStyle", val="Table")
    ox.put(tblpr, "tblW", w=avail, type="dxa")
    ox.borders(tblpr, "tblBorders", ("top", "left", "bottom", "right", "insideH", "insideV"), t.table_border, 6)
    ox.put(tblpr, "tblLayout", type="fixed")
    pad_y, pad_x = tw(t.cell_pad_y_px * k), tw(t.cell_pad_x_px * k)
    ox.margins(tblpr, "tblCellMar", pad_y, pad_x, pad_y, pad_x)
    widths = _grid(tbl, avail)
    for tr, tc, w in _cells_with_widths(tbl, widths):
        trpr = tr.find(qn("w:trPr"))
        header = trpr is not None and trpr.find(qn("w:tblHeader")) is not None
        if header:
            ox.shade(ox.child(tc, "tcPr"), t.table_header_fill)
        paras = _cell_paragraphs(tc)
        for p in paras:
            if _pstyle(p) in BODY_LIKE:
                _set_pstyle(p, "TableText")
        if paras:
            _spacing(paras[-1], after=0)
        _layout(tc, max(200, w - 2 * pad_x), ctx, stats, before)
    for tr in tbl.findall(qn("w:tr")):
        if tr.find(".//" + qn("w:drawing")) is None and tr.find(".//" + qn("w:tbl")) is None and _text_len(tr) < 900:
            trpr = ox.child(tr, "trPr")
            if trpr.find(qn("w:cantSplit")) is None:
                trpr.insert(0, ox.make("cantSplit"))
    if k < 0.999:
        _scale_runs(tbl, k, t)


def _scale_runs(tbl, k: float, t: Theme) -> None:
    for p in tbl.iter(qn("w:p")):
        code = _pstyle(p) == "SourceCode"
        for r in p.iter(qn("w:r")):
            rpr = ox.child(r, "rPr")
            rs = rpr.find(qn("w:rStyle"))
            sid = rs.get(qn("w:val")) if rs is not None else ""
            base = t.code.size_px if code else t.inline_code_px if sid == "VerbatimChar" else t.body.size_px
            ox.put(rpr, "sz", val=half_pt(base * k))
            ox.put(rpr, "szCs", val=half_pt(base * k))


def _callout(tbl, kind: str, avail: int, ctx: PostCtx, stats: dict, before: dict[str, int]) -> None:
    t = ctx.theme
    c = t.callouts.get(kind) or t.callouts["note"]
    stats["callouts"] += 1
    tblpr = ox.child(tbl, "tblPr")
    for old in tblpr.findall(qn("w:tblStyle")):
        tblpr.remove(old)
    ox.put(tblpr, "tblW", w=avail, type="dxa")
    ox.borders(tblpr, "tblBorders", ("top", "left", "bottom", "right", "insideH", "insideV"), "auto", 0, val="nil")
    ox.shade(tblpr, c.fill)
    ox.put(tblpr, "tblLayout", type="fixed")
    pad = tw(t.callout_pad_px)
    ox.margins(tblpr, "tblCellMar", pad, pad, pad, pad)
    ox.put(tblpr, "tblLook", val="0000", firstRow=0, lastRow=0, firstColumn=0, lastColumn=0, noHBand=1, noVBand=1)
    widths = _grid(tbl, avail)
    style = f"Callout{kind.title()}"
    for tr, tc, w in _cells_with_widths(tbl, widths):
        trpr = tr.find(qn("w:trPr"))
        if trpr is not None:
            for h in trpr.findall(qn("w:tblHeader")):
                trpr.remove(h)
        ox.shade(ox.child(tc, "tcPr"), c.fill)
        paras = _cell_paragraphs(tc)
        for p in paras:
            if _pstyle(p) in BODY_LIKE:
                _set_pstyle(p, style)
        if paras:
            _spacing(paras[-1], after=0)
        _layout(tc, max(200, w - 2 * pad), ctx, stats, before)


def _space_after_table(tbl, before: dict[str, int]) -> None:
    nxt = tbl.getnext()
    while nxt is not None and ox.local(nxt) in ("bookmarkStart", "bookmarkEnd"):
        nxt = nxt.getnext()
    if nxt is None:
        return
    if ox.local(nxt) == "tbl":  # adjacent tables would merge into one in Word
        spacer = ox.make("p")
        _spacing(spacer, before=0, after=tw(GAP["after_table"]), line=20, lineRule="exact")
        tbl.addnext(spacer)
        return
    if ox.local(nxt) == "p":
        sid = _pstyle(nxt) or "Normal"
        cur = nxt.find(qn("w:pPr") + "/" + qn("w:spacing"))
        base = int(cur.get(qn("w:before"))) if cur is not None and cur.get(qn("w:before")) else before.get(sid, 0)
        _spacing(nxt, before=base + tw(GAP["after_table"]))


def _figure(p, avail: int, max_h: int, stats: dict) -> None:
    drawings = p.findall(".//" + qn("w:drawing"))
    if not drawings:
        return
    if not any((t.text or "").strip() for t in p.iter(qn("w:t"))):
        if _pstyle(p) != "FigureBordered":
            _set_pstyle(p, "Figure")
        stats["figures"] += 1
    max_emu = avail * EMU_PER_TWIP
    bordered = _pstyle(p) == "FigureBordered"
    for d in drawings:
        ext = d.find(f".//{{{_WP}}}extent")
        if ext is None:
            continue
        cx, cy = int(ext.get("cx")), int(ext.get("cy"))
        ratio = min(1.0, max_emu / cx if cx else 1.0, (max_h * EMU_PER_TWIP) / cy if (cy and max_h > 0) else 1.0)
        if ratio < 0.999:
            cx, cy = round(cx * ratio), round(cy * ratio)
            ext.set("cx", str(cx))
            ext.set("cy", str(cy))
            for a in d.iter(f"{{{_A}}}ext"):
                a.set("cx", str(cx))
                a.set("cy", str(cy))
        if bordered:
            sppr = d.find(f".//{{{_PIC}}}spPr")
            if sppr is not None and sppr.find(f"{{{_A}}}ln") is None:
                ln = sppr.makeelement(f"{{{_A}}}ln", {"w": "9525"})
                fill = ln.makeelement(f"{{{_A}}}solidFill", {})
                fill.append(fill.makeelement(f"{{{_A}}}srgbClr", {"val": "D1D1D2"}))
                ln.append(fill)
                sppr.append(ln)


# --------------------------------------------------------------------------- rhythm, bookmarks


MONO_ADVANCE = 0.6        # JetBrains Mono / Consolas glyph advance, in em
DIAGRAM_KEEP_MAX_LINES = 60  # longer listings may break across pages


def _style_id(p) -> str | None:
    st = p.find(qn("w:pPr") + "/" + qn("w:pStyle"))
    return st.get(qn("w:val")) if st is not None else None


def _text_diagrams(body, ctx: PostCtx) -> int:
    """Group consecutive "Text Diagram" lines: keep a diagram on one page, end it with the code-block gap, and
    shrink the font when the longest line is wider than the text column (box art must never wrap)."""
    groups, seen = [], set()
    for p in body.iter(qn("w:p")):
        if id(p) in seen or _style_id(p) != "TextDiagram":
            continue
        g = [p]
        nxt = p.getnext()
        while nxt is not None and ox.local(nxt) == "p" and _style_id(nxt) == "TextDiagram":
            g.append(nxt)
            nxt = nxt.getnext()
        seen.update(id(x) for x in g)
        groups.append(g)
    size_px = ctx.theme.code.size_px
    for g in groups:
        longest = max(len("".join(t.text or "" for t in p.iter(qn("w:t")))) for p in g)
        avail = ctx.text_width
        cell = g[0].getparent()
        if ox.local(cell) == "tc":
            w = cell.find(qn("w:tcPr") + "/" + qn("w:tcW"))
            avail = int(w.get(qn("w:w"))) if w is not None else avail
        need = tw(longest * MONO_ADVANCE * size_px)
        sz = half_pt(size_px * avail / need) if need > avail else None
        for i, p in enumerate(g):
            if i < len(g) - 1 and len(g) <= DIAGRAM_KEEP_MAX_LINES:
                ox.put(ox.child(p, "pPr"), "keepNext", val=1)
            if sz:
                for r in p.findall(qn("w:r")):
                    rpr = ox.child(r, "rPr")
                    ox.put(rpr, "sz", val=sz)
                    ox.put(rpr, "szCs", val=sz)
        _spacing(g[-1], after=tw(GAP["code"]))
    return len(groups)


def _list_ends(body) -> None:
    for p in body.iter(qn("w:p")):
        if p.find(qn("w:pPr") + "/" + qn("w:numPr")) is None:
            continue
        nxt = p.getnext()
        if nxt is not None and ox.local(nxt) == "p" and nxt.find(qn("w:pPr") + "/" + qn("w:numPr")) is not None:
            continue
        in_cell = ox.local(p.getparent()) == "tc"
        _spacing(p, after=0 if (in_cell and nxt is None) else tw(GAP["list_end"]))


def _drop_internal_bookmarks(body) -> None:
    """Remove table/callout tags; hide anchor bookmarks (a leading underscore hides them in Word's list --
    Pandoc would hash such names, so the underscore is added here, together with the hyperlinks to them)."""
    ids = set()
    for b in list(body.iter(qn("w:bookmarkStart"))):
        name = b.get(qn("w:name")) or ""
        if _INTERNAL.match(name):
            ids.add(b.get(qn("w:id")))
            b.getparent().remove(b)
        elif _ANCHOR.match(name):
            b.set(qn("w:name"), "_" + name)
    for h in body.iter(qn("w:hyperlink")):
        a = h.get(qn("w:anchor")) or ""
        if _ANCHOR.match(a):
            h.set(qn("w:anchor"), "_" + a)
    for b in list(body.iter(qn("w:bookmarkEnd"))):
        if b.get(qn("w:id")) in ids:
            b.getparent().remove(b)


# --------------------------------------------------------------------------- combined document


def _page_break_paragraph():
    p = ox.make("p")
    r = ox.make("r")
    r.append(ox.make("br", type="page"))
    p.append(r)
    return p


def _chapter_breaks(doc) -> None:
    """Title page, TOC, then every top-level chapter on a new page (Heading 1 'page break before')."""
    h1 = doc.styles.element.find(f"{qn('w:style')}[@{qn('w:styleId')}='Heading1']")
    if h1 is not None:
        ppr = h1.find(qn("w:pPr"))
        if ppr is None:
            ppr = ox.make("pPr")
            h1.append(ppr)
        ox.put(ppr, "pageBreakBefore", val=1)
    body = doc.element.body
    sdt = body.find(qn("w:sdt"))
    if sdt is not None:
        sdt.addprevious(_page_break_paragraph())


def _heading_level(p, ids: dict[str, int]) -> int | None:
    return ids.get(_pstyle(p) or "")


def _populate_toc(doc, depth: int, combined: bool) -> None:
    """Fill the TOC field result with the headings (as links), so the TOC reads correctly before Word refreshes
    page numbers, and in viewers that never do (LibreOffice preview, Google Docs, web previews)."""
    body = doc.element.body
    sdt = body.find(qn("w:sdt"))
    if sdt is None:
        return
    content = sdt.find(qn("w:sdtContent"))
    field_p = next((p for p in content.findall(qn("w:p")) if p.find(".//" + qn("w:instrText")) is not None), None)
    if field_p is None:
        return
    by_name = {s.name.lower(): s.style_id for s in doc.styles if s.name}
    levels = {by_name.get(f"heading {i}", f"Heading{i}"): i for i in range(1, depth + 1)}
    entries: list[tuple[int, str, str]] = []
    for p in body.iter(qn("w:p")):
        if p.getparent() is not body:
            continue
        lvl = _heading_level(p, levels)
        if not lvl:
            continue
        text = "".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
        bm = p.find(qn("w:bookmarkStart"))
        prev = p.getprevious()
        while bm is None and prev is not None and ox.local(prev) in ("bookmarkStart", "bookmarkEnd"):
            if ox.local(prev) == "bookmarkStart":
                bm = prev
            prev = prev.getprevious()
        if text and bm is not None:
            entries.append((lvl, text, bm.get(qn("w:name"))))
    if not entries:
        return

    begin, instr, sep, end = (list(field_p.iter(qn("w:fldChar")))[0], field_p.find(".//" + qn("w:instrText")),
                              list(field_p.iter(qn("w:fldChar")))[1], list(field_p.iter(qn("w:fldChar")))[-1])

    def run_of(el):
        r = ox.make("r")
        r.append(el)
        return r

    paras = []
    for i, (lvl, text, anchor) in enumerate(entries):
        p = ox.make("p")
        ox.put(ox.child(p, "pPr"), "pStyle", val=by_name.get(f"toc {lvl}", f"TOC{lvl}"))
        if i == 0:
            for el in (begin, instr, sep):
                el.getparent().remove(el)
                p.append(run_of(el))
        link = ox.make("hyperlink", anchor=anchor, history=1)
        r = ox.make("r")
        t = ox.make("t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text
        r.append(t)
        link.append(r)
        p.append(link)
        paras.append(p)
    end.getparent().remove(end)
    paras[-1].append(run_of(end))
    for p in paras:
        field_p.addprevious(p)
    field_p.getparent().remove(field_p)


def _update_fields_on_open(doc) -> None:
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is None:
        settings.append(ox.make("updateFields", val="true"))
