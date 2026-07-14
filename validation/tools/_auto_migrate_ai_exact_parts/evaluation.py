from __future__ import annotations

from validation.tools._auto_migrate_ai_exact_parts.attempts import (
    validate_stage_candidate,
)
from validation.tools._auto_migrate_ai_exact_parts.contracts import (
    CandidateState,
    StageDependencies,
    StageInputs,
)


def evaluate_candidates(
    inputs: StageInputs,
    dependencies: StageDependencies,
) -> CandidateState:
    baseline_path, baseline_audit = (
        dependencies.resolve_current_c2rust_baseline_candidate(
            inputs.c2rust_baseline,
            manifest_path=inputs.c2rust_baseline_manifest_path,
            evidence_dir=inputs.evidence_dir,
            repo_root=inputs.proof_root,
        )
    )
    ai_result = validate_stage_candidate(
        inputs,
        dependencies,
        label="ai-initial",
        candidate_path=inputs.canonical_draft_path,
    )
    state = CandidateState(
        ai_manifest=inputs.ai_manifest,
        baseline_path=baseline_path,
        baseline_audit=baseline_audit,
        ai_result=ai_result,
        ai_repair_eligibility=dependencies.classify_ai_repair_eligibility(ai_result),
        c2rust_repair_eligibility={
            "status": "skipped",
            "reason": "candidate_not_validated",
            "provider_invocations": 0,
            "semantic_gate": False,
        },
    )

    deterministic_path = inputs.deterministic_candidate_path
    if (
        ai_result["status"] != "passed"
        and deterministic_path is not None
        and deterministic_path.is_file()
        and dependencies.sha256_path(deterministic_path)
        != ai_result["candidate_sha256"]
    ):
        state.deterministic_result = validate_stage_candidate(
            inputs,
            dependencies,
            label="typed-ir",
            candidate_path=deterministic_path,
        )

    if baseline_path is not None:
        _evaluate_c2rust_baseline(inputs, dependencies, state)

    if state.c2rust_baseline_result is not None:
        state.c2rust_repair_eligibility = (
            dependencies.classify_ai_repair_eligibility(
                state.c2rust_baseline_result
            )
        )
    return state


def _evaluate_c2rust_baseline(
    inputs: StageInputs,
    dependencies: StageDependencies,
    state: CandidateState,
) -> None:
    baseline_path = state.baseline_path
    if baseline_path is None:
        return
    baseline_sha = dependencies.sha256_path(baseline_path)
    prior_result = next(
        (
            result
            for result in (state.ai_result, state.deterministic_result)
            if result is not None
            and result.get("candidate_sha256") == baseline_sha
        ),
        None,
    )
    if prior_result is not None:
        state.c2rust_baseline_result = prior_result
        state.baseline_audit.update(
            status="duplicate",
            reason="duplicate_exact_artifact_sha256",
            duplicate_candidate_sha256=baseline_sha,
        )
        return
    if any(
        result is not None and result.get("status") == "passed"
        for result in (state.ai_result, state.deterministic_result)
    ):
        state.baseline_audit.update(
            status="not_attempted",
            reason="higher_priority_candidate_passed",
        )
        return

    state.c2rust_baseline_result = validate_stage_candidate(
        inputs,
        dependencies,
        label="c2rust-baseline",
        candidate_path=baseline_path,
    )
    baseline_status = state.c2rust_baseline_result["status"]
    state.baseline_audit.update(
        status="exact_gates_completed",
        reason=(
            "fresh_exact_gates_passed"
            if baseline_status == "passed"
            else "fresh_exact_gates_failed"
        ),
        exact_validation_status=baseline_status,
    )
