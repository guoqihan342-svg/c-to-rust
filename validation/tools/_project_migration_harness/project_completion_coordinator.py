from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import content_sha256, write_json_artifact
from .candidate_compile_verifier import verify_candidate_compile
from .candidate_final_verifier import verify_candidate_final
from .candidate_semantic_evidence import revalidate_candidate_semantic_verdict
from .candidate_semantic_runners import (
    run_abi_layout_candidate,
    run_negative_candidate,
    run_oracle_replay_diff_candidate,
    run_unsafe_alias_candidate,
)
from .controller_project_gates import complete_verified_project
from .gate_authority import CANDIDATE_REQUIRED_GATES
from .gate_candidate_sets import candidate_set_members
from .gate_evidence import read_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .ledger_candidate_state import latest_candidate_records
from .ledger_run_contract import load_migration_contract
from .project_cargo_verifier import verify_project_cargo
from .project_completion_repair_phase import execute_project_repair_completion_step
from .project_host_gates import _record_host_project_final
from .project_integration import integrate_verified_project
from .project_integration_verifier import verify_integrated_project


SEMANTIC_RUNNERS = (
    "oracle-replay-diff", "negative", "unsafe-alias", "abi-layout",
)


def resume_project_completion(
    *, ledger: ProjectLedger, run_id: str, harness_root: Path,
    timeout_seconds: int = 300, preflight_timeout_seconds: int = 60,
    logical_model: str = "GLM-5.1", resolved_model: str = "zai/glm-5.1",
) -> dict[str, Any]:
    paths = _completion_paths(ledger, harness_root)
    try:
        candidate_set = ledger.bind_verification_candidate_set(
            run_id=run_id, scope="project-final",
        )
    except LedgerError as error:
        return _result(
            paths, run_id, "waiting", "awaiting-all-last-good", [str(error)],
        )
    with ledger.connect() as connection:
        members = candidate_set_members(connection, run_id, candidate_set)
        _contract, migration_manifest = load_migration_contract(
            ledger.path, connection, run_id,
        )
    for member in members:
        compile_result = verify_candidate_compile(
            ledger=ledger,
            run_id=run_id,
            unit_id=member["unit_id"],
            candidate_artifact_id=member["artifact_id"],
            candidate_root=paths["out_root"],
            candidate_root_rel=paths["out_root_rel"],
            quarantine_root=paths["quarantine_root"],
            runtime_root=paths["runtime_root"],
            out_root=paths["out_root"],
            out_root_rel=paths["out_root_rel"],
            timeout_seconds=timeout_seconds,
            verification_scope="project-final",
        )
        if compile_result.get("status") != "passed":
            return _result(
                paths, run_id, str(compile_result.get("status", "blocked")),
                "project-final-candidate-compile", [], candidate_set,
            )
    for member in members:
        for family in SEMANTIC_RUNNERS:
            runner = _semantic_runner(family)
            semantic = runner(
                ledger=ledger,
                out_root=paths["out_root"],
                out_root_rel=paths["out_root_rel"],
                run_id=run_id,
                unit_id=member["unit_id"],
                candidate_artifact_id=member["artifact_id"],
                verification_scope="project-final",
            )
            if semantic.get("status") != "passed":
                reason = str(
                    semantic.get("reason_code")
                    or semantic.get("gate_status")
                    or "semantic-gate-did-not-pass"
                )
                return _result(
                    paths, run_id, str(semantic.get("status", "blocked")),
                    f"project-final-{family}",
                    [f"{member['unit_id']}:{family}:{reason}"], candidate_set,
                )
    missing = _missing_candidate_semantic_gates(ledger, run_id, candidate_set, members)
    if missing:
        return _result(
            paths, run_id, "blocked", "project-final-semantic-runners",
            missing, candidate_set,
        )
    for member in members:
        verify_candidate_final(
            ledger=ledger,
            out_root=paths["out_root"],
            out_root_rel=paths["out_root_rel"],
            run_id=run_id,
            unit_id=member["unit_id"],
            candidate_artifact_id=member["artifact_id"],
            verification_scope="project-final",
        )
    integration = integrate_verified_project(
        migration_manifest,
        ledger=ledger,
        run_id=run_id,
        candidate_root=paths["out_root"],
        candidate_root_rel=paths["out_root_rel"],
        project_root=paths["project_root"],
    )
    if integration.get("status") != "integrated":
        if integration.get("stage") == "project-interface-repair":
            repair_step = execute_project_repair_completion_step(
                migration_manifest, initial_integration=integration,
                ledger=ledger, run_id=run_id, harness_root=harness_root,
                out_root=paths["out_root"], out_root_rel=paths["out_root_rel"],
                project_root=paths["project_root"], logical_model=logical_model,
                resolved_model=resolved_model, timeout_seconds=timeout_seconds,
                preflight_timeout_seconds=preflight_timeout_seconds,
            )
            if repair_step.get("status") == "integrated":
                advanced = repair_step.get("integration")
                if isinstance(advanced, dict):
                    integration = advanced
                else:
                    return _result(
                        paths, run_id, "blocked", "project-repair-state-drift",
                        ["project-repair-integrated-result-missing"], candidate_set,
                        project_repair=repair_step,
                    )
            else:
                blockers = repair_step.get("blockers", [])
                if not isinstance(blockers, list):
                    blockers = []
                return _result(
                    paths, run_id, str(repair_step.get("status", "blocked")),
                    str(repair_step.get("stage", "project-interface-repair")),
                    blockers, candidate_set, project_repair=repair_step,
                )
        else:
            return _result(
                paths, run_id, "failed", "project-final-integration", [],
                candidate_set,
            )
    completeness = integration.get("rust_project_ir_completeness")
    if not isinstance(completeness, dict) or completeness.get("status") != "complete":
        unresolved = completeness.get("unresolved_sections", []) \
            if isinstance(completeness, dict) else []
        return _result(
            paths, run_id, "blocked", "project-final-rust-project-ir-incomplete",
            [f"unresolved-interface:{item}" for item in unresolved], candidate_set,
        )
    integration_gate = verify_integrated_project(
        ledger=ledger, run_id=run_id, project_root=paths["project_root"],
        out_root=paths["out_root"], out_root_rel=paths["out_root_rel"],
    )
    if integration_gate.get("gate_status") != "passed":
        return _result(
            paths, run_id, "failed", "project-final-integration-gate", [], candidate_set,
        )
    cargo = verify_project_cargo(
        ledger=ledger, run_id=run_id, project_root=paths["project_root"],
        runtime_root=paths["runtime_root"], out_root=paths["out_root"],
        out_root_rel=paths["out_root_rel"], timeout_seconds=timeout_seconds,
    )
    if cargo.get("status") != "passed":
        return _result(
            paths, run_id, str(cargo.get("status", "blocked")),
            "project-final-cargo", [], candidate_set,
        )
    try:
        project_final = _record_host_project_final(
            ledger=ledger, out_root=paths["out_root"],
            out_root_rel=paths["out_root_rel"], run_id=run_id,
        )
        completed = complete_verified_project(
            ledger=ledger, run_id=run_id,
            candidate_set_sha256=candidate_set,
        )
    except LedgerError as error:
        return _result(
            paths, run_id, "blocked", "project-final-semantic-project-gates",
            [str(error)], candidate_set,
        )
    receipt = {
        "schema_version": 1,
        "artifact_kind": "project-completion-receipt",
        "status": "completed",
        "run_id": run_id,
        "candidate_set_sha256": candidate_set,
        "project_final_record_id": project_final["record_id"],
        "project_final_evidence": project_final["evidence"],
        "semantic_gate": True,
    }
    reference = write_json_artifact(
        paths["out_root"], "completion/completion-receipt.json", receipt,
    )
    return {**completed, "completion_receipt": reference}


