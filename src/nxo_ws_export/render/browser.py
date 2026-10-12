"""Chromium session over the built site: CDN asset cache, theme emulation, page preparation."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Route, sync_playwright

from ..config import RenderCfg
from ..geometry import content_box_px
from ..site import Site, SiteServer, TocNode

Theme = Literal["light", "dark"]


class RenderError(Exception):
    pass


def asset(name: str) -> str:
    return resources.files("nxo_ws_export.assets").joinpath(name).read_text(encoding="utf-8")


class AssetCache:
    """Disk cache for the Writerside CDN (app.css/app.js/fonts) so renders are repeatable and can run offline."""

    def __init__(self, root: Path, offline: bool):
        self.root = root.expanduser().resolve()
        self.offline = offline
        self.misses: list[str] = []
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.root / f"{key}.body", self.root / f"{key}.json"

    def handle(self, route: Route) -> None:
        url = route.request.url
        if route.request.method != "GET" or not url.startswith(("http://", "https://")):
            route.continue_()
            return
        body_p, meta_p = self._paths(url)
        if body_p.is_file() and meta_p.is_file():
            meta = json.loads(meta_p.read_text())
            route.fulfill(status=meta["status"], headers=meta["headers"], body=body_p.read_bytes())
            return
        if self.offline:
            self.misses.append(url)
            route.abort()
            return
        try:
            resp = route.fetch()
        except Exception:
            route.abort()
            return
        body = resp.body()
        keep = {k: v for k, v in resp.headers.items() if k.lower() in ("content-type", "access-control-allow-origin")}
        keep.setdefault("access-control-allow-origin", "*")
        if resp.status == 200:
            body_p.write_bytes(body)
            meta_p.write_text(json.dumps({"url": url, "status": resp.status, "headers": keep}))
        route.fulfill(status=resp.status, headers=keep, body=body)


class Session:
    """One Chromium + one served site + one theme. Use as a context manager."""

    def __init__(self, site: Site, cfg: RenderCfg, theme: Theme, device_scale_factor: float = 1.0):
        self.site = site
        self.cfg = cfg
        self.theme = theme
        self.dsf = device_scale_factor
        self.cache = AssetCache(cfg.asset_cache_dir, cfg.offline)
        # Lay pages out at the printable width so screen measurements equal the printed layout.
        self.content_w, self.content_h = content_box_px(cfg.page)
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None
        self._server: SiteServer | None = None

    def __enter__(self) -> Session:
        self._server = SiteServer(self.site.root).__enter__()
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch()
        except Exception as e:
            self.__exit__(None, None, None)
            raise RenderError(f"cannot start Chromium ({e}). Run: python -m playwright install chromium") from e
        self._ctx = self._browser.new_context(
            color_scheme=self.theme,
            viewport={"width": self.content_w, "height": self.content_h},
            device_scale_factor=self.dsf,
            locale="en-US",
        )
        self._ctx.set_default_timeout(self.cfg.navigation_timeout_ms)
        local = urlsplit(self.base_url).netloc
        self._ctx.route(lambda u: urlsplit(u).netloc != local, self.cache.handle)
        return self

    def __exit__(self, *exc) -> None:
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
                arg=self.theme,
            )
        except Exception as e:
            raise RenderError(
                f"{url}: Writerside app did not render (theme class / article missing). "
                "Is the CDN reachable, or is the asset cache populated?"
            ) from e
        page.emulate_media(media="screen", color_scheme=self.theme)

    def open_topic(self, node: TocNode, symbolic_links: bool = False) -> tuple[Page, dict]:
        """Load a topic and turn it into static, print-ready content with the browser's exact styling."""
        assert node.url
        page = self.new_page()
        self.load(page, node.url)
        stats = page.evaluate(asset("flatten.js"), {"linkBaseUrl": self.cfg.link_base_url,
                                                    "symbolicLinks": symbolic_links})
        if isinstance(stats, dict) and stats.get("error"):
            raise RenderError(f"{node.url}: {stats['error']}")
        page.add_style_tag(content=asset("print.css"))
        page.evaluate("document.fonts.ready.then(() => true)")
        # Leave room for a heading above a page-tall figure so it is not orphaned on the previous page.
        page.evaluate(asset("fit.js"), {"maxFigureHeight": self.content_h - 160,
                                         "tableMinScale": self.cfg.table_min_scale})
        return page, stats

    def open_blank(self, body_html: str, css: str = "") -> Page:
        """A page that carries the Writerside theme (fonts, colours, CSS variables) but our own body content."""
        topics = self.site.topics()
        page = self.new_page()
        self.load(page, topics[0].url if topics else "index.html")
        page.evaluate(asset("fit.js"), {"maxFigureHeight": 1e9})  # capture theme background/text colour first
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
