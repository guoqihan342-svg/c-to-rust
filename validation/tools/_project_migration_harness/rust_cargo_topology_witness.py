from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_compiler_artifact_evidence import (
    validate_cargo_compiler_artifact_evidence,
)
from .cargo_metadata_fact_evidence import validate_cargo_metadata_fact_evidence
from .rust_cargo_topology_ir import (
    validate_rust_cargo_topology_expectation,
)


RUST_CARGO_TOPOLOGY_WITNESS_SCHEMA_VERSION = 1
MAX_TOPOLOGY_PACKAGES = 256
MAX_TOPOLOGY_TARGETS = 2048
MAX_TOPOLOGY_FEATURES = 4096
_PACKAGE_SUFFIX = re.compile(
    r"(?P<name>[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})@"
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.+_-]{0,127})\Z",
    re.ASCII,
)
_CLAIM_BOUNDARY = {
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}


def build_rust_cargo_topology_witness(
    metadata_evidence: Mapping[str, Any],
    compiler_evidence: Mapping[str, Any],
    topology_expectation: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = validate_cargo_metadata_fact_evidence(metadata_evidence)
    compiler = validate_cargo_compiler_artifact_evidence(compiler_evidence)
    expectation = validate_rust_cargo_topology_expectation(
        topology_expectation,
    )
    declared = metadata["facts"]["packages"]
    _limits(declared)
    observed, identity_blockers = _observed_packages(compiler["artifacts"])
    packages: list[dict[str, Any]] = []
    blockers = [
        _block("rust_cargo_metadata_blocked", detail=code)
        for code in metadata["blockers"]
    ] + identity_blockers + _expectation_blockers(metadata["facts"], expectation)
    target_count = 0
    feature_count = 0
    for package in declared:
        semantic = _semantic(package["name"], package["version"])
        records = observed.get((semantic["name"], semantic["version"]), [])
        projected, local = _project_package(package, records)
        packages.append(projected)
        blockers.extend(local)
        target_count += len(projected["targets"])
        feature_count += len(projected["declared_features"])
    declared_semantics = {
        (item["name"], item["version"]) for item in declared
    }
    for name, version in sorted(set(observed) - declared_semantics):
        blockers.append(_block(
            "rust_cargo_compiler_workspace_package_undeclared",
            _semantic(name, version),
        ))
    if target_count > MAX_TOPOLOGY_TARGETS or feature_count > MAX_TOPOLOGY_FEATURES:
        raise ValueError("rust_cargo_topology_witness_limit_exceeded")
    feature_complete = feature_count == 0 and not any(
        item["code"] == "rust_cargo_all_features_observation_mismatch"
        for item in blockers
    )
    if not feature_complete:
        blockers.append(_block("rust_cargo_feature_matrix_lanes_missing"))
    blockers = _canonical_blockers(blockers)
    coverage = {
        "package_count": len(packages),
        "target_count": target_count,
        "declared_feature_count": feature_count,
        "observed_mode": "all-targets-all-features",
        "module_target_ownership_complete": not any(
            item["code"] in {
                "rust_cargo_package_artifact_missing",
                "rust_cargo_package_identity_ambiguous",
                "rust_cargo_compiler_package_id_unparseable",
                "rust_cargo_compiler_workspace_package_undeclared",
                "rust_cargo_declared_target_duplicate",
                "rust_cargo_target_artifact_cardinality_mismatch",
                "rust_cargo_target_artifact_missing",
                "rust_cargo_workspace_target_undeclared",
            }
            for item in blockers
        ),
        "feature_matrix_complete": feature_complete,
        "rust_project_ir_alignment_complete": not any(
            item["code"].startswith("rust_cargo_ir_") for item in blockers
        ),
    }
    core = {
        "schema_version": RUST_CARGO_TOPOLOGY_WITNESS_SCHEMA_VERSION,
        "artifact_kind": "rust-cargo-topology-witness",
        "status": "blocked" if blockers else "ready",
        "source": {
            "cargo_metadata_facts_sha256": metadata["facts_sha256"],
            "compiler_artifact_set_sha256": compiler["artifact_set_sha256"],
            "compiler_source_sha256": compiler["source_sha256"],
            "rust_project_ir_sha256": expectation["rust_project_ir_sha256"],
            "topology_expectation_sha256": expectation["expectation_sha256"],
        },
        "packages": packages,
        "coverage": coverage,
        "blockers": blockers,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return {**core, "witness_sha256": content_sha256(core)}


def validate_rust_cargo_topology_witness(
    value: Any,
    metadata_evidence: Mapping[str, Any],
    compiler_evidence: Mapping[str, Any],
    topology_expectation: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("rust_cargo_topology_witness_schema_invalid")
    expected = build_rust_cargo_topology_witness(
        metadata_evidence, compiler_evidence, topology_expectation,
    )
    if dict(value) != expected:
        raise ValueError("rust_cargo_topology_witness_source_drifted")
    return expected


def _project_package(
    package: Mapping[str, Any], records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    semantic = _semantic(package["name"], package["version"])
    blockers: list[dict[str, Any]] = []
    identities = {item["package_id_sha256"] for item in records}
    if not records:
        blockers.append(_block("rust_cargo_package_artifact_missing", semantic))
    elif len(identities) != 1:
        blockers.append(_block("rust_cargo_package_identity_ambiguous", semantic))
    declared_features = [item["name"] for item in package["features"]]
    observed_features = sorted({
        feature for item in records for feature in item["features"]
    })
    if records and any(item["features"] != declared_features for item in records):
        blockers.append(_block("rust_cargo_all_features_observation_mismatch", semantic))
    target_keys = [_target_key(item) for item in package["targets"]]
    declared_targets = dict(zip(target_keys, package["targets"]))
    if len(declared_targets) != len(target_keys):
        blockers.append(_block("rust_cargo_declared_target_duplicate", semantic))
    observed_targets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        observed_targets.setdefault(_target_key(record["target"]), []).append(record)
    targets = []
    for key, target in sorted(declared_targets.items()):
        matched = observed_targets.pop(key, [])
        if not matched:
            blockers.append(_block(
                "rust_cargo_target_artifact_missing", semantic, target["name"],
            ))
        elif len(matched) != 1:
            blockers.append(_block(
                "rust_cargo_target_artifact_cardinality_mismatch",
                semantic, target["name"],
            ))
        profiles = sorted(
            {content_sha256(item["profile"]) for item in matched}
        )
        targets.append({
            "name": target["name"],
            "kind": list(target["kind"]),
            "crate_types": list(target["crate_types"]),
            "required_features": list(target["required_features"]),
            "artifact_count": len(matched),
            "profile_set_sha256": content_sha256(profiles),
        })
    for key in sorted(observed_targets):
        blockers.append(_block(
            "rust_cargo_workspace_target_undeclared", semantic, str(key[0]),
        ))
    return ({
        "package": semantic,
        "declared_features": declared_features,
        "observed_features": observed_features,
        "targets": targets,
    }, blockers)


def _observed_packages(
    artifacts: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}
    blockers = []
    for artifact in artifacts:
        package = _package_id(artifact["package_id"])
        if package is None:
            blockers.append(_block(
                "rust_cargo_compiler_package_id_unparseable",
                detail=content_sha256(artifact["package_id"]),
            ))
            continue
        projection = {
            "package_id_sha256": content_sha256(artifact["package_id"]),
            "target": artifact["target"],
            "profile": artifact["profile"],
            "features": artifact["features"],
        }
        result.setdefault((package["name"], package["version"]), []).append(projection)
    return result, blockers


def _expectation_blockers(
    facts: Mapping[str, Any], expectation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected = expectation["facts"]
    fields = (
        ("resolver", "rust_cargo_ir_resolver_mismatch"),
        ("packages", "rust_cargo_ir_package_target_set_mismatch"),
        ("workspace_members", "rust_cargo_ir_workspace_member_set_mismatch"),
        ("default_members", "rust_cargo_ir_default_member_set_mismatch"),
    )
    return [
        _block(code, detail=content_sha256(facts.get(field)))
        for field, code in fields if facts.get(field) != expected[field]
    ]


def _package_id(value: str) -> dict[str, str] | None:
    suffix = value.rsplit("#", 1)[-1]
    match = _PACKAGE_SUFFIX.fullmatch(suffix)
    return _semantic(*match.group("name", "version")) if match else None


def _semantic(name: str, version: str) -> dict[str, str]:
    if _PACKAGE_SUFFIX.fullmatch(f"{name}@{version}") is None:
        raise ValueError("rust_cargo_package_semantic_identity_invalid")
    return {"name": name, "version": version}


def _target_key(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        value["name"], tuple(value["kind"]), tuple(value["crate_types"]),
    )


def _block(
    code: str, package: Mapping[str, str] | None = None,
    target: str | None = None, *, detail: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "package": dict(package) if package is not None else None,
        "target": target,
        "detail": detail,
    }


def _canonical_blockers(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {canonical_json_bytes(item): item for item in values}
    return [keyed[key] for key in sorted(keyed)]


def _limits(packages: Any) -> None:
    if not isinstance(packages, list) or not packages:
        raise ValueError("rust_cargo_topology_packages_invalid")
    if len(packages) > MAX_TOPOLOGY_PACKAGES:
        raise ValueError("rust_cargo_topology_witness_limit_exceeded")


__all__ = [
    "MAX_TOPOLOGY_FEATURES", "MAX_TOPOLOGY_PACKAGES", "MAX_TOPOLOGY_TARGETS",
    "RUST_CARGO_TOPOLOGY_WITNESS_SCHEMA_VERSION",
    "build_rust_cargo_topology_witness",
    "validate_rust_cargo_topology_witness",
]
