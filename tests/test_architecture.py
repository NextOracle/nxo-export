"""Layering guard: packages may only import inwards (cli → app → exporters → browser → sources → domain)."""
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).parents[1] / "src"
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


def test_every_package_is_listed_in_pyproject():
    """src/ is installed as `nxo_export` via package-dir, so packages are listed explicitly in pyproject.toml."""
    import tomllib

    listed = set(tomllib.loads((PKG.parent / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"])
    on_disk = {".".join(("nxo_export", *p.parent.relative_to(PKG).parts)) for p in PKG.rglob("__init__.py")}
    assert on_disk == listed
