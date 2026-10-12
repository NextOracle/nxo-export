"""What an export produced."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..sources.builder import BuildResult


@dataclass
class ExportReport:
    instance: str
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    build: BuildResult | None = None
