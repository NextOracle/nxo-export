# nxo-ws-export — Plan & Architecture (v3, implemented)

> Status: **implemented** (v0.1.0) and validated end-to-end against a real project (`nsk-backend/Writerside`,
> instance `nsk`: 75 topics, 60 Mermaid diagrams, tabs/collapsibles, Greek content).
> This document supersedes v2 (Pandoc/WeasyPrint "style translator"), which was rejected in the hard review.

## 1. Goal

Export a Writerside project to **PDF** and **DOCX**:
- one combined document with a TOC transformed from the Writerside tree, and/or one file per topic
- the **default Writerside theme exactly as rendered in the browser**. Light/dark is a parameter **for PDF
  only**. DOCX is always light.
- Mermaid diagrams as images, and interactive elements (collapsibles, tabs) flattened into static content
- global YAML configuration per environment
- runs locally or in Docker, and never modifies the source project

## 2. Key decision (hard-review outcome)

**Do not re-implement Writerside rendering.** Markdown/XML topics use Writerside-specific semantics (includes,
variables, filters, snippets, `<tabs>`, `<collapsible>`, Mermaid, callouts, the semantic markup). Any
reimplementation (Pandoc filters plus a CSS "style translator") drifts from the real look and breaks on
every new feature.

Instead: **the official builder renders → we print what it rendered.**

| # | ADR | Why |
|---|-----|-----|
| 1 | The pinned `jetbrains/writerside-builder` image produces the web-help site | 100 % fidelity: same HTML, CSS, Mermaid SVG as the published docs |
| 2 | The builder's own PDF is **not** used | unreliable (hangs on `nsk`), no dark mode, little control |
| 3 | Playwright **Chromium** prints each topic with `emulate_media(screen)` and `color_scheme=light|dark` | print media forces the content to light. Screen media plus a viewport equal to the printable box gives a WYSIWYG layout |
| 4 | Flattening in the browser (`assets/flatten.js`) after Writerside's JS ran | expands `.collapse__button`; clicks every tab and clones each panel under its title |
| 5 | Mermaid needs no `mmdc`: the builder ships rendered SVG that Writerside themes for dark mode | fewer moving parts, exact look |
| 6 | `@page { background: <html bg> }` and our own footer stamped via pypdf overlay | Chromium paints margins with the canvas colour; Writerside's `@page` footer can't do continuous numbering across merged topics |
| 7 | Combined PDF = cover + TOC (Writerside classes, two-pass page numbers) + topics, with hierarchical bookmarks from `HelpTOC.json` | TOC "transformed" from the tree, not from headings |
| 8 | DOCX = **builder-rendered** light DOM → normalised HTML → **Pandoc** → **OOXML post-processing** (`render/docx/`). Not raw Markdown | only the builder resolves includes, `%vars%`, filters, snippets, XML topics, and Mermaid. Pandoc gives real Word structures; post-processing adds what Pandoc can't express |
| 8a | Word styles generated from **computed styles** of the rendered theme (`docx_theme.js` → `Theme` → `reference.docx`): headings, body rhythm, `Table`, `Source Code`, `Callout *`, `Tab Title`, `Figure`, `Emoji`, TOC levels, footer | BAs edit with named styles, so the Writerside look survives editing. Nothing is hand-copied CSS |
| 8b | Tables: colgroup widths measured in the browser → Word grid in twips; borders, header shading, repeating header, cantSplit, wide-table font scaling | Pandoc alone emits borderless, equal-width tables |
| 8c | Callouts = one-cell shaded tables; code re-highlighted by Pandoc with a skylighting theme built from the **site's Prism colours** | Pandoc drops custom styles on lists inside divs; colours stay identical to the site |
| 8c' | **Text-diagram rule** (DOCX only): a code block without a language whose text contains box-drawing characters (U+2500–257F) → `Text Diagram` paragraphs (code font, single spacing, no shading, keepNext, width-fitted) | box art is a figure, not code; a code box with syntax colours obscures it and Word must not wrap it |
| 8d | The page is **frozen** (inert clone of the React root) before any DOCX mutation | Writerside's React app otherwise re-renders and swaps the topic for an error view |
| 8e | Internal ids are short (`nxo-t-N-M`, `nxoaN`), unreferenced ids are dropped, anchors are hidden (`_nxoaN`) after Pandoc | Pandoc hashes long or underscore-prefixed ids. Word caps bookmark names at 40 characters |
| 9 | Diagrams in DOCX = element screenshots (PNG, `image_scale`) taken **before** cleanup, always light, sized by explicit width/height and clamped to the page box | Word's SVG support is poor. Mermaid keeps its colours in an inner `<style>` |
| 10 | Config: Pydantic (`extra=forbid`) + layered YAML per env + env vars + CLI | reproducible per environment, typos fail fast |
| 11 | Docker: renderer image (Playwright base + Pandoc + docker CLI) starts the builder as a **sibling** container via the socket and a shared named volume | no Docker-in-Docker, no host-path translation. `--site` avoids the socket entirely |
| 12 | Builder runs on a **copy** of the project, cached by a fingerprint (sources + image + instance) | the builder writes into its sources; repeated exports are fast |

## 3. Technology stack

| Concern | Choice |
|---|---|
| Language | Python ≥ 3.11, packaged with hatchling, CLI with click |
| Site rendering | `jetbrains/writerside-builder:2026.09.0357` (pinned, amd64) via `docker run` |
| Browser | Playwright 1.63 (pinned = Docker base image tag), Chromium |
| PDF post-processing | pypdf (merge, footer overlay, outline, `/UseOutlines`) |
| DOCX | Pandoc ≥ 3 (3.9 in the image), python-docx for the reference doc |
| Config | PyYAML + Pydantic v2 |
| Tests / lint | pytest (unit, `-m e2e`), ruff |

