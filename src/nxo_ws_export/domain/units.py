"""Typographic unit conversions. CSS px are 1/96 in; Word measures in twips (1/20 pt), half-points and EMU."""

from __future__ import annotations

from typing import NewType

Px = float
Twips = NewType("Twips", int)
HalfPoints = NewType("HalfPoints", int)
Emu = NewType("Emu", int)

PX_PER_INCH = 96
TWIPS_PER_PX = 15  # 1px = 0.75pt = 15 twips
EMU_PER_TWIP = 635


def twips(px: Px) -> Twips:
    return Twips(round(px * TWIPS_PER_PX))


def half_points(px: Px) -> HalfPoints:
    """Font size attribute (w:sz). Word rejects sizes below 1pt."""
    return HalfPoints(max(2, round(px * 0.75 * 2)))


def twips_to_emu(value: int) -> Emu:
    return Emu(value * EMU_PER_TWIP)
