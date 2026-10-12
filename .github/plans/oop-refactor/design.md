# OOP refactor of the PDF and DOCX pipelines: design

Status: **implemented**. This refactor must not change behaviour: same CLI, same config, same output. The golden
snapshots (PDF light/dark, DOCX, per-topic and combined) were byte-identical before and after. The only
intentional output change came afterwards, in its own commit: figures no longer leak temp paths in `pic:cNvPr/@descr`.

## 1. Problems today

| Smell | Where |
|---|---|
| Format orchestration (`_export_pdf`, `_export_docx`) lives in `exporter.py`, with 9–10 positional args | `exporter.py` |
| PDF is a bag of free functions sharing state through arguments | `render/pdf.py` |
| DOCX post-processing is one 480-line module of private functions with a `stats` dict threaded through | `render/docx/postprocess.py` |
| Styles are built imperatively (`_para(_style(...))` × 40); the style catalogue is implicit | `render/docx/reference.py` |
| External tools (Pandoc, Chromium, Docker) are called directly, so there's no seam for fakes | `run_pandoc`, `Session` |
| JS assets are called by string name with untyped dict results | `page.evaluate(asset("..."), {...})` |
| Units (px, twips, half-points, EMU) are bare ints, so conversion bugs are easy | `tw`, `half_pt`, `EMU_PER_TWIP` |

## 2. Principles

1. **One exporter per format behind one interface (Strategy).** A shared skeleton (Template Method) handles
   selection, per-topic and combined output. Adding EPUB or HTML-zip later means adding a class, with no
   `if format ==` branches.
2. **Pipelines of single-responsibility steps.** DOCX post-processing becomes an ordered chain of
   `DocumentPass` objects (tables, callouts, figures, text diagrams, bookmarks, TOC, …). Each pass can be
   tested and toggled on its own.
3. **Ports and adapters for external tools.** `HtmlToDocx` (Pandoc), `BrowserSession` (Chromium) and
   `SiteBuilder` (Docker) are protocols, so the core can be unit-tested with fakes.
4. **Immutable value objects** (`frozen dataclass`, `slots=True`): `ExportJob`, `TopicPdf`, `TopicHtml`,
   `Theme`, `PageBox`, `Twips`/`Px`/`Emu`.
5. **Declarative style catalogue.** Word styles are data (`ParagraphStyleSpec`, `CharStyleSpec`,
   `TableStyleSpec`) derived from `Theme`, and one writer applies them to the document.
6. **Typed browser scripts.** Each JS asset gets a Python wrapper class with typed options and results
   (`Flatten`, `FitForPrint`, `ReadTheme`, `MarkFigures`, `PrepareForDocx`).
7. **Dependencies point inward:** `cli → app → exporters → (browser, tools) → domain`. The domain imports nothing.

## 3. Package layout (as implemented)

```
nxo_ws_export/
├── __init__.py                 public API (lazy): export, Config, load_config, ExportReport, __version__
├── cli.py                      click (thin); catches NxoError
├── config.py                   Pydantic models + layered loader
├── errors.py                   NxoError ▸ Config/Project/Build/Site/ExportError, RenderError ▸ PdfError, DocxError
├── _types.py                   Log
├── domain/                     pure, no I/O
│   ├── site.py                 Site, TocNode (frozen; topics(), select(), subset(), outline())
│   ├── job.py                  ExportJob (frozen): what to export, where, in which layout
│   ├── units.py                Px, Twips, HalfPoints, Emu (NewType + converters)
│   ├── css.py                  css colour parsing, blend, first_font, css_px
│   └── page.py                 PageBox (content box in px / twips, landscape)
├── sources/                    where the site comes from (Strategy: SiteProvider)
│   ├── provider.py             SiteProvider, PrebuiltSite, WritersideBuild → AcquiredSite
│   ├── project.py              Writerside project, instances, orphan trees
│   ├── builder.py              DockerSiteBuilder, BuildResult, fingerprint cache
│   └── site_loader.py          load_site, site_root (dir | zip), SiteServer
├── browser/
│   ├── session.py              BrowserSession (context manager)
│   ├── cdn_cache.py            AssetCache (offline CDN route)
│   ├── scripts.py              typed wrappers: Flatten, FitForPrint, ReadTheme, MarkFigures, PrepareForDocx, PrintCss
│   └── assets/                 *.js, print.css + read_asset()
├── app/
│   ├── service.py              ExportService: acquire site → select topics → run exporters → ExportReport
│   └── report.py               ExportReport
└── exporters/
    ├── base.py                 Exporter[S] ABC, template export(job): session → per-topic → combined
    ├── registry.py             FORMATS = {"pdf": PdfExporter, "docx": DocxExporter}
    ├── pdf/
    │   ├── exporter.py         PdfExporter
    │   ├── printer.py          PagePrinter → TopicPdf (Chromium page.pdf, @page css)
    │   ├── pages.py            CoverPage, TocPage
    │   ├── footer.py           PageNumberStamper
    │   └── composer.py         TopicPdfWriter, CombinedPdfComposer (TOC page numbers converge, outline)
    └── docx/
        ├── exporter.py         DocxExporter (injectable HtmlToDocx + PostProcessor)
        ├── topic.py            TopicHtml (frozen)
        ├── extract.py          TopicExtractor (theme tokens, figure rasterising, prepare)
        ├── pandoc.py           HtmlToDocx port, PandocConverter (version probe, legacy flags)
        ├── theme/              model (Theme, Text, Callout), tokens (ThemeTokens), highlight, rhythm (GAP)
        ├── styles/
        │   ├── specs.py        ParagraphStyle, CharacterStyle, TableStyle (frozen value objects)
        │   ├── catalogue.py    WritersideStyleCatalogue → list[StyleSpec]  (the one place styles are defined)
        │   ├── writer.py       StyleWriter (the only code that writes style XML)
        │   └── reference.py    ReferenceDocBuilder (defaults, catalogue, footer, page setup, font fallbacks)
        ├── html/
        │   ├── assembler.py    HtmlAssembler (topic / combined), shift_headings, short_ids
        │   └── links.py        LinkResolver
        └── ooxml/
            ├── xml.py          OOXML helpers
            ├── context.py      PassContext (frozen)
            ├── pipeline.py     PostProcessor(passes).run(path, ctx) → Counter
            └── passes/         base (DocumentPass, containers, content_width), tables (TableLayoutPass →
                                DataTableFormatter / CalloutFormatter), figures, text_diagrams, lists,
                                bookmarks, chapters (combined only), toc, properties
```

