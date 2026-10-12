"""reference.docx: the Writerside light theme expressed as Word styles (ADR-9).

Everything a business analyst edits is a named style (Body Text, Heading 1-6, Source Code, Table Text, Callout *),
so Word's style pane, "update style to match" and corporate re-theming all work. Spacing reproduces the vertical
rhythm measured on the rendered site (gaps in CSS px; Word adds space-after and space-before)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from lxml import etree

from ...config import DocxCfg, PageCfg
from ...geometry import length_px, page_size_px
from . import ooxml as ox
from .theme import Text, Theme, css_color_to_hex

# Vertical rhythm of the default theme, in CSS px (measured gaps between rendered blocks).
GAP = {
    "para": 24, "compact": 6, "list_end": 24, "code": 24, "figure": 24, "after_table": 12, "cell_para": 8,
    "h1": (0, 32), "h2": (40, 32), "h3": (24, 24), "h4": (8, 16), "tab": (16, 8),
}
MUTED = 0.7  # Writerside secondary text = text colour at 70 %


def tw(px_: float) -> int:
    """CSS px -> twips (1px = 0.75pt = 15 twips)."""
    return round(px_ * 15)


def half_pt(px_: float) -> int:
    return max(2, round(px_ * 0.75 * 2))


def text_width_twips(page: PageCfg) -> int:
    w, _ = page_size_px(page.size)
    return tw(w - 2 * length_px(page.margin_x))


def text_height_twips(page: PageCfg) -> int:
    _, h = page_size_px(page.size)
    return tw(h - length_px(page.margin_top) - length_px(page.margin_bottom))


def blend(color: str, alpha: float) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return css_color_to_hex(f"rgba({r},{g},{b},{alpha})") or color


# --------------------------------------------------------------------------- style plumbing

_STYLE_ORDER = ("name aliases basedOn next link autoRedefine hidden uiPriority semiHidden unhideWhenUsed qFormat "
                "locked personal personalCompose personalReply rsid pPr rPr tblPr trPr tcPr tblStylePr").split()


def _style_child(style_el, tag: str):
    el = style_el.find(qn(f"w:{tag}"))
    if el is not None:
        return el
    el = ox.make(tag)
    idx = _STYLE_ORDER.index(tag)
    for i, c in enumerate(style_el):
        if ox.local(c) in _STYLE_ORDER and _STYLE_ORDER.index(ox.local(c)) > idx:
            style_el.insert(i, el)
            return el
    style_el.append(el)
    return el


def _style(doc, name: str, kind=WD_STYLE_TYPE.PARAGRAPH, base: str | None = "Normal"):
    try:
        st = doc.styles[name]
    except KeyError:
        st = doc.styles.add_style(name, kind)
        if base:
            st.base_style = doc.styles[base]
    st.hidden = False
    st.quick_style = True
    return st


def _para(st, *, font: str | None = None, text: Text | None = None, color: str | None = None,
          bold: bool | None = None, before_px: float | None = None, after_px: float | None = None,
          line_px: float | None = None, keep_next: bool | None = None, keep_lines: bool | None = None,
          jc: str | None = None, ind_px: tuple[float, float] | None = None, italic: bool | None = None) -> None:
    el = st.element
    ppr = _style_child(el, "pPr")
    rpr = _style_child(el, "rPr")
    if keep_next is not None:
        ox.put(ppr, "keepNext", val=int(keep_next))
    if keep_lines is not None:
        ox.put(ppr, "keepLines", val=int(keep_lines))
    line_px = line_px if line_px is not None else (text.line_px if text else None)
    sp = {}
    if before_px is not None:
        sp["before"] = tw(before_px)
    if after_px is not None:
        sp["after"] = tw(after_px)
    if line_px:
        sp.update(line=tw(line_px), lineRule="atLeast")
    if sp:
        old = ppr.find(qn("w:spacing"))
        if old is not None:
            for k in ("before", "after", "line", "lineRule", "beforeAutospacing", "afterAutospacing"):
                if k not in sp and old.get(qn(f"w:{k}")) is not None and k in ("before", "after", "line", "lineRule"):
                    sp[k] = old.get(qn(f"w:{k}"))
        ox.put(ppr, "spacing", **sp)
    if ind_px is not None:
        ox.put(ppr, "ind", left=tw(ind_px[0]), right=tw(ind_px[1]))
    if jc:
        ox.put(ppr, "jc", val=jc)
    if font:
        ox.fonts(rpr, font)
    if bold is not None or (text and text.bold is not None):
        b = bold if bold is not None else text.bold
        ox.put(rpr, "b", val=int(b))
        ox.put(rpr, "bCs", val=int(b))
    if italic is not None:
        ox.put(rpr, "i", val=int(italic))
    if color:
        ox.put(rpr, "color", val=color)
    if text:
        ox.put(rpr, "sz", val=half_pt(text.size_px))
        ox.put(rpr, "szCs", val=half_pt(text.size_px))


def _char(st, *, font: str | None = None, size_px: float | None = None, color: str | None = None,
          fill: str | None = None, underline: str | None = None, no_underline: bool = False) -> None:
    rpr = _style_child(st.element, "rPr")
    if font:
        ox.fonts(rpr, font)
    if color:
        ox.put(rpr, "color", val=color)
    if size_px:
        ox.put(rpr, "sz", val=half_pt(size_px))
        ox.put(rpr, "szCs", val=half_pt(size_px))
    if underline:
        ox.put(rpr, "u", val="single", color=underline)
    elif no_underline:
        ox.put(rpr, "u", val="none")
    if fill:
        ox.shade(rpr, fill)


def _box(st, fill: str, pad_y_px: float, pad_x_px: float) -> None:
    """Shaded box around a paragraph: a border in the fill colour provides the padding (Word has none)."""
    ppr = _style_child(st.element, "pPr")
    box = ox.put(ppr, "pBdr")
    for side, pad in (("top", pad_y_px), ("left", pad_x_px), ("bottom", pad_y_px), ("right", pad_x_px)):
        box.append(ox.make(side, val="single", sz=4, space=min(31, round(pad * 0.75)), color=fill))
    ox.shade(ppr, fill)
    inset = pad_x_px + 1
    ox.put(ppr, "ind", left=tw(inset), right=tw(inset))


# --------------------------------------------------------------------------- build


def build_reference_docx(theme: Theme, cfg: DocxCfg, page: PageCfg, out: Path) -> Path:
    default = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], check=False,
                             capture_output=True)
    if default.returncode != 0:
        from . import DocxError

        raise DocxError("pandoc could not provide its default reference.docx")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(default.stdout)

    t = theme
    font = cfg.font or t.font
    code_font = cfg.code_font or t.code_font
    muted = blend(t.color, MUTED)
    doc = Document(str(out))

    # Document defaults: everything inherits font, size and colour.
    rpr_default = doc.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault")).find(qn("w:rPr"))
    ox.fonts(rpr_default, font)
    ox.put(rpr_default, "color", val=t.color)
    ox.put(rpr_default, "sz", val=half_pt(t.body.size_px))
    ox.put(rpr_default, "szCs", val=half_pt(t.body.size_px))

    _para(_style(doc, "Normal"), font=font, text=t.body, color=t.color, before_px=0, after_px=0)
    for name in ("Body Text", "First Paragraph"):
        _para(_style(doc, name, base="Normal"), before_px=0, after_px=GAP["para"])
    _para(_style(doc, "Compact", base="Body Text"), before_px=0, after_px=GAP["compact"])
    for name in ("Block Text",):
        st = _style(doc, name, base="Body Text")
        _para(st, color=muted, ind_px=(16, 0))
        ppr = _style_child(st.element, "pPr")
        ox.borders(ppr, "pBdr", ("left",), "D1D1D2", 24, 12)

    heads = {1: t.h1, 2: t.h2, 3: t.h3, 4: t.h4, 5: t.h4, 6: t.h4}
    for lvl, text in heads.items():
        before, after = GAP[f"h{min(lvl, 4)}"]
        _para(_style(doc, f"Heading {lvl}"), font=font, text=text, color=t.color, before_px=before, after_px=after,
              keep_next=True, keep_lines=True, italic=False)
    _para(_style(doc, "Title"), font=font, text=t.h1, color=t.color, before_px=0, after_px=GAP["h1"][1], jc="left")
    _para(_style(doc, "Subtitle"), font=font, text=t.h3, color=muted, bold=False, before_px=0, after_px=GAP["h3"][1],
          jc="left")
    for name in ("Author", "Date"):
        _para(_style(doc, name), font=font, text=t.body, color=muted, before_px=0, after_px=GAP["compact"], jc="left")
    _para(_style(doc, "TOC Heading", base="Heading 1"), font=font, text=t.h2, color=t.color, before_px=0,
          after_px=GAP["h2"][1])
    tw_text = text_width_twips(page)
    for lvl in range(1, 10):
        st = _style(doc, f"toc {lvl}", base="Normal")
        _para(st, before_px=0, after_px=GAP["compact"] if lvl > 1 else GAP["compact"] + 2,
              ind_px=(16 * (lvl - 1), 0), bold=lvl == 1)
        ppr = _style_child(st.element, "pPr")
        tabs = ox.put(ppr, "tabs")
        tabs.append(ox.make("tab", val="right", leader="dot", pos=tw_text))

    for name in ("Image Caption", "Table Caption"):
        _para(_style(doc, name), color=muted, italic=False, before_px=0, after_px=GAP["para"])
    _para(_style(doc, "Figure", base="Normal"), before_px=0, after_px=GAP["figure"], jc="left", line_px=0)
    _para(_style(doc, "Figure Bordered", base="Figure"))
    _para(_style(doc, "Definition Term", base="Normal"), bold=True, before_px=0, after_px=GAP["compact"],
          keep_next=True)
    _para(_style(doc, "Definition", base="Normal"), before_px=0, after_px=GAP["para"], ind_px=(24, 0))

    # Code: a shaded box per block, Writerside's mono font; token colours come from the highlight theme.
    src = _style(doc, "Source Code", base="Normal")
    _para(src, font=code_font, text=t.code, color=t.color, before_px=0, after_px=GAP["code"])
    _box(src, t.code_fill, 12, 16)
    _style_child(src.element, "rPr")
    ox.put(_style_child(src.element, "pPr"), "wordWrap", val=1)
    # Text diagrams (box-drawing art in plain code blocks): the code font on single line spacing so vertical
    # strokes join, no box or shading. Post-processing keeps a diagram on one page and fits it to the width.
    diag = _style(doc, "Text Diagram", base="Normal")
    _para(diag, font=code_font, color=t.color, before_px=0, after_px=0, keep_lines=True)
    rpr = _style_child(diag.element, "rPr")
    ox.put(rpr, "sz", val=half_pt(t.code.size_px))
    ox.put(rpr, "szCs", val=half_pt(t.code.size_px))
    ox.put(_style_child(diag.element, "pPr"), "spacing", before=0, after=0, line=240, lineRule="auto")
    _char(_style(doc, "Verbatim Char", WD_STYLE_TYPE.CHARACTER, base=None), font=code_font,
          size_px=t.inline_code_px, fill=t.inline_code_fill)
    _char(_style(doc, "Emoji", WD_STYLE_TYPE.CHARACTER, base=None), font=cfg.emoji_font)
    _char(_style(doc, "Hyperlink", WD_STYLE_TYPE.CHARACTER, base=None), color=t.link,
          underline=t.link_underline, no_underline=t.link_underline is None)

    # Tables: Writerside grid, header row shading; cell text has its own compact style.
    _para(_style(doc, "Table Text", base="Normal"), before_px=0, after_px=GAP["cell_para"])
    _table_style(doc, t)
    for kind, c in t.callouts.items():
        _para(_style(doc, f"Callout {kind.title()}", base="Normal"), color=c.text, before_px=0,
              after_px=GAP["cell_para"])

    tab = _style(doc, "Tab Title", base="Normal")
    _para(tab, bold=True, before_px=GAP["tab"][0], after_px=GAP["tab"][1], keep_next=True)
    ox.borders(_style_child(tab.element, "pPr"), "pBdr", ("bottom",), t.table_border, 8, 4)

    _footer(doc, t, font)
    _page_setup(doc, page)
    doc.core_properties.title = ""
    doc.core_properties.author = "nxo-ws-export"
    doc.save(str(out))
    _font_fallbacks(out, {font: cfg.font_fallback, code_font: cfg.code_font_fallback})
    return out


def _table_style(doc, t: Theme) -> None:
    st = _style(doc, "Table", WD_STYLE_TYPE.TABLE, base=None)
    el = st.element
    for old in el.findall(qn("w:tblPr")) + el.findall(qn("w:tblStylePr")) + el.findall(qn("w:tcPr")):
        el.remove(old)
    ppr = _style_child(el, "pPr")
    ox.put(ppr, "spacing", before=0, after=0)
    tblpr = _style_child(el, "tblPr")
    ox.borders(tblpr, "tblBorders", ("top", "left", "bottom", "right", "insideH", "insideV"), t.table_border, 6)
    ox.margins(tblpr, "tblCellMar", tw(t.cell_pad_y_px), tw(t.cell_pad_x_px), tw(t.cell_pad_y_px), tw(t.cell_pad_x_px))
    first = ox.make("tblStylePr", type="firstRow")
    el.append(first)
    frpr = ox.make("rPr")
    first.append(frpr)
    ox.put(frpr, "b", val=int(t.table_header_bold))
    first.append(ox.make("tblPr"))
    trpr = ox.make("trPr")
    trpr.append(ox.make("tblHeader"))
    first.append(trpr)
    tcpr = ox.make("tcPr")
    first.append(tcpr)
    ox.shade(tcpr, t.table_header_fill)


def _footer(doc, t: Theme, font: str) -> None:
    """Footer "PAGE X OF Y" like the PDF: Writerside overline type, centred, fields Word keeps up to date."""
    st = _style(doc, "Footer", base="Normal")
    _para(st, font=font, color=blend(t.color, 0.75), bold=True, before_px=0, after_px=0, jc="center",
          text=Text(13, 18, True))
    rpr = _style_child(st.element, "rPr")
    ox.put(rpr, "caps", val=1)
    ox.put(rpr, "spacing", val=20)
    footer = doc.sections[0].footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    for r in list(p._p):
        if ox.local(r) != "pPr":
            p._p.remove(r)
    p.style = st

    def run(text: str | None = None, fld: str | None = None, instr: str | None = None):
        r = ox.make("r")
        if fld:
            r.append(ox.make("fldChar", fldCharType=fld))
        elif instr:
            it = ox.make("instrText")
            it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            it.text = instr
            r.append(it)
        else:
            tx = ox.make("t")
            tx.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            tx.text = text
            r.append(tx)
        p._p.append(r)

    def field(code: str, placeholder: str) -> None:
        run(fld="begin")
        run(instr=f" {code} ")
        run(fld="separate")
        run(placeholder)
        run(fld="end")

    run("Page ")
    field("PAGE", "1")
    run(" of ")
    field("NUMPAGES", "1")


def _page_setup(doc, page: PageCfg) -> None:
    w, h = page_size_px(page.size)
    sect = doc.sections[-1]._sectPr
    ox.put(sect, "pgSz", w=tw(w), h=tw(h), **({"orient": "landscape"} if w > h else {}))
    top, bottom, x = (length_px(v) for v in (page.margin_top, page.margin_bottom, page.margin_x))
    ox.put(sect, "pgMar", top=tw(top), right=tw(x), bottom=tw(bottom), left=tw(x),
           header=tw(top / 2), footer=tw(bottom / 2), gutter=0)


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _font_fallbacks(path: Path, fallbacks: dict[str, str | None]) -> None:
    """Declare Writerside fonts with an alternate (w:altName) so machines without them substitute sensibly."""
    doc = Document(str(path))
    part = next((p for p in doc.part.package.parts if str(p.partname) == "/word/fontTable.xml"), None)
    if part is None:
        return
    root = etree.fromstring(part.blob)
    for name, alt in fallbacks.items():
        if not alt or name == alt:
            continue
        for old in root.findall(f"{{{_W}}}font"):
            if old.get(f"{{{_W}}}name") == name:
                root.remove(old)
        mono = "Mono" in name or "Code" in name
        font = etree.SubElement(root, f"{{{_W}}}font", {f"{{{_W}}}name": name})
        etree.SubElement(font, f"{{{_W}}}altName", {f"{{{_W}}}val": alt})
        etree.SubElement(font, f"{{{_W}}}family", {f"{{{_W}}}val": "modern" if mono else "swiss"})
        etree.SubElement(font, f"{{{_W}}}pitch", {f"{{{_W}}}val": "fixed" if mono else "variable"})
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    doc.save(str(path))
