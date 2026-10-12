"""The Writerside light theme expressed as named Word styles: the one place every style is defined.

Everything a business analyst edits is a named style (Body Text, Heading 1-6, Source Code, Table Text,
Callout *), so Word's style pane, "update style to match" and corporate re-theming all work. Spacing reproduces
the vertical rhythm measured on the rendered site (gaps in CSS px; Word adds space-after and space-before)."""

from __future__ import annotations

from ....config import DocxCfg
from ....domain.css import blend
from ..theme import GAP, Text, Theme
from .specs import Border, CharacterStyle, LineSpacing, ParagraphStyle, ShadedBox, StyleSpec, TableStyle

MUTED = 0.7  # Writerside secondary text = text colour at 70 %
FOOTER_ALPHA = 0.75
QUOTE_BAR = "D1D1D2"
SINGLE_LINE = LineSpacing(240, "auto")
FOOTER_TEXT = Text(13, 18, True)  # Writerside overline type
HEADING_LEVELS = 6
TOC_LEVELS = 9


class WritersideStyleCatalogue:
    def __init__(self, theme: Theme, cfg: DocxCfg, text_width_twips: int):
        self.t = theme
        self.cfg = cfg
        self.text_width = text_width_twips
        self.font = cfg.font or theme.font
        self.code_font = cfg.code_font or theme.code_font
        self.muted = blend(theme.color, MUTED)

    def styles(self) -> list[StyleSpec]:
        """In document order (new styles are appended to styles.xml in this order)."""
        return [*self.text(), *self.headings(), *self.front_matter(), *self.toc(), *self.figures(), *self.code(),
                *self.characters(), *self.tables(), *self.callouts(), self.tab_title(), self.footer()]

    def text(self) -> list[StyleSpec]:
        t = self.t
        return [
            ParagraphStyle("Normal", font=self.font, text=t.body, color=t.color, before_px=0, after_px=0),
            ParagraphStyle("Body Text", before_px=0, after_px=GAP["para"]),
            ParagraphStyle("First Paragraph", before_px=0, after_px=GAP["para"]),
            ParagraphStyle("Compact", base="Body Text", before_px=0, after_px=GAP["compact"]),
            ParagraphStyle("Block Text", base="Body Text", color=self.muted, ind_px=(16, 0),
                           border=Border(("left",), QUOTE_BAR, 24, 12)),
        ]

    def headings(self) -> list[StyleSpec]:
        t = self.t
        sizes = {1: t.h1, 2: t.h2, 3: t.h3, 4: t.h4, 5: t.h4, 6: t.h4}
        out: list[StyleSpec] = []
        for lvl in range(1, HEADING_LEVELS + 1):
            before, after = GAP[f"h{min(lvl, 4)}"]
            out.append(ParagraphStyle(f"Heading {lvl}", font=self.font, text=sizes[lvl], color=t.color,
                                      before_px=before, after_px=after, keep_next=True, keep_lines=True,
                                      italic=False))
        return out

    def front_matter(self) -> list[StyleSpec]:
        t = self.t
        return [
            ParagraphStyle("Title", font=self.font, text=t.h1, color=t.color, before_px=0, after_px=GAP["h1"][1],
                           jc="left"),
            ParagraphStyle("Subtitle", font=self.font, text=t.h3, color=self.muted, bold=False, before_px=0,
                           after_px=GAP["h3"][1], jc="left"),
            *(ParagraphStyle(name, font=self.font, text=t.body, color=self.muted, before_px=0,
                             after_px=GAP["compact"], jc="left") for name in ("Author", "Date")),
        ]

    def toc(self) -> list[StyleSpec]:
        t = self.t
        out: list[StyleSpec] = [ParagraphStyle("TOC Heading", base="Heading 1", font=self.font, text=t.h2,
                                               color=t.color, before_px=0, after_px=GAP["h2"][1])]
        for lvl in range(1, TOC_LEVELS + 1):
            out.append(ParagraphStyle(f"toc {lvl}", before_px=0,
                                      after_px=GAP["compact"] if lvl > 1 else GAP["compact"] + 2,
                                      ind_px=(16 * (lvl - 1), 0), bold=lvl == 1, right_tab_twips=self.text_width))
        return out

    def figures(self) -> list[StyleSpec]:
        return [
            *(ParagraphStyle(name, color=self.muted, italic=False, before_px=0, after_px=GAP["para"])
              for name in ("Image Caption", "Table Caption")),
            ParagraphStyle("Figure", before_px=0, after_px=GAP["figure"], jc="left", line_px=0),
            ParagraphStyle("Figure Bordered", base="Figure"),
            ParagraphStyle("Definition Term", bold=True, before_px=0, after_px=GAP["compact"], keep_next=True),
            ParagraphStyle("Definition", before_px=0, after_px=GAP["para"], ind_px=(24, 0)),
        ]

    def code(self) -> list[StyleSpec]:
        t = self.t
        return [
            # A shaded box per block in Writerside's mono font; token colours come from the highlight theme.
            ParagraphStyle("Source Code", font=self.code_font, text=t.code, color=t.color, before_px=0,
                           after_px=GAP["code"], box=ShadedBox(t.code_fill, 12, 16), word_wrap=True),
            # Box-drawing art from plain code blocks: single line spacing so vertical strokes join, no box.
            # TextDiagramPass keeps a diagram on one page and fits it to the column.
            ParagraphStyle("Text Diagram", font=self.code_font, size_px=t.code.size_px, color=t.color,
                           before_px=0, after_px=0, line=SINGLE_LINE, keep_lines=True),
        ]

    def characters(self) -> list[StyleSpec]:
        t = self.t
        return [
            CharacterStyle("Verbatim Char", font=self.code_font, size_px=t.inline_code_px, fill=t.inline_code_fill),
            CharacterStyle("Emoji", font=self.cfg.emoji_font),
            CharacterStyle("Hyperlink", color=t.link, underline=t.link_underline,
                           no_underline=t.link_underline is None),
        ]

    def tables(self) -> list[StyleSpec]:
        t = self.t
        return [
            ParagraphStyle("Table Text", before_px=0, after_px=GAP["cell_para"]),
            TableStyle("Table", t.table_border, t.cell_pad_y_px, t.cell_pad_x_px, t.table_header_fill,
                       t.table_header_bold),
        ]

    def callouts(self) -> list[StyleSpec]:
        return [ParagraphStyle(f"Callout {kind.title()}", color=c.text, before_px=0, after_px=GAP["cell_para"])
                for kind, c in self.t.callouts.items()]

    def tab_title(self) -> StyleSpec:
        return ParagraphStyle("Tab Title", bold=True, before_px=GAP["tab"][0], after_px=GAP["tab"][1],
                              keep_next=True, border=Border(("bottom",), self.t.table_border, 8, 4))

    def footer(self) -> StyleSpec:
        """"PAGE X OF Y" like the PDF: Writerside overline type, centred."""
        return ParagraphStyle("Footer", font=self.font, color=blend(self.t.color, FOOTER_ALPHA), bold=True,
                              before_px=0, after_px=0, jc="center", text=FOOTER_TEXT, caps=True,
                              letter_spacing_twips=20)
