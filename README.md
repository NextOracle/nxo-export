# nxo-ws-export

Export a JetBrains **Writerside** project to **PDF** (light or dark, the default Writerside theme as in the
browser) and **DOCX**: one combined document with a table of contents, and/or one file per topic.

It does **not** re-implement Writerside. The official Writerside builder renders the site, and the exporter
prints that site:

```
Writerside project ──► writerside-builder (Docker, pinned) ──► web-help site (HTML, CSS, Mermaid as SVG)
                                                                   │
                         Playwright Chromium (screen media, light|dark) ── flatten tabs/collapsibles,
                                                                   │      hide navigation, fit diagrams
                                     ┌─────────────────────────────┴───────────────────┐
                                PDF: page.pdf + footer stamp,             DOCX: normalised HTML + diagrams as PNG
                                cover, TOC, bookmarks (pypdf)             ──► Pandoc + reference.docx derived
                                                                          from the rendered light theme
```

What you get:
- Identical styling to the published site (fonts, code blocks, callouts, tables, Mermaid diagrams) in PDF.
  Dark mode is the real Writerside dark theme, including dark Mermaid diagrams.
- Interactive elements flattened: every collapsible is expanded, and every tab is rendered one after another
  with its title. Horizontally scrolling tables always fit the page width: they shrink, down to
  `render.table_min_scale`, then long words and identifiers wrap.
- Combined PDF: cover page, a TOC with page numbers built from the Writerside tree, hierarchical bookmarks,
  and continuous "PAGE X OF Y" footers.
- DOCX, made for business analysts to **edit**. Everything is a real, named Word style derived from the
  rendered Writerside light theme, so the document stays consistent while you edit it:
  - Headings 1–6, with Writerside's vertical rhythm.
  - Real Word tables (`Table` style): grey grid, shaded header row repeated on every page, column widths
    measured from the site, wide tables scaled to fit the page.
  - Code blocks highlighted with the site's own Prism colours (`Source Code`).
  - ASCII/box-drawing diagrams (a code block without a language that uses `┌ ─ │ ├ └` …) become
    `Text Diagram` lines instead: monospace, exact spacing, no code box or highlighting, kept on one page,
    shrunk to fit the width. DOCX only; PDF keeps the site look. Give the block a language to keep it as code.
  - Callouts as shaded boxes (`Callout Note/Tip/Warning`), `Tab Title`, `Figure`.
  - Hyperlinks styled like the site; emoji in their own `Emoji` style.
  - Mermaid and other SVG diagrams as sharp, light-theme PNGs, never larger than the page.
  - A pre-filled, clickable TOC, "Page X of Y" footers, and working in-document and cross-topic links.
  - DOCX is always light. Dark mode is ignored for DOCX, with a warning.

## Quick start (local)

Requirements: Python ≥ 3.11, Docker (for the builder), and Pandoc ≥ 3 (for DOCX only).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
nxo-ws-export doctor

