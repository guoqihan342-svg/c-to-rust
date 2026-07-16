from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any
from .artifacts import canonical_json_bytes, content_sha256
from .cargo_output_limits import MAX_CARGO_STREAM_BYTES
from .native_link_trace_json import StrictJsonError, load_strict_json
CARGO_METADATA_FACT_EVIDENCE_SCHEMA_VERSION = 1
MAX_CARGO_METADATA_FACT_EVIDENCE_BYTES = MAX_CARGO_STREAM_BYTES
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REQUIRED_TOP_KEYS = {
    "metadata", "packages", "resolve", "target_directory", "version",
    "workspace_default_members", "workspace_members", "workspace_root",
}
_ALLOWED_TOP_KEYS = _REQUIRED_TOP_KEYS | {"build_directory"}
_PATH_FIELDS = {"build_directory", "target_directory", "workspace_root"}
_SUPPORTED_TARGET_KINDS = {
    "bench", "bin", "cdylib", "custom-build", "dylib", "example", "lib",
    "proc-macro", "rlib", "staticlib", "test",
}
_SUPPORTED_CRATE_TYPES = {
    "bin", "cdylib", "dylib", "lib", "proc-macro", "rlib", "staticlib",
}
_CLAIM_BOUNDARY = {
    "semantic_gate": False, "translation_coverage_numerator": 0,
}
_EVIDENCE_KEYS = {
    "schema_version", "status", "facts", "blockers", "raw_sha256",
    "facts_sha256", "claim_boundary",
}
_FACT_KEYS = {"resolver", "packages", "default_members", "workspace_members"}
_MISSING = object()
class CargoMetadataFactEvidenceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
def parse_cargo_metadata_fact_evidence(data: bytes) -> dict[str, Any]:
    raw, root = _strict_root(data)
    unknown = set(root) - _ALLOWED_TOP_KEYS
    if unknown:
        _fail("cargo_metadata_top_level_structure_unknown")
    facts, blockers = _topology_facts(root)
    ordered_blockers = sorted(blockers)
    return {
        "schema_version": CARGO_METADATA_FACT_EVIDENCE_SCHEMA_VERSION,
        "status": "blocked" if ordered_blockers else "ready",
        "facts": facts,
        "blockers": ordered_blockers,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "facts_sha256": content_sha256(facts),
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
def validate_cargo_metadata_fact_evidence(
    value: Mapping[str, Any], source: bytes | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _EVIDENCE_KEYS:
        _fail("cargo_metadata_fact_evidence_schema_invalid")
    status = value.get("status")
    blockers = value.get("blockers")
    facts = value.get("facts")
    if (
        status not in {"ready", "blocked"}
        or not isinstance(blockers, list)
        or blockers != sorted(set(blockers))
        or any(not _valid_text(item) for item in blockers)
        or (status == "ready") != (not blockers)
    ):
        _fail("cargo_metadata_fact_evidence_status_invalid")
    if (
        not isinstance(facts, Mapping) or set(facts) != _FACT_KEYS
        or any(
            not isinstance(facts.get(field), list)
            for field in ("packages", "default_members", "workspace_members")
        )
    ):
        _fail("cargo_metadata_facts_schema_invalid")
    if (
        value.get("schema_version") != CARGO_METADATA_FACT_EVIDENCE_SCHEMA_VERSION
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
        or _SHA256.fullmatch(str(value.get("raw_sha256"))) is None
        or value.get("facts_sha256") != content_sha256(facts)
    ):
        _fail("cargo_metadata_fact_evidence_binding_invalid")
    result = dict(value)
    if source is not None:
        expected = parse_cargo_metadata_fact_evidence(source)
        if result != expected:
            _fail("cargo_metadata_fact_evidence_source_reparse_drift")
        return expected
    return result
def _strict_root(data: bytes) -> tuple[bytes, dict[str, Any]]:
    if type(data) is not bytes:
        raise TypeError("Cargo metadata fact evidence input must be bytes")
    if len(data) > MAX_CARGO_METADATA_FACT_EVIDENCE_BYTES:
        _fail("cargo_metadata_input_limit")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CargoMetadataFactEvidenceError(
            "cargo_metadata_input_not_utf8"
        ) from error
    try:
        value = load_strict_json(text)
    except (json.JSONDecodeError, RecursionError, StrictJsonError) as error:
        raise CargoMetadataFactEvidenceError("cargo_metadata_json_invalid") from error
    if not isinstance(value, dict):
        _fail("cargo_metadata_top_level_object_required")
    return data, value
def _topology_facts(root: Mapping[str, Any]) -> tuple[dict[str, Any], set[str]]:
    blockers = {
        f"cargo_metadata_{field}_missing"
        for field in _REQUIRED_TOP_KEYS if field not in root
    }
    if "version" in root and (
        type(root["version"]) is not int or root["version"] != 1
    ):
        blockers.add("cargo_metadata_format_version_unsupported")
    resolve = root.get("resolve", _MISSING)
    resolver = "no-deps" if resolve is None else None
    if resolve is not _MISSING and resolve is not None:
        blockers.add("cargo_metadata_resolver_not_no_deps")
    for field in _PATH_FIELDS & set(root):
        if not _host_absolute_path(root[field]):
            blockers.add("cargo_metadata_host_path_shape_invalid")
    metadata = root.get("metadata", _MISSING)
    if metadata is not _MISSING and metadata is not None \
            and not isinstance(metadata, Mapping):
        blockers.add("cargo_metadata_workspace_metadata_invalid")
    packages, by_id = _packages(root.get("packages", _MISSING), blockers)
    workspace_ids, workspace = _members(
        root.get("workspace_members", _MISSING), "workspace", by_id, blockers,
    )
    default_ids, default = _members(
        root.get("workspace_default_members", _MISSING), "default", by_id,
        blockers,
    )
    if set(by_id) != set(workspace_ids):
        blockers.add("cargo_metadata_workspace_package_set_ambiguous")
    if any(item not in set(workspace_ids) for item in default_ids):
        blockers.add("cargo_metadata_default_member_not_in_workspace")
    return {
        "resolver": resolver,
        "packages": packages,
        "default_members": default,
        "workspace_members": workspace,
    }, blockers
def _packages(
    value: Any, blockers: set[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(value, list) or not value:
        blockers.add("cargo_metadata_packages_invalid")
        return [], {}
    facts: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    semantic_ids: set[tuple[str, str]] = set()
    for package in value:
        if not isinstance(package, Mapping):
            blockers.add("cargo_metadata_package_structure_ambiguous")
            continue
        package_id = package.get("id", _MISSING)
        if not _valid_text(package_id):
            blockers.add("cargo_metadata_package_id_invalid")
            package_id = None
        name, version = package.get("name"), package.get("version")
        if not _valid_text(name) or not _valid_text(version):
            blockers.add("cargo_metadata_package_semantic_identity_invalid")
            name, version = None, None
        elif (name, version) in semantic_ids:
            blockers.add("cargo_metadata_package_semantic_identity_duplicate")
        else:
            semantic_ids.add((name, version))
        features = _features(package.get("features", _MISSING), blockers)
        raw_targets = package.get("targets", _MISSING)
        targets: list[dict[str, Any]] = []
        if not isinstance(raw_targets, list) or not raw_targets:
            blockers.add("cargo_metadata_package_targets_invalid")
        else:
            for target in raw_targets:
                normalized = _target(target, blockers)
                if normalized is not None:
                    targets.append(normalized)
        known_features = {item["name"] for item in features}
        if any(set(item["required_features"]) - known_features for item in targets):
            blockers.add("cargo_metadata_target_required_feature_unknown")
        projection = {
            "name": name, "version": version,
            "features": features, "targets": _ordered(targets),
        }
        facts.append(projection)
        if package_id is not None:
            if package_id in by_id:
                blockers.add("cargo_metadata_package_id_duplicate")
            else:
                by_id[package_id] = projection
    return _ordered(facts), by_id
def _features(value: Any, blockers: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping):
        blockers.add("cargo_metadata_package_features_invalid")
        return []
    result = []
    for name, enabled in value.items():
        if not _valid_text(name):
            blockers.add("cargo_metadata_feature_name_invalid")
            continue
        result.append({
            "name": name,
            "enables": _texts(enabled, "cargo_metadata_feature_values_invalid", blockers),
        })
    return sorted(result, key=lambda item: item["name"])
def _target(value: Any, blockers: set[str]) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        blockers.add("cargo_metadata_target_structure_ambiguous")
        return None
    name = value.get("name")
    if not _valid_text(name):
        blockers.add("cargo_metadata_target_name_invalid")
        name = None
    kind = _texts(
        value.get("kind", _MISSING), "cargo_metadata_target_kind_invalid",
        blockers, nonempty=True,
    )
    if set(kind) - _SUPPORTED_TARGET_KINDS:
        blockers.add("cargo_metadata_target_kind_unsupported")
    crate_types = _texts(
        value.get("crate_types", _MISSING),
        "cargo_metadata_target_crate_types_invalid", blockers, nonempty=True,
    )
    if set(crate_types) - _SUPPORTED_CRATE_TYPES:
        blockers.add("cargo_metadata_target_crate_type_unsupported")
    required = _texts(
        value.get("required-features", []),
        "cargo_metadata_target_required_features_invalid", blockers,
    )
    return {
        "name": name, "kind": kind, "crate_types": crate_types,
        "required_features": required,
    }
def _members(
    value: Any, label: str, by_id: Mapping[str, dict[str, Any]],
    blockers: set[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    if not isinstance(value, list) or (label == "workspace" and not value):
        blockers.add(f"cargo_metadata_{label}_members_invalid")
        return [], []
    identities = []
    for item in value:
        if _valid_text(item):
            identities.append(item)
        else:
            blockers.add(f"cargo_metadata_{label}_member_reference_invalid")
    if len(identities) != len(set(identities)):
        blockers.add(f"cargo_metadata_{label}_member_reference_duplicate")
    projected = []
    for identity in identities:
        if identity not in by_id:
            blockers.add(f"cargo_metadata_{label}_member_unknown")
        else:
            projected.append(by_id[identity])
    return identities, _ordered(projected)
def _texts(
    value: Any, code: str, blockers: set[str], *, nonempty: bool = False,
) -> list[str]:
    if (
        not isinstance(value, list) or (nonempty and not value)
        or any(not _valid_text(item) for item in value)
    ):
        blockers.add(code)
        return []
    return sorted(set(value))
def _valid_text(value: Any) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        return len(value.encode("utf-8")) <= 16384 and not any(
            unicodedata.category(character) in {"Cc", "Cs"} for character in value
        )
    except UnicodeEncodeError:
        return False
def _host_absolute_path(value: Any) -> bool:
    if not _valid_text(value):
        return False
    normalized = value.replace("\\", "/")
    prefix = normalized.startswith("/") or bool(re.match(r"[A-Za-z]:/", normalized))
    parts = normalized[3:].split("/") if re.match(r"[A-Za-z]:/", normalized) else normalized[1:].split("/")
    return prefix and bool(parts) and all(part not in {"", ".", ".."} for part in parts)
def _ordered(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(values, key=_sort_key)
def _sort_key(value: Any) -> bytes:
    return canonical_json_bytes(value)
def _fail(code: str) -> None:
    raise CargoMetadataFactEvidenceError(code)
__all__ = [
    "CARGO_METADATA_FACT_EVIDENCE_SCHEMA_VERSION",
    "CargoMetadataFactEvidenceError", "MAX_CARGO_METADATA_FACT_EVIDENCE_BYTES",
    "parse_cargo_metadata_fact_evidence", "validate_cargo_metadata_fact_evidence",
]
