"""Minimal OOXML helpers (WordprocessingML). Word rejects some out-of-order elements, so every insert respects the schema sequence."""

from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

PPR_ORDER = ("pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd "
             "tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi "
             "adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection "
             "textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange").split()
RPR_ORDER = ("rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof "
             "snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText "
             "vertAlign rtl cs em lang eastAsianLayout specVanish oMath").split()
TBLPR_ORDER = ("tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing "
               "tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription").split()
TCPR_ORDER = ("cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign "
              "hideMark").split()
SECTPR_ORDER = ("headerReference footerReference footnotePr endnotePr type pgSz pgMar paperSrc pgBorders lnNumType "
                "pgNumType cols formProt vAlign noEndnote titlePg textDirection bidi rtlGutter docGrid "
                "printerSettings").split()
BORDER_SIDES = ("top", "left", "bottom", "right")
_ORDERS = {"pPr": PPR_ORDER, "rPr": RPR_ORDER, "tblPr": TBLPR_ORDER, "tcPr": TCPR_ORDER, "sectPr": SECTPR_ORDER}


def local(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def make(tag: str, **attrs) -> OxmlElement:
    el = OxmlElement(f"w:{tag}")
    for k, v in attrs.items():
        el.set(qn(f"w:{k}"), str(v))
    return el


def put(parent, tag: str, **attrs):
    """Replace child `tag` of parent (pPr/rPr/tblPr/tcPr/sectPr) keeping the schema order. Returns the new child."""
    for old in parent.findall(qn(f"w:{tag}")):
        parent.remove(old)
    el = make(tag, **attrs)
    insert_ordered(parent, el)
    return el


def insert_ordered(parent, el) -> None:
    order = _ORDERS.get(local(parent))
    name = local(el)
    if not order or name not in order:
        parent.append(el)
        return
    idx = order.index(name)
    for i, child in enumerate(parent):
        if local(child) in order and order.index(local(child)) > idx:
            parent.insert(i, el)
            return
    parent.append(el)


def child(parent, tag: str, order_parent: bool = True):
    """Get or create child `tag` (e.g. pPr inside p, rPr inside r, tblPr inside tbl) at its schema position."""
    el = parent.find(qn(f"w:{tag}"))
    if el is None:
        el = make(tag)
        if tag in ("pPr", "rPr", "tblPr", "tcPr", "trPr"):
            parent.insert(0, el)
        else:
            insert_ordered(parent, el) if order_parent else parent.append(el)
    return el


def borders(parent, tag: str, sides, color: str, size_eighths: int, space_pt: float = 0, val: str = "single"):
    """pBdr / tblBorders / tcBorders with the given sides."""
    box = put(parent, tag)
    for side in sides:
        box.append(make(side, val=val, sz=size_eighths, space=round(space_pt), color=color))
    return box


def shade(parent, fill: str):
    return put(parent, "shd", val="clear", color="auto", fill=fill)


def margins(parent, tag: str, top: int, left: int, bottom: int, right: int):
    """tblCellMar / tcMar in twips."""
    box = put(parent, tag)
    for side, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        box.append(make(side, w=v, type="dxa"))
    return box


def fonts(rpr, name: str) -> None:
    put(rpr, "rFonts", ascii=name, hAnsi=name, cs=name, eastAsia=name)


# --------------------------------------------------------------------------- paragraphs


def pstyle(p) -> str | None:
    """Paragraph style id, or None for direct "Normal"."""
    ps = p.find(qn("w:pPr") + "/" + qn("w:pStyle"))
    return ps.get(qn("w:val")) if ps is not None else None


def set_pstyle(p, style_id: str) -> None:
    put(child(p, "pPr"), "pStyle", val=style_id)


def spacing(p, **kw) -> None:
    """Merge spacing attributes (twips) into a paragraph's w:spacing."""
    ppr = child(p, "pPr")
    sp = ppr.find(qn("w:spacing"))
    attrs = {k.split("}")[-1]: v for k, v in sp.attrib.items()} if sp is not None else {}
    attrs.update({k: str(v) for k, v in kw.items()})
    put(ppr, "spacing", **attrs)


def text_of(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def text_len(el) -> int:
    return sum(len(t.text or "") for t in el.iter(qn("w:t")))


def text_run(text: str):
    r = make("r")
    t = make("t")
    t.set(XML_SPACE, "preserve")
    t.text = text
    r.append(t)
    return r


XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
