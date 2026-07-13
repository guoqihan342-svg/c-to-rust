from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256


PROJECT_DIAGNOSTIC_KEYS = {
    "code", "scope", "entity_ids", "affected_module_ids",
    "random_unit_attribution", "diagnostic_sha256",
}


def build_project_diagnostic(
    *, code: str, entity_ids: Sequence[str], affected_module_ids: Sequence[str],
) -> dict[str, Any]:
    payload = {
        "code": _text(code, "diagnostic code"),
        "scope": "project",
        "entity_ids": _texts(entity_ids, "diagnostic entities"),
        "affected_module_ids": _texts(
            affected_module_ids, "diagnostic modules",
        ),
        "random_unit_attribution": False,
    }
    return {**payload, "diagnostic_sha256": content_sha256(payload)}


def validate_project_diagnostic(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROJECT_DIAGNOSTIC_KEYS:
        raise ValueError("project diagnostic fields are invalid")
    result = json.loads(canonical_json_bytes(value).decode("utf-8"))
    expected = build_project_diagnostic(
        code=result["code"], entity_ids=result["entity_ids"],
        affected_module_ids=result["affected_module_ids"],
    )
    if result != expected:
        raise ValueError("project diagnostic content hash drifted")
    return result


def _texts(value: Any, label: str) -> list[str]:
    if (
        isinstance(value, (str, bytes)) or not isinstance(value, Sequence)
        or len(value) > 512
    ):
        raise ValueError(f"{label} are invalid")
    result = [_text(item, label) for item in value]
    if len(set(result)) != len(result):
        raise ValueError(f"{label} are duplicated")
    return sorted(result)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
        raise ValueError(f"{label} is invalid")
    return value


__all__ = [
    "PROJECT_DIAGNOSTIC_KEYS", "build_project_diagnostic",
    "validate_project_diagnostic",
]
