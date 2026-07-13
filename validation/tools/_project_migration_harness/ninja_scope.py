from __future__ import annotations

from collections import ChainMap
from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class NinjaScope:
    parent: "NinjaScope | None" = None
    variables: dict[str, str] = field(default_factory=dict)
    rules: dict[str, dict[str, str]] = field(default_factory=dict)

    def child(self) -> "NinjaScope":
        return NinjaScope(parent=self)

    def values(
        self, *overlays: Mapping[str, str],
    ) -> ChainMap[str, str]:
        maps = [dict(value) for value in overlays]
        current: NinjaScope | None = self
        while current is not None:
            maps.append(current.variables)
            current = current.parent
        return ChainMap(*maps)

    def rule(self, name: str) -> dict[str, str] | None:
        current: NinjaScope | None = self
        while current is not None:
            if name in current.rules:
                return current.rules[name]
            current = current.parent
        return None

    def define_rule(self, name: str, bindings: dict[str, str]) -> bool:
        if name in self.rules:
            return False
        self.rules[name] = dict(bindings)
        return True


__all__ = ["NinjaScope"]
