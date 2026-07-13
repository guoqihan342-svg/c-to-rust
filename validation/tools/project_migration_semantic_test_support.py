from __future__ import annotations

import hashlib
from typing import Any

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.candidate_semantic_evidence import (
    current_semantic_context,
    semantic_observation_payload,
)
from validation.tools._project_migration_harness.candidate_semantic_schema import (
    fixed_adapter_plan,
    semantic_raw_payload,
)


def passed_semantic_observation(
    family: str, *, run_id: str, unit_id: str, candidate_artifact_id: str,
    candidate_sha256: str, candidate_set_sha256: str,
) -> dict[str, Any]:
    sha = lambda label: hashlib.sha256(label.encode("utf-8")).hexdigest()
    context = sha(f"{family}-execution-context")
    observations = {
        "oracle-replay-diff": {
            "case_count": 2, "mismatch_count": 0, "crash_count": 0,
            "c_oracle_sha256": sha("c-oracle"),
            "rust_replay_sha256": sha("rust-replay"),
            "diff_sha256": sha("semantic-diff"),
            "execution_context_sha256": context,
        },
        "negative": {
            "case_count": 2, "unexpected_accept_count": 0,
            "mutation_manifest_sha256": sha("negative-mutations"),
            "execution_context_sha256": context,
        },
        "unsafe-alias": {
            "unsafe_site_count": 0, "unproven_alias_count": 0,
            "unsafe_ledger_sha256": sha("unsafe-ledger"),
            "alias_evidence_sha256": sha("alias-evidence"),
            "execution_context_sha256": context,
        },
        "abi-layout": {
            "check_count": 2, "mismatch_count": 0,
            "c_layout_sha256": sha("c-layout"),
            "rust_layout_sha256": sha("rust-layout"),
            "execution_context_sha256": context,
        },
    }
    return semantic_observation_payload(
        run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=candidate_sha256,
        candidate_set_sha256=candidate_set_sha256,
        gate_family=family, observation=observations[family],
    )


def passed_strict_semantic_observation(
    family: str, *, ledger: Any, run_id: str, unit_id: str,
    candidate_artifact_id: str, candidate_sha256: str,
    candidate_set_sha256: str, verification_scope: str = "wave-provisional",
) -> dict[str, Any]:
    context, _repository_root = current_semantic_context(
        ledger, run_id, unit_id, candidate_artifact_id, verification_scope,
    )
    if (
        context["candidate_sha256"] != candidate_sha256
        or context["candidate_set_sha256"] != candidate_set_sha256
    ):
        raise AssertionError("strict semantic test context drifted")
    observations = {
        "oracle-replay-diff": {
            "case_count": 2, "mismatch_count": 0, "crash_count": 0,
            "c_oracle_sha256": _digest("c-oracle"),
            "rust_replay_sha256": _digest("rust-replay"),
            "diff_sha256": _digest("semantic-diff"),
        },
        "negative": {
            "case_count": 2, "unexpected_accept_count": 0,
            "mutation_manifest_sha256": _digest("negative-mutations"),
        },
        "unsafe-alias": {
            "unsafe_site_count": 0, "unproven_alias_count": 0,
            "unsafe_ledger_sha256": _digest("unsafe-ledger"),
            "alias_evidence_sha256": _digest("alias-evidence"),
        },
        "abi-layout": {
            "check_count": 2, "mismatch_count": 0,
            "c_layout_sha256": _digest("c-layout"),
            "rust_layout_sha256": _digest("rust-layout"),
        },
    }
    observation = observations[family]
    stdout = canonical_json_bytes(observation)
    plan = fixed_adapter_plan(family)
    return semantic_raw_payload(
        gate_family=family, context=context,
        execution={
            "command_sha256": plan["command_sha256"],
            "launcher_argv_sha256": plan["launcher_argv_sha256"],
            "command_started": True, "returncode": 0, "timed_out": False,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "stdout_size_bytes": len(stdout), "stderr_size_bytes": 0,
        },
        observation=observation,
    )


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


__all__ = [
    "passed_semantic_observation", "passed_strict_semantic_observation",
]
