from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)
from .cargo_fact_commands import CARGO_BUILD_COMMAND, CARGO_METADATA_COMMAND
from .cargo_metadata_fact_evidence import parse_cargo_metadata_fact_evidence
from .cargo_raw_output_evidence import (
    read_cargo_raw_output,
)
from .gate_evidence import (
    read_content_addressed_json, write_content_addressed_json,
)
from .ledger_security import LedgerError
from .project_rust_cargo_topology_paths import (
    fixed_topology_paths as _fixed_paths,
    topology_reference as _reference,
)
from .project_rust_cargo_topology_scope import PROJECT_RUST_CARGO_TOPOLOGY_SCOPE
from .project_rust_cargo_topology_receipt import (
    CLAIM_BOUNDARY, validate_project_rust_cargo_topology_receipt,
    validate_topology_sources,
)
from .rust_cargo_link_expectation import (
    derive_rust_cargo_link_expectation,
    validate_rust_cargo_link_expectation,
)
from .rust_cargo_link_order_witness import build_rust_cargo_link_order_witness
from .rust_cargo_link_trace_capture import parse_required_target_link_trace
from .rust_cargo_occurrence_expectation import (
    derive_rust_cargo_occurrence_expectation,
    validate_rust_cargo_occurrence_expectation,
)
from .rust_cargo_occurrence_witness import build_rust_cargo_occurrence_witness
from .rust_cargo_product_witness import build_rust_cargo_product_witness
from .rust_cargo_topology_ir import (
    derive_rust_cargo_topology_expectation,
    validate_rust_cargo_topology_expectation,
)
from .rust_cargo_topology_witness import build_rust_cargo_topology_witness
from .sandbox_execution_schema import is_sha256


