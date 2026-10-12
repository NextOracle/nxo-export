"""Layered, per-environment YAML configuration.

Precedence (lowest -> highest):
  1. model defaults (this file)
  2. <config_dir>/default.yml
  3. <config_dir>/<env>.yml          (env from --env or NXO_EXPORT_ENV, default "local")
  4. <config_dir>/local.yml          (git-ignored personal overrides; always applied last among files)
  5. NXO_EXPORT__SECTION__KEY=value environment variables
  6. CLI flags / --set section.key=value
String values may reference environment variables as ${VAR} or ${VAR:-default}.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ConfigError

__all__ = ["Config", "ConfigError", "dump_config", "load_config", "parse_override", "set_path"]

CONFIG_VERSION = 1
ENV_VAR_ENV = "NXO_EXPORT_ENV"
ENV_VAR_CONFIG_DIR = "NXO_EXPORT_CONFIG_DIR"
ENV_PREFIX = "NXO_EXPORT__"
_INTERP = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, v: Any, info) -> Any:
        # "${VAR:-}" interpolates to "", which means "unset" for optional settings.
        field = cls.model_fields.get(info.field_name)
        if v == "" and field is not None and type(None) in getattr(field.annotation, "__args__", ()):
            return None
        return v


class ProjectCfg(_Model):
    path: Path = Path("./Writerside")
    """Directory that contains writerside.cfg."""
    instance: str | None = None
    """Instance (tree) id, e.g. 'nsk'. Required when the project defines several instances."""


class BuilderCfg(_Model):
    image: str = "jetbrains/writerside-builder:2026.09.0357"
    platform: str = "linux/amd64"
    timeout_s: int = 1800
    work_dir: Path = Path("./.nxo-export/work")
    work_volume: str | None = None
    """Named Docker volume mounted at work_dir. Set only when this tool itself runs inside a container
    (the builder is then a sibling container and cannot see this container's paths)."""
    fail_on_inspection_errors: bool = False
    reuse_cache: bool = True
    docker_bin: str = "docker"


class PageCfg(_Model):
    size: str = "A4"
    margin_top: str = "16mm"
    margin_bottom: str = "18mm"
    margin_x: str = "16mm"


class TocCfg(_Model):
    enabled: bool = True
    title: str = "Contents"
    depth: int = Field(3, ge=1, le=9)


class CoverCfg(_Model):
    enabled: bool = True
    title: str | None = None
    subtitle: str | None = None


class RenderCfg(_Model):
    theme: Literal["light", "dark"] = "light"
    page: PageCfg = PageCfg()
    toc: TocCfg = TocCfg()
    cover: CoverCfg = CoverCfg()
    page_numbers: bool = True
    link_base_url: str | None = None
    """Published docs URL. Cross-topic links are rewritten to it; when unset they become plain text."""
    asset_cache_dir: Path = Path("./.nxo-export/cdn-cache")
    offline: bool = False
    """Fail instead of downloading Writerside CDN assets that are not cached yet."""
    navigation_timeout_ms: int = 90_000
    table_min_scale: float = Field(0.75, ge=0.3, le=1)
    """Wide tables are scaled down to fit the page width, but not below this factor; beyond it, long
    words/identifiers in cells are broken instead (then scaled further only if still necessary)."""


class DocxCfg(_Model):
    reference_doc: Path | None = None
    """Custom reference.docx. When unset one is derived from the Writerside light theme."""
    image_scale: float = Field(2.0, gt=0, le=4)
    """Pixel density of rasterised diagrams (Mermaid, SVG): 2 = sharp on print and HiDPI screens."""
    font: str | None = None
    """Body/heading font. Default: the Writerside theme font (JetBrains Sans)."""
    code_font: str | None = None
    font_fallback: str | None = "Arial"
    """Word substitutes this when the theme font is not installed on the reader's machine."""
    code_font_fallback: str | None = "Consolas"
    emoji_font: str = "Segoe UI Emoji"
    """Character style "Emoji" (Windows font; Word on macOS falls back to Apple Color Emoji)."""
    highlight: bool = True
    """Syntax-highlight code blocks with the colours Writerside rendered."""
    toc: bool = True


class OutputCfg(_Model):
    dir: Path = Path("./dist")
    formats: list[Literal["pdf", "docx"]] = ["pdf"]
    mode: Literal["combined", "per-topic", "both"] = "combined"
    strict: bool = False


class Config(_Model):
    config_version: int = CONFIG_VERSION
    env: str = "local"
    project: ProjectCfg = ProjectCfg()
    builder: BuilderCfg = BuilderCfg()
    render: RenderCfg = RenderCfg()
    docx: DocxCfg = DocxCfg()
    output: OutputCfg = OutputCfg()

    @field_validator("config_version")
    @classmethod
    def _version(cls, v: int) -> int:
        if v != CONFIG_VERSION:
            raise ValueError(f"unsupported config_version {v}; this release understands {CONFIG_VERSION}")
        return v


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _interpolate(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            name, default = m.group(1), m.group(2)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise ConfigError(f"environment variable ${{{name}}} referenced in config is not set")
        return _INTERP.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def set_path(tree: dict, dotted: str, value: Any) -> None:
    keys = [k for k in dotted.split(".") if k]
    if not keys:
        raise ConfigError(f"invalid key {dotted!r}")
    node = tree
    for k in keys[:-1]:
        node = node.setdefault(k, {})
        if not isinstance(node, dict):
            raise ConfigError(f"cannot set {dotted!r}: {k!r} is not a section")
    node[keys[-1]] = value


def parse_override(item: str) -> tuple[str, Any]:
    if "=" not in item:
        raise ConfigError(f"--set expects key=value, got {item!r}")
    key, raw = item.split("=", 1)
    return key.strip(), (yaml.safe_load(raw) if raw != "" else "")


def env_overrides(environ: dict[str, str]) -> dict:
    tree: dict = {}
    for name, raw in environ.items():
        if name.startswith(ENV_PREFIX):
            dotted = name[len(ENV_PREFIX):].lower().replace("__", ".")
            set_path(tree, dotted, yaml.safe_load(raw) if raw != "" else "")
    return tree


def load_config(
    env: str | None = None,
    config_dir: Path | None = None,
    overrides: dict | None = None,
    environ: dict[str, str] | None = None,
) -> tuple[Config, list[Path]]:
    """Return the merged, validated config and the files that contributed to it."""
    environ = dict(os.environ) if environ is None else environ
    env = env or environ.get(ENV_VAR_ENV) or "local"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", env):
        raise ConfigError(f"invalid environment name {env!r}")
    config_dir = Path(config_dir or environ.get(ENV_VAR_CONFIG_DIR) or "config")

    merged: dict = {}
    used: list[Path] = []
    names = ["default.yml"] + ([f"{env}.yml"] if env != "local" else []) + ["local.yml"]
    for name in names:
        f = config_dir / name
        if f.is_file():
            merged = deep_merge(merged, _read_yaml(f))
            used.append(f)
        elif name == f"{env}.yml" and name != "local.yml":
            raise ConfigError(f"environment {env!r} requested but {f} does not exist")

    merged = deep_merge(merged, env_overrides(environ))
    if overrides:
        merged = deep_merge(merged, overrides)
    merged = _interpolate(merged)
    merged["env"] = env
    try:
        cfg = Config.model_validate(merged)
    except ValidationError as e:
        raise ConfigError(f"invalid configuration:\n{e}") from e
    return cfg, used


def dump_config(cfg: Config) -> str:
    return yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
