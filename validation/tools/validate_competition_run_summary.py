#!/usr/bin/env python3
"""Validate the OpenCode competition run summary contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "validation" / "competition-run-summary.schema.json"
REQUIRED_ARTIFACT_ROOTS = {
    "target/competition-out/evidence",
    "target/competition-out/summary",
    "target/competition-out/logs",
}
LF_STABLE_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hh",
    ".hpp",
    ".json",
    ".jsonl",
    ".md",
    ".rs",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
COMPETITION_OPENCODE_COMMAND = "opencode"
COMPETITION_OPENCODE_AGENT = "c2rust-migrator"
COMPETITION_OPENCODE_MODEL = "GLM-5.1"
COMPETITION_OPENCODE_VARIANT = "max"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPO_ROOT / "target" / "competition-out" / "summary" / "competition-run-summary.json",
    )
    args = parser.parse_args()

    result = validate_summary(args.summary, repo_root=REPO_ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_summary(summary_path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    summary = load_json(summary_path)
    schema = load_json(SCHEMA_PATH)
    try:
        jsonschema.validate(summary, schema)
    except jsonschema.ValidationError as error:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise SystemExit(f"competition run summary schema error at {path}: {error.message}") from error

    validate_artifact_roots(summary.get("artifact_roots", []), repo_root=repo_root)
    validate_workflow_metrics(summary, summary_path=summary_path, repo_root=repo_root)
    validate_final_gate(summary)
    validate_slice_counts(summary)
    validate_workers(summary)
    validate_competition_exact_host_attestation(summary, summary_path=summary_path, repo_root=repo_root)

    return {
        "status": "passed",
        "summary": repo_relative(summary_path, repo_root),
        "proof_class": summary["proof_class"],
        "profile_id": summary["profile_id"],
        "semantic_pass": summary["slices"]["semantic_pass"],
        "final_gate": summary["final_gate"]["status"],
    }


def validate_competition_exact_host_attestation(
    summary: dict[str, Any],
    *,
    summary_path: Path,
    repo_root: Path,
) -> None:
    proof_class = summary["proof_class"]
    attestation = summary.get("competition_exact_host_attestation")
    if proof_class != "competition-exact":
        if attestation is not None:
            raise SystemExit(
                "competition run summary competition_exact_host_attestation is allowed only for "
                "proof_class=competition-exact"
            )
        return
    if not isinstance(attestation, dict):
        raise SystemExit(
            "competition run summary proof_class=competition-exact requires "
            "competition_exact_host_attestation"
        )
    if attestation.get("competition_exact_host_attested") is not True:
        raise SystemExit(
            "competition run summary proof_class=competition-exact requires "
            "competition_exact_host_attestation.competition_exact_host_attested=true"
        )
    if attestation.get("required_agent_tool") != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit("competition exact host attestation required_agent_tool must be opencode")
    if attestation.get("required_agent") != COMPETITION_OPENCODE_AGENT:
        raise SystemExit("competition exact host attestation required_agent must be c2rust-migrator")
    if attestation.get("required_model") != COMPETITION_OPENCODE_MODEL:
        raise SystemExit("competition exact host attestation required_model must be GLM-5.1")
    if attestation.get("required_variant") != COMPETITION_OPENCODE_VARIANT:
        raise SystemExit("competition exact host attestation required_variant must be max")
    availability = attestation.get("opencode_model_availability")
    if not isinstance(availability, dict):
        raise SystemExit("competition exact host attestation opencode_model_availability must be an object")
    validate_opencode_model_availability_for_exact_host(
        availability,
        summary_path=summary_path,
        repo_root=repo_root,
    )


def validate_opencode_model_availability_for_exact_host(
    availability: dict[str, Any],
    *,
    summary_path: Path,
    repo_root: Path,
) -> None:
    if availability.get("status") != "available":
        raise SystemExit("competition exact host opencode_model_availability.status must be available")
    if availability.get("required_model") != COMPETITION_OPENCODE_MODEL:
        raise SystemExit("competition exact host opencode_model_availability.required_model must be GLM-5.1")
    if availability.get("model_listed") is not True:
        raise SystemExit("competition exact host opencode_model_availability.model_listed must be true")
    if availability.get("opencode_command") != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit("competition exact host opencode_model_availability.opencode_command must be opencode")
    if int(availability.get("process_returncode", -1)) != 0:
        raise SystemExit("competition exact host opencode_model_availability.process_returncode must be 0")
    if not opencode_models_argv_matches(availability.get("argv")):
        raise SystemExit("competition exact host opencode_model_availability.argv must be opencode models")
    logs = availability.get("logs")
    if not isinstance(logs, dict):
        raise SystemExit("competition exact host opencode_model_availability.logs must be an object")
    for stream in ("stdout", "stderr"):
        log_ref = logs.get(stream)
        if not isinstance(log_ref, str) or not is_repo_relative_posix_path(log_ref):
            raise SystemExit(f"competition exact host opencode_model_availability.logs.{stream} must be repo-relative POSIX")
        log_path = resolve_summary_artifact(log_ref, summary_path=summary_path, repo_root=repo_root)
        if log_path is None:
            raise SystemExit(f"competition exact host opencode_model_availability.logs.{stream} does not exist")
        expected_sha = availability.get(f"{stream}_sha256")
        if not isinstance(expected_sha, str) or not is_sha256(expected_sha):
            raise SystemExit(f"competition exact host opencode_model_availability.{stream}_sha256 must be a sha256")
        if sha256(log_path) != expected_sha:
            raise SystemExit(f"competition exact host opencode_model_availability.logs.{stream} sha256 mismatch")
        if stream == "stdout":
            stdout_text = log_path.read_text(encoding="utf-8", errors="replace")
            if not opencode_models_stdout_lists_required_model(stdout_text):
                raise SystemExit("competition exact host opencode_model_availability.logs.stdout must list GLM-5.1")


def opencode_models_argv_matches(value: Any) -> bool:
    return value == [COMPETITION_OPENCODE_COMMAND, "models"]


def opencode_models_stdout_lists_required_model(stdout: str) -> bool:
    for token in re.split(r"[\s,;]+", stdout):
        candidate = token.strip().strip("'\"`[](){}")
        if candidate == COMPETITION_OPENCODE_MODEL:
            return True
        if "/" in candidate and candidate.rsplit("/", 1)[-1] == COMPETITION_OPENCODE_MODEL:
            return True
    return False


def validate_artifact_roots(artifact_roots: list[str], *, repo_root: Path) -> None:
    roots = set(artifact_roots)
    missing = sorted(REQUIRED_ARTIFACT_ROOTS - roots)
    if missing:
        raise SystemExit(f"competition run summary artifact_roots missing required roots: {', '.join(missing)}")

    for root in artifact_roots:
        if not is_repo_relative_posix_path(root):
            raise SystemExit(f"competition run summary artifact_roots must be repo-relative POSIX paths: {root}")
        resolved = (repo_root / root).resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError as error:
            raise SystemExit(f"competition run summary artifact_roots escapes repository: {root}") from error


def is_repo_relative_posix_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    if value.startswith("/") or value.startswith("~"):
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    parts = PurePosixPath(value).parts
    return ".." not in parts


def validate_workflow_metrics(summary: dict[str, Any], *, summary_path: Path, repo_root: Path) -> None:
    binding = summary["workflow_metrics"]
    metrics_ref = binding["path"]
    if not is_repo_relative_posix_path(metrics_ref):
        raise SystemExit(f"competition run summary workflow_metrics.path must be repo-relative POSIX: {metrics_ref}")
    metrics_path = resolve_summary_artifact(metrics_ref, summary_path=summary_path, repo_root=repo_root)
    if metrics_path is None:
        raise SystemExit(f"competition run summary workflow_metrics.path does not exist: {metrics_ref}")
    actual_sha = sha256(metrics_path)
    if actual_sha != binding["sha256"]:
        raise SystemExit("competition run summary workflow_metrics.sha256 does not match artifact")
    metrics = load_json(metrics_path)
    required_fields = [
        "schema_version",
        "run_id",
        "proof_class",
        "units_total",
        "units_converged",
        "units_baseline_only",
        "unsafe_reduction",
        "translation_before_after",
        "avg_repair_rounds",
        "auto_recovery_rate",
        "human_interventions",
        "always_compiles",
        "always_equivalent",
        "fail_closed_count",
        "root_cause_counts",
        "wall_clock_seconds",
        "llm_calls",
        "per_unit_statuses",
    ]
    missing = [field for field in required_fields if field not in metrics]
    if missing:
        raise SystemExit(f"workflow metrics artifact missing required fields: {', '.join(missing)}")
    slices = summary["slices"]
    expected = {
        "run_id": summary["run_id"],
        "proof_class": summary["proof_class"],
        "units_total": slices["attempted"],
        "units_converged": slices["semantic_pass"],
        "units_baseline_only": max(0, int(slices["compiled"]) - int(slices["semantic_pass"])),
        "fail_closed_count": int(slices["refused"]) + int(slices["blocked"]),
        "wall_clock_seconds": summary["elapsed_seconds"],
    }
    for field, value in expected.items():
        if metrics[field] != value:
            raise SystemExit(f"workflow metrics artifact {field} does not match competition summary")
    if not isinstance(metrics["per_unit_statuses"], list):
        raise SystemExit("workflow metrics artifact per_unit_statuses must be an array")
    if len(metrics["per_unit_statuses"]) != int(metrics["units_total"]):
        raise SystemExit("workflow metrics artifact per_unit_statuses count does not match units_total")
    validate_translation_before_after_summary(metrics)
    validate_per_unit_statuses(metrics, summary_path=summary_path, repo_root=repo_root)
    validate_root_unsafe_reduction_consistency(metrics)
    validate_root_cause_counts(metrics)


def validate_translation_before_after_summary(metrics: dict[str, Any]) -> None:
    summary = metrics.get("translation_before_after")
    if not isinstance(summary, dict):
        raise SystemExit("workflow metrics artifact translation_before_after must be an object")
    status = summary.get("status")
    if status not in {"bound", "not_provided"}:
        raise SystemExit("workflow metrics artifact translation_before_after.status is invalid")
    unit_count = summary.get("unit_count")
    measured_count = summary.get("measured_unsafe_unit_count")
    patch_count = summary.get("accepted_patch_unit_count")
    if not isinstance(unit_count, int) or unit_count < 0:
        raise SystemExit("workflow metrics artifact translation_before_after.unit_count must be nonnegative")
    if not isinstance(measured_count, int) or measured_count < 0:
        raise SystemExit(
            "workflow metrics artifact translation_before_after.measured_unsafe_unit_count must be nonnegative"
        )
    if not isinstance(patch_count, int) or patch_count < 0:
        raise SystemExit(
            "workflow metrics artifact translation_before_after.accepted_patch_unit_count must be nonnegative"
        )
    units = summary.get("units")
    if not isinstance(units, list) or len(units) != unit_count:
        raise SystemExit("workflow metrics artifact translation_before_after.units count must match unit_count")
    actual_count = sum(
        1 for unit in metrics["per_unit_statuses"] if isinstance(unit, dict) and isinstance(unit.get("translation_before_after"), dict)
    )
    if actual_count != unit_count:
        raise SystemExit("workflow metrics artifact translation_before_after.unit_count does not match per-unit evidence")
    if status == "not_provided" and unit_count != 0:
        raise SystemExit("workflow metrics artifact translation_before_after not_provided status requires zero units")
    if status == "bound" and unit_count == 0:
        raise SystemExit("workflow metrics artifact translation_before_after bound status requires units")


def validate_per_unit_statuses(
    metrics: dict[str, Any],
    *,
    summary_path: Path,
    repo_root: Path,
) -> None:
    for index, unit in enumerate(metrics["per_unit_statuses"]):
        if not isinstance(unit, dict):
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}] must be an object")
        root_cause = unit.get("root_cause_key")
        if root_cause is not None and (not isinstance(root_cause, str) or not root_cause):
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}].root_cause_key must be a non-empty string")
        contract_verification = unit.get("opencode_contract_verification")
        if contract_verification is not None:
            if not isinstance(contract_verification, dict) or not isinstance(contract_verification.get("status"), str):
                raise SystemExit(
                    f"workflow metrics per_unit_statuses[{index}].opencode_contract_verification.status "
                    "must be a string"
                )
        before_after = unit.get("translation_before_after")
        if before_after is not None:
            validate_translation_before_after_unit(
                before_after,
                unit=unit,
                index=index,
                summary_path=summary_path,
                repo_root=repo_root,
            )
        if "repair_rounds" not in unit:
            continue
        repair_rounds = unit["repair_rounds"]
        if not isinstance(repair_rounds, int) or repair_rounds < 1:
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}].repair_rounds must be a positive integer")
        if not isinstance(unit.get("auto_recovered"), bool):
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}].auto_recovered must be boolean")
        repair_history = unit.get("repair_history")
        if not isinstance(repair_history, dict):
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}] missing repair_history")
        patch_events_ref = repair_history.get("patch_events_path")
        patch_events_sha = repair_history.get("patch_events_sha256")
        if not isinstance(patch_events_ref, str) or not is_repo_relative_posix_path(patch_events_ref):
            raise SystemExit(
                f"workflow metrics per_unit_statuses[{index}].repair_history.patch_events_path "
                "must be repo-relative POSIX"
            )
        if not isinstance(patch_events_sha, str) or len(patch_events_sha) != 64:
            raise SystemExit(
                f"workflow metrics per_unit_statuses[{index}].repair_history.patch_events_sha256 must be sha256"
            )
        patch_events_path = resolve_summary_artifact(
            patch_events_ref,
            summary_path=summary_path,
            repo_root=repo_root,
        )
        if patch_events_path is None:
            raise SystemExit(
                f"workflow metrics per_unit_statuses[{index}].repair_history.patch_events_path does not exist: "
                f"{patch_events_ref}"
            )
        if sha256(patch_events_path) != patch_events_sha:
            raise SystemExit(
                f"workflow metrics per_unit_statuses[{index}].repair_history.patch_events_sha256 does not match"
            )
        statuses = repair_history.get("statuses")
        if not isinstance(statuses, list) or not all(isinstance(status, str) for status in statuses):
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}].repair_history.statuses must be strings")
        rollback_ids = repair_history.get("rollback_ids")
        if not isinstance(rollback_ids, list) or not all(isinstance(item, str) for item in rollback_ids):
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}].repair_history.rollback_ids must be strings")
        verified = repair_history.get("verified")
        if not isinstance(verified, bool):
            raise SystemExit(f"workflow metrics per_unit_statuses[{index}].repair_history.verified must be boolean")
        if unit["auto_recovered"] and (not verified or "verified" not in statuses):
            raise SystemExit(
                f"workflow metrics per_unit_statuses[{index}] auto_recovered requires verified repair history"
            )


def validate_translation_before_after_unit(
    evidence: Any,
    *,
    unit: dict[str, Any],
    index: int,
    summary_path: Path,
    repo_root: Path,
) -> None:
    if not isinstance(evidence, dict):
        raise SystemExit(f"workflow metrics per_unit_statuses[{index}].translation_before_after must be an object")
    status = evidence.get("status")
    if status != "bound":
        raise SystemExit(f"workflow metrics per_unit_statuses[{index}].translation_before_after.status must be bound")
    for key in ["baseline", "final", "oracle_evidence", "accepted_patch"]:
        validate_before_after_artifact_ref(
            evidence.get(key),
            key=key,
            unit=unit,
            index=index,
            summary_path=summary_path,
            repo_root=repo_root,
        )
    patch_log = evidence.get("patch_log")
    if patch_log is not None:
        validate_before_after_artifact_ref(
            patch_log,
            key="patch_log",
            unit=unit,
            index=index,
            summary_path=summary_path,
            repo_root=repo_root,
        )
    baseline_verification = evidence.get("baseline_verification")
    if baseline_verification is not None:
        baseline_verification_path = validate_before_after_artifact_ref(
            baseline_verification,
            key="baseline_verification",
            unit=unit,
            index=index,
            summary_path=summary_path,
            repo_root=repo_root,
        )
        validate_before_after_baseline_verification(
            baseline_verification,
            baseline_verification_path,
            index=index,
        )
    unsafe_reduction = evidence.get("unsafe_reduction")
    if not isinstance(unsafe_reduction, dict) or unsafe_reduction.get("status") != "measured":
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.unsafe_reduction "
            "must be measured"
        )
    baseline = nonnegative_count(unsafe_reduction.get("baseline_total_unsafe"))
    current = nonnegative_count(unsafe_reduction.get("current_total_unsafe"))
    reduced_by = nonnegative_count(unsafe_reduction.get("reduced_by"))
    if baseline is None or current is None or reduced_by is None:
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.unsafe_reduction "
            "requires nonnegative baseline/current/reduced_by"
        )
    if baseline - current != reduced_by or reduced_by <= 0:
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.unsafe_reduction "
            "must strictly reduce unsafe"
        )


def validate_root_unsafe_reduction_consistency(metrics: dict[str, Any]) -> None:
    measured_units = []
    for unit in metrics["per_unit_statuses"]:
        if not isinstance(unit, dict):
            continue
        before_after = unit.get("translation_before_after")
        if not isinstance(before_after, dict):
            continue
        unsafe_reduction = before_after.get("unsafe_reduction")
        if isinstance(unsafe_reduction, dict) and unsafe_reduction.get("status") == "measured":
            measured_units.append(unsafe_reduction)
    if len(measured_units) != int(metrics["units_total"]):
        return

    baseline_total = 0
    current_total = 0
    for unsafe_reduction in measured_units:
        baseline = nonnegative_count(unsafe_reduction.get("baseline_total_unsafe"))
        current = nonnegative_count(unsafe_reduction.get("current_total_unsafe"))
        reduced_by = nonnegative_count(unsafe_reduction.get("reduced_by"))
        if baseline is None or current is None or reduced_by is None or baseline - current != reduced_by:
            raise SystemExit("workflow metrics translation_before_after unsafe_reduction counts are inconsistent")
        baseline_total += baseline
        current_total += current

    root = metrics.get("unsafe_reduction")
    expected = {
        "status": "measured",
        "baseline_total_unsafe": baseline_total,
        "current_total_unsafe": current_total,
        "reduced_by": baseline_total - current_total,
        "ratio": 0.0 if baseline_total == 0 else current_total / baseline_total,
    }
    if not isinstance(root, dict) or root.get("status") != "measured":
        raise SystemExit("workflow metrics unsafe_reduction does not match translation_before_after units")
    for field in ["baseline_total_unsafe", "current_total_unsafe", "reduced_by"]:
        if root.get(field) != expected[field]:
            raise SystemExit("workflow metrics unsafe_reduction does not match translation_before_after units")
    ratio = root.get("ratio")
    if not isinstance(ratio, (int, float)) or abs(float(ratio) - float(expected["ratio"])) > 1e-12:
        raise SystemExit("workflow metrics unsafe_reduction does not match translation_before_after units")


def validate_before_after_artifact_ref(
    artifact: Any,
    *,
    key: str,
    unit: dict[str, Any],
    index: int,
    summary_path: Path,
    repo_root: Path,
) -> Path:
    if not isinstance(artifact, dict):
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.{key} must be an object"
        )
    artifact_ref = artifact.get("path")
    artifact_sha = artifact.get("sha256")
    if not isinstance(artifact_ref, str) or not is_repo_relative_posix_path(artifact_ref):
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.{key}.path "
            "must be repo-relative POSIX"
        )
    if not isinstance(artifact_sha, str) or len(artifact_sha) != 64:
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.{key}.sha256 must be sha256"
        )
    artifact_path = resolve_unit_artifact(
        artifact_ref,
        unit=unit,
        summary_path=summary_path,
        repo_root=repo_root,
    )
    if artifact_path is None:
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.{key}.path "
            f"does not exist: {artifact_ref}"
        )
    if sha256(artifact_path) != artifact_sha:
        raise SystemExit(
            f"workflow metrics per_unit_statuses[{index}].translation_before_after.{key}.sha256 does not match"
        )
    return artifact_path


def validate_before_after_baseline_verification(artifact: dict[str, Any], artifact_path: Path, *, index: int) -> None:
    prefix = f"workflow metrics per_unit_statuses[{index}].translation_before_after.baseline_verification"
    if artifact.get("status") is not None and artifact.get("status") != "passed":
        raise SystemExit(f"{prefix}.status must be passed")
    if artifact.get("semantic_pass") is not None and artifact.get("semantic_pass") is not True:
        raise SystemExit(f"{prefix}.semantic_pass must be true")
    if artifact.get("semantic_claim_source") is not None and artifact.get("semantic_claim_source") != "verified_unsafe_baseline_gates":
        raise SystemExit(f"{prefix}.semantic_claim_source must be verified_unsafe_baseline_gates")
    if artifact.get("generated_draft_semantic_pass") is not None and artifact.get("generated_draft_semantic_pass") is not False:
        raise SystemExit(f"{prefix}.generated_draft_semantic_pass must be false")
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{prefix} artifact must be JSON") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{prefix} artifact must be an object")
    if payload.get("status") != "passed":
        raise SystemExit(f"{prefix}.status must be passed")
    if payload.get("semantic_pass") is not True:
        raise SystemExit(f"{prefix}.semantic_pass must be true")
    if payload.get("semantic_claim_source") != "verified_unsafe_baseline_gates":
        raise SystemExit(f"{prefix}.semantic_claim_source must be verified_unsafe_baseline_gates")
    if payload.get("generated_draft_semantic_pass") is not False:
        raise SystemExit(f"{prefix}.generated_draft_semantic_pass must be false")


def resolve_unit_artifact(
    value: str,
    *,
    unit: dict[str, Any],
    summary_path: Path,
    repo_root: Path,
) -> Path | None:
    candidates = [
        repo_root / value,
        summary_path.parent / value,
        summary_path.parent.parent / value,
    ]
    worker_summary = unit.get("worker_summary_path")
    if isinstance(worker_summary, str) and is_repo_relative_posix_path(worker_summary):
        worker_summary_path = resolve_summary_artifact(worker_summary, summary_path=summary_path, repo_root=repo_root)
        if worker_summary_path is not None:
            candidates.extend([worker_summary_path.parent / value, worker_summary_path.parent.parent / value])
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            try:
                resolved.relative_to(summary_path.parent.parent.resolve())
            except ValueError:
                continue
        if resolved.exists():
            return resolved
    return None


def validate_root_cause_counts(metrics: dict[str, Any]) -> None:
    counts = metrics.get("root_cause_counts")
    if not isinstance(counts, dict):
        raise SystemExit("workflow metrics artifact root_cause_counts must be an object")
    expected: dict[str, int] = {}
    for unit in metrics["per_unit_statuses"]:
        if not isinstance(unit, dict):
            continue
        root_cause = unit.get("root_cause_key")
        if isinstance(root_cause, str) and root_cause:
            expected[root_cause] = expected.get(root_cause, 0) + 1
    actual: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(key, str) or not key:
            raise SystemExit("workflow metrics artifact root_cause_counts keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SystemExit(f"workflow metrics artifact root_cause_counts.{key} must be a non-negative integer")
        actual[key] = value
    if actual != expected:
        raise SystemExit("workflow metrics artifact root_cause_counts does not match per_unit_statuses")


def resolve_summary_artifact(value: str, *, summary_path: Path, repo_root: Path) -> Path | None:
    candidates = [
        repo_root / value,
        summary_path.parent / value,
        summary_path.parent.parent / value,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def should_normalize_lf_for_hash(path: Path) -> bool:
    return path.suffix.lower() in LF_STABLE_TEXT_SUFFIXES


def lf_stable_file_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if not should_normalize_lf_for_hash(path):
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(lf_stable_file_bytes(path)).hexdigest()


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_final_gate(summary: dict[str, Any]) -> None:
    status = summary["final_gate"]["status"]
    semantic_pass = int(summary["slices"]["semantic_pass"])
    if status == "passed" and semantic_pass < 1:
        raise SystemExit("competition run summary final_gate passed requires slices.semantic_pass >= 1")
    validator = summary["final_gate"]["validator"]
    if status == "passed" and "--require-semantic-pass" not in validator:
        raise SystemExit("competition run summary final_gate passed requires --require-semantic-pass validator")


def validate_slice_counts(summary: dict[str, Any]) -> None:
    slices = summary["slices"]
    attempted = int(slices["attempted"])
    terminal = int(slices["semantic_pass"]) + int(slices["refused"]) + int(slices["blocked"]) + int(slices["failed"])
    if terminal > attempted:
        raise SystemExit("competition run summary terminal slice counts exceed slices.attempted")
    if int(slices["compiled"]) > int(slices["typed_ir_generated"]):
        raise SystemExit("competition run summary slices.compiled exceeds slices.typed_ir_generated")
    if int(slices["typed_ir_generated"]) > attempted:
        raise SystemExit("competition run summary slices.typed_ir_generated exceeds slices.attempted")


def validate_workers(summary: dict[str, Any]) -> None:
    workers = summary.get("workers")
    if workers is None:
        return
    summaries = workers["summaries"]
    if int(workers["count"]) != len(summaries):
        raise SystemExit("competition run summary workers.count does not match workers.summaries length")
    seen_paths: set[str] = set()
    for index, worker in enumerate(summaries):
        validate_worker_summary_path(worker["path"], index=index, seen_paths=seen_paths)
        if worker["proof_class"] != summary["proof_class"]:
            raise SystemExit(f"competition run summary workers.summaries[{index}].proof_class does not match summary")
        slices = worker["slices"]
        for key in ["attempted", "semantic_pass", "failed"]:
            if int(worker[key]) != int(slices[key]):
                raise SystemExit(f"competition run summary workers.summaries[{index}].{key} does not match slices.{key}")
        for path_key in ["assignment_request", "source_repo_root", "source_file"]:
            if path_key in worker and not is_repo_relative_posix_path(worker[path_key]):
                raise SystemExit(
                    f"competition run summary workers.summaries[{index}].{path_key} must be repo-relative POSIX"
                )
        for spec_index, slice_spec in enumerate(worker.get("slice_specs", [])):
            if not is_repo_relative_posix_path(slice_spec):
                raise SystemExit(
                    f"competition run summary workers.summaries[{index}].slice_specs[{spec_index}] must be repo-relative POSIX"
                )
        if "source_sha256" in worker and not is_sha256(str(worker["source_sha256"])):
            raise SystemExit(f"competition run summary workers.summaries[{index}].source_sha256 must be a sha256")
        if worker["status"] != "passed" and summary["final_gate"]["status"] == "passed":
            raise SystemExit("competition run summary final_gate passed with failed worker summary")


def validate_worker_summary_path(value: str, *, index: int, seen_paths: set[str]) -> None:
    if not isinstance(value, str) or not is_repo_relative_posix_path(value):
        raise SystemExit(
            f"competition run summary workers.summaries[{index}].worker summary path must be repo-relative POSIX"
        )
    parts = PurePosixPath(value).parts
    worker_relative = (
        len(parts) == 4
        and parts[0] == "workers"
        and parts[2] == "summary"
        and parts[3] == "competition-run-summary.json"
    )
    nested_run_relative = (
        len(parts) >= 5
        and parts[-4] == "workers"
        and parts[-2] == "summary"
        and parts[-1] == "competition-run-summary.json"
    )
    if not worker_relative and not nested_run_relative:
        raise SystemExit(
            "competition run summary worker summary path must match "
            "workers/<worker-id>/summary/competition-run-summary.json"
        )
    if value in seen_paths:
        raise SystemExit(f"competition run summary duplicate worker summary path: {value}")
    seen_paths.add(value)


def nonnegative_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
