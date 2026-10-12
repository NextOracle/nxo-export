"""The exporter contract (Strategy + Template Method).

Every format renders the selected topics once (``session``), then writes per-topic and/or combined documents
from that state. Formats differ only in those three steps, never in the skeleton."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from .._types import Log
from ..config import Config
from ..domain.job import ExportJob

S = TypeVar("S")


class Exporter(ABC, Generic[S]):
    format: ClassVar[str]

    def __init__(self, cfg: Config, log: Log):
        self.cfg = cfg
        self.log = log

    def export(self, job: ExportJob) -> list[Path]:
        outs: list[Path] = []
        with self.session(job) as state:
            if job.per_topic:
                outs += self.write_per_topic(state, job)
            if job.combined:
                outs.append(self.write_combined(state, job))
        return outs

    @abstractmethod
    def session(self, job: ExportJob) -> AbstractContextManager[S]:
        """Render every selected topic; the yielded state lives until all documents are written."""

    @abstractmethod
    def write_per_topic(self, state: S, job: ExportJob) -> list[Path]: ...

    @abstractmethod
    def write_combined(self, state: S, job: ExportJob) -> Path: ...
