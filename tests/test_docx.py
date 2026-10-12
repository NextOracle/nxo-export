"""DOCX pipeline without a browser: prepared HTML -> Pandoc -> post-processing, checked at the OOXML level."""
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from nxo_ws_export.config import DocxCfg, PageCfg
from nxo_ws_export.domain.page import PageBox
from nxo_ws_export.exporters.docx.html import html_document as _html_doc
from nxo_ws_export.exporters.docx.ooxml import PassContext, PostProcessor
from nxo_ws_export.exporters.docx.pandoc import PandocConverter
from nxo_ws_export.exporters.docx.styles import ReferenceDocBuilder
from nxo_ws_export.exporters.docx.theme import Theme, highlight_theme

needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")


def test_short_ids_keep_targets_and_drop_unreferenced():
    html = _html_doc(None, '<h2 id="a-very-long-heading-id-that-word-would-ignore-anyway">H</h2>'
                           '<p><span id="unused"></span>x</p><p><span id="used"></span>y</p>'
                           '<table id="nxo-t-0-0"></table><a href="#used">l</a>'
                           '<a href="#a-very-long-heading-id-that-word-would-ignore-anyway">h</a>')
    assert 'id="unused"' not in html and "<span" in html
    assert 'id="nxo-t-0-0"' in html
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert all(len(i) <= 40 and not i.startswith("_") for i in ids)
    assert set(re.findall(r'href="#([^"]+)"', html)) <= set(ids)


def test_highlight_theme_uses_prism_colours():
    th = highlight_theme({"keyword": {"color": "rgb(0, 51, 179)", "fontWeight": "400"}}, "19191C")
    assert th["text-styles"]["Keyword"]["text-color"].upper() == "#0033B3"
    assert th["text-color"].upper() == "#19191C"


@needs_pandoc
def test_docx_structure(tmp_path: Path):
    fig = tmp_path / "fig.png"
    Image.new("RGB", (2400, 4000), "white").save(fig)  # taller and wider than the page: must be clamped
    body = f"""
      <h1 id="top">Topic</h1>
      <p>Intro <a href="#anchor-target">jump</a></p>
      <table id="nxo-t-0-0"><colgroup><col width="30%"><col width="70%"></colgroup>
        <thead><tr><th>Key</th><th>Value</th></tr></thead>
        <tbody><tr><td>a</td><td>b</td></tr></tbody></table>
      <table id="nxo-callout-tip-0-0"><tr><td><p>Tip text</p></td></tr></table>
      <ul><li><p><span id="anchor-target"></span>first</p></li><li><p>second</p></li></ul>
      <p><img src="{fig.as_posix()}" width="1200px" height="2000px"></p>
      <pre><code class="java">int x = 1;</code></pre>
      <div data-custom-style="Text Diagram"><p>┌──┐</p><p>│ A│</p><p>└──┘</p></div>"""
    html = tmp_path / "t.html"
    html.write_text(_html_doc(None, body), encoding="utf-8")
    theme, page = Theme(), PageCfg()
    pandoc, box = PandocConverter(), PageBox.from_cfg(page)
    ref = ReferenceDocBuilder(theme, DocxCfg(), page).build(pandoc.default_reference_docx(), tmp_path / "ref.docx")
    out = tmp_path / "t.docx"
    pandoc.convert(html, out, resource_path=tmp_path, reference=ref, highlight=None)
    ctx = PassContext(theme=theme, text_width=box.text_width_twips, text_height=box.text_height_twips,
                      table_scales={"nxo-t-0-0": 1.0})
    stats = PostProcessor().run(out, ctx)
    assert stats["tables"] == 1 and stats["callouts"] == 1 and stats["figures"] == 1
    assert stats["text_diagrams"] == 1

    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    tables = re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.S)
    data, callout = tables
    assert "<w:tblBorders>" in data and 'w:val="Table"' in data and "<w:tblHeader" in data
    assert 'w:fill="' in data.split("</w:tr>")[0]                       # shaded header row
    assert "TableText" in data
    assert 'w:fill="' in callout and "CalloutTip" in callout and 'w:val="Table"' not in callout
    names = re.findall(r'w:name="([^"]+)"', xml)
    assert not any(n.startswith("X") or n.startswith("nxo-") for n in names)   # no hashed / internal bookmarks
    assert set(re.findall(r'w:anchor="([^"]+)"', xml)) <= set(names)
    assert not re.search(r"<w:p><w:pPr>(?:(?!</w:p>).)*?<w:numPr>(?:(?!</w:p>).)*?</w:pPr>(<w:bookmark[^>]*/>)*</w:p>",
                         xml)                                            # no empty bullet paragraphs
    cx, cy = map(int, re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"', xml).groups())
    assert cx <= ctx.text_width * 635 and cy <= ctx.text_height * 635
    assert abs(cx / cy - 1200 / 2000) < 0.01                             # aspect ratio kept

    diagram = re.findall(r'<w:p>(?:(?!</w:p>).)*?w:val="TextDiagram".*?</w:p>', xml)
    assert len(diagram) == 3                                             # one paragraph per line
    assert all("keepNext" in p for p in diagram[:-1]) and "keepNext" not in diagram[-1]
    assert "w:shd" not in "".join(diagram) and "SourceCode" not in "".join(diagram)
