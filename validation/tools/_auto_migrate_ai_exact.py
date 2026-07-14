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
from validation.tools._auto_migrate_ai_exact_parts.attempts import (
    validate_with_new_attempt as _validate_with_new_attempt_impl,
)
from validation.tools._auto_migrate_ai_exact_parts.contracts import StageDependencies
from validation.tools._auto_migrate_ai_exact_parts.stage import (
    run_ai_exact_stage as _run_ai_exact_stage_impl,
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
    dependencies = StageDependencies(
        validate_ai_exact_stage_contract=validate_ai_exact_stage_contract,
        resolve_current_c2rust_baseline_candidate=(
            resolve_current_c2rust_baseline_candidate
        ),
        validate_with_new_attempt=_validate_with_new_attempt,
        classify_ai_repair_eligibility=classify_ai_repair_eligibility,
        passed_gate_count=_passed_gate_count,
        repair_c2rust_candidate_after_validation=(
            repair_c2rust_candidate_after_validation
        ),
        c2rust_repair_report_binding=c2rust_repair_report_binding,
        repair_ai_candidate_after_validation=repair_ai_candidate_after_validation,
        manifest_candidate_id=_manifest_candidate_id,
        manifest_generator_metadata=_manifest_generator_metadata,
        router_candidate=_router_candidate,
        route_candidates=route_candidates,
        sync_duplicate_audit=_sync_duplicate_audit,
        sha256_path=sha256_path,
        mark_ai_not_applied=_mark_ai_not_applied,
        persist_candidate_result=_persist_candidate_result,
        atomic_write_json=atomic_write_json,
    )
    return _run_ai_exact_stage_impl(
        spec,
        context_pack=context_pack,
        ai_manifest=ai_manifest,
        evidence_dir=evidence_dir,
        canonical_draft_path=canonical_draft_path,
        deterministic_candidate_path=deterministic_candidate_path,
        c2rust_baseline=c2rust_baseline,
        c2rust_baseline_manifest_path=c2rust_baseline_manifest_path,
        replay_test_path=replay_test_path,
        oracle_payload=oracle_payload,
        harness_path=harness_path,
        proof_root=proof_root,
        compile_runner=compile_runner,
        replay_runner=replay_runner,
        max_repair_rounds=max_repair_rounds,
        opencode_command=opencode_command,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        timeout_seconds=timeout_seconds,
        dependencies=dependencies,
    )


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
    return _validate_with_new_attempt_impl(
        spec,
        label=label,
        candidate_path=candidate_path,
        replay_test_path=replay_test_path,
        oracle_payload=oracle_payload,
        harness_path=harness_path,
        proof_root=proof_root,
        attempts_root=attempts_root,
        compile_runner=compile_runner,
        replay_runner=replay_runner,
        sha256_path=sha256_path,
        next_attempt_dir=next_attempt_dir,
        validate_auto_migrate_candidate=validate_auto_migrate_candidate,
    )


def _persist_candidate_result(
    result: Mapping[str, Any],
    path: Path,
) -> dict[str, Any]:
    return _persist_candidate_result_impl(
        result,
        path,
        persist_summary=persist_exact_validation_summary,
        sha256_path=sha256_path,
    )


def _mark_ai_not_applied(
    manifest: dict[str, Any],
    evidence_dir: Path,
    slice_id: str,
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
