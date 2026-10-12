"""Pandoc (skylighting) syntax-highlighting theme from the Prism token colours Writerside rendered."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ....domain.css import css_color_to_hex

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


def highlight_theme(prism: dict[str, dict[str, Any]], text_color: str) -> dict[str, Any]:
    def style(name: str) -> dict[str, Any] | None:
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


def write_highlight_theme(prism: dict[str, dict[str, Any]], text_color: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(highlight_theme(prism, text_color), indent=1), encoding="utf-8")
    return out
