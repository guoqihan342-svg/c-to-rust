from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .artifact_write_once import write_once_bytes_artifact
from .build_facts import is_linklike
from .orchestration_facts import read_artifact_reference


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_KIND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z", re.ASCII)
_CAS_PREFIX = ("context", "frontier-cas")


def write_frontier_cas_json(
    out_root: Path, kind: str, payload: Mapping[str, Any],
) -> dict[str, Any]:
    kind = _validated_kind(kind)
    if not isinstance(payload, Mapping):
        raise ValueError("frontier CAS payload must be a JSON object")
    value = dict(payload)
    if value.get("artifact_kind") != kind:
        raise ValueError("frontier CAS payload artifact_kind is invalid")
    encoded = canonical_json_bytes(value)
    digest = hashlib.sha256(encoded).hexdigest()
    relative = _cas_relative(kind, digest)
    _reject_linked_root(Path(out_root))
    reference = write_once_bytes_artifact(
        Path(out_root), relative, encoded,
    )
    expected = {
        "path": relative,
        "sha256": digest,
        "size_bytes": len(encoded),
    }
    if reference != expected:
        raise ValueError("frontier CAS write binding drifted")
    return reference


def read_frontier_cas_json(
    harness_root: Path, ref: Mapping[str, Any], expected_kind: str,
) -> dict[str, Any]:
    kind = _validated_kind(expected_kind)
    reference = _validated_reference(ref, kind)
    _reject_linked_root(Path(harness_root))
    data = read_artifact_reference(Path(harness_root), reference)
    if len(data) != reference["size_bytes"]:
        raise ValueError("frontier CAS reference size drifted")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("frontier CAS artifact is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("frontier CAS artifact must be a JSON object")
    if canonical_json_bytes(value) != data:
        raise ValueError("frontier CAS artifact is not canonical JSON")
    if value.get("artifact_kind") != kind:
        raise ValueError("frontier CAS artifact_kind is invalid")
    return value


def read_bound_frontier_cas_json(
    harness_root: Path, ref: Mapping[str, Any], expected_kind: str,
) -> dict[str, Any]:
    if not isinstance(ref, Mapping) or not isinstance(ref.get("path"), str):
        raise ValueError("bound frontier CAS reference is invalid")
    path = PurePosixPath(checked_relative_path(str(ref["path"])))
    parts = path.parts
    marker = _CAS_PREFIX
    indexes = [
        index for index in range(len(parts) - len(marker) + 1)
        if tuple(parts[index:index + len(marker)]) == marker
    ]
    if len(indexes) != 1:
        raise ValueError("bound frontier CAS path has no unique CAS root")
    index = indexes[0]
    local = {
        **dict(ref), "path": PurePosixPath(*parts[index:]).as_posix(),
    }
    root = Path(harness_root).joinpath(*parts[:index])
    return read_frontier_cas_json(root, local, expected_kind)


def _validated_reference(
    value: Mapping[str, Any], kind: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("frontier CAS reference must be an object")
    relative = value.get("path")
    digest = value.get("sha256")
    size = value.get("size_bytes")
    if (
        not isinstance(relative, str)
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise ValueError("frontier CAS reference binding is incomplete")
    try:
        checked_relative_path(relative)
    except (IndexError, ValueError) as error:
        raise ValueError("frontier CAS reference path is unsafe") from error
    if relative != _cas_relative(kind, digest):
        raise ValueError("frontier CAS path SHA-256 or kind binding is invalid")
    return {"path": relative, "sha256": digest, "size_bytes": size}


def _cas_relative(kind: str, digest: str) -> str:
    return PurePosixPath(
        *_CAS_PREFIX, kind, "sha256", digest[:2], f"{digest}.json",
    ).as_posix()


def _validated_kind(value: str) -> str:
    if not isinstance(value, str) or _KIND.fullmatch(value) is None:
        raise ValueError("frontier CAS kind must be one portable path segment")
    return value


def _reject_linked_root(root: Path) -> None:
    lexical = Path(os.path.abspath(root))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if is_linklike(current):
            raise ValueError("frontier CAS root contains a link")


__all__ = [
    "read_bound_frontier_cas_json", "read_frontier_cas_json",
    "write_frontier_cas_json",
]
