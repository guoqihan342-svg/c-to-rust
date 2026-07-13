from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


def exact_replay_runner_result(
    result: dict[str, Any],
    *,
    candidate_path: Path,
    replay_path: Path,
    target_sha256: str | None,
    fixture_sha256: str | None,
    observable_outputs: Any,
    sha256_path: Callable[[Path], str],
    sha256_observables: Callable[[Any], str],
) -> dict[str, Any]:
    phase = str(result.get("phase", "compile"))
    returncode = (
        result.get("run_returncode")
        if phase == "run"
        else result.get("compile_returncode")
    )
    projected = {
        "status": str(result.get("status", "failed")),
        "phase": phase,
        "returncode": int(returncode if isinstance(returncode, int) else 1),
        "candidate_sha256": sha256_path(candidate_path),
        "replay_test_sha256": sha256_path(replay_path),
        "shared_fixture_identity_sha256": fixture_sha256,
        "target_contract_sha256": target_sha256,
        "observable_outputs": observable_outputs,
        "observable_outputs_sha256": (
            sha256_observables(observable_outputs)
            if observable_outputs is not None
            else None
        ),
    }
    compile_stderr = result.get("compile_stderr")
    if phase == "compile" and isinstance(compile_stderr, str):
        projected["compile_stderr"] = compile_stderr
    return projected


__all__ = ["exact_replay_runner_result"]