def _missing_candidate_semantic_gates(
    ledger: ProjectLedger, run_id: str, candidate_set: str,
    members: list[dict[str, str]],
) -> list[str]:
    missing = []
    with ledger.connect() as connection:
        for member in members:
            rows = latest_candidate_records(
                connection, run_id, member["unit_id"], member["artifact_id"],
            )
            by_family = {str(row["gate_family"]): row for row in rows}
            for family in sorted(CANDIDATE_REQUIRED_GATES - {"compile"}):
                row = by_family.get(family)
                if row is None or row["status"] != "passed":
                    missing.append(f"{member['unit_id']}:{family}:missing-pass")
                    continue
                payload = read_content_addressed_json(
                    ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"]),
                )
                if payload.get("candidate_set_sha256") != candidate_set:
                    missing.append(f"{member['unit_id']}:{family}:cohort-drift")
                    continue
                try:
                    strict = revalidate_candidate_semantic_verdict(ledger, payload)
                except LedgerError:
                    strict = False
                if not strict:
                    missing.append(f"{member['unit_id']}:{family}:untrusted-evidence")
    return missing


def _semantic_runner(family: str) -> Any:
    return {
        "oracle-replay-diff": run_oracle_replay_diff_candidate,
        "negative": run_negative_candidate,
        "unsafe-alias": run_unsafe_alias_candidate,
        "abi-layout": run_abi_layout_candidate,
    }[family]


def _completion_paths(ledger: ProjectLedger, harness_root: Path) -> dict[str, Any]:
    root = harness_root.resolve(strict=True)
    database = ledger.path.resolve()
    try:
        relative = database.relative_to(root)
    except ValueError as error:
        raise LedgerError("completion ledger is outside the harness repository") from error
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise LedgerError("completion requires the fixed project migration ledger path")
    out_root = database.parent.parent
    out_rel = out_root.relative_to(root).as_posix()
    return {
        "out_root": out_root,
        "out_root_rel": out_rel,
        "quarantine_root": out_root / "completion" / "quarantine",
        "runtime_root": out_root / "completion" / "runtime",
        "project_root": out_root / "completion" / "project",
    }


def _result(
    paths: dict[str, Any], run_id: str, status: str, stage: str,
    blockers: list[str], candidate_set: str | None = None, **details: Any,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "status": status,
        "run_id": run_id,
        "stage": stage,
        "candidate_set_sha256": candidate_set,
        "blockers": blockers[:64],
        "semantic_gate": False,
        **details,
    }
    payload["checkpoint_sha256"] = content_sha256(payload)
    write_json_artifact(
        paths["out_root"], "completion/coordinator-state.json", payload,
    )
    return payload


__all__ = ["SEMANTIC_RUNNERS", "resume_project_completion"]
