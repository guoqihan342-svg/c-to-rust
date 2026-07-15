from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from . import cargo_project
from .build_ir import is_sha256
from .integration_validation import (
    MAX_MANIFEST_BYTES,
    digest,
    existing_state,
    read_bounded,
)
from .ledger_security import LedgerError
from .quarantine_manifest import QUARANTINE_MANIFEST


def reopen_candidate_generation(
    quarantine_root: Path, materialization: Mapping[str, Any],
) -> None:
    generation = materialization["generation"]
    relative = generation_relative(generation["path"])
    if relative is None:
        raise LedgerError("candidate project generation path is invalid")
    try:
        root = _resolve_unlinked_root(quarantine_root)
        target = root
        for part in relative.parts:
            target /= part
            if target.exists() and _linklike(target):
                raise ValueError
        target = target.resolve(strict=True)
        target.relative_to(root)
        _assert_no_links(target)
        state, managed = existing_state(target)
    except (OSError, TypeError, ValueError) as error:
        raise LedgerError("candidate project generation cannot be reopened") from error
    if not managed or state != generation["sha256"]:
        raise LedgerError("candidate project generation content drifted")
    manifests = {
        key: _reopen_reference(root, materialization[key])
        for key in ("manifest_ref", "generation_manifest_ref")
    }
    try:
        quarantine = json.loads(manifests["manifest_ref"].decode("utf-8"))
        last_good = json.loads(
            manifests["generation_manifest_ref"].decode("utf-8")
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("candidate project generation manifest invalid") from error
    candidate_set = materialization["candidate_set"]
    quarantine_set = (
        quarantine.get("candidate_set") if isinstance(quarantine, Mapping) else None
    )
    if not isinstance(quarantine_set, Mapping) or not isinstance(last_good, Mapping):
        raise LedgerError("candidate project generation manifest invalid")
    candidate_manifest = quarantine_set.get("manifest")
    members = (
        candidate_manifest.get("members")
        if isinstance(candidate_manifest, Mapping) else None
    )
    bindings = quarantine.get("candidate_bindings")
    quarantine_binding = last_good.get("quarantine_manifest")
    try:
        manifest_sha256 = digest(json.dumps(
            dict(candidate_manifest), sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))
        member_projection = _candidate_members(members)
        binding_projection = _candidate_bindings(bindings)
    except (TypeError, ValueError) as error:
        raise LedgerError("candidate project candidate set manifest invalid") from error
    if (
        quarantine.get("schema_version") != 1
        or quarantine.get("kind") != "detached-cargo-quarantine"
        or quarantine_set.get("sha256") != candidate_set["sha256"]
        or manifest_sha256 != candidate_set["sha256"]
        or quarantine.get("candidate_count") != candidate_set["member_count"]
        or len(member_projection) != candidate_set["member_count"]
        or binding_projection != member_projection
        or quarantine.get("immutable") is not True
        or quarantine.get("last_good_updated") is not False
        or quarantine.get("cargo_executed") is not False
        or last_good.get("generator") != materialization["generator"]
        or last_good.get("rust_project_ir_scope") != "full-project"
        or last_good.get("rust_project_ir_sha256")
        != materialization["rust_project_ir_sha256"]
        or last_good.get("rust_project_interface_sha256")
        != materialization["rust_project_interface_sha256"]
        or last_good.get("generation_kind") != "detached-quarantine"
        or last_good.get("immutable") is not True
        or last_good.get("last_good_updated") is not False
        or last_good.get("cargo_executed") is not False
        or quarantine_binding != {
            "path": QUARANTINE_MANIFEST,
            "sha256": materialization["manifest_ref"]["sha256"],
        }
    ):
        raise LedgerError("candidate project generation manifest drifted")


def _candidate_members(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("candidate members missing")
    expected = {"unit_id", "artifact_id", "content_sha256"}
    result = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != expected:
            raise ValueError("candidate member invalid")
        projection = {key: item[key] for key in sorted(expected)}
        if (
            any(not isinstance(field, str) or not field for field in projection.values())
            or not is_sha256(projection["content_sha256"])
        ):
            raise ValueError("candidate member invalid")
        result.append(projection)
    ordered = sorted(result, key=lambda item: item["unit_id"])
    if result != ordered or len({item["unit_id"] for item in result}) != len(result):
        raise ValueError("candidate members noncanonical")
    return result


def _candidate_bindings(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("candidate bindings missing")
    expected = {"unit_id", "artifact_id", "group_id", "content_sha256"}
    result = []
    for item in value:
        if (
            not isinstance(item, Mapping) or set(item) != expected
            or not isinstance(item.get("group_id"), str) or not item["group_id"]
        ):
            raise ValueError("candidate binding invalid")
        result.append({
            key: item[key] for key in
            ("artifact_id", "content_sha256", "unit_id")
        })
    return sorted(result, key=lambda item: item["unit_id"])


def generation_relative(value: Any) -> PurePosixPath | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    if any(part in {"", ".", ".."} for part in value.split("/")):
        return None
    path = PurePosixPath(value)
    return None if path.is_absolute() else path


def generation_reference_path(
    generation: Any, reference: Any, filename: str,
) -> bool:
    if not isinstance(generation, Mapping) or not isinstance(reference, Mapping):
        return False
    base = generation.get("path")
    path = reference.get("path")
    if not isinstance(base, str) or not isinstance(path, str):
        return False
    expected = PurePosixPath(base) / filename
    return not expected.is_absolute() and path == expected.as_posix()


def _reopen_reference(root: Path, reference: Mapping[str, Any]) -> bytes:
    path = root.joinpath(*PurePosixPath(reference["path"]).parts)
    try:
        data = read_bounded(path, MAX_MANIFEST_BYTES)
    except (OSError, ValueError) as error:
        raise LedgerError("candidate project generation reference unreadable") from error
    if len(data) != reference["size_bytes"] or digest(data) != reference["sha256"]:
        raise LedgerError("candidate project generation reference drifted")
    return data


def _resolve_unlinked_root(value: Path) -> Path:
    lexical = Path(os.path.abspath(value))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if current.exists() and _linklike(current):
            raise ValueError("linked quarantine root")
    root = lexical.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("quarantine root is not a directory")
    return root


def _assert_no_links(root: Path) -> None:
    for directory, directories, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        if any(_linklike(base / name) for name in directories + filenames):
            raise ValueError("linked generation entry")


def _linklike(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    if path.is_symlink() or bool(junction and junction()):
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


__all__ = [
    "generation_reference_path", "generation_relative",
    "reopen_candidate_generation",
]
