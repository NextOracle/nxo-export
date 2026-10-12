import json
import textwrap
from pathlib import Path

import pytest

from nxo_export.config import ConfigError, PageCfg, load_config
from nxo_export.domain.css import css_color_to_hex, first_font
from nxo_export.domain.page import PageBox, content_box_px, length_px, page_size_px
from nxo_export.errors import ExportError
from nxo_export.exporters.docx.html import shift_headings
from nxo_export.sources.builder import parse_report, source_fingerprint
from nxo_export.sources.project import ProjectError, load_project
from nxo_export.sources.site_loader import load_site

# ------------------------------------------------------------------ config


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text))
    return p


def test_config_layers_precedence(tmp_path):
    d = tmp_path / "config"
    write(d / "default.yml", "render: {theme: light, toc: {depth: 2}}\noutput: {formats: [pdf]}\n")
    write(d / "ci.yml", "render: {theme: dark}\noutput: {strict: true}\n")
    write(d / "local.yml", "render: {toc: {depth: 4}}\n")
    env = {"NXO_EXPORT__OUTPUT__MODE": "both"}
    cfg, used = load_config("ci", d, {"output": {"formats": ["docx"]}}, environ=env)
    assert cfg.env == "ci"
    assert cfg.render.theme == "dark"          # ci.yml over default.yml
    assert cfg.render.toc.depth == 4           # local.yml over everything file-based
    assert cfg.output.mode == "both"           # env var
    assert cfg.output.formats == ["docx"]      # CLI override wins
    assert cfg.output.strict is True
    assert [p.name for p in used] == ["default.yml", "ci.yml", "local.yml"]


def test_config_interpolation_and_blank_is_none(tmp_path, monkeypatch):
    d = tmp_path / "config"
    write(d / "default.yml", "render: {link_base_url: '${DOCS_URL:-}'}\nproject: {path: '${PRJ}'}\n")
    monkeypatch.setenv("PRJ", "/x/Writerside")
    monkeypatch.delenv("DOCS_URL", raising=False)
    cfg, _ = load_config(None, d, environ={})
    assert str(cfg.project.path) == "/x/Writerside"
    assert cfg.render.link_base_url is None


def test_config_errors(tmp_path):
    d = tmp_path / "config"
    write(d / "default.yml", "render: {theme: sepia}\n")
    with pytest.raises(ConfigError, match="theme"):
        load_config(None, d, environ={})
    write(d / "default.yml", "render: {unknown_key: 1}\n")
    with pytest.raises(ConfigError):
        load_config(None, d, environ={})
    write(d / "default.yml", "{}\n")
    with pytest.raises(ConfigError, match="does not exist"):
        load_config("staging", d, environ={})
    with pytest.raises(ConfigError, match="not set"):
        write(d / "default.yml", "project: {path: '${NOPE_NOT_SET_VAR}'}\n")
        load_config(None, d, environ={})
    write(d / "default.yml", "render: {table_min_scale: 0.1}\n")
    with pytest.raises(ConfigError, match="table_min_scale"):
        load_config(None, d, environ={})


def test_repo_config_files_are_valid():
    root = Path(__file__).resolve().parents[1] / "config"
    cfg, _ = load_config(None, root, environ={})
    assert cfg.env == "local"


# ------------------------------------------------------------------ project

