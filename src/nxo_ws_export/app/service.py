"""Use case: configuration -> site -> topic selection -> every requested format -> report."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .._types import Log
from ..config import Config
from ..errors import ExportError
from ..sources.provider import PrebuiltSite, SiteProvider, WritersideBuild
from .job import ExportJob
from .report import ExportReport


class ExportService:
    def __init__(self, cfg: Config, log: Log = print):
        self.cfg = cfg
        self.log = log

    def run(self, provider: SiteProvider, topics: tuple[str, ...] = ()) -> ExportReport:
        from ..exporters.registry import FORMATS

        out = self.cfg.output
        warnings = self._preflight()
        scratch = Path(tempfile.mkdtemp(prefix="nxo-ws-export-"))
        try:
            acquired = provider.acquire(scratch)
            warnings += acquired.warnings
            site = acquired.site
            selected = site.select(topics)
            job = ExportJob(
                site=site.subset({t.url for t in selected}) if topics else site,
                topics=tuple(selected),
                instance_id=acquired.instance_id,
                title=self.cfg.render.cover.title or site.product_name,
                out_root=out.dir.expanduser().resolve() / acquired.instance_id,
                combined=out.mode in ("combined", "both"),
                per_topic=out.mode in ("per-topic", "both"),
                scratch=scratch,
            )
            report = ExportReport(instance=acquired.instance_id, warnings=warnings, build=acquired.build)
            for fmt, exporter in FORMATS.items():
                if fmt in out.formats:
                    report.outputs += exporter(self.cfg, self.log).export(job)
            return report
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def _preflight(self) -> list[str]:
        out = self.cfg.output
        if "docx" in out.formats and self.cfg.render.theme == "dark":
            msg = "theme 'dark' applies to PDF only; DOCX is always rendered in the light theme"
            if out.strict and out.formats == ["docx"]:
                raise ExportError(msg)
            return [msg]
        return []


def export(cfg: Config, *, site_path: Path | None = None, topics: tuple[str, ...] = (),
           log: Log = print) -> ExportReport:
    """Build the configured project (or use `site_path`) and write every configured format."""
    provider: SiteProvider = PrebuiltSite(site_path) if site_path is not None else WritersideBuild(cfg, log)
    return ExportService(cfg, log).run(provider, topics)
