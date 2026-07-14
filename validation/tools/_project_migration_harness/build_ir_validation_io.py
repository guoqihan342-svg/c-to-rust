from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes
from .build_facts import is_linklike
from .build_ir import validate_artifact_reference


MAX_BUILD_IR_ARTIFACT_BYTES = 64 * 1024 * 1024


def read_bound(
    root: Path, reference: Mapping[str, Any], label: str,
) -> bytes:
    validate_artifact_reference(reference, f"{label}_reference_invalid")
    current = root
    for part in PurePosixPath(str(reference["path"])).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError(f"{label}_linked_path")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label}_path_escape") from error
    size = resolved.stat().st_size
    if size != reference["size_bytes"]:
        raise ValueError(f"{label}_size_drift")
    if size > MAX_BUILD_IR_ARTIFACT_BYTES:
        raise ValueError(f"{label}_size_limit_exceeded")
    data = resolved.read_bytes()
    if hashlib.sha256(data).hexdigest() != reference["sha256"]:
        raise ValueError(f"{label}_sha256_drift")
    return data


def strict_object(data: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{label}_duplicate_key")
            result[key] = value
        return result

    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ValueError(f"{label}_not_canonical")
    return value


def attachments(
    root: Path, refs: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result = {}
    for reference in refs:
        role = str(reference["role"])
        result[role] = strict_object(read_bound(root, reference, role), role)
    return result


def repository_bindings(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = [*value["build_metadata"], *value["source_inputs"]]
    result.extend(item["binding"] for item in value["generated_inputs"])
    for unit in value["translation_units"]:
        result.extend([unit["source"], unit["output"]])
        result.extend(unit["compile_arguments"]["response_files"])
    for target in value["targets"]:
        result.extend(target["outputs"])
        result.extend(item["binding"] for item in target["ordered_inputs"])
    return result


__all__ = [
    "MAX_BUILD_IR_ARTIFACT_BYTES", "attachments", "read_bound",
    "repository_bindings", "strict_object",
]
