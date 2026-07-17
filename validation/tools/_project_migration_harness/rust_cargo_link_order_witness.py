from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_compiler_artifact_evidence import (
    validate_cargo_compiler_artifact_evidence,
)
from .rust_cargo_link_expectation import (
    derive_rust_cargo_link_expectation, validate_rust_cargo_link_expectation,
)
from .rust_cargo_target_link_trace import (
    validate_rust_cargo_target_link_trace,
)
from .rust_product_evidence import validate_rust_product_evidence


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
_LIB_SUFFIXES = {
    "cdylib": (".so",), "lib": (".rlib",), "rlib": (".rlib",),
    "staticlib": (".a",),
}


def build_rust_cargo_link_order_witness(
    rust_project_ir_or_expectation: Mapping[str, Any],
    compiler_evidence: Mapping[str, Any], products: Any,
    target_trace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    expectation = (
        derive_rust_cargo_link_expectation(rust_project_ir_or_expectation)
        if rust_project_ir_or_expectation.get("schema_version") == 3
        else validate_rust_cargo_link_expectation(
            rust_project_ir_or_expectation,
        )
    )
    compiler = validate_cargo_compiler_artifact_evidence(compiler_evidence)
    normalized_products = _products(products)
    expected_targets = expectation["targets"]
    blockers: list[dict[str, str]] = []
    witnesses = []
    trace = None
    if expected_targets:
        if target_trace is None:
            blockers.append(_block("rust_cargo_target_link_trace_missing"))
        else:
            trace = validate_rust_cargo_target_link_trace(target_trace)
            if trace["source_sha256"] != compiler["source_sha256"]:
                blockers.append(_block("rust_cargo_link_source_binding_mismatch"))
            witnesses, trace_blockers = _target_witnesses(
                expected_targets, trace, compiler, normalized_products,
            )
            blockers.extend(trace_blockers)
    elif target_trace is not None:
        blockers.append(_block("rust_cargo_target_link_trace_unexpected"))
    blockers = sorted(blockers, key=canonical_json_bytes)
    core = {
        "schema_version": 1,
        "artifact_kind": "rust-cargo-link-order-witness",
        "status": "blocked" if blockers else "ready",
        "mode": "required" if expected_targets else "not-required",
        "expectation_sha256": expectation["expectation_sha256"],
        "trace_source_sha256": trace["source_sha256"] if trace else None,
        "targets": witnesses,
        "target_set_sha256": content_sha256(witnesses),
        "coverage": {
            "expected_link_target_count": len(expected_targets),
            "observed_link_target_count": len(witnesses),
            "link_order_coverage_complete": not blockers,
        },
        "blockers": blockers, "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return {**core, "witness_sha256": content_sha256(core)}


def _target_witnesses(expected, trace, compiler, products):
    diagnostics = {_identity(item): item for item in trace["diagnostics"]}
    expected_map = {_identity(item): item for item in expected}
    blockers = []
    for identity in sorted(set(diagnostics) - set(expected_map)):
        blockers.append(_block("rust_cargo_link_target_undeclared", identity))
    witnesses = []
    for identity in sorted(expected_map):
        target = expected_map[identity]
        diagnostic = diagnostics.get(identity)
        if diagnostic is None:
            blockers.append(_block("rust_cargo_link_target_missing", identity))
            continue
        artifact = _artifact_for(identity, compiler["artifacts"])
        if artifact is None or diagnostic["package"]["package_id_sha256"] != (
            hashlib.sha256(artifact["package_id"].encode("utf-8")).hexdigest()
        ):
            blockers.append(_block("rust_cargo_link_target_binding_mismatch", identity))
            continue
        witness, target_blockers = _dependency_order(
            target, diagnostic, compiler["artifacts"], products,
        )
        blockers.extend(target_blockers)
        witnesses.append(witness)
    return sorted(witnesses, key=canonical_json_bytes), blockers


def _dependency_order(target, diagnostic, artifacts, products):
    identity = _identity(target)
    entries = diagnostic["entries"]
    dependency_rows = []
    path_owners: dict[str, tuple[str, str, str]] = {}
    blockers = []
    for dependency in target["dependencies"]:
        dep_identity = _identity(dependency)
        artifact = _artifact_for(dep_identity, artifacts)
        if artifact is None or not _has_product(dep_identity, dependency, products):
            blockers.append(_block("rust_cargo_link_dependency_binding_missing", dep_identity))
            continue
        hashes = _linkable_filename_hashes(artifact, dependency["target"])
        if not hashes:
            blockers.append(_block("rust_cargo_link_dependency_artifact_missing", dep_identity))
            continue
        for digest in hashes:
            previous = path_owners.setdefault(digest, dep_identity)
            if previous != dep_identity:
                blockers.append(_block("rust_cargo_link_dependency_path_ambiguous", identity))
        positions = [item["link_ordinal"] for item in entries
                     if item["guest_path_sha256"] in hashes]
        if not positions:
            blockers.append(_block("rust_cargo_link_dependency_not_observed", dep_identity))
            continue
        if len(positions) != 1:
            blockers.append(_block(
                "rust_cargo_link_dependency_occurrence_count_mismatch", dep_identity,
            ))
        observed_hashes = sorted({
            item["guest_path_sha256"] for item in entries
            if item["guest_path_sha256"] in hashes
        })
        if len(observed_hashes) != 1:
            blockers.append(_block("rust_cargo_link_dependency_path_ambiguous", dep_identity))
            continue
        dependency_rows.append({
            "ordinal": dependency["ordinal"], "identity_sha256": content_sha256(
                list(dep_identity),
            ),
            "first_link_ordinal": min(positions),
            "guest_path_sha256": observed_hashes[0],
        })
    ordinals = [item["first_link_ordinal"] for item in dependency_rows]
    if len(dependency_rows) == len(target["dependencies"]) and any(
        right <= left for left, right in zip(ordinals, ordinals[1:])
    ):
        blockers.append(_block("rust_cargo_link_dependency_order_mismatch", identity))
    known = set(path_owners)
    unexpected = sorted({item["guest_path_sha256"] for item in entries
                         if item["guest_path_sha256"] in _workspace_paths(artifacts)
                         and item["guest_path_sha256"] not in known})
    if unexpected:
        blockers.append(_block("rust_cargo_link_dependency_unexpected", identity))
    return {
        "package": dict(target["package"]), "target": dict(target["target"]),
        "dependencies": dependency_rows,
        "dependency_order_sha256": content_sha256(dependency_rows),
        "link_entry_set_sha256": diagnostic["entry_set_sha256"],
    }, blockers


def _artifact_for(identity, artifacts):
    matches = []
    for artifact in artifacts:
        match = _PACKAGE_SUFFIX.search(artifact["package_id"])
        if match is not None and (
            match.group("name"), match.group("version"),
            artifact["target"]["name"],
        ) == identity:
            matches.append(artifact)
    return matches[0] if len(matches) == 1 else None


def _linkable_filename_hashes(artifact, target):
    suffixes = set()
    for crate_type in target["crate_types"]:
        suffixes.update(_LIB_SUFFIXES.get(crate_type, ()))
    return {
        hashlib.sha256(path.encode("utf-8")).hexdigest()
        for path in artifact["filenames"]
        if any(path.endswith(suffix) for suffix in suffixes)
    }


def _workspace_paths(artifacts):
    result = set()
    for artifact in artifacts:
        result.update(_linkable_filename_hashes(artifact, artifact["target"]))
    return result


def _has_product(identity, dependency, products):
    kinds = set(dependency["target"]["crate_types"])
    if "lib" in kinds:
        kinds.add("rlib")
    return any(_product_identity(item) == identity
               and item["product_kind"] in kinds for item in products)


def _products(value):
    if not isinstance(value, list) or not value:
        raise ValueError("rust_cargo_link_order_products_invalid")
    return [validate_rust_product_evidence(item) for item in value]


def _identity(value):
    return (str(value["package"]["name"]), str(value["package"]["version"]),
            str(value["target"]["name"]))


def _product_identity(value):
    return (str(value["package"]["name"]), str(value["package"]["version"]),
            str(value["target"]["name"]))


def _block(code, identity=None):
    result = {"code": code}
    if identity is not None:
        result["detail"] = content_sha256(list(identity))
    return result


__all__ = ["build_rust_cargo_link_order_witness"]
