from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from validation.tools._auto_migrate_ai_exact_parts.contracts import (
    CompileRunner,
    ReplayRunner,
    StageDependencies,
    StageInputs,
)
from validation.tools._auto_migrate_ai_exact_parts.evaluation import (
    evaluate_candidates,
)
from validation.tools._auto_migrate_ai_exact_parts.finalize import finalize_stage
from validation.tools._auto_migrate_ai_exact_parts.repair import (
    repair_failed_candidates,
)


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
    dependencies: StageDependencies,
) -> dict[str, Any]:
    dependencies.validate_ai_exact_stage_contract(
        context_pack,
        ai_manifest,
        evidence_dir=evidence_dir,
        replay_test_path=replay_test_path,
        canonical_draft_path=canonical_draft_path,
    )
    inputs = StageInputs(
        spec=spec,
        slice_id=str(spec["slice_id"]),
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
        attempts_root=evidence_dir / "ai-exact-attempts",
        compile_runner=compile_runner,
        replay_runner=replay_runner,
        max_repair_rounds=max_repair_rounds,
        opencode_command=opencode_command,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        timeout_seconds=timeout_seconds,
    )
    state = evaluate_candidates(inputs, dependencies)
    repair_failed_candidates(inputs, dependencies, state)
    return finalize_stage(inputs, dependencies, state)
