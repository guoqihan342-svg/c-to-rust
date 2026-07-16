from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .project_test_invocation_commitment import (
    SHARED_RAW_INVOCATION_KEYS, build_project_test_invocation_commitment,
    validate_raw_project_test_invocation,
)
from .project_test_process_sandbox import (
    canonical_sha256_bytes, public_process_result,
)
from .sandbox_contract import canonical_sha256


MAX_DETAILS = 32
PREFIX_BYTES = 64
def build_project_oracle_evidence(
    *, inventory: Mapping[str, Any], mapping: Mapping[str, Any],
    oracle_results: Mapping[str, Mapping[str, Any]],
    replay_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    tests = inventory.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("project_test_oracle_evidence_inventory_invalid")
    expected = {str(item["test_id"]) for item in tests if isinstance(item, Mapping)}
    if set(oracle_results) != expected or set(replay_results) != expected:
        raise ValueError("project_test_oracle_evidence_case_binding_invalid")
    failures = []
    mismatch_count = 0
    crash_count = 0
    case_records = []
    for test_id in sorted(expected):
        oracle = _validated_result(oracle_results[test_id])
        replay = _validated_result(replay_results[test_id])
        oracle_invocation = build_project_test_invocation_commitment(
            oracle["invocation"],
        )
        replay_invocation = build_project_test_invocation_commitment(
            replay["invocation"],
        )
        matched = _successful(oracle) and _equivalent(oracle, replay)
        crashed = _crashed(oracle) or _crashed(replay)
        mismatch_count += int(not matched)
        crash_count += int(crashed)
        case_records.append({
            "test_id": test_id,
            "oracle_invocation": oracle_invocation,
            "replay_invocation": replay_invocation,
            "oracle_invocation_sha256": oracle_invocation["commitment_sha256"],
            "replay_invocation_sha256": replay_invocation["commitment_sha256"],
            "stdin_sha256": oracle["invocation"]["stdin_sha256"],
            "stdin_size_bytes": oracle["invocation"]["stdin_size_bytes"],
            "matched": matched, "crashed": crashed,
        })
        if not matched and len(failures) < MAX_DETAILS:
            failures.append({
                "test_id": test_id, "matched": False, "crashed": crashed,
                "oracle": _observation(oracle), "replay": _observation(replay),
            })
    payload = {
        "schema_version": 3,
        "artifact_kind": "project-test-oracle-evidence",
        "inventory_sha256": str(inventory["inventory_sha256"]),
        "mapping_sha256": str(mapping["mapping_sha256"]),
        "case_count": len(expected), "mismatch_count": mismatch_count,
        "crash_count": crash_count, "cases": case_records,
        "failure_details": failures,
        "details_truncated": mismatch_count > len(failures),
        "semantic_gate": False,
    }
    payload["evidence_sha256"] = content_sha256(payload)
    return payload


def baseline_passed(result: Mapping[str, Any]) -> bool:
    value = _validated_result(result)
    return _successful(value)


def _validated_result(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("project_test_process_result_invalid")
    stdout, stderr = value.get("_stdout"), value.get("_stderr")
    invocation = value.get("invocation")
    try:
        validate_raw_project_test_invocation(invocation)
    except ValueError as error:
        raise ValueError("project_test_process_result_invalid") from error
    if (
        value.get("status") not in {"completed", "blocked"}
        or value.get("invocation_sha256") != canonical_sha256(invocation)
        or not isinstance(stdout, bytes) or not isinstance(stderr, bytes)
        or value.get("stdout_sha256") != canonical_sha256_bytes(stdout)
        or value.get("stderr_sha256") != canonical_sha256_bytes(stderr)
        or value.get("stdout_size_bytes") != len(stdout)
        or value.get("stderr_size_bytes") != len(stderr)
        or not isinstance(value.get("invocation_sha256"), str)
    ):
        raise ValueError("project_test_process_result_invalid")
    return value


def _successful(value: Mapping[str, Any]) -> bool:
    return (
        value.get("status") == "completed" and value.get("exit_code") == 0
        and value.get("signal") is None and value.get("timed_out") is False
        and value.get("oversized") is False
    )


def _equivalent(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        right.get("status") == "completed"
        and all(
            left["invocation"][key] == right["invocation"][key]
            for key in SHARED_RAW_INVOCATION_KEYS
        )
        and left.get("exit_code") == right.get("exit_code")
        and left.get("signal") == right.get("signal")
        and left["_stdout"] == right["_stdout"]
        and left["_stderr"] == right["_stderr"]
    )


def _crashed(value: Mapping[str, Any]) -> bool:
    return (
        value.get("status") != "completed" or value.get("signal") is not None
        or value.get("timed_out") is True or value.get("oversized") is True
    )


def _observation(value: Mapping[str, Any]) -> dict[str, Any]:
    public = public_process_result(value)
    invocation = public["invocation"]
    return {
        "status": public["status"], "reason_code": public["reason_code"],
        "exit_code": public["exit_code"], "signal": public["signal"],
        "timed_out": public["timed_out"], "oversized": public["oversized"],
        "stdout_size_bytes": public["stdout_size_bytes"],
        "stderr_size_bytes": public["stderr_size_bytes"],
        "stdout_sha256": public["stdout_sha256"],
        "stderr_sha256": public["stderr_sha256"],
        "stdin_sha256": invocation["stdin_sha256"],
        "stdin_size_bytes": invocation["stdin_size_bytes"],
        "stdout_prefix_hex": value["_stdout"][:PREFIX_BYTES].hex(),
        "stderr_prefix_hex": value["_stderr"][:PREFIX_BYTES].hex(),
    }

__all__ = ["baseline_passed", "build_project_oracle_evidence"]
