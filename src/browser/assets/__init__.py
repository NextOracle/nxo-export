"""In-page JavaScript and CSS that run inside the rendered Writerside page."""

from __future__ import annotations

from functools import cache
from importlib import resources


@cache
def read_asset(name: str) -> str:
    return resources.files(__name__).joinpath(name).read_text(encoding="utf-8")
