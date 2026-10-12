"""Layering guard: packages may only import inwards (cli → app → exporters → browser → sources → domain)."""
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).parents[1] / "src" / "nxo_ws_export"
LAYERS = ["domain", "sources", "browser", "exporters", "app"]
"""Inner first; a layer may import any layer at or before its own position."""


def _imports(path: Path) -> set[str]:
    rel = path.relative_to(PKG).parts[:-1]
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = list(rel[: len(rel) - node.level + 1])
            target = base + (node.module.split(".") if node.module else [])
            if target:
                found.add(target[0])
    return found


@pytest.mark.parametrize("layer", LAYERS)
def test_layers_import_inwards_only(layer):
    allowed = set(LAYERS[: LAYERS.index(layer) + 1])
    outer = set(LAYERS) - allowed
    bad = {f"{p.relative_to(PKG)} -> {m}" for p in (PKG / layer).rglob("*.py") for m in _imports(p) & outer}
    assert not bad, bad
