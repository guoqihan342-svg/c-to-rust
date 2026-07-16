from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_compiler_artifact_evidence import (
    validate_cargo_compiler_artifact_evidence,
)
from .rust_cargo_occurrence_expectation import (
    validate_rust_cargo_occurrence_expectation,
)
from .rust_link_product_inspection import inspect_rust_link_product
from .rust_occurrence_manifest import inspect_occurrence_manifest_commitment
from .rust_product_evidence import read_rust_product, validate_rust_product_evidence
from .rustc_dep_info_evidence import (
    read_rustc_dep_info, validate_rustc_dep_info_evidence,
)
from .sandbox_execution_schema import is_sha256


_PACKAGE_SUFFIX = re.compile(
    r"(?P<name>[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})@"
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.+_-]{0,127})\Z",
    re.ASCII,
)
_CLAIM_BOUNDARY = {
    "section_closure": False, "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_TOP_KEYS = {
    "schema_version", "artifact_kind", "status", "expectation_sha256",
    "compiler_source_sha256", "dep_info", "targets", "target_set_sha256",
    "coverage", "blockers", "claim_boundary", "witness_sha256",
}


def build_rust_cargo_occurrence_witness(
    ledger_path: Path, expectation: Mapping[str, Any],
    compiler_evidence: Mapping[str, Any], dep_info: Any, products: Any,
) -> dict[str, Any]:
    expected = validate_rust_cargo_occurrence_expectation(expectation)
    compiler = validate_cargo_compiler_artifact_evidence(compiler_evidence)
    dep_records = _dep_info(dep_info)
    product_records = _products(products)
    blockers = [dict(item) for item in expected["blockers"]]
    expected_map = {_identity(item): item for item in expected["targets"]}
    dep_map = {_identity(item): item for item in dep_records}
    product_map: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for product in product_records:
        product_map.setdefault(_identity(product), []).append(product)
    compiler_map = _compiler_map(compiler["artifacts"])
    for identity in sorted(set(dep_map) - set(expected_map)):
        blockers.append(_block("rust_cargo_dep_info_target_unexpected", identity))
    witnesses = []
    observed_occurrences = 0
    for identity in sorted(expected_map):
        target = expected_map[identity]
        before = len(blockers)
        artifact = compiler_map.get(identity)
        dep = dep_map.get(identity)
        target_products = product_map.get(identity, [])
        if artifact is None:
            blockers.append(_block("rust_cargo_occurrence_compiler_target_missing", identity))
        elif _hash(artifact["target"]["src_path"]) != target["root_guest_path_sha256"]:
            blockers.append(_block("rust_cargo_occurrence_root_source_mismatch", identity))
        if dep is None:
            blockers.append(_block("rust_cargo_occurrence_dep_info_missing", identity))
        if not target_products:
            blockers.append(_block("rust_cargo_occurrence_product_missing", identity))
        if artifact is None or dep is None or not target_products:
            continue
        compiler_package_hash = _hash(artifact["package_id"])
        if dep["package"]["package_id_sha256"] != compiler_package_hash:
            blockers.append(_block("rust_cargo_occurrence_dep_info_binding_mismatch", identity))
            continue
        _raw, facts = read_rustc_dep_info(ledger_path, dep)
        expected_sources = [item["guest_path_sha256"]
                            for item in target["expected_sources"]]
        actual_sources = [item["guest_path_sha256"] for item in facts["sources"]]
        if len(actual_sources) != len(expected_sources) \
                or set(actual_sources) != set(expected_sources):
            blockers.append(_block("rust_cargo_occurrence_source_closure_mismatch", identity))
        matching_products = [item for item in target_products
                             if item["guest_path_sha256"]
                             == facts["product_guest_path_sha256"]]
        if len(matching_products) != 1:
            blockers.append(_block("rust_cargo_occurrence_dep_product_mismatch", identity))
        product_witnesses = []
        for product in target_products:
            try:
                data = read_rust_product(ledger_path, product)
                inspection = inspect_rust_link_product(
                    data, str(product["product_kind"]),
                )
                marker = inspect_occurrence_manifest_commitment(
                    data, occurrence_count=target["occurrence_count"],
                    occurrence_order_sha256=target["occurrence_order_sha256"],
                    object_format=inspection["object_format"],
                )
            except (OSError, TypeError, ValueError):
                blockers.append(_block(
                    "rust_cargo_occurrence_product_manifest_missing", identity,
                    str(product["product_kind"]),
                ))
                continue
            if marker["manifest_sha256"] != target["manifest_sha256"]:
                blockers.append(_block(
                    "rust_cargo_occurrence_product_manifest_mismatch", identity,
                    str(product["product_kind"]),
                ))
                continue
            product_witnesses.append({
                "product_kind": product["product_kind"],
                "product_sha256": product["product_sha256"],
                "inspection_sha256": inspection["inspection_sha256"],
                "manifest_inspection_sha256": marker["inspection_sha256"],
                "archive_member_ordinal": marker["archive_member_ordinal"],
                "archive_member_name_sha256": marker["archive_member_name_sha256"],
                "archive_member_payload_sha256": marker[
                    "archive_member_payload_sha256"
                ],
            })
        product_witnesses = sorted(product_witnesses, key=canonical_json_bytes)
        if len(product_witnesses) != len(target_products):
            continue
        witnesses.append({
            "package": dict(target["package"]), "target": dict(target["target"]),
            "occurrence_count": target["occurrence_count"],
            "occurrence_order_sha256": target["occurrence_order_sha256"],
            "expected_source_order_sha256": target["source_order_sha256"],
            "observed_source_order_sha256": facts["source_order_sha256"],
            "dep_info_evidence_sha256": dep["evidence_sha256"],
            "products": product_witnesses,
            "product_set_sha256": content_sha256(product_witnesses),
        })
        if len(blockers) == before:
            observed_occurrences += target["occurrence_count"]
    blockers = sorted(blockers, key=canonical_json_bytes)
    witnesses = sorted(witnesses, key=canonical_json_bytes)
    expected_count = sum(item["occurrence_count"] for item in expected["targets"])
    core = {
        "schema_version": 1,
        "artifact_kind": "rust-cargo-object-occurrence-witness",
        "status": "blocked" if blockers else "ready",
        "expectation_sha256": expected["expectation_sha256"],
        "compiler_source_sha256": compiler["source_sha256"],
        "dep_info": dep_records, "targets": witnesses,
        "target_set_sha256": content_sha256(witnesses),
        "coverage": {
            "expected_occurrence_count": expected_count,
            "observed_occurrence_count": observed_occurrences,
            "object_occurrence_coverage_complete": not blockers,
        },
        "blockers": blockers, "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return validate_rust_cargo_occurrence_witness({
        **core, "witness_sha256": content_sha256(core),
    })


