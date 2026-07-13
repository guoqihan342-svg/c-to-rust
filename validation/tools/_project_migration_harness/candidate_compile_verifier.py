from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .accepted_candidates import candidate_set_descriptors
from .artifacts import content_sha256
from .candidate_compile_evidence import compile_observation_payload
from .gate_authority import candidate_authority, candidate_verdict_payload
from .gate_candidate_sets import candidate_set_manifest, candidate_set_members
from .gate_diagnostics import normalize_gate_evidence
from .gate_evidence import write_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .ledger_artifact_binding import candidate_source_reference, read_ledger_artifact
from .ledger_candidate_state import candidate_row
from .ledger_run_contract import load_migration_contract
from .project_verification import run_cargo_generation_gates
from .quarantine_generation import materialize_quarantine_generation


def verify_candidate_compile(
    *, ledger: ProjectLedger, run_id: str, unit_id: str,
    candidate_artifact_id: str,
    candidate_root: Path, candidate_root_rel: str, quarantine_root: Path,
    runtime_root: Path, out_root: Path, out_root_rel: str,
    timeout_seconds: int = 300,
    verification_scope: str = "wave-provisional",
) -> dict[str, Any]:
    with ledger.connect() as connection:
        _run_contract, migration_manifest = load_migration_contract(
            ledger.path, connection, run_id,
        )
    candidate_set = ledger.bind_verification_candidate_set(
        run_id=run_id, scope=verification_scope,
    )
    with ledger.connect() as connection:
        cohort_manifest = candidate_set_manifest(connection, run_id, candidate_set)
    candidate = _require_target_member(
        ledger, run_id, unit_id, candidate_artifact_id, candidate_set,
    )
    candidate_sha = str(candidate["content_sha256"])
    source_reference = candidate_source_reference(ledger.path, candidate)
    _source, repository_root = read_ledger_artifact(ledger.path, source_reference)
    descriptors = candidate_set_descriptors(
        ledger, run_id=run_id, out_root_rel=candidate_root_rel,
        candidate_set_sha256=candidate_set,
    )
    materialized = materialize_quarantine_generation(
        migration_manifest, descriptors, candidate_root, quarantine_root,
        candidate_set, cohort_manifest,
    )
    if materialized.get("status") != "materialized":
        return _blocked(
            run_id, unit_id, candidate_artifact_id, candidate_set,
            "quarantine_generation_failed", materialized,
        )
    generation = materialized.get("generation")
    if not isinstance(generation, Mapping):
        raise LedgerError("quarantine generation report is invalid")
    generation_sha = str(generation.get("sha256", ""))
    generation_path = quarantine_root.joinpath(*Path(str(generation.get("path", ""))).parts)
    execution = run_cargo_generation_gates(
        generation_path,
        runtime_root=runtime_root,
        timeout_seconds=timeout_seconds,
    )
    if execution.get("status") == "blocked":
        return _blocked(
            run_id, unit_id, candidate_artifact_id, candidate_set,
            _reason_code(execution, "candidate_compile_environment_blocked"),
            {"materialization": materialized, "execution": execution},
        )
    check = _cargo_check(execution)
    gate_status = "passed" if check.get("status") == "passed" else "failed"
    diagnostics = [] if gate_status == "passed" else _target_diagnostics(check, candidate_sha)
    if gate_status == "failed" and not diagnostics:
        return {
            "schema_version": 1,
            "status": "project-repair-required",
            "run_id": run_id,
            "unit_id": unit_id,
            "candidate_artifact_id": candidate_artifact_id,
            "candidate_set_sha256": candidate_set,
            "reason_code": "candidate_compile_failure_not_attributable",
            "materialization": materialized,
            "execution": execution,
            "candidate_gate_recorded": False,
            "semantic_gate": False,
        }
    try:
        quarantine_evidence = {
            "generation_sha256": generation_sha,
            "quarantine_manifest": _repository_reference(
                quarantine_root, materialized.get("manifest_ref"), repository_root,
                ledger.path,
            ),
            "generation_manifest": _repository_reference(
                quarantine_root, materialized.get("generation_manifest_ref"),
                repository_root, ledger.path,
            ),
        }
        observation = compile_observation_payload(
            run_id=run_id, unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            candidate_sha256=candidate_sha,
            candidate_set_sha256=candidate_set,
            candidate_source=source_reference,
            run_contract=_run_contract,
            quarantine=quarantine_evidence,
            execution=execution,
        )
    except LedgerError:
        return _blocked(
            run_id, unit_id, candidate_artifact_id, candidate_set,
            "candidate_compile_execution_untrusted",
            {"materialization": materialized, "execution": execution},
        )
    normalized = normalize_gate_evidence(
        gate_family="compile", status=gate_status,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=candidate_sha, diagnostics=diagnostics,
    )
    raw_ref = _write_reference(
        out_root, out_root_rel, "raw/candidate/compile", observation,
    )
    verdict = candidate_verdict_payload(
        run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=candidate_sha,
        gate_family="compile", status=gate_status,
        diagnostics=normalized["diagnostics"],
        candidate_set_sha256=candidate_set,
        source_evidence=[raw_ref],
    )
    verdict_ref = _write_reference(
        out_root, out_root_rel, "candidate/compile", verdict,
    )
    record_id = "host-compile-" + content_sha256({
        "run_id": run_id, "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_set_sha256": candidate_set,
        "observation_sha256": raw_ref["sha256"],
    })[:24]
    ledger._record_derived_verification(
        record_id=record_id, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        kind="verifier", status=gate_status,
        verifier_id=candidate_authority("compile"),
        evidence_path=str(verdict_ref["path"]),
        evidence_sha256=str(verdict_ref["sha256"]),
        gate_family="compile",
        metadata={
            "candidate_set_sha256": candidate_set,
            "generation_sha256": generation_sha,
            "observation_sha256": raw_ref["sha256"],
        },
    )
    if gate_status == "failed":
        ledger.mark_verification_failed(
            run_id=run_id, unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            failed_record_id=record_id,
        )
    return {
        "schema_version": 1,
        "status": "passed" if gate_status == "passed" else "failed",
        "gate_status": gate_status,
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_set_sha256": candidate_set,
        "verification_scope": verification_scope,
        "generation_sha256": generation_sha,
        "record_id": record_id,
        "observation": raw_ref,
        "verdict": verdict_ref,
        "materialization": materialized,
        "execution": execution,
        "candidate_gate_recorded": True,
        "semantic_gate": False,
    }


