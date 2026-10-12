"""Document properties: title, subject, author, timestamps."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from docx.document import Document

from ..context import PassContext
from .base import DocumentPass

PRODUCER = "nxo-ws-export"


class CorePropertiesPass(DocumentPass):
    name = "properties"

    def run(self, doc: Document, ctx: PassContext, stats: Counter[str]) -> None:
        cp = doc.core_properties
        if ctx.title:
            cp.title = ctx.title
        if ctx.subject:
            cp.subject = ctx.subject
        cp.author = cp.author or PRODUCER
        cp.last_modified_by = PRODUCER
        now = datetime.now(UTC).replace(microsecond=0)
        cp.created = cp.created or now
        cp.modified = now
