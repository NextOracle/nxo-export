"""Orchestration: config -> (build | given site) -> PDF / DOCX outputs."""

from __future__ import annotations

import fnmatch
import re
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .builder import Builder, BuildResult
from .config import Config
from .project import load_project
from .site import Site, TocNode, load_site


class ExportError(Exception):
    pass


@dataclass
class ExportReport:
    instance: str
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    build: BuildResult | None = None


def _filter_topics(site: Site, patterns: tuple[str, ...]) -> list[TocNode]:
    topics = site.topics()
    if not patterns:
        return topics
    keep = [
        t for t in topics
        if any(fnmatch.fnmatch(k.lower(), p.lower()) for p in patterns for k in (t.id, t.slug, t.url or ""))
    ]
    if not keep:
        raise ExportError(f"no topic matches {', '.join(patterns)}")
    return keep


def _resolve_site(site_arg: Path, scratch: Path) -> Path:
    site_arg = site_arg.expanduser().resolve()
    if site_arg.is_file() and zipfile.is_zipfile(site_arg):
        dest = scratch / "site"
        with zipfile.ZipFile(site_arg) as z:
            z.extractall(dest)
        found = [p.parent for p in dest.rglob("HelpTOC.json")]
        if not found:
            raise ExportError(f"{site_arg} does not contain a Writerside site (HelpTOC.json)")
        return found[0]
    return site_arg


def shift_headings(html: str, shift: int) -> str:
    if shift <= 0:
        return html
    return re.sub(r"<(/?)h([1-6])\b", lambda m: f"<{m.group(1)}h{min(6, int(m.group(2)) + shift)}", html)


def export(
    cfg: Config,
    *,
    site_path: Path | None = None,
    topics: tuple[str, ...] = (),
    log: Callable[[str], None] = print,
) -> ExportReport:
    out_cfg = cfg.output
    warnings: list[str] = []

    if "docx" in out_cfg.formats and cfg.render.theme == "dark":
        msg = "theme 'dark' applies to PDF only; DOCX is always rendered in the light theme"
        if out_cfg.strict and out_cfg.formats == ["docx"]:
            raise ExportError(msg)
        warnings.append(msg)

    scratch = Path(tempfile.mkdtemp(prefix="nxo-ws-export-"))
    try:
        build: BuildResult | None = None
        if site_path is not None:
            site_dir = _resolve_site(site_path, scratch)
            instance_id = None
        else:
            project = load_project(cfg.project.path)
            for orphan in project.orphan_trees:
                warnings.append(f"{orphan.name} is not referenced by writerside.cfg and is ignored")
            instance = project.instance(cfg.project.instance)
            build = Builder(cfg.builder, log).build(project, instance)
            site_dir, instance_id = build.site_dir, instance.id
            if build.errors:
                codes = sorted({e.code for e in build.errors})
                msg = (f"Writerside reported {len(build.errors)} inspection error(s) ({', '.join(codes)}); "
                       f"see {build.site_dir.parent / 'report.html'}")
                if out_cfg.strict:
                    raise ExportError(msg)
                warnings.append(msg + " (output still produced)")
        site = load_site(site_dir)
        instance_id = instance_id or str(site.config.get("productId") or site_dir.name)
        title = cfg.render.cover.title or site.product_name
        selected = _filter_topics(site, topics)

        report = ExportReport(instance=instance_id, warnings=warnings, build=build)
        root = out_cfg.dir.expanduser().resolve() / instance_id
        want_combined = out_cfg.mode in ("combined", "both")
        want_topics = out_cfg.mode in ("per-topic", "both")
        sub = None
        if topics:
            sub = _subset_site(site, {t.url for t in selected})

        if "pdf" in out_cfg.formats:
            report.outputs += _export_pdf(cfg, sub or site, selected, root, instance_id, title,
                                          want_combined, want_topics, log)
        if "docx" in out_cfg.formats:
            report.outputs += _export_docx(cfg, sub or site, selected, root, instance_id, title,
                                           want_combined, want_topics, scratch, log)
        return report
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _subset_site(site: Site, urls: set[str | None]) -> Site:
    def prune(n: TocNode) -> TocNode | None:
        kids = [c for c in (prune(c) for c in n.children) if c]
        if (n.url in urls) or kids:
            return TocNode(n.id, n.title, n.url if n.url in urls else None, n.level, kids)
        return None

    return Site(site.root, [t for t in (prune(n) for n in site.toc) if t], site.product_name, site.config)


