"""One Chromium + one served site + one colour scheme, laid out at the printable page width."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from ..config import RenderCfg
from ..domain.page import PageBox
from ..domain.site import Site, TocNode
from ..errors import RenderError
from ..sources.site_loader import SiteServer
from .cdn_cache import AssetCache
from .scripts import FitForPrint, Flatten, PrintCss

ColorScheme = Literal["light", "dark"]
FIGURE_HEADROOM_PX = 160
"""Room left above a page-tall figure for its heading, so the heading is not orphaned (PDF and DOCX)."""


class BrowserSession:
    """Use as a context manager. Pages are laid out at the printable width, so screen measurements equal the
    printed layout."""

    def __init__(self, site: Site, cfg: RenderCfg, scheme: ColorScheme, device_scale_factor: float = 1.0):
        self.site = site
        self.cfg = cfg
        self.scheme = scheme
        self.dsf = device_scale_factor
        self.cache = AssetCache(cfg.asset_cache_dir, cfg.offline)
        self.content_w, self.content_h = PageBox.from_cfg(cfg.page).content_px
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None
        self._server: SiteServer | None = None

    def __enter__(self) -> BrowserSession:
        self._server = SiteServer(self.site.root).__enter__()
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch()
        except Exception as e:
            self.__exit__(None, None, None)
            raise RenderError(f"cannot start Chromium ({e}). Run: python -m playwright install chromium") from e
        self._ctx = self._browser.new_context(
            color_scheme=self.scheme,
            viewport={"width": self.content_w, "height": self.content_h},
            device_scale_factor=self.dsf,
            locale="en-US",
        )
        self._ctx.set_default_timeout(self.cfg.navigation_timeout_ms)
        local = urlsplit(self.base_url).netloc
        self._ctx.route(lambda u: urlsplit(u).netloc != local, self.cache.handle)
        return self

    def __exit__(self, *exc: object) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()
        if self._server:
            self._server.__exit__(None, None, None)

    @property
    def base_url(self) -> str:
        assert self._server
        return self._server.base_url

    def new_page(self) -> Page:
        assert self._ctx
        return self._ctx.new_page()

    def load(self, page: Page, url: str) -> None:
        page.goto(self.base_url + url, wait_until="networkidle")
        if self.cache.misses:
            raise RenderError(
                "render.offline=true but these assets are not cached yet:\n  " + "\n  ".join(self.cache.misses[:5])
            )
        try:
            page.wait_for_function(
                "(t) => document.documentElement.classList.contains('theme-' + t)"
                " && !!document.querySelector('article.app__article')",
                arg=self.scheme,
            )
        except Exception as e:
            raise RenderError(
                f"{url}: Writerside app did not render (theme class / article missing). "
                "Is the CDN reachable, or is the asset cache populated?"
            ) from e
        page.emulate_media(media="screen", color_scheme=self.scheme)

    def open_topic(self, node: TocNode, symbolic_links: bool = False) -> tuple[Page, dict[str, Any]]:
        """Load a topic and turn it into static, print-ready content with the browser's exact styling."""
        assert node.url
        page = self.new_page()
        self.load(page, node.url)
        stats = Flatten.run(page, link_base_url=self.cfg.link_base_url, symbolic_links=symbolic_links)
        if stats.get("error"):
            raise RenderError(f"{node.url}: {stats['error']}")
        PrintCss.inject(page)
        page.evaluate("document.fonts.ready.then(() => true)")
        FitForPrint.run(page, max_figure_height=self.content_h - FIGURE_HEADROOM_PX,
                        table_min_scale=self.cfg.table_min_scale)
        return page, stats

    def open_blank(self, body_html: str, css: str = "") -> Page:
        """A page that carries the Writerside theme (fonts, colours, CSS variables) but our own body content."""
        topics = self.site.topics()
        page = self.new_page()
        self.load(page, topics[0].url if topics and topics[0].url else "index.html")
        FitForPrint.run(page, max_figure_height=1e9)  # captures the theme background/text colour first
        page.evaluate(
            """([html, css]) => {
                 document.documentElement.classList.add('nxo-print');
                 document.body.innerHTML = html;
                 const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
               }""",
            [body_html, css],
        )
        page.evaluate("document.fonts.ready.then(() => true)")
        return page
