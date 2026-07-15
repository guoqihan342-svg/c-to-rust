from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .clang_toolchain_binding import reopen_clang_toolchain_binding
from .gate_candidate_sets import candidate_set_manifest
from .gate_evidence import read_content_addressed_json, write_content_addressed_json
from .ledger import ProjectLedger
from .ledger_run_contract import load_migration_contract
from .ledger_security import LedgerError
from .project_candidate_verification_receipt import (
    reopen_candidate_project_verification,
)
from .project_interface_domain_sources import reopen_project_interface_source_domain
from .project_interface_validation_domain_projection import (
    bind_contract_dag,
    candidate_domain,
    clang_plan_projection,
    domain_payload,
)
from .project_interface_validation_domain_contract import (
    DOMAIN_SCOPE,
    artifact_reference,
    validate_project_interface_validation_domain,
)
from .project_repair_worker_request import read_bound_rust_project_ir


_DOMAIN_KEYS = (
    "run_id", "run_context_sha256", "dag_sha256", "integration_manifest",
    "candidate_set_sha256", "candidate_set_manifest_sha256",
    "rust_project_ir_sha256", "rust_project_interface_sha256",
    "rust_project_binding_sha256", "candidate_domain_context_sha256",
)


def materialize_project_interface_validation_domain(
    *, ledger_path: Path, run_id: str, candidate_set_sha256: str,
    base_rust_project_ir: Mapping[str, Any],
    candidate_project_verification: Mapping[str, Any],
    clang_toolchain_receipt: Mapping[str, Any], repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    out_root: Path, environment: Mapping[str, str] | None = None,
    resolver: Any = None, runner: Any = None,
) -> dict[str, Any]:
    database = _fixed_ledger_path(ledger_path)
    _fixed_out_root(database, out_root)
    payload = _derive(
        database=database, run_id=run_id,
        candidate_set_sha256=candidate_set_sha256,
        base_rust_project_ir=base_rust_project_ir,
        candidate_project_verification=candidate_project_verification,
        clang_toolchain_receipt=clang_toolchain_receipt,
        repo_root=repo_root, artifact_root=artifact_root,
        harness_root=harness_root, quarantine_root=quarantine_root,
        environment=environment, resolver=resolver, runner=runner,
    )
    reference = write_content_addressed_json(out_root, DOMAIN_SCOPE, payload)
    return {"domain": payload, "reference": reference}


def reopen_project_interface_validation_domain(
    ledger_path: Path, reference: Mapping[str, Any], *, repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    environment: Mapping[str, str] | None = None, resolver: Any = None,
    runner: Any = None,
) -> dict[str, Any]:
    database = _fixed_ledger_path(ledger_path)
    bound = artifact_reference(reference)
    payload = read_content_addressed_json(
        database, bound["path"], bound["sha256"],
    )
    if len(canonical_json_bytes(payload)) != bound["size_bytes"]:
        raise LedgerError("interface validation domain size drifted")
    current = validate_project_interface_validation_domain(payload)
    expected = _derive(
        database=database, run_id=current["run"]["run_id"],
        candidate_set_sha256=current["candidate_set"]["sha256"],
        base_rust_project_ir=current["rust_project_ir"]["reference"],
        candidate_project_verification=current[
            "candidate_project_verification"
        ]["reference"],
        clang_toolchain_receipt=current["clang_toolchain"]["receipt"],
        repo_root=repo_root, artifact_root=artifact_root,
        harness_root=harness_root, quarantine_root=quarantine_root,
        environment=environment, resolver=resolver, runner=runner,
    )
    if current != expected:
        raise LedgerError("interface validation domain drifted")
    return current


def _derive(
    *, database: Path, run_id: str, candidate_set_sha256: str,
    base_rust_project_ir: Mapping[str, Any],
    candidate_project_verification: Mapping[str, Any],
    clang_toolchain_receipt: Mapping[str, Any], repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    environment: Mapping[str, str] | None, resolver: Any, runner: Any,
) -> dict[str, Any]:
    ir_reference = artifact_reference(base_rust_project_ir)
    b2a_reference = artifact_reference(candidate_project_verification)
    ir = read_bound_rust_project_ir(harness_root, ir_reference)
    source_domain, build_irs = reopen_project_interface_source_domain(
        ir, repo_root=repo_root, artifact_root=artifact_root,
    )
    ledger = ProjectLedger(database, read_only=True)
    with ledger.connect() as connection:
        connection.execute("BEGIN")
        try:
            contract, _ = load_migration_contract(database, connection, run_id)
            candidate_manifest = candidate_set_manifest(
                connection, run_id, candidate_set_sha256,
            )
        finally:
            connection.rollback()
    bind_contract_dag(contract, source_domain)
    domain = candidate_domain(
        run_id, contract, ir, source_domain, candidate_set_sha256,
        candidate_manifest, artifact_root,
    )
    b2a = reopen_candidate_project_verification(
        database, b2a_reference, quarantine_root=quarantine_root,
        run_id=run_id, candidate_set_sha256=candidate_set_sha256,
        rust_project_ir_sha256=ir["ir_sha256"],
        rust_project_interface_sha256=ir["interface_sha256"],
    )
    if b2a.get("status") != "candidate-verified" or any(
        b2a.get(key) != domain[key] for key in _DOMAIN_KEYS
    ):
        raise LedgerError("candidate b2a receipt does not bind the validation domain")
    toolchain = reopen_clang_toolchain_binding(
        database, clang_toolchain_receipt, environment=environment,
        resolver=resolver, runner=runner,
    )
    plans = clang_plan_projection(build_irs, toolchain["portable_binding"])
    payload = domain_payload(
        contract, ir_reference, ir, source_domain, candidate_manifest,
        candidate_set_sha256, b2a_reference, b2a, toolchain, plans,
    )
    return validate_project_interface_validation_domain(payload)


def _fixed_ledger_path(value: Path) -> Path:
    database = Path(value).resolve(strict=True)
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise LedgerError("interface validation requires the fixed ledger state path")
    return database


def _fixed_out_root(database: Path, out_root: Path) -> None:
    if Path(out_root).resolve() != database.parent.parent:
        raise LedgerError("interface validation output root is not ledger-bound")


__all__ = [
    "materialize_project_interface_validation_domain",
    "reopen_project_interface_validation_domain",
]
