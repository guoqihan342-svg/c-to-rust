from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from validation.tools._auto_migrate_ai_exact_parts.contracts import (
    CompileRunner,
    ReplayRunner,
    StageDependencies,
    StageInputs,
)


def validate_with_new_attempt(
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
    sha256_path: Callable[[Path], str],
    next_attempt_dir: Callable[[Path, str, str], Path],
    validate_auto_migrate_candidate: Callable[..., dict[str, Any]],
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


def validate_stage_candidate(
    inputs: StageInputs,
    dependencies: StageDependencies,
    *,
    label: str,
    candidate_path: Path,
) -> dict[str, Any]:
    return dependencies.validate_with_new_attempt(
        inputs.spec,
        label=label,
        candidate_path=candidate_path,
        replay_test_path=inputs.replay_test_path,
        oracle_payload=inputs.oracle_payload,
        harness_path=inputs.harness_path,
        proof_root=inputs.proof_root,
        attempts_root=inputs.attempts_root,
        compile_runner=inputs.compile_runner,
        replay_runner=inputs.replay_runner,
    )
