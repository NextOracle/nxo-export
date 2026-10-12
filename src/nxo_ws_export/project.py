"""Discovery of a Writerside project (writerside.cfg + *.tree instance files)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class ProjectError(Exception):
    pass


@dataclass(frozen=True)
class Instance:
    id: str
    name: str
    tree_file: Path
    start_page: str | None


@dataclass(frozen=True)
class Project:
    root: Path
    """Directory containing writerside.cfg (the Writerside 'module')."""
    instances: tuple[Instance, ...]
    orphan_trees: tuple[Path, ...]

    @property
    def module_name(self) -> str:
        return self.root.name

    def instance(self, wanted: str | None) -> Instance:
        if wanted is None:
            if len(self.instances) == 1:
                return self.instances[0]
            ids = ", ".join(i.id for i in self.instances)
            raise ProjectError(f"project defines several instances ({ids}); choose one with --instance")
        for i in self.instances:
            if i.id.lower() == wanted.lower():
                return i
        ids = ", ".join(i.id for i in self.instances)
        raise ProjectError(f"instance {wanted!r} not found; available: {ids}")


def _parse_xml(path: Path) -> ET.Element:
    # The files carry a DOCTYPE with an external DTD; ElementTree ignores it and never fetches it.
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ProjectError(f"{path}: invalid XML: {e}") from e


def load_project(path: Path) -> Project:
    path = path.expanduser().resolve()
    cfg = path / "writerside.cfg" if path.is_dir() else path
    if cfg.name != "writerside.cfg" or not cfg.is_file():
        raise ProjectError(f"no writerside.cfg found at {path}")
    root = cfg.parent
    ihp = _parse_xml(cfg)
    instances: list[Instance] = []
    referenced: set[Path] = set()
    for el in ihp.findall("instance"):
        src = el.get("src")
        if not src:
            continue
        tree_path = (root / src).resolve()
        referenced.add(tree_path)
        if not tree_path.is_file():
            raise ProjectError(f"writerside.cfg references missing tree file {src}")
        prof = _parse_xml(tree_path)
        iid = prof.get("id")
        if not iid:
            raise ProjectError(f"{src}: <instance-profile> has no id")
        instances.append(Instance(iid, prof.get("name") or iid, tree_path, prof.get("start-page")))
    if not instances:
        raise ProjectError(f"{cfg}: no <instance> entries")
    orphans = tuple(sorted(p.resolve() for p in root.glob("*.tree") if p.resolve() not in referenced))
    return Project(root=root, instances=tuple(instances), orphan_trees=orphans)
