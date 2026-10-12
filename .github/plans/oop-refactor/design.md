# OOP refactor of the PDF and DOCX pipelines: design

Status: **proposed**. This refactor must not change behaviour: same CLI, same config, same output.

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

## 3. Package layout

```
nxo_ws_export/
├── __init__.py                 public API: export(), Config, ExportReport, __version__
├── cli.py                      click (thin)
├── config.py                   Pydantic models + layered loader (unchanged)
├── errors.py                   NxoError ▸ ConfigError, ProjectError, BuildError, RenderError ▸ PdfError, DocxError
├── domain/                     pure, no I/O
│   ├── site.py                 Site, TocNode (+ subset/filter as methods)
│   ├── units.py                Px, Twips, HalfPt, Emu (NewType + converters)
│   ├── color.py                Color value object (css parse, blend, hex)
│   └── page.py                 PageBox (size, margins → content box in px/twips)
├── sources/                    where the site comes from
│   ├── project.py              WritersideProject, Instance
│   ├── builder.py              DockerSiteBuilder (SiteBuilder port), BuildResult, fingerprint cache
│   └── site_loader.py          SiteLoader (dir | zip → Site), LocalSiteServer
├── browser/
│   ├── session.py              BrowserSession (context manager), AssetCache
│   ├── scripts.py              BrowserScript[Opts, Result] + Flatten, FitForPrint, ReadTheme, MarkFigures, PrepareForDocx
│   └── assets/                 *.js, print.css (moved, unchanged)
├── app/
│   ├── job.py                  ExportJob (site, selection, title, out_dir, mode) – frozen
│   ├── service.py              ExportService: acquire site → select topics → run exporters → ExportReport
│   └── report.py               ExportReport, warnings
└── exporters/
    ├── base.py                 Exporter ABC: export(job) -> list[Path]  (template: prepare → per-topic → combined)
    ├── registry.py             FORMATS = {"pdf": PdfExporter, "docx": DocxExporter}
    ├── pdf/
    │   ├── exporter.py         PdfExporter(Exporter)
    │   ├── renderer.py         TopicPdfRenderer → TopicPdf
    │   ├── pages.py            CoverPage, TocPage (two-pass page numbers)
    │   ├── footer.py           PageNumberStamper
    │   └── composer.py         CombinedPdfComposer (merge, outline/bookmarks, viewer prefs)
    └── docx/
        ├── exporter.py         DocxExporter(Exporter)
        ├── extract.py          TopicExtractor → TopicHtml (freeze, rasterise figures, prepare)
        ├── theme/
        │   ├── model.py        Theme, TextStyle, CalloutStyle (from tokens)
        │   ├── tokens.py       TokenAccumulator (merge across topics)
        │   └── highlight.py    HighlightTheme (Prism → skylighting JSON)
        ├── styles/
        │   ├── specs.py        ParagraphStyleSpec, CharStyleSpec, TableStyleSpec
        │   ├── catalogue.py    WritersideStyleCatalogue(theme, cfg) → list[StyleSpec]   (the one place styles are defined)
        │   └── reference.py    ReferenceDocBuilder (applies specs, footer, page setup, font fallbacks)
        ├── html/
        │   ├── assembler.py    HtmlAssembler: topic / combined HTML, heading shift, short ids
        │   └── links.py        LinkResolver
        ├── pandoc.py           PandocConverter (HtmlToDocx port; version probe, legacy flags)
        └── ooxml/
            ├── xml.py          OOXML helpers (put, child, borders, shade, …)
            ├── context.py      PassContext (theme, page box, table scales, stats: Counter)
            ├── pipeline.py     PostProcessor(passes).run(path, ctx)
            └── passes/
                ├── base.py     DocumentPass protocol: name, applies(ctx), run(doc, ctx)
                ├── tables.py   DataTablePass
                ├── callouts.py CalloutPass
                ├── figures.py  FigurePass
                ├── text_diagrams.py TextDiagramPass
                ├── lists.py    ListSpacingPass
                ├── bookmarks.py BookmarkPass
                ├── chapters.py ChapterBreakPass (combined only)
                ├── toc.py      TocPass
                └── properties.py CorePropertiesPass
```

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
