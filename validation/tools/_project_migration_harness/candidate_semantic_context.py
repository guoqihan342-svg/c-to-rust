from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .artifacts import canonical_json_bytes
from .candidate_compile_evidence import derive_compile_status, verify_compile_bindings
from .candidate_admission_ledger import require_semantic_candidate_admission
from .gate_authority import candidate_authority, validate_candidate_verdict
from .gate_candidate_sets import candidate_set_manifest
from .gate_evidence import (
    read_content_addressed_json,
    require_candidate_raw_reference,
)
from .ledger_artifact_binding import candidate_source_reference, read_ledger_artifact
from .ledger_candidate_state import candidate_row, latest_candidate_records
from .ledger_run_contract import load_migration_contract
from .ledger_security import LedgerError


def current_semantic_context(
    ledger: Any, run_id: str, unit_id: str, artifact_id: str, scope: str,
) -> tuple[dict[str, Any], Any]:
    candidate_set = ledger.bind_verification_candidate_set(
        run_id=run_id, scope=scope,
    )
    with ledger.connect() as connection:
        return current_semantic_context_bound(
            ledger, connection, run_id, unit_id, artifact_id,
            candidate_set, scope,
        )


def current_semantic_context_bound(
    ledger: Any, connection: Any, run_id: str, unit_id: str,
    artifact_id: str, candidate_set: str, scope: str,
) -> tuple[dict[str, Any], Any]:
    manifest = candidate_set_manifest(connection, run_id, candidate_set)
    candidate = dict(candidate_row(
        connection, run_id, unit_id, artifact_id, active=True,
    ))
    require_semantic_candidate_admission(
        ledger, connection, run_id, candidate,
    )
    unit = connection.execute(
        "select group_id from migration_units where run_id=? and unit_id=?",
        (run_id, unit_id),
    ).fetchone()
    contract, _integration = load_migration_contract(
        ledger.path, connection, run_id,
    )
    records = latest_candidate_records(
        connection, run_id, unit_id, artifact_id,
    )
    compile_rows = [row for row in records if row["gate_family"] == "compile"]
    if (
        len(compile_rows) != 1
        or compile_rows[0]["status"] != "passed"
        or compile_rows[0]["kind"] != "verifier"
        or compile_rows[0]["verifier_id"] != candidate_authority("compile")
    ):
        raise LedgerError(
            "candidate semantic runner requires the latest compile pass"
        )
    compile_row = compile_rows[0]
    verdict = read_content_addressed_json(
        ledger.path, str(compile_row["evidence_path"]),
        str(compile_row["evidence_sha256"]),
    )
    validate_candidate_verdict(
        verdict, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=artifact_id,
        candidate_sha256=str(candidate["content_sha256"]),
        gate_family="compile", candidate_set_sha256=candidate_set,
        status="passed", verifier_id=candidate_authority("compile"),
        kind="verifier",
    )
    source_values = verdict.get("source_evidence")
    if not isinstance(source_values, list) or len(source_values) != 1:
        raise LedgerError(
            "candidate compile verdict has no unique raw observation"
        )
    compile_raw_ref = source_values[0]
    if not isinstance(compile_raw_ref, Mapping):
        raise LedgerError(
            "candidate compile raw observation reference is invalid"
        )
    require_candidate_raw_reference(compile_raw_ref, "compile")
    compile_raw = read_content_addressed_json(
        ledger.path, str(compile_raw_ref["path"]),
        str(compile_raw_ref["sha256"]),
    )
    actual = derive_compile_status(
        compile_raw, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=artifact_id,
        candidate_sha256=str(candidate["content_sha256"]),
        candidate_set_sha256=candidate_set,
    )
    verify_compile_bindings(
        compile_raw, ledger_path=ledger.path, connection=connection,
    )
    if actual != "passed" or unit is None or manifest["scope"] != scope:
        raise LedgerError("candidate semantic compile context is invalid")
    source = candidate_source_reference(ledger.path, candidate)
    _data, repository_root = read_ledger_artifact(ledger.path, source)
    worker_request = _worker_request_reference(
        ledger.path, candidate, repository_root,
    )
    contract_payload = compile_raw.get("sandbox", {}).get("contract", {})
    quarantine = compile_raw.get("quarantine", {})
    context = {
        "run_id": run_id, "group_id": str(unit["group_id"]),
        "unit_id": unit_id, "candidate_artifact_id": artifact_id,
        "candidate_sha256": str(candidate["content_sha256"]),
        "candidate_set_sha256": candidate_set, "candidate_source": source,
        "run_context_sha256": str(contract["context_sha256"]),
        "compile_verdict": {
            "path": str(compile_row["evidence_path"]),
            "sha256": str(compile_row["evidence_sha256"]),
            "size_bytes": len(canonical_json_bytes(verdict)),
        },
        "compile_observation": dict(compile_raw_ref),
        "generation_sha256": str(quarantine.get("generation_sha256")),
        "toolchain_sha256": str(contract_payload.get("toolchain_sha256")),
        "worker_request": worker_request,
    }
    return context, repository_root


def _worker_request_reference(
    ledger_path: Any, candidate: Mapping[str, Any], repository_root: Any,
) -> dict[str, Any] | None:
    try:
        metadata = json.loads(str(candidate.get("attempt_metadata_json", "{}")))
    except json.JSONDecodeError as error:
        raise LedgerError("candidate worker request metadata is invalid") from error
    if not isinstance(metadata, dict):
        raise LedgerError("candidate worker request metadata is invalid")
    path = metadata.get("request_path")
    digest = metadata.get("request_sha256")
    if path is None and digest is None:
        return None
    if not isinstance(path, str) or not isinstance(digest, str):
        raise LedgerError("candidate worker request binding is incomplete")
    data, root = read_ledger_artifact(
        ledger_path, {"path": path, "sha256": digest},
    )
    if root != repository_root or not data:
        raise LedgerError("candidate worker request repository binding drifted")
    return {"path": path, "sha256": digest, "size_bytes": len(data)}


__all__ = ["current_semantic_context", "current_semantic_context_bound"]
