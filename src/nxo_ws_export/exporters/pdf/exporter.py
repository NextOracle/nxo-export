"""PDF: each topic printed by Chromium from the real Writerside page (light or dark), assembled with pypdf."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ...app.job import ExportJob
from ...browser import BrowserSession
from ..base import Exporter
from .composer import CombinedPdfComposer, TopicPdfWriter
from .footer import PageNumberStamper
from .printer import PagePrinter, TopicPdf


@dataclass(frozen=True)
class PdfState:
    printer: PagePrinter
    stamper: PageNumberStamper
    rendered: tuple[TopicPdf, ...]


class PdfExporter(Exporter[PdfState]):
    format = "pdf"

    @property
    def theme(self) -> str:
        return self.cfg.render.theme

    @contextmanager
    def session(self, job: ExportJob) -> Iterator[PdfState]:
        with BrowserSession(job.site, self.cfg.render, self.cfg.render.theme) as s:
            printer = PagePrinter(s)
            rendered = []
            for i, node in enumerate(job.topics, 1):
                self.log(f"[pdf {self.theme} {i}/{len(job.topics)}] {node.title}")
                rendered.append(printer.topic(node))
            yield PdfState(printer, PageNumberStamper(s), tuple(rendered))

    def write_per_topic(self, state: PdfState, job: ExportJob) -> list[Path]:
        out_dir = job.out_root / f"pdf-{self.theme}"
        paths = TopicPdfWriter(state.stamper, self.cfg.render.page_numbers).write(state.rendered, out_dir)
        self.log(f"per-topic PDFs: {out_dir} ({len(state.rendered)} files)")
        return paths

    def write_combined(self, state: PdfState, job: ExportJob) -> Path:
        out = job.out_root / f"{job.instance_id}-{self.theme}.pdf"
        return CombinedPdfComposer(state.printer, state.stamper, self.log).compose(
            job.site, state.rendered, out, job.title)
