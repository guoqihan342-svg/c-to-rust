from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from validation.tools.replay_assertion_inventory import (
    build_replay_assertion_inventory,
    validate_inventory_replay_source,
)
from validation.tools.replay_call_plan import build_replay_call_plan
from validation.tools.replay_runtime_assertion import (
    runtime_assertion_failure_envelope,
)


def bound_replay_assertion_inventory(
    spec: Mapping[str, Any], repo_root: Path, replay_path: Path
) -> dict[str, Any] | None:
    try:
        plan = build_replay_call_plan(dict(spec), repo_root)
        if plan.get("status") != "bound":
            return None
        inventory = build_replay_assertion_inventory(plan)
        replay_source = replay_path.read_text(encoding="utf-8-sig")
        validate_inventory_replay_source(plan, inventory, replay_source)
    except (OSError, UnicodeError, ValueError):
        return None
    return inventory


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
    assertion_inventory: dict[str, Any] | None = None,
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
    if phase == "run" and projected["status"] == "failed":
        failure = runtime_assertion_failure_envelope(
            result.get("runtime_assertion_id"), assertion_inventory
        )
        if failure is not None:
            projected["runtime_assertion_failure"] = failure
    return projected


__all__ = ["bound_replay_assertion_inventory", "exact_replay_runner_result"]
