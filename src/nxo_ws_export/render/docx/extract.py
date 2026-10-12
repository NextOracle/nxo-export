"""Topic extraction from the flattened light-theme DOM (figures rasterised first, then normalised HTML)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...site import TocNode
from ..browser import RenderError, Session, asset
from .theme import merge_tokens

MIN_FIGURE_PX = 48


@dataclass
class TopicHtml:
    node: TocNode
    html: str
    figures: int
    anchor: str | None = None
    ids: set[str] = field(default_factory=set)
    tables: dict[str, float] = field(default_factory=dict)
    prism: dict[str, dict] = field(default_factory=dict)


def extract_topic(session: Session, node: TocNode, fig_dir: Path, id_prefix: str, tokens: dict | None = None,
                  heading_shift: int = 0, uid: int = 0) -> TopicHtml:
    page, _ = session.open_topic(node, symbolic_links=True)
    try:
        if tokens is not None:
            merge_tokens(tokens, page.evaluate(asset("docx_theme.js")))
        # Rasterise while every figure still has its own styles (Mermaid colours live in an inner <style>).
        figs = page.evaluate(asset("docx_figures.js"), {"minFigure": MIN_FIGURE_PX})
        fig_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(figs):
            el = page.query_selector(f'[data-nxo-fig="{f["id"]}"]')
            if el is None:
                continue
            png = fig_dir / f"{node.slug}-{i + 1}.png"
            el.screenshot(path=str(png), animations="disabled", omit_background=False)
            el.evaluate(
                """(e, [src, w]) => { const i = document.createElement('img'); i.setAttribute('src', src); i.alt = e.getAttribute('aria-label') || e.getAttribute('alt') || '';
                                      i.setAttribute('data-nxo-figure', '1'); i.setAttribute('data-nxo-width', String(w[0])); i.setAttribute('data-nxo-height', String(w[1]));
                                      e.replaceWith(i); }""",
                [png.resolve().as_posix(), [f["width"], f["height"]]],
            )
        info = page.evaluate(asset("docx_prepare.js"), {"headingShift": heading_shift, "idPrefix": id_prefix, "uid": uid})
        html = page.evaluate(
            "(() => { const a = document.querySelector('article.app__article .article') || "
            "document.querySelector('article.app__article'); return a ? a.innerHTML : null; })()"
        )
        if html is None:
            raise RenderError(f"{node.url}: article content not found after DOCX preparation")
    finally:
        page.close()
    return TopicHtml(
        node, html, len(figs), info.get("anchor"), set(info.get("ids", [])),
        {t["id"]: float(t["scale"]) for t in info.get("tables", [])}, info.get("prism", {}),
    )
