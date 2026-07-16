from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate_compile_verifier import verify_candidate_compile
from .candidate_final_verifier import verify_candidate_final
from .controller_project_gates import complete_verified_project
from .gate_candidate_sets import candidate_set_members
from .ledger import LedgerError, ProjectLedger
from .ledger_run_contract import load_migration_contract
from .project_cargo_verifier import verify_project_cargo
from .project_candidate_gate_aggregation import (
    record_project_candidate_aggregate_gates,
)
from .project_candidate_completion import advance_gate_pending_candidates
from .project_completion_build_ir import (
    build_ir_allows_candidate_execution, build_ir_allows_completion,
    build_ir_blocker_kinds, record_build_ir_checkpoint,
    verify_project_final_build_ir,
)
from .project_completion_semantics import (
    SEMANTIC_RUNNERS, missing_candidate_semantic_gates as _missing_candidate_semantic_gates,
    semantic_runner as _semantic_runner,
)
from .project_completion_state import completion_paths, completion_result
from .project_completion_finalize import finalize_verified_project
from .project_completion_repair_phase import execute_project_repair_completion_step
from .project_completion_verifier_phase import advance_project_verifier_phase
from .project_host_gates import _record_host_project_final
from .project_integration import integrate_verified_project
from .project_integration_verifier import verify_integrated_project
from .project_test_semantic_verifier import (
    reopen_project_test_semantic_evidence, verify_project_test_semantics,
)

_write_build_ir_verification = record_build_ir_checkpoint
_build_ir_allows_candidate_execution = build_ir_allows_candidate_execution
_build_ir_allows_completion = build_ir_allows_completion
_build_ir_blocker_kinds = build_ir_blocker_kinds
_result = completion_result
def resume_project_completion(
    *, ledger: ProjectLedger, run_id: str, harness_root: Path,
    repo_root: Path | None = None,
    timeout_seconds: int = 300, preflight_timeout_seconds: int = 60,
    logical_model: str = "GLM-5.1", resolved_model: str = "zai/glm-5.1",
) -> dict[str, Any]:
    paths = completion_paths(ledger, harness_root)
    candidate_wave = advance_gate_pending_candidates(
        ledger=ledger, run_id=run_id,
        out_root=paths["out_root"], out_root_rel=paths["out_root_rel"],
        quarantine_root=paths["quarantine_root"],
        runtime_root=paths["runtime_root"], timeout_seconds=timeout_seconds,
    )
    if candidate_wave.get("status") in {
        "waiting", "blocked", "failed", "repair-required",
    }:
        repair_ready = candidate_wave.get("status") == "repair-required"
        return _result(
            paths, run_id, "waiting" if repair_ready else str(
                candidate_wave.get("status", "blocked")
            ), str(candidate_wave.get("stage", "candidate-wave-verification")),
            list(candidate_wave.get("blockers", [])),
            candidate_wave=candidate_wave,
        )
    try:
        candidate_set = ledger.bind_verification_candidate_set(
            run_id=run_id, scope="project-final",
        )
    except LedgerError as error:
        return _result(
            paths, run_id, "waiting", "awaiting-all-last-good", [str(error)],
            candidate_wave=candidate_wave,
        )
    with ledger.connect() as connection:
        members = candidate_set_members(connection, run_id, candidate_set)
        _contract, migration_manifest = load_migration_contract(
            ledger.path, connection, run_id,
        )
    initial_build_ir = verify_project_final_build_ir(
        migration_manifest=migration_manifest, repo_root=repo_root,
        artifact_root=paths["out_root"],
    )
    initial_build_ir_ref = _write_build_ir_verification(
        paths, "before-candidate-execution", initial_build_ir,
    )
    if not _build_ir_allows_candidate_execution(initial_build_ir):
        return _result(
            paths, run_id, "blocked", "project-final-build-ir-verification",
            _build_ir_blocker_kinds(initial_build_ir), candidate_set,
            build_ir_verification=initial_build_ir_ref,
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
            diagnostics = integration.get("diagnostics")
            blockers = [
                str(item["code"])
                for item in diagnostics if isinstance(item, dict) and item.get("code")
            ] if isinstance(diagnostics, list) else []
            return _result(
                paths, run_id, str(integration.get("status", "failed")),
                str(integration.get("stage", "project-final-integration")),
                blockers, candidate_set,
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
    verifier_repair = advance_project_verifier_phase(
        ledger=ledger, run_id=run_id, harness_root=harness_root,
        integration=integration, cargo_result=cargo,
    )
    if verifier_repair is not None:
        return _result(
            paths, run_id, str(verifier_repair["status"]),
            str(verifier_repair["stage"]), list(verifier_repair["blockers"]),
            candidate_set, project_repair=verifier_repair["project_repair"],
        )
    if cargo.get("status") != "passed":
        return _result(
            paths, run_id, str(cargo.get("status", "blocked")),
            "project-final-cargo", [], candidate_set,
        )
    project_semantics = verify_project_test_semantics(
        ledger=ledger, run_id=run_id, repo_root=repo_root,
        artifact_root=paths["out_root"], out_root_rel=paths["out_root_rel"],
        project_root=paths["project_root"], runtime_root=paths["runtime_root"],
        migration_manifest=migration_manifest, candidate_members=members,
        timeout_seconds=timeout_seconds,
    )
    if project_semantics.get("status") != "passed":
        blockers = project_semantics.get("blockers")
        repair_ready = project_semantics.get("status") == "repair-required"
        return _result(
            paths, run_id, "waiting" if repair_ready else str(
                project_semantics.get("status", "blocked")
            ),
            "project-final-semantic-repair-ready" if repair_ready
            else "project-final-oracle-replay",
            list(blockers) if isinstance(blockers, list) else [], candidate_set,
            project_semantics=project_semantics,
        )
    try:
        project_candidate_gates = record_project_candidate_aggregate_gates(
            ledger=ledger, run_id=run_id, out_root=paths["out_root"],
            out_root_rel=paths["out_root_rel"],
            candidate_set_sha256=candidate_set,
            candidate_members=members,
        )
    except LedgerError as error:
        return _result(
            paths, run_id, "blocked",
            "project-final-candidate-aggregate-gates", [str(error)],
            candidate_set, project_semantics=project_semantics,
        )
    if project_candidate_gates.get("status") != "passed":
        return _result(
            paths, run_id, "failed",
            "project-final-candidate-aggregate-gates", [], candidate_set,
            project_semantics=project_semantics,
            project_candidate_gates=project_candidate_gates,
        )
    final_build_ir = verify_project_final_build_ir(
        migration_manifest=migration_manifest, repo_root=repo_root,
        artifact_root=paths["out_root"],
    )
    final_build_ir_ref = _write_build_ir_verification(
        paths, "before-project-final", final_build_ir,
    )
    if not _build_ir_allows_completion(final_build_ir):
        return _result(
            paths, run_id, "blocked", "project-final-build-ir-verification",
            _build_ir_blocker_kinds(final_build_ir), candidate_set,
            build_ir_verification=final_build_ir_ref,
        )
    return finalize_verified_project(
        paths=paths, ledger=ledger, run_id=run_id,
        candidate_set_sha256=candidate_set,
        project_semantics=project_semantics,
        initial_build_ir_ref=initial_build_ir_ref,
        final_build_ir_ref=final_build_ir_ref,
        evidence_reopener=reopen_project_test_semantic_evidence,
        project_final_recorder=_record_host_project_final,
        project_completer=complete_verified_project,
    )


__all__ = ["SEMANTIC_RUNNERS", "resume_project_completion"]
