#!/usr/bin/env python3
"""Build a judge-facing external milestone bundle from entrypoint evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import validate_judge_entrypoints as validator


DEFAULT_RUN_REPORT = Path("target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json")
DEFAULT_BUNDLE = Path("target/competition-out-flashdb-judge-entrypoints/summary/judge-milestone-bundle.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-report", type=Path, default=DEFAULT_RUN_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args()
    report = build_judge_milestone_bundle(
        run_report_path=args.run_report,
        out_path=args.out,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


def build_judge_milestone_bundle(
    *,
    run_report_path: Path,
    out_path: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    run_report_path = resolve_input_path(run_report_path, repo_root=repo_root)
    out_path = resolve_output_path(out_path, repo_root=repo_root)
    run_report = validator.load_json(run_report_path)
    entrypoints = [entry for entry in run_report.get("entrypoints", []) if isinstance(entry, dict)]
    readiness = run_report.get("summary", {}).get("readiness", {}) if isinstance(run_report.get("summary"), dict) else {}
    claim_boundary = milestone_claim_boundary(run_report)
    validated_artifacts = validation_artifacts_by_entrypoint(run_report.get("validation"))

    entrypoint_reports: list[dict[str, Any]] = []
    workflow_sources: list[dict[str, Any]] = []
    opencode_sources: list[dict[str, Any]] = []
    for entry in entrypoints:
        entry_report, workflow_source, opencode_source = summarize_entrypoint(
            entry,
            validated_artifacts=validated_artifacts.get(str(entry.get("id", "unknown")), {}),
            repo_root=repo_root,
        )
        entrypoint_reports.append(entry_report)
        if workflow_source is not None:
            workflow_sources.append(workflow_source)
        if opencode_source is not None:
            opencode_sources.append(opencode_source)

    blockers = milestone_blockers(run_report, readiness, claim_boundary)
    status = "passed" if not blockers else "blocked"
    report = {
        "schema_version": 1,
        "report_kind": "judge-milestone-bundle",
        "status": status,
        "blockers": blockers,
        "judge_entrypoints_run_report": artifact_ref(run_report_path, repo_root=repo_root),
        "readiness_report": artifact_ref_from_existing(run_report.get("readiness_report"), repo_root=repo_root),
        "summary": build_bundle_summary(
            status=status,
            run_report=run_report,
            readiness=readiness,
            blockers=blockers,
        ),
        "claim_boundary": claim_boundary,
        "entrypoints": entrypoint_reports,
        "workflow_metrics": build_workflow_metrics_rollup(workflow_sources),
        "opencode_runtime": build_opencode_runtime_rollup(opencode_sources),
        "retention_policy": build_retention_policy(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def summarize_entrypoint(
    entry: dict[str, Any],
    *,
    validated_artifacts: dict[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    artifacts = artifact_refs_from_key_artifacts(entry.get("key_artifacts", {}), repo_root=repo_root)
    artifacts.update(artifact_refs_from_key_artifacts(validated_artifacts, repo_root=repo_root))
    workflow_source = workflow_source_from_artifact(
        entrypoint_id=str(entry.get("id", "unknown")),
        artifact=artifacts.get("workflow_metrics"),
        repo_root=repo_root,
    )
    opencode_source = opencode_source_from_artifact(
        entrypoint_id=str(entry.get("id", "unknown")),
        artifact=artifacts.get("judge_evidence_index"),
        repo_root=repo_root,
    )
    return (
        {
            "id": entry.get("id"),
            "purpose": entry.get("purpose"),
            "status": entry.get("status"),
            "exit_code": entry.get("exit_code"),
            "proof_class": entry.get("proof_class", "unknown"),
            "run_id": entry.get("run_id", "unknown"),
            "judge_focus": entry.get("judge_focus", []) if isinstance(entry.get("judge_focus"), list) else [],
            "artifacts": artifacts,
            "logs": entry.get("logs", {}),
        },
        workflow_source,
        opencode_source,
    )


def validation_artifacts_by_entrypoint(validation: object) -> dict[str, dict[str, Any]]:
    if not isinstance(validation, dict) or not isinstance(validation.get("entrypoints"), list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in validation["entrypoints"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        expected = entry.get("expected_artifacts")
        if isinstance(expected, dict):
            result[entry["id"]] = expected
    return result


def milestone_claim_boundary(run_report: dict[str, Any]) -> dict[str, Any]:
    summary_claim = {}
    if isinstance(run_report.get("summary"), dict) and isinstance(run_report["summary"].get("claim_boundary"), dict):
        summary_claim = run_report["summary"]["claim_boundary"]
    source_claim = run_report.get("claim_boundary", {}) if isinstance(run_report.get("claim_boundary"), dict) else {}
    return {
        "semantic_gate": False,
        "semantic_claim_source": summary_claim.get(
            "semantic_claim_source",
            source_claim.get("semantic_claim_source", "validator-owned-artifacts"),
        ),
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "bundle_is_semantic_gate": False,
        "source_semantic_gate": bool(summary_claim.get("semantic_gate", source_claim.get("semantic_gate", False))),
        "boundary": (
            "This bundle indexes judge entrypoint artifacts and workflow metrics for external review. "
            "It does not perform semantic acceptance; semantic acceptance remains owned by validators, "
            "oracle evidence, Rust replay, diff gates, unsafe ledgers, and hash-bound summaries."
        ),
    }


def milestone_blockers(
    run_report: dict[str, Any],
    readiness: dict[str, Any],
    claim_boundary: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if run_report.get("status") != "passed":
        blockers.append("judge_entrypoints_not_passed")
    if not readiness.get("all_entrypoints_executed"):
        blockers.append("not_all_entrypoints_executed")
    if readiness.get("validation_status") != "passed":
        blockers.append("validation_not_passed")
    if claim_boundary.get("source_semantic_gate"):
        blockers.append("source_semantic_gate_must_be_false")
    return blockers


def build_bundle_summary(
    *,
    status: str,
    run_report: dict[str, Any],
    readiness: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    executed = int_or_zero(readiness.get("executed_count"))
    configured = int_or_zero(readiness.get("configured_count"))
    return {
        "report_kind": "judge-milestone-bundle-summary",
        "headline": (
            f"External milestone bundle {status}: judge entrypoints {run_report.get('status', 'unknown')}; "
            f"{executed}/{configured} executed; semantic_gate=false"
        ),
        "source_run_headline": run_report.get("summary", {}).get("headline")
        if isinstance(run_report.get("summary"), dict)
        else None,
        "external_milestone_claim_ready": status == "passed",
        "blockers": blockers,
        "readiness": {
            "all_entrypoints_executed": bool(readiness.get("all_entrypoints_executed")),
            "executed_count": executed,
            "configured_count": configured,
            "validation_status": readiness.get("validation_status", "unknown"),
        },
    }


def artifact_refs_from_key_artifacts(value: object, *, repo_root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    refs: dict[str, Any] = {}
    for key, raw_ref in value.items():
        ref = artifact_ref_from_existing(raw_ref, repo_root=repo_root)
        if ref is not None:
            refs[str(key)] = ref
    return refs


def artifact_ref_from_existing(value: object, *, repo_root: Path) -> dict[str, Any] | None:
    path_text: str | None = None
    if isinstance(value, str):
        path_text = value
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        path_text = value["path"]
    if path_text is None:
        return None
    try:
        path = resolve_input_path(Path(path_text), repo_root=repo_root)
    except (OSError, ValueError):
        return {"path": path_text, "status": "invalid"}
    return artifact_ref(path, repo_root=repo_root)


def workflow_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    unsafe_reduction = payload.get("unsafe_reduction", {}) if isinstance(payload.get("unsafe_reduction"), dict) else {}
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "units_total": int_or_zero(payload.get("units_total")),
        "units_converged": int_or_zero(payload.get("units_converged")),
        "avg_repair_rounds": number_or_zero(payload.get("avg_repair_rounds")),
        "auto_recovery_rate": number_or_zero(payload.get("auto_recovery_rate")),
        "human_interventions": int_or_zero(payload.get("human_interventions")),
        "llm_calls": int_or_zero(payload.get("llm_calls")),
        "unsafe_reduction_status": unsafe_reduction.get("status", "unknown"),
        "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
        "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
        "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
    }


def opencode_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    headline = payload.get("judge_headline", {}) if isinstance(payload.get("judge_headline"), dict) else {}
    runtime = payload.get("opencode_agent_runtime", {}) if isinstance(payload.get("opencode_agent_runtime"), dict) else {}
    headline_runtime = headline.get("opencode_runtime", {}) if isinstance(headline.get("opencode_runtime"), dict) else {}
    enabled = bool(headline_runtime.get("enabled", runtime.get("runtime") == "opencode"))
    if not enabled:
        return None
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "worker_count": int_or_zero(headline_runtime.get("worker_count", runtime.get("worker_count"))),
        "all_contracts_executed": bool(
            headline_runtime.get("all_contracts_executed", runtime.get("all_contracts_executed"))
        ),
        "chat_output_is_evidence": bool(
            headline_runtime.get("chat_output_is_evidence", runtime.get("chat_output_is_evidence", False))
        ),
        "semantic_gate": bool(headline_runtime.get("semantic_gate", runtime.get("semantic_gate", False))),
        "repair_round_cap": int_or_zero(headline.get("repair_round_cap")),
    }


def build_workflow_metrics_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    measured_sources = [source for source in sources if source.get("unsafe_reduction_status") == "measured"]
    baseline_values = [source.get("baseline_total_unsafe") for source in measured_sources]
    current_values = [source.get("current_total_unsafe") for source in measured_sources]
    reduced_values = [source.get("reduced_by") for source in measured_sources]
    measured_complete = all(value is not None for value in baseline_values + current_values + reduced_values)
    return {
        "report_kind": "workflow-metrics-rollup",
        "sources": sources,
        "rollup": {
            "source_count": len(sources),
            "units_total": sum(int_or_zero(source.get("units_total")) for source in sources),
            "units_converged": sum(int_or_zero(source.get("units_converged")) for source in sources),
            "human_interventions": sum(int_or_zero(source.get("human_interventions")) for source in sources),
            "llm_calls": sum(int_or_zero(source.get("llm_calls")) for source in sources),
            "measured_unsafe_reduction_source_count": len(measured_sources),
            "unsafe_reduction": {
                "status": "measured" if measured_sources else "not_measured",
                "baseline_total_unsafe": sum(baseline_values) if measured_complete else None,
                "current_total_unsafe": sum(current_values) if measured_complete else None,
                "reduced_by": sum(reduced_values) if measured_complete else None,
            },
        },
    }


def build_opencode_runtime_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "report_kind": "opencode-runtime-rollup",
        "sources": sources,
        "enabled_entrypoint_count": len(sources),
        "worker_count": sum(int_or_zero(source.get("worker_count")) for source in sources),
        "all_contracts_executed": bool(sources) and all(bool(source.get("all_contracts_executed")) for source in sources),
        "chat_output_is_evidence_false": all(not bool(source.get("chat_output_is_evidence")) for source in sources),
        "semantic_gate_false": all(not bool(source.get("semantic_gate")) for source in sources),
    }


def build_retention_policy() -> dict[str, Any]:
    return {
        "report_kind": "milestone-retention-policy",
        "bundle_role": "external-review-index",
        "target_artifacts": {
            "retention_class": "reproducible-local-output",
            "committed": False,
            "policy": "Regenerate from the judge entrypoint commands; bind by repo-relative path and sha256.",
        },
        "committed_manifests": {
            "retention_class": "release-evidence",
            "policy": "Use validation/evidence manifests and config/competition-env profiles as committed anchors.",
        },
        "claim_boundary": "Retention policy does not expand semantic acceptance or translation coverage.",
    }


def load_present_json_artifact(artifact: dict[str, Any] | None, *, repo_root: Path) -> dict[str, Any] | None:
    if not isinstance(artifact, dict) or artifact.get("status") != "present":
        return None
    path_text = artifact.get("path")
    if not isinstance(path_text, str):
        return None
    try:
        return validator.load_json(resolve_input_path(Path(path_text), repo_root=repo_root))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def artifact_ref(path: Path, *, repo_root: Path) -> dict[str, Any]:
    ref = {
        "path": validator.repo_relative(path, repo_root),
        "status": "present" if path.is_file() else "missing",
    }
    if path.is_file():
        ref["sha256"] = validator.sha256_file(path)
    return ref


def resolve_input_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root)
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def resolve_output_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root)
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def number_or_zero(value: object) -> int | float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