### Deviations from the proposal

- Data tables and callouts are both Word tables and nest inside each other, so one `TableLayoutPass` walks
  them recursively and dispatches to `DataTableFormatter` or `CalloutFormatter` (Strategy). Two separate
  passes would have had to share that walk.
- `domain/color.py` became `domain/css.py` (functions, not a Color class: values stay hex strings end-to-end).
- `renderer.py` became `printer.py`; `AssetCache` lives in `browser/cdn_cache.py`; site acquisition is a
  `SiteProvider` strategy in `sources/provider.py`.
- `GAP` (vertical rhythm) lives in `theme/rhythm.py`, so `styles` and `ooxml` both depend on `theme` and not
  on each other.
- `styles/writer.py` split out of `reference.py`: the catalogue declares, the writer applies, the builder
  packages.
- `ExportJob` lives in `domain/job.py` (not `app/`), so exporters never import the app layer.
  `tests/test_architecture.py` enforces inward-only imports.
- mypy is not adopted (no new dev dependencies); ruff keeps `E,F,W,I,B,UP,PLW1510`.

## 4. Key contracts

```python
class Exporter(ABC):
    format: ClassVar[str]
    def __init__(self, cfg: Config, log: Logger): ...
    def export(self, job: ExportJob) -> list[Path]:          # template method
        with self.session(job) as ctx:
            topics = self.render_topics(ctx, job)             # abstract
            out = self.write_per_topic(ctx, job, topics) if job.per_topic else []
            if job.combined:
                out.append(self.write_combined(ctx, job, topics))
            return out

class DocumentPass(Protocol):
    name: str
    def applies(self, ctx: PassContext) -> bool: ...
    def run(self, doc: Document, ctx: PassContext) -> None: ...

class BrowserScript(Generic[O, R]):
    asset: ClassVar[str]
    def __call__(self, page: Page, opts: O) -> R: ...

class HtmlToDocx(Protocol):
    def convert(self, html: Path, out: Path, *, reference: Path, highlight: Path | None,
                meta: Mapping[str, str], toc_depth: int | None) -> list[str]: ...   # returns warnings
```

The DOCX flow is a readable composition:

```python
DocxExporter
  ├─ TopicExtractor(session, scripts)       → TopicHtml × N   (+ TokenAccumulator)
  ├─ Theme.from_tokens → WritersideStyleCatalogue → ReferenceDocBuilder → reference.docx
  ├─ HighlightTheme → writerside.theme
  ├─ HtmlAssembler + LinkResolver           → topic.html / combined.html
  ├─ PandocConverter                        → raw.docx
  └─ PostProcessor([BookmarkPass…, DataTablePass, CalloutPass, FigurePass, TextDiagramPass,
                    ListSpacingPass, ChapterBreakPass, TocPass, CorePropertiesPass])
```

## 5. Quality gates

- **Golden regression:** before refactoring, export a fixed topic subset (PDF light/dark + DOCX) and snapshot
  the normalised `document.xml`/`styles.xml` and the PDF text and page counts. After each step, compare against
  the snapshot; it must be identical.
- Unit tests per pass and per value object, using `FakeConverter`/`FakeSession` where useful. The existing
  25 tests keep passing, with import paths updated.
- ruff (plus `I`, `B`, `UP`, `SIM`, `RET`), and mypy `--strict` on `domain/` and `exporters/`.
- No new runtime dependencies. CLI, YAML keys and output layout unchanged.

## 6. Migration steps (each step green before the next)

1. Golden snapshot plus `errors.py`/`domain/units.py`/`domain/color.py`.
2. `browser/` (session + typed scripts), `assets/` moved.
3. `exporters/base.py`, `app/service.py`; `exporter.py` becomes a thin façade (`export()` kept).
4. `exporters/pdf/*`.
5. `exporters/docx/*`: theme, styles catalogue, html, pandoc, ooxml passes.
6. Docs (README, plan ADR "module structure"), delete the old modules, full `nsk` export, golden diff.
