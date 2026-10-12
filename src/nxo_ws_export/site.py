"""The built HTML site produced by the Writerside builder, and its table of contents."""

from __future__ import annotations

import functools
import json
import threading
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SiteError(Exception):
    pass


@dataclass
class TocNode:
    id: str
    title: str
    url: str | None
    """Relative page URL; None for pure section nodes (a tree <toc-element> with only a title)."""
    level: int
    children: list[TocNode] = field(default_factory=list)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    @property
    def slug(self) -> str:
        return (self.url or self.id).removesuffix(".html")


@dataclass
class Site:
    root: Path
    toc: list[TocNode]
    product_name: str
    config: dict

    def topics(self) -> list[TocNode]:
        """Pages in reading order (depth-first through the TOC), de-duplicated."""
        seen: set[str] = set()
        out: list[TocNode] = []
        for top in self.toc:
            for n in top.walk():
                if n.url and n.url not in seen:
                    seen.add(n.url)
                    out.append(n)
        return out


def load_site(root: Path) -> Site:
    toc_file = root / "HelpTOC.json"
    if not toc_file.is_file():
        raise SiteError(f"{root} is not a Writerside HTML build (HelpTOC.json missing)")
    data = json.loads(toc_file.read_text(encoding="utf-8"))
    pages: dict = data.get("entities", {}).get("pages", {})

    def build(pid: str, level: int) -> TocNode:
        p = pages[pid]
        node = TocNode(pid, p.get("title") or pid, p.get("url"), level)
        node.children = [build(c, level + 1) for c in p.get("pages", []) if c in pages]
        return node

    toc = [build(pid, 0) for pid in data.get("topLevelIds", []) if pid in pages]
    cfg_file = root / "config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.is_file() else {}
    return Site(root=root, toc=toc, product_name=cfg.get("productName") or root.name, config=cfg)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


class SiteServer:
    """Serves the static site on 127.0.0.1 so the Writerside app.js runs exactly as in a browser."""

    def __init__(self, root: Path):
        handler = functools.partial(_QuietHandler, directory=str(root))
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/"

    def __enter__(self) -> SiteServer:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
