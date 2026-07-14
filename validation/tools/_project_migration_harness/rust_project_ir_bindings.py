from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .build_facts import is_linklike
from .build_ir import canonical_build_ir_bytes, is_sha256
from .build_ir_validation import BuildIRValidationError, validate_build_ir
from .rust_project_ir_validation import RustProjectIRError, validate_rust_project_ir
from .rust_project_ir_cohort import PARENT_DAG_KEY, validate_cohort_dag


MAX_BOUND_ARTIFACT_BYTES = 64 * 1024 * 1024
_DAG_REQUIRED_KEYS = {"schema_version", "dag", "dag_order"}
_DAG_ALLOWED_KEYS = _DAG_REQUIRED_KEYS | {
    "unsafe_policy", "generated_build_closure", "build_ir", "claim_boundary",
    "profile", PARENT_DAG_KEY,
}
_EVIDENCE_SECTIONS = (
    "modules", "public_api", "shared_types", "global_ownership",
    "initialization", "ffi_boundaries", "cfgs", "features",
    "unsafe_obligations",
)


def reopen_rust_project_ir_bindings(
    value: Mapping[str, Any], artifact_root: Path,
) -> dict[str, Any]:
    validate_rust_project_ir(value)
    bindings = value["bindings"]
    dag_data = _read_reference(artifact_root, bindings["migration_dag"])
    dag = _strict_json(dag_data, "migration DAG")
    dag_units = _validate_migration_dag(dag)
    try:
        validate_cohort_dag(dag, artifact_root)
    except ValueError as error:
        raise RustProjectIRError(str(error)) from error
    build_payloads: dict[str, dict[str, Any]] = {}
    build_unit_count = 0
    for reference in bindings["build_ir"]:
        data = _read_reference(artifact_root, reference)
        payload = _strict_json(data, "BuildIR")
        _validate_build_ir(payload, data)
        digest = str(reference["sha256"])
        if digest in build_payloads:
            _fail("RustProjectIR binds a duplicate BuildIR entity")
        build_payloads[digest] = payload
        build_unit_count += len(payload["translation_units"])
    if build_unit_count == 0:
        _fail("RustProjectIR BuildIR closure has no translation units")
    for candidate in bindings["candidates"]:
        _read_reference(artifact_root, candidate["source"])
    _validate_domain_coverage(value, dag, dag_units, build_payloads)
    return {
        "schema_version": 1,
        "status": "domain-bound",
        "reference_count": 1 + len(build_payloads) + len(bindings["candidates"]),
        "bindings_sha256": content_sha256(bindings),
        "dag_unit_count": len(dag_units),
        "build_ir_count": len(build_payloads),
        "build_ir_translation_unit_count": build_unit_count,
        "candidate_count": len(bindings["candidates"]),
        "semantic_gate": False,
        "semantic_pass": False,
    }


def _validate_build_ir(payload: Mapping[str, Any], data: bytes) -> None:
    try:
        validate_build_ir(payload)
        if canonical_build_ir_bytes(payload) != data:
            raise BuildIRValidationError("build_ir_not_canonical")
    except (BuildIRValidationError, TypeError, ValueError) as error:
        raise RustProjectIRError(f"bound BuildIR validation failed: {error}") from error


def _validate_migration_dag(payload: Mapping[str, Any]) -> set[str]:
    keys = set(payload)
    if (
        not _DAG_REQUIRED_KEYS <= keys
        or not keys <= _DAG_ALLOWED_KEYS
        or payload.get("schema_version") != 1
    ):
        _fail("bound migration DAG schema is invalid")
    dag, order = payload.get("dag"), payload.get("dag_order")
    if not isinstance(dag, Mapping) or not dag or not isinstance(order, list):
        _fail("bound migration DAG closure is invalid")
    units = set(dag)
    if not all(isinstance(unit, str) and unit for unit in units):
        _fail("bound migration DAG unit identity is invalid")
    if (
        len(order) != len(units)
        or not all(isinstance(unit, str) for unit in order)
        or len(order) != len(set(order))
        or set(order) != units
    ):
        _fail("bound migration DAG order does not cover its units")
    positions = {unit: index for index, unit in enumerate(order)}
    for unit in sorted(units):
        dependencies = dag.get(unit)
        if (
            not isinstance(dependencies, list)
            or not all(isinstance(item, str) and item for item in dependencies)
            or dependencies != sorted(set(dependencies))
            or any(item not in units or item == unit for item in dependencies)
            or any(positions[item] >= positions[unit] for item in dependencies)
        ):
            _fail("bound migration DAG dependency closure is invalid")
    _validate_dag_metadata(payload)
    return units


def _validate_dag_metadata(payload: Mapping[str, Any]) -> None:
    profile = payload.get("profile")
    if profile is not None and profile not in {"competition", "development"}:
        _fail("bound migration DAG profile is invalid")
    boundary = payload.get("claim_boundary")
    if boundary is not None and boundary != {
        "semantic_gate": False, "translation_coverage_numerator": 0,
    }:
        _fail("bound migration DAG claim boundary is invalid")
    policy = payload.get("unsafe_policy")
    if policy is not None:
        if not isinstance(policy, Mapping) or set(policy) != {
            "allow_unsafe", "max_total", "max_per_group",
        } or not isinstance(policy.get("allow_unsafe"), bool):
            _fail("bound migration DAG unsafe policy is invalid")
        for key in ("max_total", "max_per_group"):
            limit = policy.get(key)
            if limit is not None and (
                isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
            ):
                _fail("bound migration DAG unsafe policy is invalid")
    generated = payload.get("generated_build_closure")
    if generated is not None:
        if not isinstance(generated, Mapping) or set(generated) != {
            "status", "closure", "verification",
        } or generated.get("status") not in {"bound", "blocked"}:
            _fail("bound migration DAG generated closure binding is invalid")
        _artifact_identity(generated.get("closure"))
        _artifact_identity(generated.get("verification"))


