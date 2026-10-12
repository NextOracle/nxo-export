"""Vertical rhythm of the default Writerside theme, in CSS px (measured gaps between rendered blocks).

Word adds space-after of one paragraph and space-before of the next, so each gap is split accordingly."""

from __future__ import annotations

GAP = {
    "para": 24, "compact": 6, "list_end": 24, "code": 24, "figure": 24, "after_table": 12, "cell_para": 8,
    "h1": (0, 32), "h2": (40, 32), "h3": (24, 24), "h4": (8, 16), "tab": (16, 8),
}
