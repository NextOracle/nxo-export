"""Load a built Writerside site (directory or webHelp*-all.zip) and serve it to Chromium."""

from __future__ import annotations

import functools
import json
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..domain.site import Site, TocNode
from ..errors import SiteError


def load_site(root: Path) -> Site:
    toc_file = root / "HelpTOC.json"
    if not toc_file.is_file():
        raise SiteError(f"{root} is not a Writerside HTML build (HelpTOC.json missing)")
    data = json.loads(toc_file.read_text(encoding="utf-8"))
    pages: dict[str, Any] = data.get("entities", {}).get("pages", {})

    def build(pid: str, level: int) -> TocNode:
        p = pages[pid]
        kids = tuple(build(c, level + 1) for c in p.get("pages", []) if c in pages)
        return TocNode(pid, p.get("title") or pid, p.get("url"), level, kids)

    toc = tuple(build(pid, 0) for pid in data.get("topLevelIds", []) if pid in pages)
    cfg_file = root / "config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.is_file() else {}
    return Site(root=root, toc=toc, product_name=cfg.get("productName") or root.name, config=cfg)


def site_root(path: Path, scratch: Path) -> Path:
    """The site directory for a directory or a builder archive (unpacked into `scratch`)."""
    path = path.expanduser().resolve()
    if path.is_file() and zipfile.is_zipfile(path):
        dest = scratch / "site"
        with zipfile.ZipFile(path) as z:
            z.extractall(dest)
        found = [p.parent for p in dest.rglob("HelpTOC.json")]
        if not found:
            raise SiteError(f"{path} does not contain a Writerside site (HelpTOC.json)")
        return found[0]
    return path


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
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
        return f"http://{host!s}:{port}/"

    def __enter__(self) -> SiteServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
