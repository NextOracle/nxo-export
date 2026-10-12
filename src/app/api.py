"""The Python entry point: one call, same layered configuration as the CLI.

    from nxo_export import run

    report = run(project="/path/to/Writerside", instance="nsk", formats=("pdf", "docx"), mode="both")
    print(report.outputs)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from .._types import Log
from ..config import load_config, set_path
from .report import ExportReport
from .service import export


def run(
    project: str | Path | None = None,
    instance: str | None = None,
    *,
    formats: Iterable[Literal["pdf", "docx"]] | None = None,
    mode: Literal["combined", "per-topic", "both"] | None = None,
    theme: Literal["light", "dark"] | None = None,
    out: str | Path | None = None,
    topics: Iterable[str] = (),
    site: str | Path | None = None,
    offline: bool | None = None,
    strict: bool | None = None,
    env: str | None = None,
    config_dir: str | Path | None = None,
    settings: Mapping[str, Any] | None = None,
    log: Log = print,
) -> ExportReport:
    """Export a Writerside instance. Arguments left as None come from config/default.yml and config/local.yml.

    `settings`: any other config key, e.g. ``{"render.page.size": "Letter", "docx.font": "Arial"}``.
    """
    overrides: dict[str, Any] = {}
    for key, value in {
        "project.path": str(project) if project else None, "project.instance": instance,
        "output.formats": list(formats) if formats else None, "output.mode": mode, "render.theme": theme,
        "output.dir": str(out) if out else None, "render.offline": offline, "output.strict": strict,
        **(settings or {}),
    }.items():
        if value is not None:
            set_path(overrides, key, value)
    cfg, _ = load_config(env, Path(config_dir) if config_dir else None, overrides)
    return export(cfg, site_path=Path(site) if site else None, topics=tuple(topics), log=log)
