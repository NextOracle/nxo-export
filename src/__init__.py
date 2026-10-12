"""Export a JetBrains Writerside instance to PDF (light/dark) and editable DOCX.

    from nxo_ws_export import run
    run(project="/path/to/Writerside", instance="nsk", formats=("pdf",), theme="dark")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"
__all__ = ["Config", "ExportReport", "__version__", "export", "load_config", "run"]

if TYPE_CHECKING:
    from .app.api import run
    from .app.report import ExportReport
    from .app.service import export
    from .config import Config, load_config


def __getattr__(name: str) -> Any:  # lazy: `nxo_ws_export.__version__` must not import Playwright/pydantic
    if name == "run":
        from .app.api import run
        return run
    if name == "export":
        from .app.service import export
        return export
    if name == "ExportReport":
        from .app.report import ExportReport
        return ExportReport
    if name in ("Config", "load_config"):
        from . import config
        return getattr(config, name)
    raise AttributeError(name)