def validate_rust_cargo_occurrence_witness(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("rust_cargo_occurrence_witness_schema_invalid")
    dep_info, targets, blockers, coverage = (
        value.get("dep_info"), value.get("targets"), value.get("blockers"),
        value.get("coverage"),
    )
    if not isinstance(dep_info, list) or not isinstance(targets, list) \
            or not isinstance(blockers, list) or not isinstance(coverage, Mapping):
        raise ValueError("rust_cargo_occurrence_witness_collections_invalid")
    [_ for _ in (validate_rustc_dep_info_evidence(item) for item in dep_info)]
    if dep_info != sorted(dep_info, key=canonical_json_bytes) \
            or targets != sorted(targets, key=canonical_json_bytes) \
            or blockers != sorted(blockers, key=canonical_json_bytes):
        raise ValueError("rust_cargo_occurrence_witness_not_canonical")
    expected_count = coverage.get("expected_occurrence_count")
    observed_count = coverage.get("observed_occurrence_count")
    core = {key: value[key] for key in value if key != "witness_sha256"}
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "rust-cargo-object-occurrence-witness"
        or value.get("status") not in {"ready", "blocked"}
        or (value["status"] == "ready") != (not blockers)
        or not is_sha256(value.get("expectation_sha256"))
        or not is_sha256(value.get("compiler_source_sha256"))
        or value.get("target_set_sha256") != content_sha256(targets)
        or type(expected_count) is not int or expected_count < 0
        or type(observed_count) is not int or not 0 <= observed_count <= expected_count
        or coverage.get("object_occurrence_coverage_complete") is not (not blockers)
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
        or value.get("witness_sha256") != content_sha256(core)
    ):
        raise ValueError("rust_cargo_occurrence_witness_invalid")
    return dict(value)


def _compiler_map(values):
    result = {}
    for artifact in values:
        match = _PACKAGE_SUFFIX.search(artifact["package_id"])
        if match is None:
            continue
        identity = (match.group("name"), match.group("version"),
                    artifact["target"]["name"])
        if identity in result:
            result[identity] = None
        else:
            result[identity] = artifact
    return result


def _dep_info(value: Any) -> list[dict[str, Any]]:
    if value is None or value == []:
        return []
    if not isinstance(value, list):
        raise ValueError("rust_cargo_occurrence_dep_info_invalid")
    result = sorted(
        (validate_rustc_dep_info_evidence(item) for item in value),
        key=canonical_json_bytes,
    )
    if len({_identity(item) for item in result}) != len(result):
        raise ValueError("rust_cargo_occurrence_dep_info_duplicate")
    return result


def _products(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("rust_cargo_occurrence_products_invalid")
    return [validate_rust_product_evidence(item) for item in value]


def _identity(value):
    return (str(value["package"]["name"]), str(value["package"]["version"]),
            str(value["target"]["name"]))


def _block(code, identity, suffix=None):
    detail = [*identity, *([] if suffix is None else [suffix])]
    return {
        "code": code, "detail": content_sha256(detail),
        **({"product_kind": suffix} if suffix is not None else {}),
    }


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "build_rust_cargo_occurrence_witness",
    "validate_rust_cargo_occurrence_witness",
]