TREE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE instance-profile SYSTEM "https://resources.jetbrains.com/writerside/1.0/product-profile.dtd">
<instance-profile id="{id}" name="{name}" start-page="start.md"><toc-element topic="start.md"/></instance-profile>
"""


def make_project(tmp_path: Path, ids=("nsk", "ntd"), orphan=True) -> Path:
    root = tmp_path / "Writerside"
    insts = "".join(f'<instance src="{i}.tree"/>' for i in ids)
    write(root / "writerside.cfg", f'<?xml version="1.0"?><ihp version="2.0"><topics dir="topics"/>{insts}</ihp>')
    for i in ids:
        write(root / f"{i}.tree", TREE.format(id=i, name=i.upper() + " Docs"))
    if orphan:
        write(root / "old.tree", TREE.format(id="old", name="Old"))
    write(root / "topics" / "start.md", "# Start\n")
    return root


def test_project_discovery(tmp_path):
    prj = load_project(make_project(tmp_path))
    assert [i.id for i in prj.instances] == ["nsk", "ntd"]
    assert prj.instance("NTD").name == "NTD Docs"
    assert [p.name for p in prj.orphan_trees] == ["old.tree"]
    with pytest.raises(ProjectError, match="several instances"):
        prj.instance(None)
    with pytest.raises(ProjectError, match="not found"):
        prj.instance("zzz")


def test_project_single_instance_is_default(tmp_path):
    prj = load_project(make_project(tmp_path, ids=("only",), orphan=False))
    assert prj.instance(None).id == "only"


def test_fingerprint_changes_with_content_not_with_ide_files(tmp_path):
    root = make_project(tmp_path)
    prj = load_project(root)
    inst = prj.instance("nsk")
    a = source_fingerprint(prj, inst, "img:1")
    write(root / ".idea" / "workspace.xml", "<x/>")
    write(root / "output" / "junk.txt", "x")
    assert source_fingerprint(prj, inst, "img:1") == a
    write(root / "topics" / "start.md", "# Changed\n")
    assert source_fingerprint(prj, inst, "img:1") != a
    assert source_fingerprint(prj, inst, "img:2") != source_fingerprint(prj, inst, "img:1")


def test_parse_report(tmp_path):
    rep = tmp_path / "report.json"
    rep.write_text(json.dumps({
        "testsErrors": {"REF002": [{"name": "Broken link", "description": "In a.md:1:1"}]},
        "testsWarnings": {"MRK056": [{"name": "Title", "description": "In b.md:2:2"}]},
    }))
    errors, warnings = parse_report(rep)
    assert [(e.code, e.where) for e in errors] == [("REF002", "In a.md:1:1")]
    assert warnings[0].code == "MRK056"
    assert parse_report(tmp_path / "missing.json") == ([], [])


# ------------------------------------------------------------------ site / toc


def make_site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    pages = {
        "sec": {"id": "sec", "title": "Section", "level": 0, "pages": ["a", "b"]},
        "a": {"id": "a", "title": "Topic A", "url": "topic-a.html", "level": 1, "parentId": "sec"},
        "b": {"id": "b", "title": "Topic B", "url": "topic-b.html", "level": 1, "parentId": "sec", "pages": ["c"]},
        "c": {"id": "c", "title": "Topic C", "url": "topic-c.html", "level": 2, "parentId": "b"},
        "d": {"id": "d", "title": "Topic D", "url": "topic-d.html", "level": 0},
    }
    write(root / "HelpTOC.json", json.dumps({"entities": {"pages": pages}, "topLevelIds": ["sec", "d"]}))
    write(root / "config.json", json.dumps({"productName": "Demo", "productId": "demo"}))
    return root


def test_site_toc_order(tmp_path):
    site = load_site(make_site(tmp_path))
    assert site.product_name == "Demo"
    assert [t.title for t in site.topics()] == ["Topic A", "Topic B", "Topic C", "Topic D"]
    assert site.toc[0].url is None and site.toc[0].children[1].children[0].level == 2


def test_topic_filter_and_subset(tmp_path):
    site = load_site(make_site(tmp_path))
    sel = site.select(("topic-c", "d"))
    assert [t.id for t in sel] == ["c", "d"]
    sub = site.subset({t.url for t in sel})
    assert [t.title for t in sub.topics()] == ["Topic C", "Topic D"]
    assert sub.toc[0].title == "Section" and sub.toc[0].children[0].url is None  # B kept as a section only
    with pytest.raises(ExportError, match="no topic"):
        site.select(("nothing*",))


def test_shift_headings():
    html = '<h1 id="x">A</h1><p>t</p><h2>B</h2></h2><h6>z</h6><header>keep</header>'
    out = shift_headings(html, 2)
    assert out == '<h3 id="x">A</h3><p>t</p><h4>B</h4></h4><h6>z</h6><header>keep</header>'
    assert shift_headings(html, 0) == html


# ------------------------------------------------------------------ geometry / style translation


def test_geometry():
    assert round(length_px("25.4mm")) == 96
    assert page_size_px("A4 landscape")[0] > page_size_px("A4")[0]
    w, h = content_box_px(PageCfg(size="A4", margin_top="10mm", margin_bottom="10mm", margin_x="10mm"))
    assert (w, h) == (718, 1046)
    with pytest.raises(ValueError):
        length_px("10em")
    box = PageBox.from_cfg(PageCfg(size="A4", margin_top="10mm", margin_bottom="10mm", margin_x="10mm"))
    assert box.content_px == (718, 1046) and not box.landscape
    with pytest.raises(ValueError):
        PageBox.from_cfg(PageCfg(size="A6", margin_top="60mm", margin_bottom="60mm", margin_x="10mm"))


@pytest.mark.parametrize("css,expected", [
    ("rgb(25, 25, 28)", "19191C"),
    ("rgba(25, 25, 28, 0.05)", "F4F4F4"),
    ("rgba(0, 0, 0, 0)", None),
    ("transparent", None),
    ("rgb(48 127 255 / 1)", "307FFF"),
])
def test_css_color_to_hex(css, expected):
    assert css_color_to_hex(css) == expected


def test_first_font():
    assert first_font('"JetBrains Sans", Inter, system-ui') == "JetBrains Sans"
    assert first_font("system-ui, -apple-system, sans-serif") is None


def test_local_example_config_is_valid(tmp_path):
    root = Path(__file__).resolve().parents[1] / "config"
    (tmp_path / "default.yml").write_text((root / "default.yml").read_text())
    (tmp_path / "local.yml").write_text((root / "local.example.yml").read_text())
    cfg, used = load_config(None, tmp_path, environ={})
    assert cfg.project.instance == "nsk" and [p.name for p in used] == ["default.yml", "local.yml"]


# ------------------------------------------------------------------ cli


@pytest.mark.parametrize("args", [["-p", "/nonexistent", "-i", "x"], ["--set", "render.theme=dark", "-p", "/nonexistent"]])
def test_export_is_the_default_command(args):
    from click.testing import CliRunner

    from nxo_export.cli import main

    r = CliRunner().invoke(main, args)
    assert r.exit_code == 2 and "error:" in r.output and "No such command" not in r.output


def test_named_commands_still_route():
    from click.testing import CliRunner

    from nxo_export.cli import main

    assert "List the instances" in CliRunner().invoke(main, ["instances", "-h"]).output