## 4. Architecture

```
cli.py ─► config.py (layered YAML/env/CLI) ─► exporter.export()
                                                 │
            project.py (writerside.cfg, *.tree, orphan trees)
                                                 │
            builder.py ── docker run writerside-builder ──► <work>/<inst>-<fp>/site  (cached)
                                                 │                │ report.json → warnings/errors
            site.py (HelpTOC.json → topic tree, local HTTP server)
                                                 │
            render/browser.py  Session: Chromium + CDN AssetCache route + open_topic()
                                   flatten.js → print.css → fit.js
                     ┌───────────────────────────┴──────────────────────────┐
            render/pdf.py                                         render/docx/
            per-topic page.pdf, @page css, footer stamp,          extract (freeze, SVG→PNG, docx_prepare.js) →
            cover/TOC (two pass), bookmarks, merge                theme → reference → links → pandoc →
                                                                  postprocess (tables, callouts, figures, TOC)
```

Modules: `config`, `project`, `builder`, `site`, `geometry` (page box in CSS px), `exporter` (orchestration,
topic filter and subset TOC, heading shift for the combined DOCX), `render/{browser,pdf,docx}`, and
`assets/{flatten.js,print.css,fit.js,docx_theme.js,docx_figures.js,docx_prepare.js}`.
`render/docx/` = `extract`, `theme`, `reference`, `links`, `ooxml`, `postprocess`.

### Configuration

`defaults → config/default.yml → config/<env>.yml → config/local.yml → NXO_WS_EXPORT__A__B → CLI/--set`,
with `${VAR}`/`${VAR:-default}` interpolation and `config_version: 1`. Environments: `dev`, `ci` (strict, all
artifacts, fresh build), `prod` (release, `link_base_url`). Commands: `export`, `build`, `instances`,
`config show|validate`, `doctor`.

### Output

`dist/<inst>/<inst>-<theme>.pdf`, `dist/<inst>/pdf-<theme>/NNN-slug.pdf`, `dist/<inst>/<inst>.docx`,
`dist/<inst>/docx/NNN-slug.docx`.

## 5. Spike findings (kept as facts)

- PDF approach vs alternatives: the Writerside PDF exporter doesn't keep the HTML styles and hangs on `nsk`.
  Browser *Print* uses the same Chromium engine but has no flattening, TOC, bookmarks, table fitting, page
  numbers, per-topic files, or dark margins. Automated printing of the builder output is the optimum.

- Builder: exit **255** with a `webHelp*-all.zip` present means inspection errors only, so the output is valid.
  `report.json` has `testsErrors`/`testsWarnings`.
- DOM (pinned version): `.collapse__button[aria-expanded]`, `.tabs__wrapper [role=tab]`,
  `blockquote.prompt .prompt__wrapper--type-{note|tip|warning}`, `article.app__article`, `html.theme-{light|dark}`.
- The site loads app.css/app.js/fonts from `resources.jetbrains.com` → disk cache, `--offline` for hermetic runs.
- Dark: Chromium page margins need `@page` background. Print media must not be used.
- Wide tables (`.table--with-scroll`, min-content forced by long `code` identifiers) scroll horizontally on the
  site. On paper `fit.js` forces 100 % width, zooms down to `render.table_min_scale`, then enables
  `overflow-wrap:anywhere` in cells and zooms the remainder, so a table can never be clipped.
- Large diagrams must be scaled to the page height minus heading space (`fit.js`) to avoid clipping and orphan headings.

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Builder DOM/CSS changes on upgrade | image pinned; selectors isolated in `assets/`; e2e test on a real project before bumping |
| amd64 emulation on Apple Silicon is slow (~2 min build) | fingerprint cache, `--site` |
| Docker socket = root on host | documented; `--site` path needs no socket |
| CDN unavailable | asset cache + `render.offline` |
| DOCX fidelity (Word has no CSS) | styles derived from the real rendering; structural tests (`tests/test_docx.py`), LibreOffice visual QA; overridable `docx.reference_doc`, `docx.font` |
| Theme fonts missing on BA machines | fontTable `altName` fallbacks (`docx.font_fallback`, `docx.code_font_fallback`) |
| Cross-topic links in PDF | rewritten to `link_base_url` or unlinked; in-page anchors kept |

## 7. Acceptance (met on `nsk`)

- [x] full build + export, PDF light + DOCX, combined + per topic: 75 topics, 971-page combined PDF with 28
      top-level bookmarks, ~6.5 min including the emulated build on an M-series Mac
- [x] dark PDF from the cached build
- [x] collapsibles expanded, tabs flattened with titles, Mermaid visible (dark-themed in dark PDF)
- [x] DOCX (75 topics, about 2 min from a cached build): 478 real Word tables, 151 callouts, 45 light diagrams
      (none dark), 0 broken internal links, pre-filled TOC, per-topic files
- [x] per-env config validated (`config validate` for local/dev/ci/prod), unknown keys rejected
- [x] source project untouched
- [x] unit tests + ruff clean

## 8. Future work

- Clickable entries in the combined PDF TOC (link annotations to bookmark destinations).
- Cross-topic links resolved to internal PDF destinations in the combined PDF.
- Parallel topic rendering (several pages per browser context).
- Multi-instance export in one run; CI workflow publishing artifacts.
- Optional PDF/A conversion; page header with the topic title.
- Selector smoke test run automatically when `builder.image` changes.
