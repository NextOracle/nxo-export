"""An export request after the site is known: what to export, where, and in which layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..domain.site import Site, TocNode


@dataclass(frozen=True, slots=True)
class ExportJob:
    site: Site
    """The site, pruned to the selected topics when a selection was given."""
    topics: tuple[TocNode, ...]
    """Selected topics in reading order."""
    instance_id: str
    title: str
    out_root: Path
    """<output.dir>/<instance>; each exporter writes below it."""
    combined: bool
    per_topic: bool
    scratch: Path
    """Private temporary directory, removed after the export."""
