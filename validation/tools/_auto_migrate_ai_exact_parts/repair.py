from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools._auto_migrate_ai_exact_parts.attempts import (
    validate_stage_candidate,
)
from validation.tools._auto_migrate_ai_exact_parts.contracts import (
    CandidateState,
    StageDependencies,
    StageInputs,
)


def repair_failed_candidates(
    inputs: StageInputs,
    dependencies: StageDependencies,
    state: CandidateState,
) -> None:
    zero_token_results = (
        state.ai_result,
        state.deterministic_result,
        state.c2rust_baseline_result,
    )
    if any(
        result is not None and result.get("status") == "passed"
        for result in zero_token_results
    ):
        return

    repair_raw_c2rust = (
        inputs.max_repair_rounds > 0
        and state.baseline_path is not None
        and state.c2rust_baseline_result is not None
        and state.baseline_audit.get("status") != "duplicate"
        and dependencies.passed_gate_count(state.c2rust_baseline_result)
        > dependencies.passed_gate_count(state.ai_result)
        and state.c2rust_repair_eligibility["status"] == "eligible"
    )
    if repair_raw_c2rust:
        _repair_c2rust_candidate(inputs, dependencies, state)
    elif (
        inputs.max_repair_rounds > 0
        and state.ai_repair_eligibility["status"] == "eligible"
    ):
        _repair_ai_candidate(inputs, dependencies, state)


def _repair_c2rust_candidate(
    inputs: StageInputs,
    dependencies: StageDependencies,
    state: CandidateState,
) -> None:
    baseline_path = state.baseline_path
    baseline_result = state.c2rust_baseline_result
    if baseline_path is None or baseline_result is None:
        return

    def validate_c2rust_repair(
        path: Path,
        round_number: int,
    ) -> dict[str, Any]:
        result = validate_stage_candidate(
            inputs,
            dependencies,
            label=f"c2rust-repair-{round_number:02d}",
            candidate_path=path,
        )
        return result["repair_validation_result"]

    repair_report, repaired_candidate_path = (
        dependencies.repair_c2rust_candidate_after_validation(
            inputs.context_pack,
            out_dir=inputs.evidence_dir,
            baseline_candidate_path=baseline_path,
            initial_failure_facts=baseline_result["repair_validation_result"],
            validation_runner=validate_c2rust_repair,
            max_rounds=inputs.max_repair_rounds,
            opencode_command=inputs.opencode_command,
            resolved_model=inputs.resolved_model,
            agent=inputs.agent,
            variant=inputs.variant,
            timeout_seconds=inputs.timeout_seconds,
        )
    )
    state.c2rust_repaired_candidate_path = repaired_candidate_path
    if repair_report is not None:
        state.c2rust_repair_audit = {
            "source": "c2rust-repair",
            "status": "repair_completed_without_candidate",
            "reason": "repair_report_has_no_reopenable_candidate",
            "base_candidate_sha256": baseline_result["candidate_sha256"],
            "repair_report": dependencies.c2rust_repair_report_binding(
                repair_report,
                out_dir=inputs.evidence_dir,
            ),
            "repair_rounds": len(repair_report.get("rounds", [])),
        }
    if repaired_candidate_path is None or state.c2rust_repair_audit is None:
        return

    repaired_sha = dependencies.sha256_path(repaired_candidate_path)
    state.c2rust_repair_audit["final_candidate_sha256"] = repaired_sha
    state.c2rust_repair_result = validate_stage_candidate(
        inputs,
        dependencies,
        label="c2rust-repair-final",
        candidate_path=repaired_candidate_path,
    )
    state.c2rust_repair_audit.update(
        status="exact_gates_completed",
        reason=(
            "fresh_exact_gates_passed"
            if state.c2rust_repair_result["status"] == "passed"
            else "fresh_exact_gates_failed"
        ),
    )


def _repair_ai_candidate(
    inputs: StageInputs,
    dependencies: StageDependencies,
    state: CandidateState,
) -> None:
    def validate_ai_repair(path: Path, round_number: int) -> dict[str, Any]:
        result = validate_stage_candidate(
            inputs,
            dependencies,
            label=f"ai-repair-{round_number:02d}",
            candidate_path=path,
        )
        return result["repair_validation_result"]

    state.ai_manifest, repair_report = (
        dependencies.repair_ai_candidate_after_validation(
            inputs.context_pack,
            state.ai_manifest,
            out_dir=inputs.evidence_dir,
            canonical_draft_path=inputs.canonical_draft_path,
            initial_failure_facts=state.ai_result["repair_validation_result"],
            validation_runner=validate_ai_repair,
            max_rounds=inputs.max_repair_rounds,
            opencode_command=inputs.opencode_command,
            resolved_model=inputs.resolved_model,
            agent=inputs.agent,
            variant=inputs.variant,
            timeout_seconds=inputs.timeout_seconds,
        )
    )
    if not (
        repair_report
        and repair_report.get("status")
        == "candidate_ready_for_common_validation"
    ):
        return

    state.canonical_changed = True
    state.ai_result = validate_stage_candidate(
        inputs,
        dependencies,
        label="ai-repair-final",
        candidate_path=inputs.canonical_draft_path,
    )
    state.ai_repair_eligibility = dependencies.classify_ai_repair_eligibility(
        state.ai_result
    )
