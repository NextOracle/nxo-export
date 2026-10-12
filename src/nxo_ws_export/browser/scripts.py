"""Typed wrappers for the in-page scripts: one class per asset, with named options and a typed result.

Python never builds JavaScript strings; every script is a static asset called with a JSON argument."""

from __future__ import annotations

from typing import Any, ClassVar, TypedDict

from playwright.sync_api import Page

from .assets import read_asset


class BrowserScript:
    asset: ClassVar[str]

    @classmethod
    def evaluate(cls, page: Page, arg: Any = None) -> Any:
        return page.evaluate(read_asset(cls.asset), arg)


class Stylesheet:
    asset: ClassVar[str]

    @classmethod
    def inject(cls, page: Page) -> None:
        page.add_style_tag(content=read_asset(cls.asset))


class PrintCss(Stylesheet):
    """Static print look: no chrome, expanded collapsibles, print-safe tables."""

    asset = "print.css"


class Flatten(BrowserScript):
    """Removes interactivity (tabs, collapsibles, copy buttons) and rewrites same-site links."""

    asset = "flatten.js"

    @classmethod
    def run(cls, page: Page, *, link_base_url: str | None, symbolic_links: bool) -> dict[str, Any]:
        out = cls.evaluate(page, {"linkBaseUrl": link_base_url, "symbolicLinks": symbolic_links})
        return out if isinstance(out, dict) else {}


class FitForPrint(BrowserScript):
    """Fits tables and figures to the printable box; captures the theme background first."""

    asset = "fit.js"

    @classmethod
    def run(cls, page: Page, *, max_figure_height: float, table_min_scale: float | None = None) -> None:
        arg: dict[str, Any] = {"maxFigureHeight": max_figure_height}
        if table_min_scale is not None:
            arg["tableMinScale"] = table_min_scale
        cls.evaluate(page, arg)


class ReadTheme(BrowserScript):
    """Computed styles of representative elements (body text, headings, code, callouts, tables)."""

    asset = "docx_theme.js"

    @classmethod
    def run(cls, page: Page) -> dict[str, Any]:
        return cls.evaluate(page) or {}


class FigureBox(TypedDict):
    id: str
    width: float
    height: float


class MarkFigures(BrowserScript):
    """Freezes the page and tags every diagram/image to be rasterised as it is drawn."""

    asset = "docx_figures.js"

    @classmethod
    def run(cls, page: Page, *, min_figure: int) -> list[FigureBox]:
        return cls.evaluate(page, {"minFigure": min_figure}) or []


class PreparedTable(TypedDict):
    id: str
    scale: float


class Prepared(TypedDict, total=False):
    anchor: str | None
    ids: list[str]
    tables: list[PreparedTable]
    prism: dict[str, dict[str, Any]]


class PrepareForDocx(BrowserScript):
    """Normalises the article to the semantic HTML Pandoc maps onto the Writerside Word styles."""

    asset = "docx_prepare.js"

    @classmethod
    def run(cls, page: Page, *, heading_shift: int, id_prefix: str, uid: int) -> Prepared:
        return cls.evaluate(page, {"headingShift": heading_shift, "idPrefix": id_prefix, "uid": uid}) or {}
