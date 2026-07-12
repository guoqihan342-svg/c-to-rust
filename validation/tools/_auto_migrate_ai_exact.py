from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from validation.tools.ai_candidate_harness import (
    canonical_json_bytes,
    extract_gate_failure_facts,
    prove_fresh_oracle,
    route_candidates,
    validate_exact_candidate,
)
from validation.tools._ai_candidate_harness_parts.context import (
    atomic_write_json,
    sha256_bytes,
    sha256_path,
)
from validation.tools._auto_migrate_c2rust_repair import (
    repair_c2rust_candidate_after_validation,
    repair_report_binding as c2rust_repair_report_binding,
)
from validation.tools._auto_migrate_c2rust_candidates import (
    resolve_current_c2rust_baseline_candidate,
)
from validation.tools._auto_migrate_ai_repair import repair_ai_candidate_after_validation
from validation.tools._auto_migrate_ai_repair_eligibility import (
    classify_ai_repair_eligibility,
)
from validation.tools._auto_migrate_ai_exact_persistence import (
    mark_ai_not_applied as _mark_ai_not_applied_impl,
    persist_candidate_result as _persist_candidate_result_impl,
    persist_exact_validation_summary as _persist_exact_validation_summary_impl,
)
from validation.tools._auto_migrate_ai_exact_routing import (
    manifest_candidate_id as _manifest_candidate_id,
    manifest_generator_metadata as _manifest_generator_metadata,
    next_attempt_dir,
    passed_gate_count as _passed_gate_count,
    router_candidate as _router_candidate,
    sync_duplicate_audit as _sync_duplicate_audit,
)
from validation.tools._auto_migrate_ai_exact_validation import (
    artifact_root as _artifact_root,
    current_candidate_unsafe_ledger,
    router_gate_results,
    unsafe_policy_from_spec,
    validate_ai_exact_stage_contract,
    validate_auto_migrate_candidate as _validate_auto_migrate_candidate_impl,
)


CompileRunner = Callable[[Path], dict[str, Any]]
ReplayRunner = Callable[[Path, Path], dict[str, Any]]