def _validate_domain_coverage(
    value: Mapping[str, Any], dag: Mapping[str, Any], dag_units: set[str],
    build_payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    bindings = value["bindings"]
    candidate_units = {str(item["unit_id"]) for item in bindings["candidates"]}
    candidate_shas = {str(item["source"]["sha256"]) for item in bindings["candidates"]}
    if len(candidate_shas) != len(bindings["candidates"]):
        _fail("RustProjectIR candidate entities are not unique")
    if candidate_units != dag_units:
        _fail("RustProjectIR candidate units do not exactly cover the migration DAG")
    module_units = [str(item["unit_id"]) for item in value["modules"]]
    if len(module_units) != len(set(module_units)) or set(module_units) != dag_units:
        _fail("RustProjectIR module units do not exactly cover the migration DAG")
    build_digests = set(build_payloads)
    _validate_embedded_build_ir(dag, bindings["build_ir"])
    records = [value["crate"]]
    records.extend(record for section in _EVIDENCE_SECTIONS for record in value[section])
    covered_builds: set[str] = set()
    covered_units: set[str] = set()
    covered_candidates: set[str] = set()
    for record in records:
        evidence = record["evidence"]
        evidence_builds = set(evidence["build_ir_sha256s"])
        evidence_units = set(evidence["dag_unit_ids"])
        evidence_candidates = set(evidence["candidate_sha256s"])
        if (
            not evidence_builds <= build_digests
            or not evidence_units <= dag_units
            or not evidence_candidates <= candidate_shas
        ):
            _fail("RustProjectIR evidence references an unknown domain entity")
        covered_builds.update(evidence_builds)
        covered_units.update(evidence_units)
        covered_candidates.update(evidence_candidates)
    if (
        covered_builds != build_digests
        or covered_units != dag_units
        or covered_candidates != candidate_shas
    ):
        _fail("RustProjectIR evidence does not cover every bound domain entity")
    crate_evidence = value["crate"]["evidence"]
    if (
        set(crate_evidence["build_ir_sha256s"]) != build_digests
        or set(crate_evidence["dag_unit_ids"]) != dag_units
        or set(crate_evidence["candidate_sha256s"]) != candidate_shas
    ):
        _fail("RustProjectIR crate evidence does not bind the complete project")


def _validate_embedded_build_ir(
    dag: Mapping[str, Any], references: list[Mapping[str, Any]],
) -> None:
    binding = dag.get("build_ir")
    if binding is None:
        return
    if not isinstance(binding, Mapping) or set(binding) != {
        "status", "artifact", "verification", "worker_admission",
    } or binding.get("status") != "bound":
        _fail("bound migration DAG BuildIR binding is invalid")
    artifact = binding.get("artifact")
    artifact_identity = _artifact_identity(artifact)
    _artifact_identity(binding.get("verification"))
    _artifact_identity(binding.get("worker_admission"))
    identities = {
        _artifact_identity(item) for item in references
    }
    if artifact_identity not in identities:
        _fail("migration DAG and RustProjectIR bind different BuildIR artifacts")


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, item in items:
            if key in result:
                _fail(f"bound {label} contains duplicate keys")
            result[key] = item
        return result
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RustProjectIRError(f"bound {label} is invalid JSON") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        _fail(f"bound {label} is not canonical JSON")
    return payload


def _read_reference(root: Path, reference: Mapping[str, Any]) -> bytes:
    relative, expected_sha, size = _artifact_identity(reference)
    try:
        resolved_root = root.resolve(strict=True)
        current = resolved_root
        for part in PurePosixPath(relative).parts:
            current /= part
            if current.exists() and is_linklike(current):
                _fail("bound artifact linked path is forbidden")
        target = current.resolve(strict=True)
        target.relative_to(resolved_root)
        if target.stat().st_size != size:
            _fail("bound artifact content drifted")
        data = target.read_bytes()
    except RustProjectIRError:
        raise
    except (OSError, ValueError) as error:
        raise RustProjectIRError("bound artifact cannot be reopened") from error
    if hashlib.sha256(data).hexdigest() != expected_sha:
        _fail("bound artifact content drifted")
    return data


def _artifact_identity(value: Any) -> tuple[str, str, int]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        _fail("bound artifact reference schema is invalid")
    try:
        path = checked_relative_path(value.get("path"))
    except ValueError as error:
        raise RustProjectIRError("bound artifact path is invalid") from error
    digest, size = value.get("sha256"), value.get("size_bytes")
    if not is_sha256(digest):
        _fail("bound artifact sha256 is invalid")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_BOUND_ARTIFACT_BYTES:
        _fail("bound artifact size is invalid")
    return path, digest, size


def _fail(message: str) -> None:
    raise RustProjectIRError(message)


__all__ = ["MAX_BOUND_ARTIFACT_BYTES", "reopen_rust_project_ir_bindings"]
