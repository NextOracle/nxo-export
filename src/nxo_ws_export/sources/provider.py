"""Where the rendered site comes from (Strategy): an existing build, or the Writerside builder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .._types import Log
from ..config import Config
from ..domain.site import Site
from ..errors import ExportError
from .builder import BuildResult, DockerSiteBuilder
from .project import load_project
from .site_loader import load_site, site_root


@dataclass(frozen=True)
class AcquiredSite:
    site: Site
    instance_id: str
    build: BuildResult | None = None
    warnings: tuple[str, ...] = ()


class SiteProvider(Protocol):
    def acquire(self, scratch: Path) -> AcquiredSite: ...


class PrebuiltSite:
    """`--site DIR|ZIP`: a site built elsewhere (CI artifact, IDE build)."""

    def __init__(self, path: Path):
        self.path = path

    def acquire(self, scratch: Path) -> AcquiredSite:
        site = load_site(site_root(self.path, scratch))
        return AcquiredSite(site, site.product_id)


class WritersideBuild:
    """Builds the configured project instance with the pinned builder image (cached by source fingerprint)."""

    def __init__(self, cfg: Config, log: Log):
        self.cfg = cfg
        self.log = log

    def acquire(self, scratch: Path) -> AcquiredSite:
        warnings: list[str] = []
        project = load_project(self.cfg.project.path)
        for orphan in project.orphan_trees:
            warnings.append(f"{orphan.name} is not referenced by writerside.cfg and is ignored")
        instance = project.instance(self.cfg.project.instance)
        build = DockerSiteBuilder(self.cfg.builder, self.log).build(project, instance)
        if build.errors:
            codes = sorted({e.code for e in build.errors})
            msg = (f"Writerside reported {len(build.errors)} inspection error(s) ({', '.join(codes)}); "
                   f"see {build.site_dir.parent / 'report.html'}")
            if self.cfg.output.strict:
                raise ExportError(msg)
            warnings.append(msg + " (output still produced)")
        return AcquiredSite(load_site(build.site_dir), instance.id, build, tuple(warnings))