def run_ai_exact_stage(
    spec: Mapping[str, Any],
    *,
    context_pack: dict[str, Any],
    ai_manifest: dict[str, Any],
    evidence_dir: Path,
    canonical_draft_path: Path,
    deterministic_candidate_path: Path | None,
    c2rust_baseline: Mapping[str, Any] | None,
    c2rust_baseline_manifest_path: Path | None,
    replay_test_path: Path,
    oracle_payload: Mapping[str, Any],
    harness_path: Path,
    proof_root: Path,
    compile_runner: CompileRunner,
    replay_runner: ReplayRunner,
    max_repair_rounds: int,
    opencode_command: str,
    resolved_model: str,
    agent: str,
    variant: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    validate_ai_exact_stage_contract(
        context_pack,
        ai_manifest,
        evidence_dir=evidence_dir,
        replay_test_path=replay_test_path,
        canonical_draft_path=canonical_draft_path,
    )
    slice_id = str(spec["slice_id"])
    attempts_root = evidence_dir / "ai-exact-attempts"
    baseline_path, baseline_audit = resolve_current_c2rust_baseline_candidate(
        c2rust_baseline,
        manifest_path=c2rust_baseline_manifest_path,
        evidence_dir=evidence_dir,
        repo_root=proof_root,
    )
    ai_result = _validate_with_new_attempt(
        spec,
        label="ai-initial",
        candidate_path=canonical_draft_path,
        replay_test_path=replay_test_path,
        oracle_payload=oracle_payload,
        harness_path=harness_path,
        proof_root=proof_root,
        attempts_root=attempts_root,
        compile_runner=compile_runner,
        replay_runner=replay_runner,
    )
    deterministic_result = None
    c2rust_baseline_result = None
    c2rust_repair_result = None
    c2rust_repair_audit = None
    c2rust_repaired_candidate_path = None
    canonical_changed = False
    ai_repair_eligibility = classify_ai_repair_eligibility(ai_result)
    c2rust_repair_eligibility = {
        "status": "skipped",
        "reason": "candidate_not_validated",
        "provider_invocations": 0,
        "semantic_gate": False,
    }

    if (
        ai_result["status"] != "passed"
        and deterministic_candidate_path is not None
        and deterministic_candidate_path.is_file()
        and sha256_path(deterministic_candidate_path) != ai_result["candidate_sha256"]
    ):
        deterministic_result = _validate_with_new_attempt(
            spec,
            label="typed-ir",
            candidate_path=deterministic_candidate_path,
            replay_test_path=replay_test_path,
            oracle_payload=oracle_payload,
            harness_path=harness_path,
            proof_root=proof_root,
            attempts_root=attempts_root,
            compile_runner=compile_runner,
            replay_runner=replay_runner,
        )

    if baseline_path is not None:
        baseline_sha = sha256_path(baseline_path)
        prior_result = next(
            (
                result
                for result in (ai_result, deterministic_result)
                if result is not None and result.get("candidate_sha256") == baseline_sha
            ),
            None,
        )
        if prior_result is not None:
            c2rust_baseline_result = prior_result
            baseline_audit.update(
                status="duplicate",
                reason="duplicate_exact_artifact_sha256",
                duplicate_candidate_sha256=baseline_sha,
            )
        elif not any(
            result is not None and result.get("status") == "passed"
            for result in (ai_result, deterministic_result)
        ):
            c2rust_baseline_result = _validate_with_new_attempt(
                spec,
                label="c2rust-baseline",
                candidate_path=baseline_path,
                replay_test_path=replay_test_path,
                oracle_payload=oracle_payload,
                harness_path=harness_path,
                proof_root=proof_root,
                attempts_root=attempts_root,
                compile_runner=compile_runner,
                replay_runner=replay_runner,
            )
            baseline_audit.update(
                status="exact_gates_completed",
                reason="fresh_exact_gates_passed"
                if c2rust_baseline_result["status"] == "passed"
                else "fresh_exact_gates_failed",
                exact_validation_status=c2rust_baseline_result["status"],
            )
        else:
            baseline_audit.update(
                status="not_attempted",
                reason="higher_priority_candidate_passed",
            )

    if c2rust_baseline_result is not None:
        c2rust_repair_eligibility = classify_ai_repair_eligibility(
            c2rust_baseline_result
        )

    zero_token_results = (ai_result, deterministic_result, c2rust_baseline_result)
    if not any(result is not None and result.get("status") == "passed" for result in zero_token_results):
        repair_raw_c2rust = (
            max_repair_rounds > 0
            and baseline_path is not None
            and c2rust_baseline_result is not None
            and baseline_audit.get("status") != "duplicate"
            and _passed_gate_count(c2rust_baseline_result) > _passed_gate_count(ai_result)
            and c2rust_repair_eligibility["status"] == "eligible"
        )
        if repair_raw_c2rust:
            def validate_c2rust_repair(path: Path, round_number: int) -> dict[str, Any]:
                result = _validate_with_new_attempt(
                    spec,
                    label=f"c2rust-repair-{round_number:02d}",
                    candidate_path=path,
                    replay_test_path=replay_test_path,
                    oracle_payload=oracle_payload,
                    harness_path=harness_path,
                    proof_root=proof_root,
                    attempts_root=attempts_root,
                    compile_runner=compile_runner,
                    replay_runner=replay_runner,
                )
                return result["repair_validation_result"]

            repair_report, repaired_candidate_path = repair_c2rust_candidate_after_validation(
                context_pack,
                out_dir=evidence_dir,
                baseline_candidate_path=baseline_path,
                initial_failure_facts=c2rust_baseline_result["repair_validation_result"],
                validation_runner=validate_c2rust_repair,
                max_rounds=max_repair_rounds,
                opencode_command=opencode_command,
                resolved_model=resolved_model,
                agent=agent,
                variant=variant,
                timeout_seconds=timeout_seconds,
            )
            c2rust_repaired_candidate_path = repaired_candidate_path
            if repair_report is not None:
                c2rust_repair_audit = {
                    "source": "c2rust-repair",
                    "status": "repair_completed_without_candidate",
                    "reason": "repair_report_has_no_reopenable_candidate",
                    "base_candidate_sha256": c2rust_baseline_result["candidate_sha256"],
                    "repair_report": c2rust_repair_report_binding(
                        repair_report,
                        out_dir=evidence_dir,
                    ),
                    "repair_rounds": len(repair_report.get("rounds", [])),
                }
            if repaired_candidate_path is not None and c2rust_repair_audit is not None:
                repaired_sha = sha256_path(repaired_candidate_path)
                c2rust_repair_audit["final_candidate_sha256"] = repaired_sha
                c2rust_repair_result = _validate_with_new_attempt(
                    spec,
                    label="c2rust-repair-final",
                    candidate_path=repaired_candidate_path,
                    replay_test_path=replay_test_path,
                    oracle_payload=oracle_payload,
                    harness_path=harness_path,
                    proof_root=proof_root,
                    attempts_root=attempts_root,
                    compile_runner=compile_runner,
                    replay_runner=replay_runner,
                )
                c2rust_repair_audit.update(
                    status="exact_gates_completed",
                    reason="fresh_exact_gates_passed"
                    if c2rust_repair_result["status"] == "passed"
                    else "fresh_exact_gates_failed",
                )
        elif max_repair_rounds > 0 and ai_repair_eligibility["status"] == "eligible":
            def validate_ai_repair(path: Path, round_number: int) -> dict[str, Any]:
                result = _validate_with_new_attempt(
                    spec,
                    label=f"ai-repair-{round_number:02d}",
                    candidate_path=path,
                    replay_test_path=replay_test_path,
                    oracle_payload=oracle_payload,
                    harness_path=harness_path,
                    proof_root=proof_root,
                    attempts_root=attempts_root,
                    compile_runner=compile_runner,
                    replay_runner=replay_runner,
                )
                return result["repair_validation_result"]

            ai_manifest, repair_report = repair_ai_candidate_after_validation(
                context_pack,
                ai_manifest,
                out_dir=evidence_dir,
                canonical_draft_path=canonical_draft_path,
                initial_failure_facts=ai_result["repair_validation_result"],
                validation_runner=validate_ai_repair,
                max_rounds=max_repair_rounds,
                opencode_command=opencode_command,
                resolved_model=resolved_model,
                agent=agent,
                variant=variant,
                timeout_seconds=timeout_seconds,
            )
            if repair_report and repair_report.get("status") == "candidate_ready_for_common_validation":
                canonical_changed = True
                ai_result = _validate_with_new_attempt(
                    spec,
                    label="ai-repair-final",
                    candidate_path=canonical_draft_path,
                    replay_test_path=replay_test_path,
                    oracle_payload=oracle_payload,
                    harness_path=harness_path,
                    proof_root=proof_root,
                    attempts_root=attempts_root,
                    compile_runner=compile_runner,
                    replay_runner=replay_runner,
                )
                ai_repair_eligibility = classify_ai_repair_eligibility(ai_result)

    ai_candidate_id = _manifest_candidate_id(ai_manifest)
    candidates = [
        _router_candidate(
            ai_candidate_id,
            "opencode-ai",
            ai_result,
            metadata=_manifest_generator_metadata(ai_manifest),
        )
    ]
    if deterministic_result is not None:
        candidates.append(
            _router_candidate("typed-ir:clang-lowered", "typed-ir", deterministic_result)
        )
    if c2rust_repair_result is not None:
        candidates.append(
            _router_candidate(
                "c2rust-repair:raw-current-run",
                "c2rust-repair",
                c2rust_repair_result,
            )
        )
    if c2rust_baseline_result is not None:
        candidates.append(
            _router_candidate(
                "c2rust-baseline:raw-current-run",
                "c2rust-baseline",
                c2rust_baseline_result,
            )
        )
    provider_invocations = ai_manifest.get("provider_invocations")
    if (
        isinstance(provider_invocations, bool)
        or not isinstance(provider_invocations, int)
        or provider_invocations not in {0, 1, 2}
    ):
        raise ValueError("AI candidate manifest provider_invocations must be 0, 1, or 2")
    router = route_candidates(
        candidates,
        provider_invocation_budget=max(1, provider_invocations),
        provider_invocations=provider_invocations,
    )
    _sync_duplicate_audit(router, source="c2rust-baseline", audit=baseline_audit)
    if c2rust_repair_audit is not None:
        _sync_duplicate_audit(router, source="c2rust-repair", audit=c2rust_repair_audit)
    unique_sources = {
        candidate.get("source")
        for candidate in router.get("candidate_set", [])
        if isinstance(candidate, Mapping)
    }
    selected_id = router.get("selected_candidate_id")
    if selected_id == "typed-ir:clang-lowered" and deterministic_candidate_path is not None:
        canonical_draft_path.write_bytes(deterministic_candidate_path.read_bytes())
        canonical_changed = True
        _mark_ai_not_applied(ai_manifest, evidence_dir, slice_id)
    elif selected_id == "c2rust-baseline:raw-current-run" and baseline_path is not None:
        canonical_draft_path.write_bytes(baseline_path.read_bytes())
        canonical_changed = True
        _mark_ai_not_applied(ai_manifest, evidence_dir, slice_id)
    elif selected_id == "c2rust-repair:raw-current-run" and c2rust_repaired_candidate_path is not None:
        canonical_draft_path.write_bytes(c2rust_repaired_candidate_path.read_bytes())
        canonical_changed = True
        _mark_ai_not_applied(ai_manifest, evidence_dir, slice_id)

    summaries: dict[str, Any] = {}
    if "opencode-ai" in unique_sources:
        summaries["ai"] = _persist_candidate_result(
            ai_result,
            evidence_dir / f"l3-{slice_id}-ai-exact-validation.json",
        )
    if deterministic_result is not None and "typed-ir" in unique_sources:
        summaries["typed_ir"] = _persist_candidate_result(
            deterministic_result,
            evidence_dir / f"l3-{slice_id}-typed-ir-exact-validation.json",
        )
    if c2rust_repair_result is not None and "c2rust-repair" in unique_sources:
        summaries["c2rust_repair"] = _persist_candidate_result(
            c2rust_repair_result,
            evidence_dir / f"l3-{slice_id}-c2rust-repair-exact-validation.json",
        )
    if c2rust_baseline_result is not None and "c2rust-baseline" in unique_sources:
        summaries["c2rust_baseline"] = _persist_candidate_result(
            c2rust_baseline_result,
            evidence_dir / f"l3-{slice_id}-c2rust-baseline-exact-validation.json",
        )
    router_path = evidence_dir / f"l3-{slice_id}-ai-router.json"
    candidate_source_audit = {"c2rust_baseline": baseline_audit}
    if c2rust_repair_audit is not None:
        candidate_source_audit["c2rust_repair"] = c2rust_repair_audit
    router_payload = {
        **router,
        "candidate_evidence": summaries,
        "candidate_source_audit": candidate_source_audit,
        "repair_eligibility": {
            "opencode-ai": ai_repair_eligibility,
            "c2rust-baseline": c2rust_repair_eligibility,
        },
        "canonical_draft_sha256": sha256_path(canonical_draft_path),
        "semantic_pass": selected_id is not None,
    }
    atomic_write_json(router_path, router_payload)
    return {
        "ai_manifest": ai_manifest,
        "router": router_payload,
        "router_path": router_path,
        "canonical_changed": canonical_changed,
    }


def _validate_with_new_attempt(
    spec: Mapping[str, Any],
    *,
    label: str,
    candidate_path: Path,
    replay_test_path: Path,
    oracle_payload: Mapping[str, Any],
    harness_path: Path,
    proof_root: Path,
    attempts_root: Path,
    compile_runner: CompileRunner,
    replay_runner: ReplayRunner,
) -> dict[str, Any]:
    candidate_sha = sha256_path(candidate_path)
    attempt_dir = next_attempt_dir(attempts_root, label, candidate_sha)
    result = validate_auto_migrate_candidate(
        spec,
        candidate_path=candidate_path,
        replay_test_path=replay_test_path,
        oracle_payload=oracle_payload,
        harness_path=harness_path,
        proof_root=proof_root,
        attempt_dir=attempt_dir,
        compile_runner=compile_runner,
        replay_runner=replay_runner,
    )
    result["attempt_dir"] = attempt_dir.as_posix()
    return result


def _persist_candidate_result(result: Mapping[str, Any], path: Path) -> dict[str, Any]:
    return _persist_candidate_result_impl(
        result,
        path,
        persist_summary=persist_exact_validation_summary,
        sha256_path=sha256_path,
    )


def _mark_ai_not_applied(
    manifest: dict[str, Any], evidence_dir: Path, slice_id: str
) -> None:
    _mark_ai_not_applied_impl(
        manifest,
        evidence_dir,
        slice_id,
        atomic_write_json=atomic_write_json,
    )


def validate_auto_migrate_candidate(
    spec: Mapping[str, Any],
    *,
    candidate_path: Path,
    replay_test_path: Path,
    oracle_payload: Mapping[str, Any],
    harness_path: Path,
    proof_root: Path,
    attempt_dir: Path,
    compile_runner: CompileRunner,
    replay_runner: ReplayRunner,
) -> dict[str, Any]:
    return _validate_auto_migrate_candidate_impl(
        spec,
        candidate_path=candidate_path,
        replay_test_path=replay_test_path,
        oracle_payload=oracle_payload,
        harness_path=harness_path,
        proof_root=proof_root,
        attempt_dir=attempt_dir,
        compile_runner=compile_runner,
        replay_runner=replay_runner,
        canonical_json_bytes=canonical_json_bytes,
        extract_gate_failure_facts=extract_gate_failure_facts,
        prove_fresh_oracle=prove_fresh_oracle,
        validate_exact_candidate=validate_exact_candidate,
        sha256_bytes=sha256_bytes,
        sha256_path=sha256_path,
        artifact_root=_artifact_root,
        current_candidate_unsafe_ledger=current_candidate_unsafe_ledger,
        router_gate_results=router_gate_results,
        unsafe_policy_from_spec=unsafe_policy_from_spec,
    )


def persist_exact_validation_summary(
    result: Mapping[str, Any],
    *,
    path: Path,
    attempt_dir: Path,
) -> dict[str, Any]:
    return _persist_exact_validation_summary_impl(
        result,
        path=path,
        attempt_dir=attempt_dir,
        atomic_write_json=atomic_write_json,
    )
