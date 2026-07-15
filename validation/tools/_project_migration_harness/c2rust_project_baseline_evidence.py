from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from .artifacts import canonical_json_bytes
from .bounded_artifact_io import (
    BoundedArtifactIOError, read_bounded_artifact, write_immutable_artifact,
)
from .c2rust_project_baseline_report_validation import (
    generated_snapshot_references, required_report_references,
    validate_baseline_report,
)
from .c2rust_project_baseline_contract_reopen import (
    validate_execution_contract_reopen,
)


MAX_CAS_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_SNAPSHOT_FILES = 20_000
MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
_ROLE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class C2RustBaselineEvidenceError(ValueError):
    pass


def write_cas_artifact(
    out_root: Path, role: str, data: bytes, *, suffix: str,
    limit: int = MAX_CAS_ARTIFACT_BYTES,
) -> dict[str, Any]:
    if (
        _ROLE.fullmatch(role) is None or suffix not in {"bin", "json"}
        or type(data) is not bytes or len(data) > limit
    ):
        raise C2RustBaselineEvidenceError("c2rust_cas_contract_invalid")
    root = Path(out_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    relative = PurePosixPath("cas", role, f"{digest}.{suffix}")
    try:
        write_immutable_artifact(root, relative, data, limit)
    except BoundedArtifactIOError as error:
        raise C2RustBaselineEvidenceError("c2rust_cas_write_failed") from error
    return {
        "path": relative.as_posix(), "sha256": digest,
        "size_bytes": len(data),
    }


def snapshot_generated_tree(
    generated_root: Path, out_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(generated_root).resolve(strict=True)
    if not root.is_dir():
        raise C2RustBaselineEvidenceError("c2rust_generated_root_invalid")
    entries: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise C2RustBaselineEvidenceError("c2rust_generated_tree_linked")
        if path.is_dir():
            continue
        if not path.is_file():
            raise C2RustBaselineEvidenceError("c2rust_generated_tree_special_file")
        relative = path.relative_to(root).as_posix()
        if relative.startswith("target/") or "/target/" in f"/{relative}/":
            continue
        size = path.stat().st_size
        total += size
        if (
            len(entries) >= MAX_SNAPSHOT_FILES
            or size > MAX_CAS_ARTIFACT_BYTES or total > MAX_SNAPSHOT_BYTES
        ):
            raise C2RustBaselineEvidenceError("c2rust_generated_tree_too_large")
        data = path.read_bytes()
        reference = write_cas_artifact(
            out_root, "generated-file", data, suffix="bin",
        )
        entries.append({"path": relative, "content_ref": reference})
    if not entries:
        raise C2RustBaselineEvidenceError("c2rust_generated_tree_empty")
    manifest = {
        "schema_version": 1,
        "artifact_kind": "c2rust-generated-tree-snapshot",
        "file_count": len(entries),
        "total_size_bytes": total,
        "files": entries,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    reference = write_cas_artifact(
        out_root, "generated-snapshot", canonical_json_bytes(manifest),
        suffix="json",
    )
    return manifest, reference


def write_baseline_report(
    out_root: Path, report: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_report_shape(report)
    _validate_execution_contract_binding(Path(out_root).resolve(), report)
    return write_cas_artifact(
        out_root, "report", canonical_json_bytes(dict(report)),
        suffix="json", limit=MAX_REPORT_BYTES,
    )


def reopen_c2rust_project_baseline(
    out_root: Path, report_ref: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(out_root).resolve(strict=True)
    data = _read_reference(root, report_ref, MAX_REPORT_BYTES, role="report")
    report = _strict_object(data, "report")
    _validate_report_shape(report)
    listed = report.get("artifact_refs")
    if not isinstance(listed, list):
        raise C2RustBaselineEvidenceError("c2rust_report_artifact_refs_invalid")
    identities: set[tuple[str, str, int]] = set()
    for item in listed:
        if not isinstance(item, dict) or set(item) != {
            "role", "visibility", "ref",
        }:
            raise C2RustBaselineEvidenceError("c2rust_report_artifact_ref_invalid")
        role = item.get("role")
        if (
            not isinstance(role, str) or _ROLE.fullmatch(role) is None
            or item.get("visibility") != "private-local"
        ):
            raise C2RustBaselineEvidenceError("c2rust_report_artifact_role_invalid")
        reference = item["ref"]
        _read_reference(root, reference, MAX_CAS_ARTIFACT_BYTES, role=role)
        identity = _identity(reference)
        if identity in identities:
            raise C2RustBaselineEvidenceError("c2rust_report_artifact_ref_duplicate")
        identities.add(identity)
    required = _required_report_refs(report)
    if not required.issubset(identities):
        raise C2RustBaselineEvidenceError("c2rust_report_artifact_binding_missing")
    for snapshot_ref in generated_snapshot_references(report):
        snapshot_data = _read_reference(
            root, snapshot_ref, MAX_CAS_ARTIFACT_BYTES,
            role="generated-snapshot",
        )
        snapshot = _strict_object(snapshot_data, "generated_snapshot")
        _validate_snapshot(root, snapshot, identities)
    if report.get("schema_version") == 3:
        from .c2rust_project_baseline_target_export_evidence import validate_target_export_reopen
        validate_target_export_reopen(root, report)
    _validate_execution_contract_binding(root, report)
    return report


def read_cas_artifact(
    out_root: Path, reference: Mapping[str, Any], *, role: str,
    limit: int = MAX_CAS_ARTIFACT_BYTES,
) -> bytes:
    root = Path(out_root).resolve(strict=True)
    return _read_reference(root, reference, limit, role=role)
def read_cas_object(
    out_root: Path, reference: Mapping[str, Any], *, role: str, label: str,
) -> dict[str, Any]:
    return _strict_object(read_cas_artifact(out_root, reference, role=role), label)
def _validate_execution_contract_binding(
    root: Path, report: Mapping[str, Any],
) -> None:
    contract = report.get("inputs", {}).get("execution_contract")
    if not isinstance(contract, Mapping) or contract.get("status") != "validated":
        return
    normalized_data = _read_reference(
        root, contract["normalized_ref"], MAX_CAS_ARTIFACT_BYTES,
        role="scenario-contract",
    )
    normalized = _strict_object(normalized_data, "scenario_contract")
    try:
        validate_execution_contract_reopen(report, normalized)
    except ValueError as error:
        raise C2RustBaselineEvidenceError(str(error)) from error


def _required_report_refs(report: Mapping[str, Any]) -> set[tuple[str, str, int]]:
    return {_identity(item) for item in required_report_references(report)}


def _validate_snapshot(
    root: Path, value: Mapping[str, Any], listed: set[tuple[str, str, int]],
) -> None:
    if (
        set(value) != {
            "schema_version", "artifact_kind", "file_count",
            "total_size_bytes", "files", "semantic_gate",
            "translation_coverage_numerator",
        }
        or value.get("schema_version") != 1
        or value.get("artifact_kind") != "c2rust-generated-tree-snapshot"
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
        or not isinstance(value.get("files"), list)
        or value.get("file_count") != len(value["files"])
    ):
        raise C2RustBaselineEvidenceError("c2rust_generated_snapshot_invalid")
    paths: list[str] = []
    total = 0
    for entry in value["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "content_ref"}:
            raise C2RustBaselineEvidenceError("c2rust_generated_snapshot_file_invalid")
        path = _safe_relative(entry.get("path"))
        data = _read_reference(
            root, entry["content_ref"], MAX_CAS_ARTIFACT_BYTES,
            role="generated-file",
        )
        identity = _identity(entry["content_ref"])
        if identity not in listed:
            raise C2RustBaselineEvidenceError("c2rust_generated_file_unlisted")
        paths.append(path)
        total += len(data)
    if paths != sorted(set(paths)) or total != value.get("total_size_bytes"):
        raise C2RustBaselineEvidenceError("c2rust_generated_snapshot_drifted")


def _validate_report_shape(value: Mapping[str, Any]) -> None:
    try:
        validate_baseline_report(value)
    except ValueError as error:
        raise C2RustBaselineEvidenceError(str(error)) from error


def _read_reference(
    root: Path, value: Mapping[str, Any], limit: int, *, role: str,
) -> bytes:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise C2RustBaselineEvidenceError("c2rust_artifact_reference_invalid")
    path = _safe_relative(value.get("path"))
    digest = value.get("sha256")
    size = value.get("size_bytes")
    expected_prefix = f"cas/{role}/"
    if (
        not path.startswith(expected_prefix) or _SHA256.fullmatch(str(digest)) is None
        or type(size) is not int or not 0 <= size <= limit
        or not PurePosixPath(path).name.startswith(str(digest) + ".")
    ):
        raise C2RustBaselineEvidenceError("c2rust_artifact_reference_binding_invalid")
    target = root.joinpath(*PurePosixPath(path).parts)
    try:
        data = read_bounded_artifact(root, target, limit)
    except BoundedArtifactIOError as error:
        raise C2RustBaselineEvidenceError("c2rust_artifact_reopen_failed") from error
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise C2RustBaselineEvidenceError("c2rust_artifact_content_drifted")
    return data


def _strict_object(data: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise C2RustBaselineEvidenceError(f"c2rust_{label}_duplicate_key")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise C2RustBaselineEvidenceError(f"c2rust_{label}_invalid_json") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise C2RustBaselineEvidenceError(f"c2rust_{label}_not_canonical")
    return value


def _identity(value: Mapping[str, Any]) -> tuple[str, str, int]:
    if not isinstance(value, Mapping):
        raise C2RustBaselineEvidenceError("c2rust_artifact_reference_invalid")
    return str(value.get("path")), str(value.get("sha256")), int(value.get("size_bytes", -1))


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise C2RustBaselineEvidenceError("c2rust_artifact_path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise C2RustBaselineEvidenceError("c2rust_artifact_path_invalid")
    return value


__all__ = [
    "C2RustBaselineEvidenceError", "read_cas_artifact", "read_cas_object",
    "reopen_c2rust_project_baseline",
    "snapshot_generated_tree", "write_baseline_report", "write_cas_artifact",
]
