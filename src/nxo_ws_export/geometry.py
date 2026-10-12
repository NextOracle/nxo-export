"""Page geometry: converts the configured page size/margins to CSS pixels (96 dpi)."""

from __future__ import annotations

import re

from .config import PageCfg

_SIZES_MM = {
    "A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
    "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6), "TABLOID": (279.4, 431.8),
}
_UNIT_PX = {"mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0, "pt": 96 / 72, "px": 1.0}
_LEN = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mm|cm|in|pt|px)\s*$")


def length_px(value: str) -> float:
    m = _LEN.match(value)
    if not m:
        raise ValueError(f"unsupported length {value!r}; use mm, cm, in, pt or px")
    return float(m.group(1)) * _UNIT_PX[m.group(2)]


def page_size_px(size: str) -> tuple[float, float]:
    parts = size.split()
    landscape = len(parts) == 2 and parts[1].lower() == "landscape"
    if parts and parts[0].upper() in _SIZES_MM:
        w, h = (v * _UNIT_PX["mm"] for v in _SIZES_MM[parts[0].upper()])
    elif len(parts) == 2 and not landscape:
        w, h = length_px(parts[0]), length_px(parts[1])
    else:
        raise ValueError(f"unsupported page size {size!r}; use A4, Letter, 'A4 landscape' or '210mm 297mm'")
    return (h, w) if landscape else (w, h)


def content_box_px(page: PageCfg) -> tuple[int, int]:
    w, h = page_size_px(page.size)
    cw = w - 2 * length_px(page.margin_x)
    ch = h - length_px(page.margin_top) - length_px(page.margin_bottom)
    if cw < 200 or ch < 200:
        raise ValueError("page margins leave less than 200px of content area")
    return int(cw), int(ch)
