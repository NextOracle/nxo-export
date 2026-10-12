"""Pandoc input: extracted topics -> standalone HTML documents with resolved links and Word-safe ids."""

from .assembler import HtmlAssembler, html_document, shift_headings, short_ids
from .links import LinkResolver

__all__ = ["HtmlAssembler", "LinkResolver", "html_document", "shift_headings", "short_ids"]
