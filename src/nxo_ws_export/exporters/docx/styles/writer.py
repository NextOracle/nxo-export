"""Applies style specs to a python-docx document (the only code that writes style XML)."""

from __future__ import annotations

from typing import Any

from docx.document import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn

from ....domain.units import half_points, twips
from ..ooxml import xml as ox
from .specs import CharacterStyle, ParagraphStyle, StyleSpec, TableStyle

_STYLE_ORDER = ("name aliases basedOn next link autoRedefine hidden uiPriority semiHidden unhideWhenUsed qFormat "
                "locked personal personalCompose personalReply rsid pPr rPr tblPr trPr tcPr tblStylePr").split()
_KEEP_SPACING = ("before", "after", "line", "lineRule")


def style_child(style_el, tag: str):
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


class StyleWriter:
    def __init__(self, doc: Document):
        self.doc = doc

    def apply(self, spec: StyleSpec) -> None:
        if isinstance(spec, ParagraphStyle):
            self._paragraph(spec)
        elif isinstance(spec, CharacterStyle):
            self._character(spec)
        elif isinstance(spec, TableStyle):
            self._table(spec)
        else:  # pragma: no cover
            raise TypeError(spec)

    def _get(self, name: str, kind: WD_STYLE_TYPE, base: str | None) -> Any:
        """Existing style (Pandoc's reference.docx defines most) or a new one based on `base`."""
        try:
            st = self.doc.styles[name]
        except KeyError:
            st = self.doc.styles.add_style(name, kind)
            if base:
                st.base_style = self.doc.styles[base]
        st.hidden = False
        st.quick_style = True
        return st

    def _paragraph(self, s: ParagraphStyle) -> None:
        el = self._get(s.name, WD_STYLE_TYPE.PARAGRAPH, s.base).element
        ppr = style_child(el, "pPr")
        rpr = style_child(el, "rPr")
        if s.keep_next is not None:
            ox.put(ppr, "keepNext", val=int(s.keep_next))
        if s.keep_lines is not None:
            ox.put(ppr, "keepLines", val=int(s.keep_lines))
        self._spacing(ppr, s)
        if s.ind_px is not None:
            ox.put(ppr, "ind", left=twips(s.ind_px[0]), right=twips(s.ind_px[1]))
        if s.jc:
            ox.put(ppr, "jc", val=s.jc)
        if s.border:
            b = s.border
            ox.borders(ppr, "pBdr", b.sides, b.color, b.size_eighths, b.space_pt)
        if s.box:
            box = ox.put(ppr, "pBdr")
            for side, pad in (("top", s.box.pad_y_px), ("left", s.box.pad_x_px), ("bottom", s.box.pad_y_px),
                              ("right", s.box.pad_x_px)):
                box.append(ox.make(side, val="single", sz=4, space=min(31, round(pad * 0.75)), color=s.box.fill))
            ox.shade(ppr, s.box.fill)
            inset = s.box.pad_x_px + 1
            ox.put(ppr, "ind", left=twips(inset), right=twips(inset))
        if s.right_tab_twips is not None:
            ox.put(ppr, "tabs").append(ox.make("tab", val="right", leader="dot", pos=s.right_tab_twips))
        if s.word_wrap:
            ox.put(ppr, "wordWrap", val=1)

        if s.font:
            ox.fonts(rpr, s.font)
        bold = s.bold if s.bold is not None else (s.text.bold if s.text else None)
        if bold is not None:
            ox.put(rpr, "b", val=int(bold))
            ox.put(rpr, "bCs", val=int(bold))
        if s.italic is not None:
            ox.put(rpr, "i", val=int(s.italic))
        if s.color:
            ox.put(rpr, "color", val=s.color)
        size = s.text.size_px if s.text else s.size_px
        if size:
            ox.put(rpr, "sz", val=half_points(size))
            ox.put(rpr, "szCs", val=half_points(size))
        if s.caps:
            ox.put(rpr, "caps", val=1)
        if s.letter_spacing_twips is not None:
            ox.put(rpr, "spacing", val=s.letter_spacing_twips)

    @staticmethod
    def _spacing(ppr, s: ParagraphStyle) -> None:
        sp: dict[str, Any] = {}
        if s.before_px is not None:
            sp["before"] = twips(s.before_px)
        if s.after_px is not None:
            sp["after"] = twips(s.after_px)
        if s.line is not None:
            sp.update(line=s.line.twips, lineRule=s.line.rule)
        else:
            line_px = s.line_px if s.line_px is not None else (s.text.line_px if s.text else None)
            if line_px:
                sp.update(line=twips(line_px), lineRule="atLeast")
        if not sp:
            return
        old = ppr.find(qn("w:spacing"))
        if old is not None:  # keep what the base reference.docx defined and the spec does not override
            for k in _KEEP_SPACING:
                if k not in sp and old.get(qn(f"w:{k}")) is not None:
                    sp[k] = old.get(qn(f"w:{k}"))
        ox.put(ppr, "spacing", **sp)

    def _character(self, s: CharacterStyle) -> None:
        rpr = style_child(self._get(s.name, WD_STYLE_TYPE.CHARACTER, None).element, "rPr")
        if s.font:
            ox.fonts(rpr, s.font)
        if s.color:
            ox.put(rpr, "color", val=s.color)
        if s.size_px:
            ox.put(rpr, "sz", val=half_points(s.size_px))
            ox.put(rpr, "szCs", val=half_points(s.size_px))
        if s.underline:
            ox.put(rpr, "u", val="single", color=s.underline)
        elif s.no_underline:
            ox.put(rpr, "u", val="none")
        if s.fill:
            ox.shade(rpr, s.fill)

    def _table(self, s: TableStyle) -> None:
        """Writerside grid with a shaded (repeating) header row."""
        el = self._get(s.name, WD_STYLE_TYPE.TABLE, None).element
        for old in el.findall(qn("w:tblPr")) + el.findall(qn("w:tblStylePr")) + el.findall(qn("w:tcPr")):
            el.remove(old)
        ox.put(style_child(el, "pPr"), "spacing", before=0, after=0)
        tblpr = style_child(el, "tblPr")
        ox.borders(tblpr, "tblBorders", ("top", "left", "bottom", "right", "insideH", "insideV"), s.border, 6)
        ox.margins(tblpr, "tblCellMar", twips(s.pad_y_px), twips(s.pad_x_px), twips(s.pad_y_px), twips(s.pad_x_px))
        first = ox.make("tblStylePr", type="firstRow")
        el.append(first)
        frpr = ox.make("rPr")
        first.append(frpr)
        ox.put(frpr, "b", val=int(s.header_bold))
        first.append(ox.make("tblPr"))
        trpr = ox.make("trPr")
        trpr.append(ox.make("tblHeader"))
        first.append(trpr)
        tcpr = ox.make("tcPr")
        first.append(tcpr)
        ox.shade(tcpr, s.header_fill)
