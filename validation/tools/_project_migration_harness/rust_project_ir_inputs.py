from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import cargo_project
from .artifacts import canonical_json_bytes
from .build_ir_validation import validate_build_ir
from .orchestration_facts import read_artifact_reference


def candidate_descriptor_map(
    values: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result = {}
    for value in values:
        unit_id = value.get("unit_id") if isinstance(value, Mapping) else None
        artifact_id = value.get("artifact_id") if isinstance(value, Mapping) else None
        group_id = value.get("group_id") if isinstance(value, Mapping) else None
        if (
            not isinstance(unit_id, str) or not unit_id
            or not isinstance(artifact_id, str) or not artifact_id
            or group_id != unit_id or unit_id in result
        ):
            _fail("rust_project_ir_candidate_identity_invalid")
        result[unit_id] = value
    return result


def build_reference_digests(values: Sequence[Mapping[str, Any]]) -> list[str]:
    digests = []
    for value in values:
        digest = value.get("sha256") if isinstance(value, Mapping) else None
        if not isinstance(digest, str):
            _fail("rust_project_ir_build_binding_invalid")
        digests.append(digest)
    if not digests or len(digests) != len(set(digests)):
        _fail("rust_project_ir_build_binding_invalid")
    return sorted(digests)


def reopen_build_payloads(
    references: Sequence[Mapping[str, Any]], artifact_root: Path,
) -> list[dict[str, Any]]:
    payloads = []
    for reference in references:
        raw = read_artifact_reference(artifact_root, reference)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise cargo_project.ProjectInputError(
                "rust_project_ir_build_binding_invalid", "rust_project_ir",
            ) from error
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != raw:
            _fail("rust_project_ir_build_binding_invalid")
        try:
            validate_build_ir(payload)
        except ValueError as error:
            raise cargo_project.ProjectInputError(
                "rust_project_ir_build_binding_invalid", "rust_project_ir",
            ) from error
        payloads.append(payload)
    return payloads


def _fail(code: str) -> None:
    raise cargo_project.ProjectInputError(code, "rust_project_ir")


__all__ = [
    "build_reference_digests", "candidate_descriptor_map",
    "reopen_build_payloads",
]
