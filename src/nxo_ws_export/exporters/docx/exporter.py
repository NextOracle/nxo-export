"""DOCX for editing: builder-rendered light DOM -> semantic HTML -> Pandoc (Writerside styles in reference.docx)
-> OOXML passes for what styles cannot express. DOCX is always light: it is a document to edit and print."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from ..._types import Log
from ...app.job import ExportJob
from ...browser import BrowserSession
from ...config import Config
from ...domain.page import PageBox
from ...errors import ExportError
from ..base import Exporter
from .extract import TopicExtractor
from .html import HtmlAssembler
from .ooxml import PassContext, PostProcessor
from .pandoc import HtmlToDocx, PandocConverter
from .styles import ReferenceDocBuilder
from .theme import ThemeTokens, write_highlight_theme
from .topic import TopicHtml


@dataclass(frozen=True)
class DocxState:
    work: Path
    topics: dict[str, TopicHtml]
    reference: Path
    highlight: Path | None
    ctx: PassContext


class DocxExporter(Exporter[DocxState]):
    format = "docx"

    def __init__(self, cfg: Config, log: Log, converter: HtmlToDocx | None = None,
                 post: PostProcessor | None = None):
        super().__init__(cfg, log)
        self.pandoc = converter or PandocConverter()
        self.post = post or PostProcessor()

    @contextmanager
    def session(self, job: ExportJob) -> Iterator[DocxState]:
        if isinstance(self.pandoc, PandocConverter):
            self.log(self.pandoc.version())
        work = job.scratch / "docx"
        work.mkdir(parents=True, exist_ok=True)
        tokens = ThemeTokens()
        topics: dict[str, TopicHtml] = {}
        render = self.cfg.render.model_copy(update={"theme": "light"})
        with BrowserSession(job.site, render, "light", device_scale_factor=self.cfg.docx.image_scale) as s:
            extractor = TopicExtractor(s, work / "figures", tokens)
            for i, node in enumerate(job.topics, 1):
                self.log(f"[docx {i}/{len(job.topics)}] {node.title}")
                topics[node.url] = extractor.extract(node, uid=i)
        theme = tokens.theme()
        box = PageBox.from_cfg(self.cfg.render.page)
        yield DocxState(
            work=work,
            topics=topics,
            reference=self._reference(theme, work),
            highlight=write_highlight_theme(tokens.prism, theme.color, work / "writerside.theme")
            if self.cfg.docx.highlight else None,
            ctx=PassContext(theme=theme, text_width=box.text_width_twips, text_height=box.text_height_twips,
                            min_scale=self.cfg.render.table_min_scale),
        )

    def _reference(self, theme, work: Path) -> Path:
        if self.cfg.docx.reference_doc:
            ref = self.cfg.docx.reference_doc.expanduser().resolve()
            if not ref.is_file():
                raise ExportError(f"docx.reference_doc {ref} not found")
            return ref
        template = PandocConverter().default_reference_docx()
        return ReferenceDocBuilder(theme, self.cfg.docx, self.cfg.render.page).build(template, work / "reference.docx")

    def _convert(self, src: Path, out: Path, job: ExportJob, state: DocxState, **kw) -> None:
        for w in self.pandoc.convert(src, out, resource_path=job.site.root, reference=state.reference,
                                     highlight=state.highlight, **kw):
            self.log(f"pandoc: {w}")

    def write_per_topic(self, state: DocxState, job: ExportJob) -> list[Path]:
        out_dir = job.out_root / "docx"
        out_dir.mkdir(parents=True, exist_ok=True)
        html = HtmlAssembler(state.topics, self.cfg.render.link_base_url)
        outs = []
        for i, node in enumerate(job.topics, 1):
            t = state.topics[node.url]
            src = state.work / f"{i:03d}-{node.slug}.html"
            src.write_text(html.topic(t), encoding="utf-8")
            out = out_dir / f"{i:03d}-{node.slug}.docx"
            self._convert(src, out, job, state)
            self.post.run(out, replace(state.ctx, table_scales=t.tables, combined=False, toc_depth=None,
                                       title=node.title))
            outs.append(out)
        self.log(f"per-topic DOCX: {out_dir} ({len(outs)} files)")
        return outs

    def write_combined(self, state: DocxState, job: ExportJob) -> Path:
        render = self.cfg.render
        subtitle = render.cover.subtitle
        toc_depth = render.toc.depth if (self.cfg.docx.toc and render.toc.enabled) else None
        src = state.work / "combined.html"
        src.write_text(HtmlAssembler(state.topics, render.link_base_url).combined(job.site, job.title),
                       encoding="utf-8")
        meta = {"title": job.title, "toc-title": render.toc.title, "date": date.today().isoformat()}
        if subtitle:
            meta["subtitle"] = subtitle
        out = job.out_root / f"{job.instance_id}.docx"
        out.parent.mkdir(parents=True, exist_ok=True)
        self._convert(src, out, job, state, meta=meta, toc_depth=toc_depth)
        scales: dict[str, float] = {}
        for t in state.topics.values():
            scales.update(t.tables)
        stats = self.post.run(out, replace(state.ctx, table_scales=scales, combined=True, toc_depth=toc_depth,
                                           title=job.title, subject=subtitle))
        self.log(f"combined DOCX: {out} ({stats['tables']} tables, {stats['callouts']} callouts, "
                 f"{stats['figures']} figures, {stats['text_diagrams']} text diagrams)")
        return out
