from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from validation.tools._auto_migrate_ai_exact_parts.contracts import (
    CandidateState,
    StageDependencies,
    StageInputs,
)


def finalize_stage(
    inputs: StageInputs,
    dependencies: StageDependencies,
    state: CandidateState,
) -> dict[str, Any]:
    ai_candidate_id = dependencies.manifest_candidate_id(state.ai_manifest)
    candidates = [
        dependencies.router_candidate(
            ai_candidate_id,
            "opencode-ai",
            state.ai_result,
            metadata=dependencies.manifest_generator_metadata(state.ai_manifest),
        )
    ]
    if state.deterministic_result is not None:
        candidates.append(
            dependencies.router_candidate(
                "typed-ir:clang-lowered",
                "typed-ir",
                state.deterministic_result,
            )
        )
    if state.c2rust_repair_result is not None:
        candidates.append(
            dependencies.router_candidate(
                "c2rust-repair:raw-current-run",
                "c2rust-repair",
                state.c2rust_repair_result,
            )
        )
    if state.c2rust_baseline_result is not None:
        candidates.append(
            dependencies.router_candidate(
                "c2rust-baseline:raw-current-run",
                "c2rust-baseline",
                state.c2rust_baseline_result,
            )
        )

    provider_invocations = state.ai_manifest.get("provider_invocations")
    if (
        isinstance(provider_invocations, bool)
        or not isinstance(provider_invocations, int)
        or provider_invocations not in {0, 1, 2}
    ):
        raise ValueError(
            "AI candidate manifest provider_invocations must be 0, 1, or 2"
        )
    router = dependencies.route_candidates(
        candidates,
        provider_invocation_budget=max(1, provider_invocations),
        provider_invocations=provider_invocations,
    )
    dependencies.sync_duplicate_audit(
        router,
        source="c2rust-baseline",
        audit=state.baseline_audit,
    )
    if state.c2rust_repair_audit is not None:
        dependencies.sync_duplicate_audit(
            router,
            source="c2rust-repair",
            audit=state.c2rust_repair_audit,
        )

    unique_sources = {
        candidate.get("source")
        for candidate in router.get("candidate_set", [])
        if isinstance(candidate, Mapping)
    }
    _apply_selected_candidate(inputs, dependencies, state, router)
    summaries = _persist_candidate_summaries(
        inputs,
        dependencies,
        state,
        unique_sources,
    )
    router_path = inputs.evidence_dir / f"l3-{inputs.slice_id}-ai-router.json"
    candidate_source_audit = {"c2rust_baseline": state.baseline_audit}
    if state.c2rust_repair_audit is not None:
        candidate_source_audit["c2rust_repair"] = state.c2rust_repair_audit
    selected_id = router.get("selected_candidate_id")
    router_payload = {
        **router,
        "candidate_evidence": summaries,
        "candidate_source_audit": candidate_source_audit,
        "repair_eligibility": {
            "opencode-ai": state.ai_repair_eligibility,
            "c2rust-baseline": state.c2rust_repair_eligibility,
        },
        "canonical_draft_sha256": dependencies.sha256_path(
            inputs.canonical_draft_path
        ),
        "semantic_pass": selected_id is not None,
    }
    dependencies.atomic_write_json(router_path, router_payload)
    return {
        "ai_manifest": state.ai_manifest,
        "router": router_payload,
        "router_path": router_path,
        "canonical_changed": state.canonical_changed,
    }


def _apply_selected_candidate(
    inputs: StageInputs,
    dependencies: StageDependencies,
    state: CandidateState,
    router: Mapping[str, Any],
) -> None:
    selected_id = router.get("selected_candidate_id")
    selected_path = None
    if (
        selected_id == "typed-ir:clang-lowered"
        and inputs.deterministic_candidate_path is not None
    ):
        selected_path = inputs.deterministic_candidate_path
    elif (
        selected_id == "c2rust-baseline:raw-current-run"
        and state.baseline_path is not None
    ):
        selected_path = state.baseline_path
    elif (
        selected_id == "c2rust-repair:raw-current-run"
        and state.c2rust_repaired_candidate_path is not None
    ):
        selected_path = state.c2rust_repaired_candidate_path
    if selected_path is None:
        return

    inputs.canonical_draft_path.write_bytes(selected_path.read_bytes())
    state.canonical_changed = True
    dependencies.mark_ai_not_applied(
        state.ai_manifest,
        inputs.evidence_dir,
        inputs.slice_id,
    )


def _persist_candidate_summaries(
    inputs: StageInputs,
    dependencies: StageDependencies,
    state: CandidateState,
    unique_sources: set[Any],
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    if "opencode-ai" in unique_sources:
        summaries["ai"] = dependencies.persist_candidate_result(
            state.ai_result,
            inputs.evidence_dir
            / f"l3-{inputs.slice_id}-ai-exact-validation.json",
        )
    if state.deterministic_result is not None and "typed-ir" in unique_sources:
        summaries["typed_ir"] = dependencies.persist_candidate_result(
            state.deterministic_result,
            inputs.evidence_dir
            / f"l3-{inputs.slice_id}-typed-ir-exact-validation.json",
        )
    if (
        state.c2rust_repair_result is not None
        and "c2rust-repair" in unique_sources
    ):
        summaries["c2rust_repair"] = dependencies.persist_candidate_result(
            state.c2rust_repair_result,
            inputs.evidence_dir
            / f"l3-{inputs.slice_id}-c2rust-repair-exact-validation.json",
        )
    if (
        state.c2rust_baseline_result is not None
        and "c2rust-baseline" in unique_sources
    ):
        summaries["c2rust_baseline"] = dependencies.persist_candidate_result(
            state.c2rust_baseline_result,
            inputs.evidence_dir
            / f"l3-{inputs.slice_id}-c2rust-baseline-exact-validation.json",
        )
    return summaries
