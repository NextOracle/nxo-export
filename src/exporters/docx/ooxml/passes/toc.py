"""Table of contents: pre-populated with the headings (as links), so it reads correctly before Word refreshes
page numbers, and in viewers that never do (LibreOffice preview, Google Docs, web previews)."""

from __future__ import annotations

from collections import Counter

from docx.document import Document
from docx.oxml.ns import qn

from .. import xml as ox
from ..context import PassContext
from .base import DocumentPass


class TocPass(DocumentPass):
    name = "toc"

    def applies(self, ctx: PassContext) -> bool:
        return bool(ctx.toc_depth)

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        assert ctx.toc_depth
        self._populate(doc, ctx.toc_depth)
        settings = doc.settings.element
        if settings.find(qn("w:updateFields")) is None:
            settings.append(ox.make("updateFields", val="true"))

    @staticmethod
    def _entries(doc: Document, depth: int, by_name: dict[str, str]) -> list[tuple[int, str, str]]:
        body = doc.element.body
        levels = {by_name.get(f"heading {i}", f"Heading{i}"): i for i in range(1, depth + 1)}
        entries: list[tuple[int, str, str]] = []
        for p in body.iter(qn("w:p")):
            if p.getparent() is not body:
                continue
            lvl = levels.get(ox.pstyle(p) or "")
            if not lvl:
                continue
            text = ox.text_of(p).strip()
            bm = p.find(qn("w:bookmarkStart"))
            prev = p.getprevious()
            while bm is None and prev is not None and ox.local(prev) in ("bookmarkStart", "bookmarkEnd"):
                if ox.local(prev) == "bookmarkStart":
                    bm = prev
                prev = prev.getprevious()
            if text and bm is not None:
                entries.append((lvl, text, bm.get(qn("w:name"))))
        return entries

    def _populate(self, doc: Document, depth: int) -> None:
        sdt = doc.element.body.find(qn("w:sdt"))
        if sdt is None:
            return
        content = sdt.find(qn("w:sdtContent"))
        field_p = next((p for p in content.findall(qn("w:p")) if p.find(".//" + qn("w:instrText")) is not None),
                       None)
        if field_p is None:
            return
        by_name = {s.name.lower(): s.style_id for s in doc.styles if s.name}
        entries = self._entries(doc, depth, by_name)
        if not entries:
            return

        chars = list(field_p.iter(qn("w:fldChar")))
        begin, instr, sep, end = chars[0], field_p.find(".//" + qn("w:instrText")), chars[1], chars[-1]

        def run_of(el):
            r = ox.make("r")
            r.append(el)
            return r

        paras = []
        for i, (lvl, text, anchor) in enumerate(entries):
            p = ox.make("p")
            ox.put(ox.child(p, "pPr"), "pStyle", val=by_name.get(f"toc {lvl}", f"TOC{lvl}"))
            if i == 0:
                for el in (begin, instr, sep):
                    el.getparent().remove(el)
                    p.append(run_of(el))
            link = ox.make("hyperlink", anchor=anchor, history=1)
            link.append(ox.text_run(text))
            p.append(link)
            paras.append(p)
        end.getparent().remove(end)
        paras[-1].append(run_of(end))
        for p in paras:
            field_p.addprevious(p)
        field_p.getparent().remove(field_p)
