from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def link_order_unproven(target: Mapping[str, Any]) -> bool:
    occurrences = target["input_occurrences"]
    products = [
        item["dependency_target_id"] for item in occurrences
        if item["dependency_target_id"] is not None
    ]
    native = [item for item in occurrences if item["dependency_target_id"] is None]
    return (
        len(products) != len(set(products))
        or bool(products and native)
        or bool(unrepresented_link_arguments(target))
    )


def unrepresented_link_arguments(target: Mapping[str, Any]) -> list[str]:
    represented = {"-shared", "--shared", "/dll"}
    kind = target.get("kind")
    return [
        str(argument) for argument in target.get("ordered_link_arguments", [])
        if not (kind == "cdylib" and str(argument).casefold() in represented)
    ]


__all__ = ["link_order_unproven", "unrepresented_link_arguments"]
