"""Command line interface."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import click

from . import __version__
from .builder import Builder, BuildError
from .config import ConfigError, dump_config, load_config, parse_override, set_path
from .exporter import ExportError, export
from .project import ProjectError, load_project
from .site import SiteError

KNOWN_ERRORS = (ConfigError, ProjectError, BuildError, SiteError, ExportError)


def _log(msg: str) -> None:
    click.echo(msg, err=True)


class Ctx:
    def __init__(self, env, config_dir, sets):
        self.env, self.config_dir, self.sets = env, config_dir, list(sets)

    def load(self, extra: dict | None = None):
        tree: dict = {}
        for item in self.sets:
            k, v = parse_override(item)
            set_path(tree, k, v)
        for k, v in (extra or {}).items():
            if v is not None and v != ():
                set_path(tree, k, v)
        return load_config(self.env, self.config_dir, tree)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="nxo-ws-export")
@click.option("--env", "-e", help="Configuration environment (config/<env>.yml). Default: $NXO_WS_EXPORT_ENV or 'local'.")
@click.option("--config-dir", type=click.Path(path_type=Path), help="Directory with default.yml/<env>.yml/local.yml.")
@click.option("--set", "sets", multiple=True, metavar="KEY=VALUE", help="Override any config key, e.g. render.theme=dark.")
@click.pass_context
def main(ctx, env, config_dir, sets):
    """Export a JetBrains Writerside project to PDF (light/dark) and DOCX, keeping the Writerside look."""
    ctx.obj = Ctx(env, config_dir, sets)


def _run(fn):
    try:
        return fn()
    except KNOWN_ERRORS as e:
        _log(f"error: {e}")
        sys.exit(2)


@main.command("export")
@click.option("--project", "-p", type=click.Path(path_type=Path), help="Writerside directory (with writerside.cfg).")
@click.option("--instance", "-i", help="Instance id (tree), e.g. nsk.")
@click.option("--site", type=click.Path(exists=True, path_type=Path),
              help="Use an already built site (directory or webHelp*-all.zip) instead of running the builder.")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(["pdf", "docx"]))
@click.option("--mode", "-m", type=click.Choice(["combined", "per-topic", "both"]))
@click.option("--theme", "-t", type=click.Choice(["light", "dark"]), help="PDF only. DOCX is always light.")
@click.option("--out", "-o", type=click.Path(path_type=Path))
@click.option("--topic", "topics", multiple=True, help="Only these topics (id, file slug or glob). Repeatable.")
@click.option("--strict/--no-strict", default=None, help="Fail on warnings that would otherwise be tolerated.")
@click.option("--offline/--online", default=None, help="Never download Writerside CDN assets (cache must be warm).")
@click.pass_obj
def export_cmd(obj: Ctx, project, instance, site, formats, mode, theme, out, topics, strict, offline):
    """Build (unless --site) and export."""
    def go():
        cfg, files = obj.load({
            "project.path": str(project) if project else None, "project.instance": instance,
            "output.formats": list(formats) or None, "output.mode": mode, "render.theme": theme,
            "output.dir": str(out) if out else None, "output.strict": strict, "render.offline": offline,
        })
        _log(f"env={cfg.env} config={', '.join(map(str, files)) or '(defaults)'}")
        report = export(cfg, site_path=site, topics=topics, log=_log)
        for w in report.warnings:
            _log(f"warning: {w}")
        for p in report.outputs:
            click.echo(str(p))
    _run(go)


@main.command()
@click.option("--project", "-p", type=click.Path(path_type=Path))
@click.option("--instance", "-i")
@click.pass_obj
def build(obj: Ctx, project, instance):
    """Only run the Writerside builder; print the site directory."""
    def go():
        cfg, _ = obj.load({"project.path": str(project) if project else None, "project.instance": instance})
        prj = load_project(cfg.project.path)
        res = Builder(cfg.builder, _log).build(prj, prj.instance(cfg.project.instance))
        _log(f"exit={res.exit_code} cached={res.cached} errors={len(res.errors)} warnings={len(res.warnings)} "
             f"time={res.duration_s:.0f}s")
        click.echo(str(res.site_dir))
    _run(go)


@main.command()
@click.option("--project", "-p", type=click.Path(path_type=Path))
@click.pass_obj
def instances(obj: Ctx, project):
    """List the instances (trees) of a Writerside project."""
    def go():
        cfg, _ = obj.load({"project.path": str(project) if project else None})
        prj = load_project(cfg.project.path)
        for i in prj.instances:
            click.echo(f"{i.id}\t{i.name}\t{i.tree_file.name}")
        for o in prj.orphan_trees:
            _log(f"note: {o.name} is not referenced by writerside.cfg")
    _run(go)


@main.group()
def config():
    """Inspect the effective configuration."""


@config.command("show")
@click.pass_obj
def config_show(obj: Ctx):
    """Print the merged configuration for the selected environment."""
    def go():
        cfg, files = obj.load()
        _log("# sources: " + (", ".join(map(str, files)) or "(defaults only)"))
        click.echo(dump_config(cfg), nl=False)
    _run(go)


@config.command("validate")
@click.pass_obj
def config_validate(obj: Ctx):
    """Validate the configuration (and that the project path exists)."""
    def go():
        cfg, files = obj.load()
        prj = load_project(cfg.project.path)
        if cfg.project.instance:
            prj.instance(cfg.project.instance)
        click.echo(f"ok: env={cfg.env}, {len(files)} file(s), {len(prj.instances)} instance(s)")
    _run(go)


@main.command()
@click.pass_obj
def doctor(obj: Ctx):
    """Check the runtime dependencies."""
    cfg, _ = obj.load()
    ok = True

    def line(good: bool, what: str, detail: str = "") -> None:
        nonlocal ok
        ok &= good
        click.echo(f"[{'ok' if good else 'missing'}] {what}{' - ' + detail if detail else ''}")

    try:
        Builder(cfg.builder, _log).check()
        line(True, "docker daemon")
        img = subprocess.run([cfg.builder.docker_bin, "image", "inspect", cfg.builder.image], check=False, capture_output=True)
        line(img.returncode == 0, f"builder image {cfg.builder.image}", "" if img.returncode == 0 else "pulled on first build")
    except BuildError as e:
        line(False, "docker", str(e))
    line(shutil.which("pandoc") is not None, "pandoc (DOCX)")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        line(True, "playwright chromium")
    except Exception as e:  # noqa: BLE001
        line(False, "playwright chromium", f"python -m playwright install chromium ({str(e).splitlines()[0]})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
