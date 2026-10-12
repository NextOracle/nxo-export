"""Bookmarks: remove the table/callout tags, hide anchor bookmarks.

A leading underscore hides a bookmark in Word's list. Pandoc would hash such names, so the underscore is added
here, together with the hyperlinks to them."""

from __future__ import annotations

import re
from collections import Counter

from docx.document import Document
from docx.oxml.ns import qn

from ..context import PassContext
from .base import DocumentPass

INTERNAL = re.compile(r"^nxo-(t|callout)-")
ANCHOR = re.compile(r"^nxoa\d+$")


class BookmarkPass(DocumentPass):
    name = "bookmarks"

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        body = doc.element.body
        ids = set()
        for b in list(body.iter(qn("w:bookmarkStart"))):
            name = b.get(qn("w:name")) or ""
            if INTERNAL.match(name):
                ids.add(b.get(qn("w:id")))
                b.getparent().remove(b)
            elif ANCHOR.match(name):
                b.set(qn("w:name"), "_" + name)
        for h in body.iter(qn("w:hyperlink")):
            a = h.get(qn("w:anchor")) or ""
            if ANCHOR.match(a):
                h.set(qn("w:anchor"), "_" + a)
        for b in list(body.iter(qn("w:bookmarkEnd"))):
            if b.get(qn("w:id")) in ids:
                b.getparent().remove(b)
