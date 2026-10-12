"""Topic extraction from the flattened light-theme DOM: figures rasterised first, then normalised HTML."""

from __future__ import annotations

from pathlib import Path

from ...browser import BrowserSession
from ...browser.scripts import MarkFigures, PrepareForDocx, ReadTheme
from ...domain.site import TocNode
from ...errors import RenderError
from .theme import ThemeTokens
from .topic import TopicHtml

MIN_FIGURE_PX = 48

_REPLACE_WITH_IMG = """(e, [src, w]) => { const i = document.createElement('img'); i.setAttribute('src', src); i.alt = e.getAttribute('aria-label') || e.getAttribute('alt') || '';
                                      i.setAttribute('data-nxo-figure', '1'); i.setAttribute('data-nxo-width', String(w[0])); i.setAttribute('data-nxo-height', String(w[1]));
                                      e.replaceWith(i); }"""
_ARTICLE_HTML = (
    "(() => { const a = document.querySelector('article.app__article .article') || "
    "document.querySelector('article.app__article'); return a ? a.innerHTML : null; })()"
)


class TopicExtractor:
    def __init__(self, session: BrowserSession, fig_dir: Path, tokens: ThemeTokens):
        self.session = session
        self.fig_dir = fig_dir
        self.tokens = tokens

    def extract(self, node: TocNode, uid: int) -> TopicHtml:
        page, _ = self.session.open_topic(node, symbolic_links=True)
        try:
            self.tokens.add(ReadTheme.run(page))
            # Rasterise while every figure still has its own styles (Mermaid colours live in an inner <style>).
            figs = MarkFigures.run(page, min_figure=MIN_FIGURE_PX)
            self.fig_dir.mkdir(parents=True, exist_ok=True)
            for i, f in enumerate(figs):
                el = page.query_selector(f'[data-nxo-fig="{f["id"]}"]')
                if el is None:
                    continue
                png = self.fig_dir / f"{node.slug}-{i + 1}.png"
                el.screenshot(path=str(png), animations="disabled", omit_background=False)
                el.evaluate(_REPLACE_WITH_IMG, [png.resolve().as_posix(), [f["width"], f["height"]]])
            info = PrepareForDocx.run(page, heading_shift=0, id_prefix=f"{node.slug}--", uid=uid)
            html = page.evaluate(_ARTICLE_HTML)
            if html is None:
                raise RenderError(f"{node.url}: article content not found after DOCX preparation")
        finally:
            page.close()
        prism = info.get("prism", {})
        self.tokens.add_prism(prism)
        return TopicHtml(
            node, html, len(figs), info.get("anchor"), frozenset(info.get("ids", [])),
            {t["id"]: float(t["scale"]) for t in info.get("tables", [])}, prism,
        )
