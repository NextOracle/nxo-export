"""Word styles as data. The catalogue declares them; ``StyleWriter`` is the only code that writes style XML."""

from __future__ import annotations

from dataclasses import dataclass

from ..theme import Text


@dataclass(frozen=True, slots=True)
class Border:
    sides: tuple[str, ...]
    color: str
    size_eighths: int
    space_pt: float = 0


@dataclass(frozen=True, slots=True)
class ShadedBox:
    """A shaded box around a paragraph; a border in the fill colour provides the padding (Word has none)."""

    fill: str
    pad_y_px: float
    pad_x_px: float


@dataclass(frozen=True, slots=True)
class LineSpacing:
    twips: int
    rule: str  # "auto" (240 = single), "atLeast", "exact"


@dataclass(frozen=True, slots=True)
class ParagraphStyle:
    name: str
    base: str | None = "Normal"
    font: str | None = None
    text: Text | None = None
    """Size, line height and weight of a rendered element."""
    size_px: float | None = None
    """Font size without a line height (when `text` is not given)."""
    color: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    before_px: float | None = None
    after_px: float | None = None
    line_px: float | None = None
    """Minimum line height; defaults to text.line_px. 0 = leave line spacing alone."""
    line: LineSpacing | None = None
    """Explicit line spacing (overrides line_px)."""
    keep_next: bool | None = None
    keep_lines: bool | None = None
    jc: str | None = None
    ind_px: tuple[float, float] | None = None
    border: Border | None = None
    box: ShadedBox | None = None
    right_tab_twips: int | None = None
    """Right-aligned tab stop with a dotted leader (TOC page numbers)."""
    word_wrap: bool = False
    caps: bool = False
    letter_spacing_twips: int | None = None


@dataclass(frozen=True, slots=True)
class CharacterStyle:
    name: str
    font: str | None = None
    size_px: float | None = None
    color: str | None = None
    fill: str | None = None
    underline: str | None = None
    """Underline colour; None with ``no_underline`` removes inherited underlines."""
    no_underline: bool = False


@dataclass(frozen=True, slots=True)
class TableStyle:
    name: str
    border: str
    pad_y_px: float
    pad_x_px: float
    header_fill: str
    header_bold: bool


StyleSpec = ParagraphStyle | CharacterStyle | TableStyle
