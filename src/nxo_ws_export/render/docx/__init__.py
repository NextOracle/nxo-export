"""Stage 2b: DOCX for editing (ADR-8/9).

Builder-rendered light-theme DOM (includes, variables, snippets and filters resolved; Mermaid rendered) ->
figures rasterised from the exact rendered SVG -> semantic HTML -> Pandoc with a reference.docx that expresses the
Writerside theme as named Word styles -> OOXML post-processing for what styles cannot express (table layout,
callout boxes, figure sizing, rhythm, TOC, chapter breaks). DOCX is always light.

Package layout:
  theme.py        computed theme -> Word units, syntax-highlight theme from rendered Prism colours
  reference.py    reference.docx (styles, table style, page setup, footer)
  extract.py      browser-side extraction per topic
  links.py        nxo:<page>#<anchor> -> in-document bookmark / published URL / plain text
  postprocess.py  OOXML fixes
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path

from ...site import Site, TocNode
from ..browser import RenderError
from .extract import TopicHtml, extract_topic
from .links import resolve_links
from .postprocess import PostCtx, postprocess
from .reference import build_reference_docx, text_height_twips, text_width_twips
from .theme import Theme, css_color_to_hex, first_font, write_highlight_theme

__all__ = [
    "DocxError", "PostCtx", "Theme", "TopicHtml", "build_reference_docx", "css_color_to_hex", "extract_topic",
    "first_font", "pandoc_version", "text_height_twips", "text_width_twips", "write_combined_docx", "write_highlight_theme",
    "write_topic_docx",
]


class DocxError(RenderError):
    pass


def pandoc_version() -> str:
    exe = shutil.which("pandoc")
    if not exe:
        raise DocxError("pandoc not found on PATH (required for DOCX)")
    out = subprocess.run([exe, "--version"], check=False, capture_output=True, text=True).stdout
    return out.splitlines()[0] if out else "pandoc"


_ID = re.compile(r'(\sid="|\shref="#)([^"]+)"')
_HREF = re.compile(r'\shref="#([^"]+)"')
_EMPTY_SPAN = re.compile(r'<span id="([^"]+)"></span>')


def _short_ids(html: str) -> str:
    """Word ignores bookmarks longer than 40 characters, and Pandoc hashes names it considers invalid.
    Heading ids and link targets get a short name ``nxoaN`` (hidden later in post-processing); ids nothing
    links to are dropped, so they do not litter the document with bookmarks. Table/callout tags are kept."""
    targets = set(_HREF.findall(html))
    names: dict[str, str] = {}

    def sub(m: re.Match) -> str:
        attr, ident = m.groups()
        if ident.startswith(("nxo-t-", "nxo-callout-")):
            return m.group(0)
        short = names.setdefault(ident, f"nxoa{len(names) + 1}")
        return f'{attr}{short}"'

    def drop(m: re.Match) -> str:
        return "" if m.group(1) not in targets else m.group(0)

    html = _EMPTY_SPAN.sub(drop, html)
    return _ID.sub(sub, html)


def _html_doc(title: str | None, body: str) -> str:
    # A <title> becomes a Word "Title" paragraph; per-topic documents already start with the topic h1.
    head = f"<title>{_esc(title)}</title>" if title else ""
    return f'<!DOCTYPE html><html><head><meta charset="utf-8">{head}</head><body>{_short_ids(body)}</body></html>'


def run_pandoc(html_file: Path, out: Path, site: Site, reference: Path, highlight: Path | None, meta: dict[str, str],
               toc_depth: int | None, log: Callable[[str], None]) -> None:
    hl = str(highlight) if highlight else "none"
    cmd = [
        "pandoc", str(html_file), "-f", "html", "-t", "docx", "-o", str(out),
        f"--reference-doc={reference}", f"--resource-path={site.root}", f"--syntax-highlighting={hl}",
    ]
    for k, v in meta.items():
        cmd += ["-M", f"{k}={v}"]
    if toc_depth:
        cmd += ["--toc", f"--toc-depth={toc_depth}"]
    r = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if r.returncode != 0 and "syntax-highlighting" in r.stderr:  # pandoc < 3.8
        old = f"--highlight-style={hl}" if highlight else "--no-highlight"
        cmd = [old if c.startswith("--syntax-highlighting") else c for c in cmd]
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if r.returncode != 0:
        raise DocxError(f"pandoc failed for {html_file.name}:\n{r.stderr.strip()}")
    for line in r.stderr.splitlines():
        if line.strip() and "Duplicate identifier" not in line:
            log(f"pandoc: {line.strip()}")


def write_topic_docx(t: TopicHtml, idx: int, out_dir: Path, work: Path, site: Site, reference: Path,
                     highlight: Path | None, ctx: PostCtx, topics: Mapping[str, TopicHtml], link_base_url: str | None,
                     log: Callable[[str], None]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    body = resolve_links(t.html, current=t, topics=topics, internal=lambda u: u == t.node.url,
                         link_base_url=link_base_url)
    src = work / f"{idx:03d}-{t.node.slug}.html"
    src.write_text(_html_doc(None, body), encoding="utf-8")
    out = out_dir / f"{idx:03d}-{t.node.slug}.docx"
    run_pandoc(src, out, site, reference, highlight, {}, None, log)
    postprocess(out, replace(ctx, table_scales=t.tables, combined=False, toc_depth=None, title=t.node.title))
    return out


def write_combined_docx(site: Site, topics: dict[str, TopicHtml], out: Path, work: Path, reference: Path,
                        highlight: Path | None, ctx: PostCtx, title: str, subtitle: str | None,
                        toc_depth: int | None, toc_title: str, link_base_url: str | None,
                        log: Callable[[str], None]) -> Path:
    parts: list[str] = []
    emitted: set[str] = set()

    def visit(n: TocNode) -> None:
        if n.url and n.url in topics and n.url not in emitted:
            emitted.add(n.url)
            t = topics[n.url]
            parts.append(resolve_links(t.html, current=t, topics=topics, internal=lambda u: u in topics,
                                       link_base_url=link_base_url))
        elif not n.url and _has_selected(n, topics):
            lvl = min(6, n.level + 1)
            parts.append(f'<h{lvl} id="group-{len(parts)}">{_esc(n.title)}</h{lvl}>')
        for c in n.children:
            visit(c)

    for top in site.toc:
        visit(top)
    src = work / "combined.html"
    src.write_text(_html_doc(title, "\n".join(parts)), encoding="utf-8")
    meta = {"title": title, "toc-title": toc_title, "date": date.today().isoformat()}
    if subtitle:
        meta["subtitle"] = subtitle
    out.parent.mkdir(parents=True, exist_ok=True)
    run_pandoc(src, out, site, reference, highlight, meta, toc_depth, log)
    scales: dict[str, float] = {}
    for t in topics.values():
        scales.update(t.tables)
    stats = postprocess(out, replace(ctx, table_scales=scales, combined=True, toc_depth=toc_depth, title=title,
                                     subject=subtitle))
    log(f"combined DOCX: {out} ({stats['tables']} tables, {stats['callouts']} callouts, {stats['figures']} figures, {stats['text_diagrams']} text diagrams)")
    return out


def _has_selected(n: TocNode, topics: Mapping[str, TopicHtml]) -> bool:
    return any((c.url in topics) or _has_selected(c, topics) for c in n.children)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
