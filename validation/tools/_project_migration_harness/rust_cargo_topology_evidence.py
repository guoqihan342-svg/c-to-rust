from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .candidate_cargo_fact_binding import reopen_candidate_cargo_fact_payloads
from .gate_evidence import (
    read_content_addressed_json,
    require_content_addressed_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError
from .project_candidate_verification_receipt import (
    reopen_candidate_project_verification,
)
from .project_interface_validation_domain import (
    reopen_project_interface_validation_domain,
)
from .rust_cargo_topology_witness import build_rust_cargo_topology_witness


RUST_CARGO_TOPOLOGY_SCOPE = "rust-cargo-topology-witness"
_CLAIM_BOUNDARY = {
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_RECEIPT_KEYS = {
    "schema_version", "artifact_kind", "status",
    "validation_domain", "candidate_project_verification", "witness",
    "claim_boundary", "receipt_sha256",
}


def materialize_rust_cargo_topology_evidence(
    *, ledger_path: Path, out_root: Path,
    validation_domain: Mapping[str, Any], repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    environment: Mapping[str, str] | None = None, resolver: Any = None,
    runner: Any = None,
) -> dict[str, Any]:
    database = _fixed_ledger_path(ledger_path)
    root = _fixed_out_root(database, out_root)
    reference = _reference(validation_domain)
    receipt = _derive(
        database, reference, repo_root=repo_root, artifact_root=artifact_root,
        harness_root=harness_root, quarantine_root=quarantine_root,
        environment=environment, resolver=resolver, runner=runner,
    )
    evidence_ref = write_content_addressed_json(
        root, RUST_CARGO_TOPOLOGY_SCOPE, receipt,
    )
    return {"receipt": receipt, "reference": evidence_ref}


def reopen_rust_cargo_topology_evidence(
    ledger_path: Path, reference: Mapping[str, Any], *,
    repo_root: Path, artifact_root: Path, harness_root: Path,
    quarantine_root: Path, environment: Mapping[str, str] | None = None,
    resolver: Any = None, runner: Any = None,
) -> dict[str, Any]:
    database = _fixed_ledger_path(ledger_path)
    bound = _reference(reference)
    stored = read_content_addressed_json(
        database, bound["path"], bound["sha256"],
    )
    if len(canonical_json_bytes(stored)) != bound["size_bytes"]:
        raise LedgerError("Rust Cargo topology evidence size drifted")
    validated = _validate_receipt(stored)
    expected = _derive(
        database,
        validated["validation_domain"]["reference"],
        repo_root=repo_root, artifact_root=artifact_root,
        harness_root=harness_root, quarantine_root=quarantine_root,
        environment=environment, resolver=resolver, runner=runner,
    )
    if validated != expected:
        raise LedgerError("Rust Cargo topology evidence drifted")
    return validated


def _derive(
    database: Path, domain_reference: Mapping[str, Any], *, repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    environment: Mapping[str, str] | None, resolver: Any, runner: Any,
) -> dict[str, Any]:
    domain = reopen_project_interface_validation_domain(
        database, domain_reference, repo_root=repo_root,
        artifact_root=artifact_root, harness_root=harness_root,
        quarantine_root=quarantine_root, environment=environment,
        resolver=resolver, runner=runner,
    )
    b2a_reference = domain["candidate_project_verification"]["reference"]
    b2a = reopen_candidate_project_verification(
        database, b2a_reference, quarantine_root=quarantine_root,
        run_id=domain["run"]["run_id"],
        candidate_set_sha256=domain["candidate_set"]["sha256"],
        rust_project_ir_sha256=domain["rust_project_ir"]["ir_sha256"],
        rust_project_interface_sha256=domain["rust_project_ir"]["interface_sha256"],
    )
    if b2a.get("status") != "candidate-verified":
        raise LedgerError("Rust Cargo topology requires candidate-verified b2a")
    payloads = reopen_candidate_cargo_fact_payloads(
        database, b2a["cargo_fact_evidence"],
        execution=b2a["execution"], observations=b2a["cargo_observations"],
    )
    witness = build_rust_cargo_topology_witness(
        payloads["cargo_metadata"], payloads["compiler_artifacts"],
    )
    core = {
        "schema_version": 1,
        "artifact_kind": "rust-cargo-topology-witness-receipt",
        "status": witness["status"],
        "validation_domain": {
            "reference": dict(domain_reference),
            "domain_sha256": domain["domain_sha256"],
        },
        "candidate_project_verification": {
            "reference": dict(b2a_reference),
            "verification_context_sha256": b2a["verification_context_sha256"],
            "generation_sha256": b2a["materialization"]["generation"]["sha256"],
            "cargo_fact_binding_sha256": payloads["binding"]["binding_sha256"],
        },
        "witness": witness,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return _validate_receipt({**core, "receipt_sha256": content_sha256(core)})


def _validate_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        raise ValueError("rust_cargo_topology_receipt_schema_invalid")
    receipt = dict(value)
    domain = receipt.get("validation_domain")
    source = receipt.get("candidate_project_verification")
    witness = receipt.get("witness")
    if not isinstance(domain, Mapping) or set(domain) != {
        "reference", "domain_sha256",
    }:
        raise ValueError("rust_cargo_topology_receipt_domain_invalid")
    _reference(domain["reference"])
    if not is_sha256(domain.get("domain_sha256")):
        raise ValueError("rust_cargo_topology_receipt_domain_invalid")
    if not isinstance(source, Mapping) or set(source) != {
        "reference", "verification_context_sha256", "generation_sha256",
        "cargo_fact_binding_sha256",
    }:
        raise ValueError("rust_cargo_topology_receipt_source_invalid")
    _reference(source["reference"])
    if any(not is_sha256(source.get(key)) for key in (
        "verification_context_sha256", "generation_sha256",
        "cargo_fact_binding_sha256",
    )):
        raise ValueError("rust_cargo_topology_receipt_source_invalid")
    core = {key: receipt[key] for key in receipt if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind")
        != "rust-cargo-topology-witness-receipt"
        or not isinstance(witness, Mapping)
        or receipt.get("status") != witness.get("status")
        or receipt.get("status") not in {"ready", "blocked"}
        or receipt.get("claim_boundary") != _CLAIM_BOUNDARY
        or receipt.get("receipt_sha256") != content_sha256(core)
    ):
        raise ValueError("rust_cargo_topology_receipt_invalid")
    return receipt


def _reference(value: Any) -> dict[str, Any]:
    try:
        require_content_addressed_reference(value)
    except (KeyError, TypeError, ValueError, LedgerError) as error:
        raise ValueError("rust_cargo_topology_reference_invalid") from error
    if type(value.get("size_bytes")) is not int or value["size_bytes"] <= 0:
        raise ValueError("rust_cargo_topology_reference_invalid")
    return {
        "path": str(value["path"]), "sha256": str(value["sha256"]),
        "size_bytes": value["size_bytes"],
    }


def _fixed_ledger_path(value: Path) -> Path:
    database = Path(value).resolve(strict=True)
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise LedgerError("Rust Cargo topology requires the fixed ledger path")
    return database


def _fixed_out_root(database: Path, value: Path) -> Path:
    root = Path(value).resolve(strict=True)
    if root != database.parent.parent:
        raise LedgerError("Rust Cargo topology output root is not ledger-bound")
    return root


__all__ = [
    "RUST_CARGO_TOPOLOGY_SCOPE",
    "materialize_rust_cargo_topology_evidence",
    "reopen_rust_cargo_topology_evidence",
]
