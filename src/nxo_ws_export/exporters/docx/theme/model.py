"""The Writerside light theme as measured values (CSS px, RRGGBB colours).

Values are read from the rendered DOM (docx_theme.js / docx_prepare.js). Defaults are the values measured on the
default Writerside theme (builder 2026.x) and are used for anything no exported topic happens to contain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ....domain.css import css_color_to_hex, css_px, first_font

CALLOUT_KINDS = ("note", "tip", "warning")


@dataclass
class Text:
    size_px: float
    line_px: float
    bold: bool = False


@dataclass
class Callout:
    fill: str
    text: str


@dataclass
class Theme:
    font: str = "JetBrains Sans"
    code_font: str = "JetBrains Mono"
    color: str = "19191C"
    body: Text = field(default_factory=lambda: Text(16, 24))
    h1: Text = field(default_factory=lambda: Text(43, 49, True))
    h2: Text = field(default_factory=lambda: Text(35, 42, True))
    h3: Text = field(default_factory=lambda: Text(20, 28, True))
    h4: Text = field(default_factory=lambda: Text(17, 24, True))
    code: Text = field(default_factory=lambda: Text(15.2, 24))
    inline_code_px: float = 15
    code_fill: str = "F4F4F4"
    inline_code_fill: str = "F4F4F4"
    link: str = "19191C"
    link_underline: str | None = "D1D1D2"
    callouts: dict[str, Callout] = field(default_factory=lambda: {
        "note": Callout("FDF2D6", "5E5E60"),
        "tip": Callout("DBF1DF", "585D5B"),
        "warning": Callout("FDDEDB", "5E5A5A"),
    })
    callout_pad_px: float = 16
    table_border: str = "D1D1D2"
    table_header_fill: str = "F4F4F4"
    table_header_bold: bool = False
    cell_pad_y_px: float = 16
    cell_pad_x_px: float = 16

    def callout(self, kind: str) -> Callout:
        return self.callouts.get(kind) or self.callouts["note"]

    @classmethod
    def from_tokens(cls, tok: dict[str, Any]) -> Theme:
        t = cls()

        def text(key: str, cur: Text) -> Text:
            v = tok.get(key)
            if not v:
                return cur
            try:
                bold = int(float(v.get("fontWeight", 400))) >= 500
            except ValueError:
                bold = cur.bold
            size = css_px(v.get("fontSize"), cur.size_px)
            line = css_px(v.get("lineHeight"), size * cur.line_px / cur.size_px)  # "normal" keeps the ratio
            return Text(size, line, bold)

        if p := tok.get("p"):
            t.font = first_font(p.get("fontFamily")) or t.font
            t.color = css_color_to_hex(p.get("color")) or t.color
        t.body = text("p", t.body)
        for k in ("h1", "h2", "h3", "h4"):
            setattr(t, k, text(k, getattr(t, k)))
        if pre := tok.get("pre"):
            t.code_font = first_font(pre.get("fontFamily")) or t.code_font
        t.code = text("pre", t.code)
        if box := tok.get("preBox"):
            t.code_fill = css_color_to_hex(box.get("backgroundColor")) or t.code_fill
        if c := tok.get("code"):
            t.inline_code_px = css_px(c.get("fontSize"), t.inline_code_px)
            t.inline_code_fill = css_color_to_hex(c.get("backgroundColor")) or t.inline_code_fill
        if a := tok.get("a"):
            t.link = css_color_to_hex(a.get("color")) or t.link
            if css_px(a.get("borderBottomWidth"), 0) > 0 and a.get("borderBottomStyle") not in (None, "none"):
                t.link_underline = css_color_to_hex(a.get("borderBottomColor")) or t.link_underline
            elif "underline" in (a.get("textDecorationLine") or ""):
                t.link_underline = t.link
            else:
                t.link_underline = None
        for kind in CALLOUT_KINDS:
            if v := tok.get(kind):
                fill = css_color_to_hex(v.get("backgroundColor")) or t.callouts[kind].fill
                t.callouts[kind] = Callout(fill, css_color_to_hex(v.get("color"), over=fill) or t.color)
                t.callout_pad_px = css_px(v.get("paddingLeft"), t.callout_pad_px)
        if th := tok.get("th"):
            t.table_header_fill = css_color_to_hex(th.get("backgroundColor")) or "FFFFFF"
            t.table_border = css_color_to_hex(th.get("borderTopColor")) or t.table_border
            t.cell_pad_y_px = css_px(th.get("paddingTop"), t.cell_pad_y_px)
            t.cell_pad_x_px = css_px(th.get("paddingLeft"), t.cell_pad_x_px)
            try:
                t.table_header_bold = int(float(th.get("fontWeight", 400))) >= 600
            except ValueError:
                pass
        return t
