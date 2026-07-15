from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger_security import LedgerError
from .orchestration_facts import read_artifact_reference
from .project_candidate_verification_receipt import (
    reopen_candidate_project_verification,
)
from .project_interface_validation_domain import (
    reopen_project_interface_validation_domain,
)
from .project_interface_validation_domain_contract import artifact_reference
from .project_repair_worker_request import read_bound_rust_project_ir
from .rust_cargo_topology_evidence import reopen_rust_cargo_topology_evidence
from .rust_project_ir_validation import reopen_rust_project_ir_bindings


def reopen_rust_source_pre_cfg_context(
    *, ledger_path: Path, validation_domain: Mapping[str, Any],
    cargo_topology_evidence: Mapping[str, Any], repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    environment: Mapping[str, str] | None = None,
    resolver: Any = None, domain_runner: Any = None,
) -> dict[str, Any]:
    database = Path(ledger_path).resolve(strict=True)
    domain_reference = artifact_reference(validation_domain)
    topology_reference = artifact_reference(cargo_topology_evidence)
    domain = reopen_project_interface_validation_domain(
        database, domain_reference, repo_root=repo_root,
        artifact_root=artifact_root, harness_root=harness_root,
        quarantine_root=quarantine_root, environment=environment,
        resolver=resolver, runner=domain_runner,
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
        raise LedgerError("Rust source witness requires candidate-verified b2a")
    topology = reopen_rust_cargo_topology_evidence(
        database, topology_reference, repo_root=repo_root,
        artifact_root=artifact_root, harness_root=harness_root,
        quarantine_root=quarantine_root, environment=environment,
        resolver=resolver, runner=domain_runner,
    )
    _bind_parent_receipts(
        domain_reference, domain, b2a_reference, b2a, topology,
    )
    ir = read_bound_rust_project_ir(
        harness_root, domain["rust_project_ir"]["reference"],
    )
    reopen_rust_project_ir_bindings(ir, artifact_root)
    sources = _candidate_sources(ir, artifact_root)
    if len(sources) != domain["source_domain"]["candidate_count"]:
        raise LedgerError("Rust source witness candidate coverage drifted")
    return {
        "domain_reference": domain_reference,
        "domain": domain,
        "b2a_reference": b2a_reference,
        "b2a": b2a,
        "topology_reference": topology_reference,
        "topology": topology,
        "sources": sources,
    }


def _bind_parent_receipts(
    domain_reference: Mapping[str, Any], domain: Mapping[str, Any],
    b2a_reference: Mapping[str, Any], b2a: Mapping[str, Any],
    topology: Mapping[str, Any],
) -> None:
    topology_source = topology.get("candidate_project_verification")
    if (
        topology.get("validation_domain", {}).get("reference")
        != dict(domain_reference)
        or not isinstance(topology_source, Mapping)
        or topology_source.get("reference") != dict(b2a_reference)
        or topology_source.get("verification_context_sha256")
        != b2a["verification_context_sha256"]
        or topology_source.get("generation_sha256")
        != b2a["materialization"]["generation"]["sha256"]
        or domain["candidate_project_verification"]["verification_context_sha256"]
        != b2a["verification_context_sha256"]
    ):
        raise LedgerError("Rust source witness parent receipt binding drifted")


def _candidate_sources(
    ir: Mapping[str, Any], artifact_root: Path,
) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for binding in ir["bindings"]["candidates"]:
        unit_id = str(binding["unit_id"])
        reference = binding["source"]
        source = read_artifact_reference(artifact_root, reference)
        if unit_id in seen or len(source) != reference["size_bytes"]:
            raise LedgerError("Rust source witness candidate binding drifted")
        seen.add(unit_id)
        result.append({
            "unit_id": unit_id,
            "artifact_id": str(binding["artifact_id"]),
            "source_sha256": str(reference["sha256"]),
            "source_size_bytes": len(source),
            "source": source,
        })
    expected = sorted(result, key=lambda item: (item["unit_id"], item["artifact_id"]))
    if not result or result != expected:
        raise LedgerError("Rust source witness candidate order drifted")
    return result


__all__ = ["reopen_rust_source_pre_cfg_context"]
