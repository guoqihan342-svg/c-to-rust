from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import atomic_write_json, canonical_json_bytes, sha256_bytes, sha256_path
from .provider import LOGICAL_MODEL


DEFAULT_MAX_REPAIR_ROUNDS = 3
HARD_MAX_REPAIR_ROUNDS = 5
MAX_CANDIDATE_BYTES = 256_000
PROTECTED_ARTIFACT_CLASSES = ("oracle", "fixture", "validator", "gate_configuration")


def report_base(
    target_id: str,
    slice_id: str,
    context_pack: dict[str, Any],
    candidate_path: Path,
    max_rounds: int,
    *,
    resolved_model: str,
    agent: str,
    variant: str,
    artifact_label: str,
    input_source: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "target_id": target_id,
        "slice_id": slice_id,
        "artifact_label": artifact_label,
        "input_source": input_source,
        "status": "running",
        "policy": {
            "default_max_rounds": DEFAULT_MAX_REPAIR_ROUNDS,
            "hard_max_rounds": HARD_MAX_REPAIR_ROUNDS,
            "effective_max_rounds": max_rounds,
            "one_candidate_or_patch_per_round": True,
            "unchanged_input_and_failure_stops": True,
            "protected_artifact_classes": list(PROTECTED_ARTIFACT_CLASSES),
        },
        "generator": {
            "tool": "opencode",
            "logical_model": LOGICAL_MODEL,
            "resolved_model": resolved_model,
            "agent": agent,
            "variant": variant,
        },
        "bindings": {
            "context_pack_sha256": sha256_bytes(canonical_json_bytes(context_pack)),
        },
        "initial_candidate": {
            "name": candidate_path.name,
            "sha256": None,
        },
        "rounds": [],
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
            "candidate_requires_common_validation": True,
        },
    }


def round_base(round_number: int, candidate_sha: str, failure_path: Path, prompt_path: Path) -> dict[str, Any]:
    failure_binding = artifact_binding(failure_path)
    return {
        "round": round_number,
        "status": "running",
        "repair_input_sha256": repair_input_key(candidate_sha, failure_binding["sha256"]),
        "bindings": {
            "previous_candidate_sha256": candidate_sha,
            "failure_facts": failure_binding,
            "prompt": artifact_binding(prompt_path),
        },
        "semantic_pass": False,
    }


def finish_blocked(
    report: dict[str, Any],
    report_path: Path,
    kind: str,
    message: str,
    final_sha: str | None = None,
) -> dict[str, Any]:
    report["status"] = "blocked"
    report["stop_reason"] = kind
    report["failure"] = structured_failure(kind, message)
    if final_sha is not None:
        report["final_candidate"] = {"sha256": final_sha}
    atomic_write_json(report_path, report)
    return report


def finish_stopped(
    report: dict[str, Any],
    report_path: Path,
    final_sha: str,
    reason: str,
    final_path: Path | None = None,
) -> dict[str, Any]:
    report["status"] = "stopped"
    report["stop_reason"] = reason
    report["final_candidate"] = artifact_binding(final_path) if final_path is not None else {"sha256": final_sha}
    atomic_write_json(report_path, report)
    return report


def artifact_binding(path: Path) -> dict[str, str]:
    return {"path": path.name, "sha256": sha256_path(path)}


def repair_input_key(candidate_sha: str, failure_sha: str) -> str:
    return sha256_bytes(canonical_json_bytes({"candidate_sha256": candidate_sha, "failure_sha256": failure_sha}))


def structured_failure(kind: str, message: str) -> dict[str, str]:
    return {"kind": kind, "message": message}
