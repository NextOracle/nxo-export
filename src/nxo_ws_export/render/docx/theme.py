"""Writerside light theme -> Word units.

Values are read from the rendered DOM (docx_theme.js / docx_prepare.js). Defaults are the values measured on the
default Writerside theme (builder 2026.x) and are used for anything no exported topic happens to contain."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)")
_GENERIC_FONTS = {"system-ui", "-apple-system", "sans-serif", "monospace", "serif", "ui-monospace", "cursive"}


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def css_color_to_hex(value: str | None, over: tuple[int, int, int] | str = (255, 255, 255)) -> str | None:
    """CSS rgb()/rgba()/#hex -> RRGGBB, alpha-blended over `over` (white). None for fully transparent/unknown."""
    if not value:
        return None
    if isinstance(over, str):
        over = hex_to_rgb(over)
    m = _RGB.search(value)
    if not m:
        h = value.strip().lstrip("#")
        return h.upper() if re.fullmatch(r"[0-9a-fA-F]{6}", h) else None
    r, g, b = (float(m.group(i)) for i in (1, 2, 3))
    a_raw = m.group(4)
    a = 1.0 if a_raw is None else (float(a_raw[:-1]) / 100 if a_raw.endswith("%") else float(a_raw))
    if a == 0:
        return None
    r, g, b = (round(c * a + o * (1 - a)) for c, o in zip((r, g, b), over, strict=True))
    return f"{r:02X}{g:02X}{b:02X}"


def first_font(family: str | None) -> str | None:
    if not family:
        return None
    for name in family.split(","):
        name = name.strip().strip("\"'")
        if name and not name.startswith("var(") and name.lower() not in _GENERIC_FONTS:
            return name
    return None


def px(value: str | float | None, default: float) -> float:
    try:
        return float(str(value).removesuffix("px"))
    except (TypeError, ValueError):
        return default


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

    @classmethod
    def from_tokens(cls, tok: dict) -> Theme:
        t = cls()

        def text(key: str, cur: Text) -> Text:
            v = tok.get(key)
            if not v:
                return cur
            try:
                bold = int(float(v.get("fontWeight", 400))) >= 500
            except ValueError:
                bold = cur.bold
            size = px(v.get("fontSize"), cur.size_px)
            line = px(v.get("lineHeight"), size * cur.line_px / cur.size_px)  # "normal" keeps the ratio
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
            t.inline_code_px = px(c.get("fontSize"), t.inline_code_px)
            t.inline_code_fill = css_color_to_hex(c.get("backgroundColor")) or t.inline_code_fill
        if a := tok.get("a"):
            t.link = css_color_to_hex(a.get("color")) or t.link
            if px(a.get("borderBottomWidth"), 0) > 0 and a.get("borderBottomStyle") not in (None, "none"):
                t.link_underline = css_color_to_hex(a.get("borderBottomColor")) or t.link_underline
            elif "underline" in (a.get("textDecorationLine") or ""):
                t.link_underline = t.link
            else:
                t.link_underline = None
        for kind in ("note", "tip", "warning"):
            if v := tok.get(kind):
                fill = css_color_to_hex(v.get("backgroundColor")) or t.callouts[kind].fill
                t.callouts[kind] = Callout(fill, css_color_to_hex(v.get("color"), over=fill) or t.color)
                t.callout_pad_px = px(v.get("paddingLeft"), t.callout_pad_px)
        if th := tok.get("th"):
            t.table_header_fill = css_color_to_hex(th.get("backgroundColor")) or "FFFFFF"
            t.table_border = css_color_to_hex(th.get("borderTopColor")) or t.table_border
            t.cell_pad_y_px = px(th.get("paddingTop"), t.cell_pad_y_px)
            t.cell_pad_x_px = px(th.get("paddingLeft"), t.cell_pad_x_px)
            try:
                t.table_header_bold = int(float(th.get("fontWeight", 400))) >= 600
            except ValueError:
                pass
        return t


def merge_tokens(acc: dict, new: dict) -> None:
    for k, v in new.items():
        acc.setdefault(k, v)


# --------------------------------------------------------------------------- syntax highlighting

# IntelliJ Light, the palette Writerside's Prism theme uses; only for token types no topic rendered.
_INTELLIJ_LIGHT = {
    "keyword": "0033B3", "class-name": "000000", "function": "00627A", "string": "067D17", "char": "067D17",
    "number": "1750EB", "boolean": "0033B3", "constant": "871094", "comment": "8C8C8C", "operator": "9A6E3A",
    "annotation": "9E880D", "property": "871094", "attr-name": "174AD4", "attr-value": "067D17", "tag": "0033B3",
    "builtin": "0033B3", "variable": "871094", "namespace": "000000", "regex": "067D17", "url": "067D17",
    "punctuation": "999999",
}
# Skylighting token type -> Prism token types; the first one with a colour wins.
_SKYLIGHTING = {
    "Keyword": ("keyword",), "ControlFlow": ("keyword",), "Import": ("keyword",),
    "DataType": ("class-name", "builtin"), "BuiltIn": ("builtin", "class-name"),
    "DecVal": ("number",), "BaseN": ("number",), "Float": ("number",),
    "Char": ("char", "string"), "String": ("string",), "VerbatimString": ("string",), "SpecialString": ("string",),
    "SpecialChar": ("string",), "Comment": ("comment",), "Documentation": ("comment",), "CommentVar": ("comment",),
    "Function": ("function",), "Operator": ("operator",), "Constant": ("constant", "boolean"),
    "Annotation": ("annotation",), "Preprocessor": ("annotation",), "Attribute": ("attr-name", "property"),
    "Variable": ("variable", "property"), "Extension": ("keyword",), "Other": ("tag",), "Information": ("comment",),
    "Warning": ("comment",), "Alert": ("comment",), "RegionMarker": ("comment",),
}


def highlight_theme(prism: dict[str, dict], text_color: str) -> dict:
    """Pandoc (skylighting) theme JSON from the Prism token colours Writerside rendered."""

    def style(name: str) -> dict | None:
        v = prism.get(name)
        color = css_color_to_hex(v.get("color")) if v else _INTELLIJ_LIGHT.get(name)
        if not color:
            return None
        return {"text-color": f"#{color}", "background-color": None,
                "bold": bool(v and v.get("bold")), "italic": bool(v and v.get("italic")), "underline": False}

    styles = {}
    for tok, sources in _SKYLIGHTING.items():
        for src in sources:
            if (s := style(src)) is not None:
                styles[tok] = s
                break
    styles["Error"] = {"text-color": "#F50000", "background-color": None, "bold": False, "italic": False,
                       "underline": True}
    return {"text-color": f"#{text_color}", "background-color": None, "line-number-color": "#AEB3C2",
            "line-number-background-color": None, "text-styles": styles}


def write_highlight_theme(prism: dict[str, dict], text_color: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(highlight_theme(prism, text_color), indent=1), encoding="utf-8")
    return out
