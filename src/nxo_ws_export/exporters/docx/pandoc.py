"""Pandoc adapter: HTML -> DOCX with a reference.docx and a syntax-highlighting theme."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from ...errors import DocxError

_IGNORED_WARNINGS = ("Duplicate identifier",)


class HtmlToDocx(Protocol):
    """Port for the HTML -> DOCX conversion (Pandoc in production, a fake in tests)."""

    def convert(self, html: Path, out: Path, *, resource_path: Path, reference: Path, highlight: Path | None,
                meta: Mapping[str, str] | None = None, toc_depth: int | None = None) -> list[str]:
        """Write `out`; return the converter's warnings."""
        ...


class PandocConverter:
    def __init__(self, exe: str = "pandoc"):
        self.exe = exe

    def _require(self) -> str:
        found = shutil.which(self.exe)
        if not found:
            raise DocxError(f"{self.exe} not found on PATH (required for DOCX)")
        return found

    def version(self) -> str:
        out = subprocess.run([self._require(), "--version"], check=False, capture_output=True, text=True).stdout
        return out.splitlines()[0] if out else "pandoc"

    def default_reference_docx(self) -> bytes:
        r = subprocess.run([self.exe, "--print-default-data-file", "reference.docx"], check=False,
                           capture_output=True)
        if r.returncode != 0:
            raise DocxError("pandoc could not provide its default reference.docx")
        return r.stdout

    def convert(self, html: Path, out: Path, *, resource_path: Path, reference: Path, highlight: Path | None,
                meta: Mapping[str, str] | None = None, toc_depth: int | None = None) -> list[str]:
        hl = str(highlight) if highlight else "none"
        cmd = [
            self.exe, str(html), "-f", "html", "-t", "docx", "-o", str(out),
            f"--reference-doc={reference}", f"--resource-path={resource_path}", f"--syntax-highlighting={hl}",
        ]
        for k, v in (meta or {}).items():
            cmd += ["-M", f"{k}={v}"]
        if toc_depth:
            cmd += ["--toc", f"--toc-depth={toc_depth}"]
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if r.returncode != 0 and "syntax-highlighting" in r.stderr:  # pandoc < 3.8
            legacy = f"--highlight-style={hl}" if highlight else "--no-highlight"
            cmd = [legacy if c.startswith("--syntax-highlighting") else c for c in cmd]
            r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if r.returncode != 0:
            raise DocxError(f"pandoc failed for {html.name}:\n{r.stderr.strip()}")
        return [line.strip() for line in r.stderr.splitlines()
                if line.strip() and not any(w in line for w in _IGNORED_WARNINGS)]
