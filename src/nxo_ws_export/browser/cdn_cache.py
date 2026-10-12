"""Disk cache for the Writerside CDN (app.css/app.js/fonts) so renders are repeatable and can run offline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from playwright.sync_api import Route


class AssetCache:
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
