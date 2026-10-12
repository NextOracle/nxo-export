"""Theme tokens gathered across topics: the first topic that renders an element defines its style."""

from __future__ import annotations

from typing import Any

from .model import Theme


class ThemeTokens:
    def __init__(self) -> None:
        self._tokens: dict[str, Any] = {}
        self._prism: dict[str, dict[str, Any]] = {}

    def add(self, tokens: dict[str, Any]) -> None:
        for k, v in tokens.items():
            self._tokens.setdefault(k, v)

    def add_prism(self, prism: dict[str, dict[str, Any]]) -> None:
        for k, v in prism.items():
            self._prism.setdefault(k, v)

    @property
    def prism(self) -> dict[str, dict[str, Any]]:
        return dict(self._prism)

    def theme(self) -> Theme:
        return Theme.from_tokens(self._tokens)
