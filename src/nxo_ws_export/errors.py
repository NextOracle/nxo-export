"""Error hierarchy. Every expected failure is an ``NxoError``: the CLI prints it and exits with status 2."""

from __future__ import annotations


class NxoError(Exception):
    """Base class of all expected, user-facing errors."""


class ConfigError(NxoError):
    """Invalid or missing configuration."""


class ProjectError(NxoError):
    """The Writerside project (writerside.cfg, *.tree) cannot be read."""


class BuildError(NxoError):
    """The Writerside builder (Docker) failed."""


class SiteError(NxoError):
    """The built HTML site is missing or malformed."""


class ExportError(NxoError):
    """The export request cannot be satisfied (topic selection, strict mode, custom reference doc...)."""


class RenderError(NxoError):
    """Chromium could not render a page."""


class PdfError(RenderError):
    """PDF assembly failed."""


class DocxError(RenderError):
    """Pandoc or the OOXML post-processing failed."""
