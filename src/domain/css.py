"""CSS values read from the rendered DOM -> plain values (hex colours without '#', font names, px)."""

from __future__ import annotations

import re

_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)")
_HEX6 = re.compile(r"[0-9a-fA-F]{6}")
_GENERIC_FONTS = {"system-ui", "-apple-system", "sans-serif", "monospace", "serif", "ui-monospace", "cursive"}

RGB = tuple[int, int, int]


def hex_to_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def css_color_to_hex(value: str | None, over: RGB | str = (255, 255, 255)) -> str | None:
    """CSS rgb()/rgba()/#hex -> RRGGBB, alpha-blended over `over` (white). None for fully transparent/unknown."""
    if not value:
        return None
    if isinstance(over, str):
        over = hex_to_rgb(over)
    m = _RGB.search(value)
    if not m:
        h = value.strip().lstrip("#")
        return h.upper() if _HEX6.fullmatch(h) else None
    r, g, b = (float(m.group(i)) for i in (1, 2, 3))
    a_raw = m.group(4)
    a = 1.0 if a_raw is None else (float(a_raw[:-1]) / 100 if a_raw.endswith("%") else float(a_raw))
    if a == 0:
        return None
    r, g, b = (round(c * a + o * (1 - a)) for c, o in zip((r, g, b), over, strict=True))
    return f"{r:02X}{g:02X}{b:02X}"


def blend(color: str, alpha: float) -> str:
    """`color` (RRGGBB) at `alpha` over white, e.g. Writerside's secondary text (text colour at 70 %)."""
    r, g, b = hex_to_rgb(color)
    return css_color_to_hex(f"rgba({r},{g},{b},{alpha})") or color


def first_font(family: str | None) -> str | None:
    """First concrete font of a CSS font-family list (generic families and var() are skipped)."""
    if not family:
        return None
    for name in family.split(","):
        name = name.strip().strip("\"'")
        if name and not name.startswith("var(") and name.lower() not in _GENERIC_FONTS:
            return name
    return None


def css_px(value: str | float | None, default: float) -> float:
    try:
        return float(str(value).removesuffix("px"))
    except (TypeError, ValueError):
        return default
