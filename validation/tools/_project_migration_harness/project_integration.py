from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .accepted_candidates import accepted_candidate_descriptors
from .artifacts import canonical_json_bytes, content_sha256, write_json_artifact
from .integration import integrate_rust_project_ir
from .ledger import LedgerError, ProjectLedger
from .ledger_run_contract import load_migration_contract
from .project_rust_ir import derive_bound_project_ir, persist_project_ir


def integrate_verified_project(
    migration_manifest: Mapping[str, Any], *, ledger: ProjectLedger,
    run_id: str, candidate_root: Path, candidate_root_rel: str,
    project_root: Path,
) -> dict[str, Any]:
    with ledger.connect() as connection:
        migration_contract, authoritative_manifest = load_migration_contract(
            ledger.path, connection, run_id,
        )
    if canonical_json_bytes(migration_manifest) != canonical_json_bytes(authoritative_manifest):
        raise LedgerError("integration manifest does not match the immutable run contract")
    descriptors = accepted_candidate_descriptors(
        ledger, run_id=run_id, out_root_rel=candidate_root_rel
    )
    rust_project_ir = derive_bound_project_ir(
        migration_contract=migration_contract,
        migration_manifest=authoritative_manifest,
        candidate_descriptors=descriptors,
        artifact_root=candidate_root,
    )
    ir_reference = persist_project_ir(candidate_root, "integration", rust_project_ir)
    result = integrate_rust_project_ir(rust_project_ir, candidate_root, project_root)
    candidate_set_sha256 = ledger.bind_current_candidate_set(run_id=run_id)
    report = {
        **result,
        "run_id": run_id,
        "candidate_set_sha256": candidate_set_sha256,
        "candidate_descriptor_sha256": content_sha256(descriptors),
        "candidate_count": len(descriptors),
        "rust_project_ir": ir_reference,
        "rust_project_ir_sha256": rust_project_ir["ir_sha256"],
        "rust_project_interface_sha256": rust_project_ir["interface_sha256"],
        "rust_project_ir_completeness": dict(
            rust_project_ir["interface_completeness"]
        ),
        "semantic_gate": False,
        "proof_boundary": "validated RustProjectIR Cargo reconstruction only; project gates not yet run",
    }
    write_json_artifact(candidate_root, "integration/latest-integration.json", report)
    return report


__all__ = ["integrate_verified_project"]
