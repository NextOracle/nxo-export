"""Build the HTML site with the pinned official Writerside builder (Docker)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .._types import Log
from ..config import BuilderCfg
from ..errors import BuildError
from .project import Instance, Project

CONTAINER_WORK = "/opt/work"
_IGNORE_DIRS = {".idea", "output", ".git", "build", "node_modules"}
# Exit codes observed from the builder: 0 = clean; 255 = inspections failed but artifacts were still written.
_EXIT_WITH_INSPECTION_ERRORS = 255


@dataclass(frozen=True, slots=True)
class Inspection:
    code: str
    name: str
    where: str


@dataclass(frozen=True)
class BuildResult:
    instance: str
    site_dir: Path
    exit_code: int
    cached: bool
    duration_s: float
    errors: list[Inspection] = field(default_factory=list)
    warnings: list[Inspection] = field(default_factory=list)
    log_file: Path | None = None


def source_fingerprint(project: Project, instance: Instance, image: str) -> str:
    h = hashlib.sha256()
    h.update(f"{image}\0{instance.id}\0".encode())
    for p in sorted(_iter_sources(project.root)):
        rel = p.relative_to(project.root).as_posix()
        h.update(rel.encode() + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()[:16]


def _iter_sources(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE_DIRS and not d.startswith("."))
        for f in filenames:
            if not f.startswith("."):
                yield Path(dirpath) / f


def parse_report(report: Path) -> tuple[list[Inspection], list[Inspection]]:
    if not report.is_file():
        return [], []
    data = json.loads(report.read_text(encoding="utf-8"))

    def flat(group: dict | None) -> list[Inspection]:
        out = []
        for code, items in (group or {}).items():
            for it in items:
                out.append(Inspection(code, it.get("name", ""), it.get("description", "")))
        return out

    return flat(data.get("testsErrors")), flat(data.get("testsWarnings"))


def _unzip_site(zip_path: Path, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            target = (tmp / m.filename).resolve()
            if not str(target).startswith(str(tmp.resolve())):
                raise BuildError(f"unsafe path in builder archive: {m.filename}")
        z.extractall(tmp)
    root = tmp
    if not (root / "HelpTOC.json").exists():
        found = list(tmp.rglob("HelpTOC.json"))
        if not found:
            raise BuildError(f"{zip_path.name} does not contain HelpTOC.json")
        root = found[0].parent
    shutil.rmtree(dest, ignore_errors=True)
    shutil.move(str(root), dest)
    shutil.rmtree(tmp, ignore_errors=True)


class DockerSiteBuilder:
    """Runs the pinned official Writerside builder image on a private copy of the project, with a source
    fingerprint cache so unchanged projects are not rebuilt."""

    def __init__(self, cfg: BuilderCfg, log: Log = print):
        self.cfg = cfg
        self.log = log

    def _docker(self, *args: str, **kw) -> subprocess.CompletedProcess:
        return subprocess.run([self.cfg.docker_bin, *args], check=False, capture_output=True, text=True, **kw)

    def check(self) -> None:
        if shutil.which(self.cfg.docker_bin) is None:
            raise BuildError(f"'{self.cfg.docker_bin}' not found; Docker is required for the build stage")
        r = self._docker("info", "--format", "{{.ServerVersion}}")
        if r.returncode != 0:
            raise BuildError(f"Docker daemon not reachable: {r.stderr.strip()}")

    def ensure_image(self) -> None:
        if self._docker("image", "inspect", self.cfg.image).returncode == 0:
            return
        self.log(f"pulling {self.cfg.image} (first run only, ~1.7 GB) ...")
        r = subprocess.run([self.cfg.docker_bin, "pull", "--platform", self.cfg.platform, self.cfg.image], check=False)
        if r.returncode != 0:
            raise BuildError(f"failed to pull {self.cfg.image}")

    def build(self, project: Project, instance: Instance) -> BuildResult:
        work_root = self.cfg.work_dir.expanduser().resolve()
        key = f"{instance.id}-{source_fingerprint(project, instance, self.cfg.image)}"
        job = work_root / key
        site_dir = job / "site"
        meta = job / "result.json"

        if self.cfg.reuse_cache and meta.is_file() and (site_dir / "HelpTOC.json").is_file():
            data = json.loads(meta.read_text())
            res = BuildResult(
                instance=instance.id, site_dir=site_dir, exit_code=data["exit_code"], cached=True,
                duration_s=0.0,
                errors=[Inspection(**i) for i in data["errors"]],
                warnings=[Inspection(**i) for i in data["warnings"]],
                log_file=job / "build.log",
            )
            self.log(f"build cache hit for {instance.id} ({key})")
            return res

        self.check()
        self.ensure_image()
        shutil.rmtree(job, ignore_errors=True)
        src_parent = job / "src"
        # The builder writes into its source tree (.idea/, output/), so it always gets a private copy.
        shutil.copytree(
            project.root, src_parent / project.module_name,
            ignore=lambda d, names: [n for n in names if n in _IGNORE_DIRS or n.startswith(".")],
        )
        out_dir = src_parent / "output"
        out_dir.mkdir(parents=True)

        mount_src = self.cfg.work_volume or str(work_root)
        name = f"nxo-wsb-{uuid.uuid4().hex[:10]}"
        cmd = [
            self.cfg.docker_bin, "run", "--rm", "--name", name, "--platform", self.cfg.platform,
            "-v", f"{mount_src}:{CONTAINER_WORK}",
            "-e", f"SOURCE_DIR={CONTAINER_WORK}/{key}/src",
            "-e", f"MODULE_INSTANCE={project.module_name}/{instance.id}",
            "-e", f"OUTPUT_DIR={CONTAINER_WORK}/{key}/src/output",
            "-e", "RUNNER=other",
            self.cfg.image,
        ]
        log_file = job / "build.log"
        self.log(f"building '{instance.id}' with {self.cfg.image} (log: {log_file})")
        started = time.monotonic()
        exit_code = self._run_logged(cmd, name, log_file)
        duration = time.monotonic() - started

        zips = sorted(out_dir.glob("webHelp*-all.zip"))
        errors, warnings = parse_report(out_dir / "report.json")
        if exit_code not in (0, _EXIT_WITH_INSPECTION_ERRORS) or not zips:
            tail = "\n".join(log_file.read_text(errors="replace").splitlines()[-25:])
            raise BuildError(f"Writerside builder failed (exit {exit_code}, no site archive).\n{tail}")
        if errors and self.cfg.fail_on_inspection_errors:
            raise BuildError(
                f"{len(errors)} Writerside inspection error(s) and builder.fail_on_inspection_errors=true:\n"
                + "\n".join(f"  {e.code} {e.name} ({e.where})" for e in errors)
            )

        _unzip_site(zips[0], site_dir)
        for f in ("report.json", "report.html"):
            if (out_dir / f).exists():
                shutil.copy2(out_dir / f, job / f)
        shutil.rmtree(src_parent, ignore_errors=True)
        res = BuildResult(instance.id, site_dir, exit_code, False, duration, errors, warnings, log_file)
        meta.write_text(json.dumps({
            "exit_code": exit_code,
            "errors": [asdict(e) for e in errors],
            "warnings": [asdict(w) for w in warnings],
        }, indent=2))
        return res

    def _run_logged(self, cmd: list[str], name: str, log_file: Path) -> int:
        with log_file.open("w", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
            timer = threading.Timer(self.cfg.timeout_s, lambda: self._docker("kill", name))
            timer.start()
            try:
                code = proc.wait()
            except KeyboardInterrupt:
                self._docker("kill", name)
                raise
            finally:
                timed_out = not timer.is_alive()
                timer.cancel()
        if timed_out and code != 0:
            raise BuildError(f"Writerside builder exceeded builder.timeout_s={self.cfg.timeout_s}s")
        return code
