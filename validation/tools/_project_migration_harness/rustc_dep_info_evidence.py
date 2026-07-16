from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .bounded_artifact_io import (
    BoundedArtifactIOError, read_bounded_artifact, write_immutable_artifact,
)
from .rustc_dep_info import (
    MAX_RUSTC_DEP_INFO_BYTES, parse_rustc_dep_info, validate_rustc_dep_info,
)
from .sandbox_execution_schema import is_sha256


_PACKAGE_SUFFIX = re.compile(
    r"(?P<name>[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})@"
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.+_-]{0,127})\Z",
    re.ASCII,
)
_TOP_KEYS = {
    "schema_version", "package", "target", "product_guest_path_sha256",
    "dep_info_guest_path_sha256", "facts", "file", "evidence_sha256",
}
_PACKAGE_KEYS = {"name", "version", "package_id_sha256"}
_TARGET_KEYS = {"name", "kind", "crate_types"}
_FILE_KEYS = {"path", "sha256", "size_bytes"}


def persist_captured_rustc_dep_info(
    execution: Mapping[str, Any], *, out_root: Path, required: bool,
) -> dict[str, Any]:
    if type(required) is not bool:
        raise ValueError("rustc dep-info requirement must be a boolean")
    result = dict(execution)
    captured = result.pop("_captured_rustc_dep_info", None)
    if not required:
        result["rustc_dep_info"] = []
        return result
    try:
        if not isinstance(captured, list) or not captured:
            raise ValueError("captured rustc dep-info is unavailable")
        evidence = _canonical([
            _persist(out_root.resolve(strict=True), item) for item in captured
        ])
    except (KeyError, OSError, TypeError, ValueError, BoundedArtifactIOError):
        result["rustc_dep_info"] = []
        result["status"] = "blocked"
        diagnostics = result.get("diagnostics")
        result["diagnostics"] = [
            *(diagnostics if isinstance(diagnostics, list) else []),
            {
                "code": "rustc_dep_info_evidence_unavailable",
                "stage": "cargo-build-products",
                "message": "rustc dep-info could not be persisted safely",
            },
        ]
        return result
    result["rustc_dep_info"] = evidence
    return result


def read_rustc_dep_info(
    ledger_path: Path, evidence: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    normalized = validate_rustc_dep_info_evidence(evidence)
    database = Path(ledger_path).resolve(strict=True)
    if database.name != "project-migration.sqlite3" \
            or database.parent.name != "state":
        raise ValueError("rustc dep-info requires the fixed ledger path")
    root = database.parent.parent.resolve(strict=True)
    relative = PurePosixPath(normalized["file"]["path"])
    try:
        data = read_bounded_artifact(
            root, root.joinpath(*relative.parts), MAX_RUSTC_DEP_INFO_BYTES,
        )
    except BoundedArtifactIOError as error:
        raise ValueError("rustc dep-info is not safely readable") from error
    if (
        len(data) != normalized["file"]["size_bytes"]
        or hashlib.sha256(data).hexdigest() != normalized["file"]["sha256"]
    ):
        raise ValueError("rustc dep-info content binding drifted")
    facts = parse_rustc_dep_info(data)
    if facts != normalized["facts"]:
        raise ValueError("rustc dep-info fact reparse drifted")
    return data, facts


def validate_rustc_dep_info_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("rustc_dep_info_evidence_schema_invalid")
    evidence = dict(value)
    package, target, file = (
        evidence.get("package"), evidence.get("target"), evidence.get("file"),
    )
    facts = validate_rustc_dep_info(evidence.get("facts"))
    if (
        evidence.get("schema_version") != 1
        or not isinstance(package, Mapping) or set(package) != _PACKAGE_KEYS
        or not _text(package.get("name")) or not _text(package.get("version"))
        or not is_sha256(package.get("package_id_sha256"))
        or not isinstance(target, Mapping) or set(target) != _TARGET_KEYS
        or not _text(target.get("name")) or not _texts(target.get("kind"))
        or not _texts(target.get("crate_types"))
        or not is_sha256(evidence.get("product_guest_path_sha256"))
        or facts["product_guest_path_sha256"]
        != evidence.get("product_guest_path_sha256")
        or not is_sha256(evidence.get("dep_info_guest_path_sha256"))
        or not isinstance(file, Mapping) or set(file) != _FILE_KEYS
        or not _file_reference(file)
    ):
        raise ValueError("rustc_dep_info_evidence_invalid")
    core = {key: evidence[key] for key in evidence if key != "evidence_sha256"}
    if evidence.get("evidence_sha256") != content_sha256(core):
        raise ValueError("rustc_dep_info_evidence_sha256_drifted")
    return evidence


def _persist(root: Path, value: Any) -> dict[str, Any]:
    required = {
        "package_id", "target", "product_guest_path_sha256",
        "dep_info_guest_path_sha256", "data",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("captured rustc dep-info schema is invalid")
    package_id, target, data = value["package_id"], value["target"], value["data"]
    match = _PACKAGE_SUFFIX.search(str(package_id))
    if not isinstance(data, bytes) or not data or match is None \
            or not isinstance(target, Mapping):
        raise ValueError("captured rustc dep-info is invalid")
    facts = parse_rustc_dep_info(data)
    if facts["product_guest_path_sha256"] != value["product_guest_path_sha256"]:
        raise ValueError("captured rustc dep-info product drifted")
    digest = hashlib.sha256(data).hexdigest()
    relative = PurePosixPath(checked_relative_path(
        f"verification/rustc-dep-info/{digest}.d",
    ))
    write_immutable_artifact(root, relative, data, MAX_RUSTC_DEP_INFO_BYTES)
    core = {
        "schema_version": 1,
        "package": {
            "name": match.group("name"), "version": match.group("version"),
            "package_id_sha256": hashlib.sha256(
                str(package_id).encode("utf-8"),
            ).hexdigest(),
        },
        "target": {
            "name": target.get("name"), "kind": target.get("kind"),
            "crate_types": target.get("crate_types"),
        },
        "product_guest_path_sha256": value["product_guest_path_sha256"],
        "dep_info_guest_path_sha256": value["dep_info_guest_path_sha256"],
        "facts": facts,
        "file": {"path": relative.as_posix(), "sha256": digest,
                 "size_bytes": len(data)},
    }
    return validate_rustc_dep_info_evidence({
        **core, "evidence_sha256": content_sha256(core),
    })


def _canonical(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(values, key=canonical_json_bytes)
    identities = {(item["package"]["name"], item["package"]["version"],
                   item["target"]["name"]) for item in ordered}
    if not ordered or len(identities) != len(ordered):
        raise ValueError("rustc dep-info identity is ambiguous")
    return ordered


def _file_reference(value: Mapping[str, Any]) -> bool:
    digest, size = value.get("sha256"), value.get("size_bytes")
    try:
        path = PurePosixPath(checked_relative_path(str(value.get("path"))))
    except ValueError:
        return False
    return (
        is_sha256(digest) and type(size) is int
        and 0 < size <= MAX_RUSTC_DEP_INFO_BYTES
        and path.parts == ("verification", "rustc-dep-info", f"{digest}.d")
    )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256


def _texts(value: Any) -> bool:
    return isinstance(value, list) and bool(value) \
        and value == sorted(set(value)) and all(_text(item) for item in value)


__all__ = [
    "persist_captured_rustc_dep_info", "read_rustc_dep_info",
    "validate_rustc_dep_info_evidence",
]
