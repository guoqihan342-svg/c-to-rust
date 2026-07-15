from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import checked_relative_path
from .project_diagnostic_contract import PROJECT_DIAGNOSTIC_GATE_FAMILIES


def verifier_model_detail(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "origin": "host-project-verifier",
        "family": value["family"], "stage": value["stage"],
        "message": value["message"], "location": dict(value["location"]),
    }


def diagnostic_keys(schema_version: int) -> set[str]:
    base = {"code", "diagnostic_sha256", "entity_ids", "affected_module_ids"}
    return base | (
        {"origin", "family", "stage", "message", "location"}
        if schema_version == 2 else set()
    )


def validate_verifier_diagnostic(
    value: Mapping[str, Any], schema_version: int,
) -> None:
    if schema_version != 2:
        return
    stage = value.get("stage")
    location = value.get("location")
    message = value.get("message")
    if (
        value.get("origin") != "host-project-verifier"
        or not isinstance(stage, str)
        or value.get("family") not in PROJECT_DIAGNOSTIC_GATE_FAMILIES.get(
            stage, frozenset(),
        )
        or not isinstance(message, str) or not message or len(message) > 512
        or not isinstance(location, dict)
        or set(location) != {"file", "line", "column"}
    ):
        raise ValueError("project verifier diagnostic context is invalid")
    file_value = location["file"]
    if file_value is not None and (
        not isinstance(file_value, str)
        or checked_relative_path(file_value) != file_value
    ):
        raise ValueError("project verifier diagnostic location is invalid")
    numbers = (location["line"], location["column"])
    if any(
        item is not None and (
            isinstance(item, bool) or not isinstance(item, int) or item < 1
        )
        for item in numbers
    ) or (file_value is None and any(item is not None for item in numbers)):
        raise ValueError("project verifier diagnostic location is invalid")


__all__ = [
    "diagnostic_keys", "validate_verifier_diagnostic", "verifier_model_detail",
]
