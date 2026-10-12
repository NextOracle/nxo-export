"""Figures: own paragraph style, clamped to the available width and page height, Writerside border on bordered
screenshots."""

from __future__ import annotations

from collections import Counter

from docx.document import Document
from docx.oxml.ns import qn

from .....browser.session import FIGURE_HEADROOM_PX
from .....domain.units import EMU_PER_TWIP, twips
from .. import xml as ox
from ..context import PassContext
from .base import DocumentPass, containers, content_width

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
SCREENSHOT_BORDER = "D1D1D2"
SCREENSHOT_BORDER_EMU = 9525  # 0.75pt


class FigurePass(DocumentPass):
    name = "figures"

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        max_h = ctx.text_height - twips(FIGURE_HEADROOM_PX) if ctx.text_height else 0
        for container in containers(doc.element.body):
            avail = content_width(container, ctx.text_width)
            for p in container.findall(qn("w:p")):
                if self._figure(p, avail, max_h):
                    stats["figures"] += 1

    @staticmethod
    def _figure(p, avail: int, max_h: int) -> bool:
        drawings = p.findall(".//" + qn("w:drawing"))
        if not drawings:
            return False
        standalone = not ox.text_of(p).strip()
        if standalone and ox.pstyle(p) != "FigureBordered":
            ox.set_pstyle(p, "Figure")
        max_emu = avail * EMU_PER_TWIP
        bordered = ox.pstyle(p) == "FigureBordered"
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
                _border(d)
        return standalone


def _border(drawing) -> None:
    sppr = drawing.find(f".//{{{_PIC}}}spPr")
    if sppr is not None and sppr.find(f"{{{_A}}}ln") is None:
        ln = sppr.makeelement(f"{{{_A}}}ln", {"w": str(SCREENSHOT_BORDER_EMU)})
        fill = ln.makeelement(f"{{{_A}}}solidFill", {})
        fill.append(fill.makeelement(f"{{{_A}}}srgbClr", {"val": SCREENSHOT_BORDER}))
        ln.append(fill)
        sppr.append(ln)