def _export_pdf(cfg, site, selected, root, instance_id, title, combined, per_topic, log) -> list[Path]:
    from .render import pdf
    from .render.browser import Session

    theme = cfg.render.theme
    outs: list[Path] = []
    with Session(site, cfg.render, theme) as s:
        rendered = []
        for i, node in enumerate(selected, 1):
            log(f"[pdf {theme} {i}/{len(selected)}] {node.title}")
            rendered.append(pdf.render_topic(s, node))
        if per_topic:
            outs += pdf.write_topic_pdfs(s, rendered, root / f"pdf-{theme}", cfg.render.page_numbers)
            log(f"per-topic PDFs: {root / f'pdf-{theme}'} ({len(rendered)} files)")
        if combined:
            outs.append(pdf.write_combined_pdf(s, site, rendered, root / f"{instance_id}-{theme}.pdf", title, log))
    return outs


def _export_docx(cfg, site, selected, root, instance_id, title, combined, per_topic, scratch, log) -> list[Path]:
    from .render import docx
    from .render.browser import Session

    log(docx.pandoc_version())
    work = scratch / "docx"
    work.mkdir(parents=True, exist_ok=True)
    outs: list[Path] = []
    tokens: dict = {}
    extracted: dict[str, docx.TopicHtml] = {}
    # DOCX is always light: it is a document to edit and print, not a screen theme.
    with Session(site, cfg.render.model_copy(update={"theme": "light"}), "light",
                 device_scale_factor=cfg.docx.image_scale) as s:
        for i, node in enumerate(selected, 1):
            log(f"[docx {i}/{len(selected)}] {node.title}")
            extracted[node.url] = docx.extract_topic(s, node, work / "figures", f"{node.slug}--", tokens, uid=i)
    theme = docx.Theme.from_tokens(tokens)
    if cfg.docx.reference_doc:
        reference = cfg.docx.reference_doc.expanduser().resolve()
        if not reference.is_file():
            raise ExportError(f"docx.reference_doc {reference} not found")
    else:
        reference = docx.build_reference_docx(theme, cfg.docx, cfg.render.page, work / "reference.docx")
    highlight = None
    if cfg.docx.highlight:
        prism: dict = {}
        for t in extracted.values():
            for k, v in t.prism.items():
                prism.setdefault(k, v)
        highlight = docx.write_highlight_theme(prism, theme.color, work / "writerside.theme")
    ctx = docx.PostCtx(theme=theme, text_width=docx.text_width_twips(cfg.render.page),
                       text_height=docx.text_height_twips(cfg.render.page),
                       min_scale=cfg.render.table_min_scale)
    link_base = cfg.render.link_base_url
    if per_topic:
        for i, node in enumerate(selected, 1):
            outs.append(docx.write_topic_docx(extracted[node.url], i, root / "docx", work, site, reference, highlight,
                                              ctx, extracted, link_base, log))
        log(f"per-topic DOCX: {root / 'docx'} ({len(selected)} files)")
    if combined:
        shifted = {u: replace(t, html=shift_headings(t.html, t.node.level)) for u, t in extracted.items()}
        outs.append(docx.write_combined_docx(
            site, shifted, root / f"{instance_id}.docx", work, reference, highlight, ctx, title,
            cfg.render.cover.subtitle, cfg.render.toc.depth if (cfg.docx.toc and cfg.render.toc.enabled) else None,
            cfg.render.toc.title, link_base, log,
        ))
    return outs
