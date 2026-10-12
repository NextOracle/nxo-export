"""Page geometry: the configured page size and margins in CSS px (96 dpi) and Word twips."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .units import PX_PER_INCH, Twips, twips

if TYPE_CHECKING:
    from ..config import PageCfg

_SIZES_MM = {
    "A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
    "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6), "TABLOID": (279.4, 431.8),
}
_UNIT_PX = {"mm": PX_PER_INCH / 25.4, "cm": PX_PER_INCH / 2.54, "in": float(PX_PER_INCH), "pt": PX_PER_INCH / 72,
            "px": 1.0}
_LEN = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mm|cm|in|pt|px)\s*$")
MIN_CONTENT_PX = 200


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


@dataclass(frozen=True, slots=True)
class PageBox:
    """A sheet and its margins, in CSS px."""

    width: float
    height: float
    margin_top: float
    margin_bottom: float
    margin_x: float

    @classmethod
    def from_cfg(cls, page: PageCfg) -> PageBox:
        w, h = page_size_px(page.size)
        box = cls(w, h, length_px(page.margin_top), length_px(page.margin_bottom), length_px(page.margin_x))
        if box.content_width < MIN_CONTENT_PX or box.content_height < MIN_CONTENT_PX:
            raise ValueError(f"page margins leave less than {MIN_CONTENT_PX}px of content area")
        return box

    @property
    def landscape(self) -> bool:
        return self.width > self.height

    @property
    def content_width(self) -> float:
        return self.width - 2 * self.margin_x

    @property
    def content_height(self) -> float:
        return self.height - self.margin_top - self.margin_bottom

    @property
    def content_px(self) -> tuple[int, int]:
        """Browser viewport that lays pages out at the printable size."""
        return int(self.content_width), int(self.content_height)

    @property
    def text_width_twips(self) -> Twips:
        return twips(self.content_width)

    @property
    def text_height_twips(self) -> Twips:
        return twips(self.content_height)


def content_box_px(page: PageCfg) -> tuple[int, int]:
    return PageBox.from_cfg(page).content_px
