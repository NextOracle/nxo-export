"""Output formats, in the order they are produced."""

from __future__ import annotations

from .base import Exporter
from .docx import DocxExporter
from .pdf import PdfExporter

FORMATS: dict[str, type[Exporter]] = {"pdf": PdfExporter, "docx": DocxExporter}
