from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from validation.tools._ai_auxiliary_suite_support import (
    artifact_ref,
    load_object,
    sha256_path,
)
from validation.tools import validate_competition_run_summary as summary_validator


class RepairReportError(ValueError):
    """The manifest repair binding cannot be trusted for accounting."""


def _sha256_string(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def manifest_invocation_count(manifest: dict[str, Any]) -> int:
    value = manifest.get("provider_invocations")
    if isinstance(value, int) and not isinstance(value, bool) and value in {0, 1, 2}:
        return value
    return 0


def apply_provider_invocation_accounting(
    unit: dict[str, Any],
    manifest: dict[str, Any],
    repair: dict[str, Any] | None,
) -> None:
    initial_invocations = manifest_invocation_count(manifest)
    repair_invocations = repair["provider_invocations"] if repair is not None else 0
    total_invocations = initial_invocations + repair_invocations
    unit["initial_candidate_provider_invocations"] = initial_invocations
    unit["repair_provider_invocations"] = repair_invocations
    unit["provider_invocations"] = total_invocations
    unit["provider_invocations_total"] = total_invocations
    unit["repair_rounds"] = repair["rounds"] if repair is not None else 0
    unit["repair_status"] = repair["status"] if repair is not None else None
    unit["repair_stop_reason"] = repair["stop_reason"] if repair is not None else None
    if repair is not None:
        unit.setdefault("artifacts", {})["repair_report"] = repair["artifact"]


def _manifest_repair_binding(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    candidates = manifest.get("candidates")
    candidate_bindings: list[tuple[dict[str, Any], Any]] = []
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("repair") is not None:
                candidate_bindings.append((candidate, candidate.get("repair")))
    top_level = manifest.get("repair")
    binding_count = len(candidate_bindings) + int(top_level is not None)
    if binding_count == 0:
        return None, None
    if binding_count != 1:
        raise RepairReportError("repair_binding_ambiguous")
    if top_level is not None:
        if not isinstance(top_level, dict):
            raise RepairReportError("repair_binding_invalid")
        return top_level, None
    candidate, binding = candidate_bindings[0]
    if not isinstance(binding, dict):
        raise RepairReportError("repair_binding_invalid")
    return binding, candidate


def _bound_repair_path(evidence_dir: Path, binding: dict[str, Any]) -> Path:
    path_value = binding.get("path")
    if not isinstance(path_value, str) or not path_value or "\\" in path_value:
        raise RepairReportError("repair_report_path_invalid")
    relative = PurePosixPath(path_value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise RepairReportError("repair_report_path_invalid")
    evidence_dir = evidence_dir.resolve()
    path = evidence_dir.joinpath(*relative.parts).resolve()
    try:
        path.relative_to(evidence_dir)
    except ValueError as error:
        raise RepairReportError("repair_report_path_escape") from error
    if not path.is_file():
        raise RepairReportError("repair_report_missing")
    expected_sha = binding.get("sha256")
    if not _sha256_string(expected_sha) or sha256_path(path) != expected_sha:
        raise RepairReportError("repair_report_sha256_mismatch")
    return path


def _validate_repair_rounds(report: dict[str, Any]) -> tuple[int, int]:
    rounds = report.get("rounds")
    if not isinstance(rounds, list) or len(rounds) > 5:
        raise RepairReportError("repair_report_rounds_invalid")
    policy = report.get("policy")
    effective_max = policy.get("effective_max_rounds") if isinstance(policy, dict) else None
    if (
        not isinstance(effective_max, int)
        or isinstance(effective_max, bool)
        or not 1 <= effective_max <= 5
        or len(rounds) > effective_max
    ):
        raise RepairReportError("repair_report_policy_invalid")
    provider_invocations = 0
    for expected_round, round_record in enumerate(rounds, 1):
        bindings = round_record.get("bindings") if isinstance(round_record, dict) else None
        round_status = round_record.get("status") if isinstance(round_record, dict) else None
        failure = round_record.get("failure") if isinstance(round_record, dict) else None
        if (
            not isinstance(round_record, dict)
            or round_record.get("round") != expected_round
            or round_status not in {"blocked", "candidate_generated"}
            or round_record.get("semantic_pass") is not False
            or not _sha256_string(round_record.get("repair_input_sha256"))
            or not isinstance(bindings, dict)
            or not _sha256_string(bindings.get("previous_candidate_sha256"))
            or not isinstance(bindings.get("failure_facts"), dict)
            or not isinstance(bindings.get("prompt"), dict)
        ):
            raise RepairReportError("repair_report_round_invalid")
        raw_response = bindings.get("raw_response")
        failure_kind = failure.get("kind") if isinstance(failure, dict) else None
        if raw_response is None:
            if round_status != "blocked" or failure_kind not in {
                "provider_runner_failed",
                "invalid_provider_execution",
            }:
                raise RepairReportError("repair_report_round_has_no_provider_evidence")
        elif not isinstance(raw_response, dict):
            raise RepairReportError("repair_report_round_has_no_provider_evidence")
        else:
            provider_invocations += 1
        if round_status == "candidate_generated" and any(
            not isinstance(bindings.get(key), dict)
            for key in ("repair_artifact", "candidate", "validation_result")
        ):
            raise RepairReportError("repair_report_candidate_round_incomplete")
    return len(rounds), provider_invocations


def reopen_bound_repair_report(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    evidence_dir: Path,
    summary_path: Path,
    repo_root: Path,
    target_id: str,
    slice_id: str,
) -> dict[str, Any] | None:
    binding, candidate = _manifest_repair_binding(manifest)
    if binding is None:
        return None
    path = _bound_repair_path(evidence_dir, binding)
    try:
        report = load_object(path, "AI repair report")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise RepairReportError("repair_report_unreadable") from error
    status = report.get("status")
    stop_reason = report.get("stop_reason")
    boundary = report.get("claim_boundary")
    generator = report.get("generator")
    expected_generator = manifest.get("generator")
    generator_keys = (
        "tool",
        "provider",
        "logical_model",
        "resolved_model",
        "competition_eligible",
        "evaluation_scope",
        "agent",
        "variant",
    )
    if (
        report.get("schema_version") != 3
        or report.get("target_id") != target_id
        or report.get("slice_id") != slice_id
        or report.get("artifact_label") != "ai-repair"
        or report.get("input_source") != "opencode-ai"
        or status not in {"blocked", "stopped", "exhausted", "candidate_ready_for_common_validation"}
        or binding.get("status") != status
        or binding.get("semantic_pass") is not False
        or not isinstance(stop_reason, str)
        or not stop_reason
        or not isinstance(boundary, dict)
        or boundary.get("semantic_gate") is not False
        or boundary.get("semantic_pass") is not False
        or boundary.get("translation_coverage_numerator") != 0
        or not isinstance(generator, dict)
        or not isinstance(expected_generator, dict)
        or any(generator.get(key) != expected_generator.get(key) for key in generator_keys)
    ):
        raise RepairReportError("repair_report_identity_or_status_invalid")
    repair_rounds, provider_invocations = _validate_repair_rounds(report)
    if repair_rounds == 0:
        if status != "blocked":
            raise RepairReportError("repair_report_zero_round_status_invalid")
        return _repair_metrics(status, stop_reason, 0, 0, path, repo_root)
    validated_rounds, reasons = summary_validator.validate_bound_ai_repair_report(
        binding,
        manifest_path=manifest_path,
        summary_path=summary_path,
        repo_root=repo_root,
        candidate=candidate,
        expected_generator=manifest.get("generator"),
        require_transport=True,
    )
    if reasons or validated_rounds != repair_rounds:
        suffix = ",".join(sorted(set(reasons))) if reasons else "round_count_mismatch"
        raise RepairReportError(f"repair_report_evidence_invalid:{suffix}")
    return _repair_metrics(
        status,
        stop_reason,
        repair_rounds,
        provider_invocations,
        path,
        repo_root,
    )


def _repair_metrics(
    status: str,
    stop_reason: str,
    rounds: int,
    provider_invocations: int,
    path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": status,
        "stop_reason": stop_reason,
        "rounds": rounds,
        "provider_invocations": provider_invocations,
        "artifact": artifact_ref(path, root=repo_root),
    }