def materialize_project_rust_cargo_topology(
    *, ledger_path: Path, out_root: Path, run_id: str,
    candidate_set_sha256: str, context: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    database = _fixed_paths(ledger_path, out_root)
    ir = context.get("rust_project_ir")
    project_input = context.get("project_input_sha256")
    if not isinstance(ir, Mapping) or not is_sha256(project_input):
        raise ValueError("project_rust_cargo_topology_context_invalid")
    expectation = derive_rust_cargo_topology_expectation(ir)
    link_expectation = derive_rust_cargo_link_expectation(ir)
    occurrence_expectation = derive_rust_cargo_occurrence_expectation(ir)
    sources = _execution_sources(execution, str(project_input))
    receipt = _derive_receipt(
        database, run_id=run_id,
        candidate_set_sha256=candidate_set_sha256,
        project_input_sha256=str(project_input), expectation=expectation,
        link_expectation=link_expectation,
        occurrence_expectation=occurrence_expectation, raw_sources=sources,
        products=execution.get("rust_products"),
        dep_info=execution.get("rustc_dep_info"),
    )
    reference = write_content_addressed_json(
        out_root.resolve(strict=True), PROJECT_RUST_CARGO_TOPOLOGY_SCOPE,
        receipt,
    )
    reopened = reopen_project_rust_cargo_topology(
        ledger_path=database, reference=reference, run_id=run_id,
        candidate_set_sha256=candidate_set_sha256,
        project_input_sha256=str(project_input), rust_project_ir=ir,
    )
    if reopened != receipt:
        raise LedgerError("project Rust Cargo topology durable reopen drifted")
    return {"status": receipt["status"], "receipt": receipt,
            "reference": reference}


def reopen_project_rust_cargo_topology(
    *, ledger_path: Path, reference: Mapping[str, Any], run_id: str,
    candidate_set_sha256: str, project_input_sha256: str | None = None,
    rust_project_ir: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    database = Path(ledger_path).resolve(strict=True)
    bound = _reference(reference)
    stored = read_content_addressed_json(
        database, bound["path"], bound["sha256"],
    )
    if len(canonical_json_bytes(stored)) != bound["size_bytes"]:
        raise LedgerError("project Rust Cargo topology evidence size drifted")
    receipt = validate_project_rust_cargo_topology_receipt(stored)
    if (
        receipt["run_id"] != run_id
        or receipt["candidate_set_sha256"] != candidate_set_sha256
        or (
            project_input_sha256 is not None
            and receipt["project_input_sha256"] != project_input_sha256
        )
    ):
        raise LedgerError("project Rust Cargo topology identity drifted")
    expectation = receipt["expectation"]
    link_expectation = receipt["link_expectation"]
    occurrence_expectation = receipt["occurrence_expectation"]
    if rust_project_ir is not None and expectation != (
        derive_rust_cargo_topology_expectation(rust_project_ir)
    ):
        raise LedgerError("project Rust Cargo topology IR binding drifted")
    if rust_project_ir is not None and link_expectation != (
        derive_rust_cargo_link_expectation(rust_project_ir)
    ):
        raise LedgerError("project Rust Cargo link expectation drifted")
    if rust_project_ir is not None and occurrence_expectation != (
        derive_rust_cargo_occurrence_expectation(rust_project_ir)
    ):
        raise LedgerError("project Rust Cargo occurrence expectation drifted")
    expected = _derive_receipt(
        database, run_id=run_id,
        candidate_set_sha256=candidate_set_sha256,
        project_input_sha256=receipt["project_input_sha256"],
        expectation=expectation, link_expectation=link_expectation,
        occurrence_expectation=occurrence_expectation,
        raw_sources=receipt["raw_sources"],
        products=receipt["product_witness"]["products"],
        dep_info=receipt["occurrence_witness"]["dep_info"],
    )
    if receipt != expected:
        raise LedgerError("project Rust Cargo topology evidence drifted")
    return receipt


def _derive_receipt(
    database: Path, *, run_id: str, candidate_set_sha256: str,
    project_input_sha256: str, expectation: Mapping[str, Any],
    link_expectation: Mapping[str, Any],
    occurrence_expectation: Mapping[str, Any],
    raw_sources: Mapping[str, Any], products: Any, dep_info: Any,
) -> dict[str, Any]:
    if not run_id or not is_sha256(candidate_set_sha256) \
            or not is_sha256(project_input_sha256):
        raise ValueError("project_rust_cargo_topology_identity_invalid")
    expected = validate_rust_cargo_topology_expectation(expectation)
    expected_link = validate_rust_cargo_link_expectation(link_expectation)
    expected_occurrences = validate_rust_cargo_occurrence_expectation(
        occurrence_expectation,
    )
    sources = validate_topology_sources(raw_sources)
    metadata_raw = read_cargo_raw_output(
        database, sources["cargo_metadata_stdout"],
        gate_kind="cargo-metadata", stream="stdout",
        expected_sha256=sources["cargo_metadata_stdout"]["sha256"],
    )
    compiler_raw = read_cargo_raw_output(
        database, sources["cargo_build_stdout"],
        gate_kind="cargo-build", stream="stdout",
        expected_sha256=sources["cargo_build_stdout"]["sha256"],
    )
    metadata = parse_cargo_metadata_fact_evidence(metadata_raw)
    compiler = parse_cargo_compiler_artifact_evidence(compiler_raw)
    witness = build_rust_cargo_topology_witness(
        metadata, compiler, expected,
    )
    product_witness = build_rust_cargo_product_witness(
        database, products, compiler, expected,
    )
    target_trace = parse_required_target_link_trace(compiler_raw, expected_link)
    link_witness = build_rust_cargo_link_order_witness(
        expected_link, compiler, products, target_trace,
    )
    occurrence_witness = build_rust_cargo_occurrence_witness(
        database, expected_occurrences, compiler, dep_info, products,
    )
    blockers = [
        *witness["blockers"], *product_witness["blockers"],
        *link_witness["blockers"], *occurrence_witness["blockers"],
    ]
    if any(item["fresh"] for item in compiler["artifacts"]):
        blockers.append({"code": "rust_cargo_compiler_artifact_fresh"})
    blockers = sorted(blockers, key=canonical_json_bytes)
    core = {
        "schema_version": 2,
        "artifact_kind": "project-rust-cargo-topology-receipt",
        "status": "blocked" if blockers else "ready",
        "run_id": run_id,
        "candidate_set_sha256": candidate_set_sha256,
        "project_input_sha256": project_input_sha256,
        "expectation": expected,
        "link_expectation": expected_link,
        "occurrence_expectation": expected_occurrences,
        "raw_sources": sources,
        "derived_evidence": {
            "cargo_metadata_facts_sha256": metadata["facts_sha256"],
            "compiler_artifact_set_sha256": compiler["artifact_set_sha256"],
            "compiler_source_sha256": compiler["source_sha256"],
            "witness_sha256": witness["witness_sha256"],
            "product_witness_sha256": product_witness["witness_sha256"],
            "link_order_witness_sha256": link_witness["witness_sha256"],
            "occurrence_witness_sha256": occurrence_witness["witness_sha256"],
        },
        "product_witness": product_witness,
        "link_order_witness": link_witness,
        "occurrence_witness": occurrence_witness,
        "coverage": {
            **witness["coverage"], **product_witness["coverage"],
            **link_witness["coverage"], **occurrence_witness["coverage"],
        },
        "blockers": blockers,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    return validate_project_rust_cargo_topology_receipt({
        **core, "receipt_sha256": content_sha256(core),
    })


def _execution_sources(
    execution: Mapping[str, Any], project_input_sha256: str,
) -> dict[str, Any]:
    facts = execution.get("fact_probes")
    structure = execution.get("structure_probes")
    metadata = facts.get("cargo-metadata") if isinstance(facts, Mapping) else None
    build = structure.get("cargo-build") if isinstance(structure, Mapping) else None
    if (
        execution.get("status") != "passed"
        or execution.get("project_state_unchanged") is not True
        or execution.get("project_input_sha256") != project_input_sha256
        or not isinstance(metadata, Mapping)
        or metadata.get("command") != list(CARGO_METADATA_COMMAND)
        or metadata.get("status") != "passed"
        or not isinstance(build, Mapping)
        or build.get("command") != list(CARGO_BUILD_COMMAND)
        or build.get("status") != "passed"
    ):
        raise ValueError("project_rust_cargo_topology_execution_invalid")
    return validate_topology_sources({
        "cargo_metadata_stdout": metadata.get("stdout_ref"),
        "cargo_build_stdout": build.get("stdout_ref"),
    })


__all__ = [
    "PROJECT_RUST_CARGO_TOPOLOGY_SCOPE",
    "materialize_project_rust_cargo_topology",
    "reopen_project_rust_cargo_topology",
]