def _require_target_member(
    ledger: ProjectLedger, run_id: str, unit_id: str,
    artifact_id: str, candidate_set: str,
) -> Mapping[str, Any]:
    with ledger.connect() as connection:
        candidate = candidate_row(connection, run_id, unit_id, artifact_id, active=True)
        members = candidate_set_members(connection, run_id, candidate_set)
    digest = str(candidate["content_sha256"])
    if not any(
        item["unit_id"] == unit_id and item["artifact_id"] == artifact_id
        and item["content_sha256"] == digest for item in members
    ):
        raise LedgerError("compile target is outside the verification candidate set")
    return dict(candidate)


def _repository_reference(
    quarantine_root: Path, value: Any, repository_root: Path, ledger_path: Path,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise LedgerError("quarantine evidence reference is invalid")
    relative = PurePosixPath(str(value["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise LedgerError("quarantine evidence path is invalid")
    target = quarantine_root.resolve(strict=True).joinpath(*relative.parts).resolve(strict=True)
    try:
        path = target.relative_to(repository_root.resolve(strict=True)).as_posix()
    except ValueError as error:
        raise LedgerError("quarantine evidence is outside the repository") from error
    reference = {
        "path": path,
        "sha256": str(value["sha256"]),
        "size_bytes": value["size_bytes"],
    }
    read_ledger_artifact(ledger_path, reference)
    return reference


def _cargo_check(execution: Mapping[str, Any]) -> Mapping[str, Any]:
    checks = execution.get("checks")
    values = [
        item for item in checks or []
        if isinstance(item, Mapping)
        and isinstance(item.get("command"), list)
        and item["command"][:2] == ["cargo", "check"]
    ]
    if len(values) != 1:
        raise LedgerError("candidate compile execution has no unique cargo check")
    return values[0]


def _target_diagnostics(check: Mapping[str, Any], candidate_sha: str) -> list[dict[str, Any]]:
    path = f"src/unit_{candidate_sha}.rs"
    return [
        dict(item) for item in check.get("diagnostics", [])
        if isinstance(item, Mapping) and item.get("file") == path
    ][:32]


def _write_reference(
    out_root: Path, out_root_rel: str, scope: str, payload: Mapping[str, Any],
) -> dict[str, Any]:
    reference = write_content_addressed_json(out_root, scope, payload)
    return {**reference, "path": f"{out_root_rel}/{reference['path']}"}


def _reason_code(value: Mapping[str, Any], fallback: str) -> str:
    diagnostics = value.get("diagnostics")
    if isinstance(diagnostics, list) and diagnostics and isinstance(diagnostics[0], Mapping):
        code = diagnostics[0].get("code")
        if isinstance(code, str) and code:
            return code
    sandbox = value.get("sandbox")
    if isinstance(sandbox, Mapping) and isinstance(sandbox.get("reason_code"), str):
        return str(sandbox["reason_code"])
    return fallback


def _blocked(
    run_id: str, unit_id: str, artifact_id: str, candidate_set: str,
    reason_code: str, detail: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": "blocked", "run_id": run_id,
        "unit_id": unit_id, "candidate_artifact_id": artifact_id,
        "candidate_set_sha256": candidate_set, "reason_code": reason_code,
        "detail": dict(detail), "candidate_gate_recorded": False,
        "semantic_gate": False,
    }


__all__ = ["verify_candidate_compile"]