nxo-ws-export instances -p /path/to/Writerside
nxo-ws-export export -p /path/to/Writerside -i nsk -f pdf -t dark            # combined dark PDF
nxo-ws-export export -p /path/to/Writerside -i nsk -f pdf -f docx -m both    # everything
nxo-ws-export export -p /path/to/Writerside -i nsk -f docx -m per-topic --topic 'database-*'
```

The project directory is never modified. The builder works on a copy, and builds are cached by a fingerprint
of the sources, the builder image, and the instance (`builder.reuse_cache`). The first build pulls the builder
image (~1.7 GB). On Apple Silicon it runs emulated (amd64), which is slower but works.

### Without Docker access: `--site`

If you already have the web-help output (from the Writerside IDE *Export → Web Help*, or from the
`JetBrains/writerside-github-action` in CI), skip the builder:

```bash
nxo-ws-export export --site webHelpNSK2-all.zip -f pdf -f docx -m both
```

## Docker

```bash
WRITERSIDE_PROJECT=/path/to/Writerside docker compose run --rm export export -i nsk -f pdf -t dark
```

The image contains the CLI, Chromium, and Pandoc. The builder runs as a *sibling* container through the
mounted Docker socket, and both containers share the named volume `nxo-ws-export-work`. Mounting the socket
grants root-equivalent access to the Docker daemon. If that is not acceptable, use `--site`.

## Configuration (YAML per environment)

Layers, lowest to highest precedence:

1. built-in defaults
2. `config/default.yml`
3. `config/<env>.yml`. The env comes from `--env` or `$NXO_WS_EXPORT_ENV` (default `local`). A missing
   file for any env other than `local` is an error.
4. `config/local.yml`: personal and git-ignored.
5. environment variables `NXO_WS_EXPORT__SECTION__KEY=value`, e.g. `NXO_WS_EXPORT__RENDER__THEME=dark`
6. CLI options and `--set render.page.size=Letter`

YAML values support `${VAR}` and `${VAR:-default}`. Unknown keys are rejected. Inspect the result with
`nxo-ws-export --env ci config show` or `config validate`.

| env | purpose |
|-----|---------|
| `dev`  | cached builds, combined PDF |
| `ci`   | fresh build, PDF+DOCX, combined + per topic, `strict` (inspection errors fail) |
| `prod` | fresh build, all artifacts, cross-topic links point to `${DOCS_BASE_URL}` |

Main keys: `builder.image` (pinned), `render.theme`, `render.page.*`, `render.toc.*`, `render.cover.*`,
`render.link_base_url`, `render.table_min_scale`, `render.offline`, `docx.reference_doc`, `docx.font`, `output.formats|mode|dir|strict`.

## Output

```
dist/<instance>/<instance>-<theme>.pdf        combined PDF
dist/<instance>/pdf-<theme>/NNN-<slug>.pdf    one PDF per topic (TOC order)
dist/<instance>/<instance>.docx               combined DOCX
dist/<instance>/docx/NNN-<slug>.docx          one DOCX per topic
```

## Notes and limitations

- **Builder pin.** The in-browser scripts (`src/browser/assets/`) target the DOM of the pinned
  `writerside-builder` version. When you bump `builder.image`, run the e2e test.
- **CDN assets.** The built site loads its CSS, JS, and fonts from `resources.jetbrains.com`. They are cached
  under `render.asset_cache_dir`, so with a warm cache use `--offline` or `render.offline: true` for
  hermetic runs.
- **Why DOCX comes from the rendered site, not from the raw Markdown.** Only the Writerside builder resolves
  includes, `%variables%`, filters, snippets, XML topics, and Mermaid. Converting the `.md` files directly
  would silently lose or garble that content. The exporter takes the builder's output, flattens it, and maps
  it onto Word styles. Word has no CSS, so the look is reproduced with styles, not copied pixel for pixel.
- **Fonts.** The theme fonts are *JetBrains Sans* and *JetBrains Mono*. When they are missing, Word substitutes
  `docx.font_fallback`/`docx.code_font_fallback` (Arial/Consolas). Set `docx.font`/`docx.code_font` to force a
  font. You can also provide your own `docx.reference_doc` (a corporate template). Word may ask to update
  fields on open; that only refreshes the TOC page numbers.
- **Emoji** use `docx.emoji_font` (Segoe UI Emoji; Word for Mac falls back to Apple Color Emoji). LibreOffice
  PDF export does not draw colour emoji, which is a LibreOffice limitation.
- Cross-topic links stay clickable only when `render.link_base_url` is set. In-page anchors always work.
- Writerside inspection errors are reported as a warning. Under `--strict` or
  `builder.fail_on_inspection_errors` they fail the run.

## Development

```bash
pytest -q                                   # unit tests
WS_E2E_PROJECT=/path/to/Writerside WS_E2E_INSTANCE=nsk pytest -m e2e   # real builder + browser + pandoc
ruff check src tests
```

### Code layout

```
src/
  domain/     pure values: Site/TocNode, PageBox, units, CSS parsing
  sources/    where the site comes from: Writerside project, Docker builder, prebuilt dir/zip
  browser/    Chromium session + typed wrappers for the in-page scripts (browser/assets/)
  exporters/  Exporter template (session → per-topic → combined) and the formats:
    pdf/        printer, cover/TOC pages, footer stamp, composer
    docx/       extract → theme → styles (catalogue → writer → reference.docx) → html → pandoc → ooxml passes
  app/        ExportService, ExportJob, ExportReport
```

`src/` is installed as the `nxo_ws_export` package (`package-dir` in `pyproject.toml`; when adding a
subpackage, list it under `[tool.setuptools] packages`, which a test enforces). Layers depend inwards only (`cli → app → exporters → browser → sources → domain`,
enforced by `tests/test_architecture.py`). To add a format, implement
`exporters.base.Exporter` and register it in `exporters/registry.py`. To change the Word look, edit
`exporters/docx/styles/catalogue.py`. To add a DOCX fix-up, add a `DocumentPass` to
`exporters/docx/ooxml/pipeline.py`. Design and rationale: `.github/plans/oop-refactor/design.md`.
