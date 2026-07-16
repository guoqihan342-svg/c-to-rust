from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_raw_output_evidence import validate_cargo_raw_output_reference
from .rust_cargo_link_expectation import validate_rust_cargo_link_expectation
from .rust_cargo_occurrence_expectation import (
    validate_rust_cargo_occurrence_expectation,
)
from .rust_cargo_occurrence_witness import (
    validate_rust_cargo_occurrence_witness,
)
from .rust_cargo_topology_ir import validate_rust_cargo_topology_expectation
from .sandbox_execution_schema import is_sha256


CLAIM_BOUNDARY = {
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
RECEIPT_KEYS = {
    "schema_version", "artifact_kind", "status", "run_id",
    "candidate_set_sha256", "project_input_sha256", "expectation",
    "link_expectation", "occurrence_expectation", "raw_sources",
    "derived_evidence", "product_witness", "link_order_witness",
    "occurrence_witness", "coverage", "blockers", "claim_boundary",
    "receipt_sha256",
}
SOURCE_KEYS = {"cargo_metadata_stdout", "cargo_build_stdout"}
DERIVED_KEYS = {
    "cargo_metadata_facts_sha256", "compiler_artifact_set_sha256",
    "compiler_source_sha256", "witness_sha256", "product_witness_sha256",
    "link_order_witness_sha256", "occurrence_witness_sha256",
}


def validate_project_rust_cargo_topology_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != RECEIPT_KEYS:
        raise ValueError("project_rust_cargo_topology_receipt_schema_invalid")
    receipt = dict(value)
    derived = receipt.get("derived_evidence")
    product_witness = receipt.get("product_witness")
    link_witness = receipt.get("link_order_witness")
    occurrence_witness = receipt.get("occurrence_witness")
    blockers = receipt.get("blockers")
    core = {key: receipt[key] for key in receipt if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") != 2
        or receipt.get("artifact_kind")
        != "project-rust-cargo-topology-receipt"
        or receipt.get("status") not in {"ready", "blocked"}
        or (receipt["status"] == "ready") != (blockers == [])
        or not isinstance(blockers, list)
        or blockers != sorted(blockers, key=canonical_json_bytes)
        or not isinstance(derived, Mapping) or set(derived) != DERIVED_KEYS
        or not all(is_sha256(derived.get(key)) for key in DERIVED_KEYS)
        or not _basic_witness(product_witness, products=True)
        or not _basic_witness(link_witness)
        or not isinstance(receipt.get("coverage"), Mapping)
        or receipt.get("claim_boundary") != CLAIM_BOUNDARY
        or receipt.get("receipt_sha256") != content_sha256(core)
    ):
        raise ValueError("project_rust_cargo_topology_receipt_invalid")
    validate_rust_cargo_occurrence_witness(occurrence_witness)
    validate_rust_cargo_topology_expectation(receipt.get("expectation"))
    validate_rust_cargo_link_expectation(receipt.get("link_expectation"))
    validate_rust_cargo_occurrence_expectation(
        receipt.get("occurrence_expectation"),
    )
    validate_topology_sources(receipt.get("raw_sources"))
    return receipt


def validate_topology_sources(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != SOURCE_KEYS:
        raise ValueError("project_rust_cargo_topology_sources_invalid")
    result = {}
    for key, gate in (
        ("cargo_metadata_stdout", "cargo-metadata"),
        ("cargo_build_stdout", "cargo-build"),
    ):
        source = value.get(key)
        digest = source.get("sha256") if isinstance(source, Mapping) else None
        result[key] = validate_cargo_raw_output_reference(
            source, gate_kind=gate, stream="stdout",
            expected_sha256=str(digest),
        )
    return result


def _basic_witness(value: Any, *, products: bool = False) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("status") in {"ready", "blocked"}
        and is_sha256(value.get("witness_sha256"))
        and (not products or isinstance(value.get("products"), list))
    )


__all__ = [
    "CLAIM_BOUNDARY", "DERIVED_KEYS", "RECEIPT_KEYS", "SOURCE_KEYS",
    "validate_project_rust_cargo_topology_receipt", "validate_topology_sources",
]
