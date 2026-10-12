"""reference.docx: Pandoc's default document re-styled from the catalogue, with page setup and footer."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.document import Document as DocumentT
from docx.oxml.ns import qn
from lxml import etree

from ....config import DocxCfg, PageCfg
from ....domain.page import PageBox
from ....domain.units import half_points, twips
from ..ooxml import xml as ox
from ..theme import Theme
from .catalogue import WritersideStyleCatalogue
from .writer import StyleWriter

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PRODUCER = "nxo-ws-export"


class ReferenceDocBuilder:
    def __init__(self, theme: Theme, cfg: DocxCfg, page: PageCfg):
        self.theme = theme
        self.cfg = cfg
        self.page = page
        self.box = PageBox.from_cfg(page)
        self.catalogue = WritersideStyleCatalogue(theme, cfg, self.box.text_width_twips)

    def build(self, template: bytes, out: Path) -> Path:
        """`template`: Pandoc's default reference.docx (it defines the style names Pandoc emits)."""
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(template)
        doc = Document(str(out))
        self._defaults(doc)
        writer = StyleWriter(doc)
        for spec in self.catalogue.styles():
            writer.apply(spec)
        self._footer(doc)
        self._page_setup(doc)
        doc.core_properties.title = ""
        doc.core_properties.author = PRODUCER
        doc.save(str(out))
        self._font_fallbacks(out, {self.catalogue.font: self.cfg.font_fallback,
                                   self.catalogue.code_font: self.cfg.code_font_fallback})
        return out

    def _defaults(self, doc: DocumentT) -> None:
        """Document defaults: everything inherits font, size and colour."""
        rpr = doc.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault")).find(qn("w:rPr"))
        ox.fonts(rpr, self.catalogue.font)
        ox.put(rpr, "color", val=self.theme.color)
        ox.put(rpr, "sz", val=half_points(self.theme.body.size_px))
        ox.put(rpr, "szCs", val=half_points(self.theme.body.size_px))

    @staticmethod
    def _footer(doc: DocumentT) -> None:
        """"Page X of Y" with fields Word keeps up to date, in the "Footer" style."""
        footer = doc.sections[0].footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        for r in list(p._p):
            if ox.local(r) != "pPr":
                p._p.remove(r)
        p.style = doc.styles["Footer"]

        def run(text: str | None = None, fld: str | None = None, instr: str | None = None) -> None:
            if text is not None:
                p._p.append(ox.text_run(text))
                return
            r = ox.make("r")
            if fld:
                r.append(ox.make("fldChar", fldCharType=fld))
            else:
                it = ox.make("instrText")
                it.set(ox.XML_SPACE, "preserve")
                it.text = instr
                r.append(it)
            p._p.append(r)

        def field(code: str, placeholder: str) -> None:
            run(fld="begin")
            run(instr=f" {code} ")
            run(fld="separate")
            run(placeholder)
            run(fld="end")

        run("Page ")
        field("PAGE", "1")
        run(" of ")
        field("NUMPAGES", "1")

    def _page_setup(self, doc: DocumentT) -> None:
        b = self.box
        sect = doc.sections[-1]._sectPr
        ox.put(sect, "pgSz", w=twips(b.width), h=twips(b.height), **({"orient": "landscape"} if b.landscape else {}))
        ox.put(sect, "pgMar", top=twips(b.margin_top), right=twips(b.margin_x), bottom=twips(b.margin_bottom),
               left=twips(b.margin_x), header=twips(b.margin_top / 2), footer=twips(b.margin_bottom / 2), gutter=0)

    @staticmethod
    def _font_fallbacks(path: Path, fallbacks: dict[str, str | None]) -> None:
        """Declare Writerside fonts with an alternate (w:altName) so machines without them substitute sensibly."""
        doc = Document(str(path))
        part = next((p for p in doc.part.package.parts if str(p.partname) == "/word/fontTable.xml"), None)
        if part is None:
            return
        root = etree.fromstring(part.blob)
        for name, alt in fallbacks.items():
            if not alt or name == alt:
                continue
            for old in root.findall(f"{{{_W}}}font"):
                if old.get(f"{{{_W}}}name") == name:
                    root.remove(old)
            mono = "Mono" in name or "Code" in name
            font = etree.SubElement(root, f"{{{_W}}}font", {f"{{{_W}}}name": name})
            etree.SubElement(font, f"{{{_W}}}altName", {f"{{{_W}}}val": alt})
            etree.SubElement(font, f"{{{_W}}}family", {f"{{{_W}}}val": "modern" if mono else "swiss"})
            etree.SubElement(font, f"{{{_W}}}pitch", {f"{{{_W}}}val": "fixed" if mono else "variable"})
        part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        doc.save(str(path))
