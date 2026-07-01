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
    run_report_contract = run_report_contract_blockers(run_report, entrypoints=entrypoints)
    proof_class_contract = validation_proof_class_contract(run_report)
    proof_class_contract_errors = proof_class_contract_blockers(
        entrypoints,
        proof_class_contract=proof_class_contract,
    )

    entrypoint_reports: list[dict[str, Any]] = []
    workflow_sources: list[dict[str, Any]] = []
    opencode_sources: list[dict[str, Any]] = []
    core_quality_sources: list[dict[str, Any]] = []
    architecture_sources: list[dict[str, Any]] = []
    route_governance_sources: list[dict[str, Any]] = []
    evidence_cost_sources: list[dict[str, Any]] = []
    for entry in entrypoints:
        (
            entry_report,
            workflow_source,
            opencode_source,
            core_quality_source,
            architecture_source,
            route_governance_source,
            evidence_cost_source,
        ) = summarize_entrypoint(
            entry,
            validated_artifacts=validated_artifacts.get(str(entry.get("id", "unknown")), {}),
            proof_class=trusted_entrypoint_proof_class(entry, proof_class_contract=proof_class_contract),
            repo_root=repo_root,
        )
        entrypoint_reports.append(entry_report)
        if workflow_source is not None:
            workflow_sources.append(workflow_source)
        if opencode_source is not None:
            opencode_sources.append(opencode_source)
        if core_quality_source is not None:
            core_quality_sources.append(core_quality_source)
        if architecture_source is not None:
            architecture_sources.append(architecture_source)
        if route_governance_source is not None:
            route_governance_sources.append(route_governance_source)
        if evidence_cost_source is not None:
            evidence_cost_sources.append(evidence_cost_source)

    proof_classes = build_proof_classes(entrypoint_reports)
    workflow_metrics = build_workflow_metrics_rollup(workflow_sources)
    core_translation_quality = build_core_translation_quality_rollup(core_quality_sources)
    before_after_repair_exhibit = build_before_after_repair_exhibit_rollup(core_quality_sources)
    harness_architecture_summary = build_harness_architecture_summary(architecture_sources)
    route_governance_metrics = build_route_governance_metrics_rollup(route_governance_sources)
    blocked_repairs_rollup = build_blocked_repairs_rollup(route_governance_sources)
    evidence_cost_retention = build_evidence_cost_retention_rollup(evidence_cost_sources)
    opencode_runtime = build_opencode_runtime_rollup(opencode_sources)
    opencode_policy = build_opencode_evidence_policy(opencode_sources)
    unsafe_scope = build_unsafe_reduction_scope(workflow_sources)
    semantic_evidence = build_semantic_evidence_rollup(run_report)
    blockers = milestone_blockers(
        run_report,
        readiness,
        claim_boundary,
        run_report_contract=run_report_contract,
        proof_class_contract_errors=proof_class_contract_errors,
        opencode_policy=opencode_policy,
        core_translation_quality=core_translation_quality,
        before_after_repair_exhibit=before_after_repair_exhibit,
        blocked_repairs_rollup=blocked_repairs_rollup,
        route_governance_metrics=route_governance_metrics,
        evidence_cost_retention=evidence_cost_retention,
    )
    status = "passed" if not blockers else "blocked"
    claim_scope = build_claim_scope(status=status, proof_classes=proof_classes, semantic_evidence=semantic_evidence)
    publishability = build_publishability(status=status, readiness=readiness, proof_classes=proof_classes)
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
            claim_scope=claim_scope,
        ),
        "claim_boundary": claim_boundary,
        "claim_scope": claim_scope,
        "proof_classes": proof_classes,
        "proof_class_rollup": proof_classes,
        "publishability": publishability,
        "semantic_evidence_rollup": semantic_evidence,
        "core_translation_quality": core_translation_quality,
        "before_after_repair_exhibit": before_after_repair_exhibit,
        "blocked_repairs_rollup": blocked_repairs_rollup,
        "harness_architecture_summary": harness_architecture_summary,
        "route_governance_metrics": route_governance_metrics,
        "evidence_cost_retention": evidence_cost_retention,
        "entrypoints": entrypoint_reports,
        "workflow_metrics": workflow_metrics,
        "unsafe_reduction_scope": unsafe_scope,
        "opencode_runtime": opencode_runtime,
        "opencode_evidence_policy": opencode_policy,
        "must_not_claim": build_must_not_claim(opencode_runtime),
        "known_gaps": build_known_gaps(proof_classes=proof_classes, opencode_runtime=opencode_runtime),
        "reproduction_commands": build_reproduction_commands(
            run_report=run_report,
            run_report_path=run_report_path,
            repo_root=repo_root,
        ),
        "retention_policy": build_retention_policy(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def summarize_entrypoint(
    entry: dict[str, Any],
    *,
    validated_artifacts: dict[str, Any],
    proof_class: str,
    repo_root: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
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
    core_quality_source = core_translation_quality_source_from_artifact(
        entrypoint_id=str(entry.get("id", "unknown")),
        artifact=artifacts.get("judge_evidence_index"),
        repo_root=repo_root,
    )
    architecture_source = harness_architecture_source_from_artifact(
        entrypoint_id=str(entry.get("id", "unknown")),
        artifact=artifacts.get("judge_evidence_index"),
        repo_root=repo_root,
    )
    route_governance_source = route_governance_metrics_source_from_artifact(
        entrypoint_id=str(entry.get("id", "unknown")),
        artifact=artifacts.get("route_governance_metrics_report"),
        repo_root=repo_root,
    )
    evidence_cost_source = evidence_cost_retention_source_from_artifact(
        entrypoint_id=str(entry.get("id", "unknown")),
        artifact=artifacts.get("evidence_governance_report"),
        repo_root=repo_root,
    )
    return (
        {
            "id": entry.get("id"),
            "purpose": entry.get("purpose"),
            "status": entry.get("status"),
            "exit_code": entry.get("exit_code"),
            "proof_class": proof_class,
            "source_proof_class": entry.get("proof_class", "unknown"),
            "run_id": entry.get("run_id", "unknown"),
            "judge_focus": entry.get("judge_focus", []) if isinstance(entry.get("judge_focus"), list) else [],
            "artifacts": artifacts,
            "logs": entry.get("logs", {}),
        },
        workflow_source,
        opencode_source,
        core_quality_source,
        architecture_source,
        route_governance_source,
        evidence_cost_source,
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
    *,
    run_report_contract: list[str],
    proof_class_contract_errors: list[str],
    opencode_policy: dict[str, Any],
    core_translation_quality: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
    blocked_repairs_rollup: dict[str, Any],
    route_governance_metrics: dict[str, Any],
    evidence_cost_retention: dict[str, Any],
) -> list[str]:
    blockers: list[str] = list(run_report_contract) + list(proof_class_contract_errors)
    if run_report.get("status") != "passed":
        blockers.append("judge_entrypoints_not_passed")
    if not readiness.get("all_entrypoints_executed"):
        blockers.append("not_all_entrypoints_executed")
    if readiness.get("validation_status") != "passed":
        blockers.append("validation_not_passed")
    if claim_boundary.get("source_semantic_gate"):
        blockers.append("source_semantic_gate_must_be_false")
    summary_claim = source_summary_claim(run_report)
    if bool(summary_claim.get("generated_draft_semantic_pass")):
        blockers.append("source_generated_draft_semantic_pass_must_be_false")
    if int_or_zero(summary_claim.get("translation_coverage_numerator")) != 0:
        blockers.append("source_translation_coverage_numerator_must_be_zero")
    if opencode_policy.get("enabled") and not opencode_policy.get("boundary_fields_explicit"):
        blockers.append("opencode_runtime_boundary_fields_missing")
    if opencode_policy.get("enabled") and not opencode_policy.get("chat_output_is_evidence_false"):
        blockers.append("opencode_chat_output_must_not_be_evidence")
    if opencode_policy.get("enabled") and not opencode_policy.get("semantic_gate_false"):
        blockers.append("opencode_semantic_gate_must_be_false")
    if bool(core_translation_quality.get("generated_draft_semantic_pass")):
        blockers.append("core_quality_generated_draft_semantic_pass_must_be_false")
    if int_or_zero(core_translation_quality.get("translation_coverage_numerator")) != 0:
        blockers.append("core_quality_translation_coverage_numerator_must_be_zero")
    blockers.extend(repair_accounting_consistency_blockers(before_after_repair_exhibit))
    blockers.extend(blocked_repairs_rollup_blockers(blocked_repairs_rollup))
    route_rollup = (
        route_governance_metrics.get("rollup", {})
        if isinstance(route_governance_metrics.get("rollup"), dict)
        else {}
    )
    if int_or_zero(route_rollup.get("translation_coverage_numerator")) != 0:
        blockers.append("route_governance_translation_coverage_numerator_must_be_zero")
    if int_or_zero(route_rollup.get("source_count")) > 0 and not route_rollup.get("all_retention_policies_present"):
        blockers.append("route_governance_metrics_retention_policy_missing")
    if int_or_zero(route_rollup.get("source_count")) > 0 and not route_rollup.get("all_target_artifacts_reproducible"):
        blockers.append("route_governance_metrics_target_artifacts_must_be_reproducible")
    evidence_rollup = (
        evidence_cost_retention.get("rollup", {})
        if isinstance(evidence_cost_retention.get("rollup"), dict)
        else {}
    )
    if int_or_zero(evidence_rollup.get("source_count")) > 0 and not evidence_rollup.get("all_sources_passed"):
        blockers.append("evidence_cost_retention_sources_must_pass")
    return blockers


def repair_accounting_consistency_blockers(before_after_repair_exhibit: dict[str, Any]) -> list[str]:
    rollup = (
        before_after_repair_exhibit.get("rollup", {})
        if isinstance(before_after_repair_exhibit.get("rollup"), dict)
        else {}
    )
    blockers: list[str] = []
    observed = int_or_zero(rollup.get("observed_repair_unit_count"))
    auto_recovered = int_or_zero(rollup.get("auto_recovered_unit_count"))
    rollback_evidence_count = int_or_zero(rollup.get("rollback_evidence_count"))
    unsafe_reduced_by = int_or_zero(rollup.get("unsafe_reduced_by"))
    unsafe_reduction = rollup.get("unsafe_reduction", {}) if isinstance(rollup.get("unsafe_reduction"), dict) else {}
    baseline_total_unsafe = int_or_none(unsafe_reduction.get("baseline_total_unsafe"))
    if auto_recovered > observed:
        blockers.append("repair_accounting_auto_recovered_exceeds_observed")
    if baseline_total_unsafe is not None and unsafe_reduced_by > baseline_total_unsafe:
        blockers.append("repair_accounting_unsafe_reduced_by_exceeds_measured_baseline")
    if observed > 0 and rollback_evidence_count == 0:
        blockers.append("repair_accounting_rollback_evidence_missing_for_observed_repairs")
    return blockers


def blocked_repairs_rollup_blockers(blocked_repairs_rollup: dict[str, Any]) -> list[str]:
    rollup = (
        blocked_repairs_rollup.get("rollup", {})
        if isinstance(blocked_repairs_rollup.get("rollup"), dict)
        else {}
    )
    status_counts = rollup.get("status_counts", {}) if isinstance(rollup.get("status_counts"), dict) else {}
    if int_or_zero(status_counts.get("stale")) > 0 or int_or_zero(status_counts.get("incomplete")) > 0:
        return ["blocked_repairs_rollup_stale_or_incomplete"]
    return []


def run_report_contract_blockers(run_report: dict[str, Any], *, entrypoints: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    if run_report.get("schema_version") != 1:
        blockers.append("run_report_schema_version_must_be_1")
    if run_report.get("report_kind") != "judge-entrypoints-run-report":
        blockers.append("run_report_kind_must_be_judge_entrypoints_run_report")
    entrypoint_count = run_report.get("entrypoint_count")
    if isinstance(entrypoint_count, int) and entrypoint_count != len(entrypoints):
        blockers.append("run_report_entrypoint_count_mismatch")
    validation = run_report.get("validation")
    if isinstance(validation, dict) and validation.get("status") not in {None, "passed"}:
        blockers.append("run_report_validation_not_passed")
    return blockers


def validation_proof_class_contract(run_report: dict[str, Any]) -> dict[str, str]:
    validation = run_report.get("validation")
    if not isinstance(validation, dict):
        return {}
    contract = validation.get("proof_class_contract")
    if not isinstance(contract, dict) or contract.get("status") != "passed":
        return {}
    entrypoints = contract.get("entrypoints")
    if not isinstance(entrypoints, dict):
        return {}
    return {
        str(entrypoint_id): proof_class
        for entrypoint_id, proof_class in entrypoints.items()
        if isinstance(proof_class, str)
    }


def proof_class_contract_blockers(
    entrypoints: list[dict[str, Any]],
    *,
    proof_class_contract: dict[str, str],
) -> list[str]:
    blockers: list[str] = []
    for entry in entrypoints:
        entrypoint_id = str(entry.get("id", "unknown"))
        source_proof_class = entry.get("proof_class", "unknown")
        contract_proof_class = proof_class_contract.get(entrypoint_id)
        if contract_proof_class is not None and source_proof_class != contract_proof_class:
            blockers.append(f"proof_class_contract_mismatch:{entrypoint_id}")
        if contract_proof_class is None and source_proof_class == "competition-exact":
            blockers.append(f"proof_class_contract_missing_for_competition_exact:{entrypoint_id}")
    return blockers


def trusted_entrypoint_proof_class(
    entry: dict[str, Any],
    *,
    proof_class_contract: dict[str, str],
) -> str:
    entrypoint_id = str(entry.get("id", "unknown"))
    contract_proof_class = proof_class_contract.get(entrypoint_id)
    if contract_proof_class is not None:
        return contract_proof_class
    source_proof_class = entry.get("proof_class", "unknown")
    if source_proof_class == "competition-exact":
        return "unknown"
    return source_proof_class if isinstance(source_proof_class, str) else "unknown"


def source_summary_claim(run_report: dict[str, Any]) -> dict[str, Any]:
    summary = run_report.get("summary")
    if not isinstance(summary, dict):
        return {}
    claim = summary.get("claim_boundary")
    return claim if isinstance(claim, dict) else {}


def build_bundle_summary(
    *,
    status: str,
    run_report: dict[str, Any],
    readiness: dict[str, Any],
    blockers: list[str],
    claim_scope: dict[str, Any],
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
        "claim_scope": claim_scope,
        "blockers": blockers,
        "readiness": {
            "all_entrypoints_executed": bool(readiness.get("all_entrypoints_executed")),
            "executed_count": executed,
            "configured_count": configured,
            "validation_status": readiness.get("validation_status", "unknown"),
        },
    }


def build_proof_classes(entrypoints: list[dict[str, Any]]) -> dict[str, Any]:
    entrypoint_proofs = [
        {
            "id": entry.get("id"),
            "proof_class": entry.get("proof_class", "unknown"),
            "run_id": entry.get("run_id", "unknown"),
        }
        for entry in entrypoints
    ]
    proof_classes = sorted(
        {
            str(entry.get("proof_class", "unknown"))
            for entry in entrypoints
            if isinstance(entry.get("proof_class", "unknown"), str)
        }
    )
    rank = {"unknown": 0, "local-simulation": 1, "wsl-local-simulation": 2, "ci-approximation": 3, "competition-exact": 4}
    highest = max(proof_classes, key=lambda value: rank.get(value, 0), default="unknown")
    non_exact = [entry for entry in entrypoint_proofs if entry.get("proof_class") != "competition-exact"]
    return {
        "all": proof_classes,
        "highest_proof_class": highest,
        "has_competition_exact": "competition-exact" in proof_classes,
        "all_entrypoints_competition_exact": bool(entrypoint_proofs) and not non_exact,
        "competition_exact_host_verified": bool(entrypoint_proofs) and not non_exact,
        "non_exact_entrypoints": non_exact,
        "entrypoints": entrypoint_proofs,
        "boundary": (
            "Proof class describes the execution environment for this bundle. "
            "local-simulation, wsl-local-simulation, and ci-approximation must not be described as competition-exact."
        ),
    }


def build_claim_scope(
    *,
    status: str,
    proof_classes: dict[str, Any],
    semantic_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "external_review_index_ready": status == "passed",
        "semantic_acceptance_ready": False,
        "competition_exact_ready": bool(proof_classes.get("all_entrypoints_competition_exact")),
        "translator_generated_coverage_ready": int_or_zero(
            semantic_evidence.get("translation_coverage_numerator")
        )
        > 0,
        "boundary": (
            "A passed bundle means the external review index is complete. It is not semantic acceptance, "
            "competition-exact proof, or translator-generated coverage."
        ),
    }


def build_publishability(
    *,
    status: str,
    readiness: dict[str, Any],
    proof_classes: dict[str, Any],
) -> dict[str, Any]:
    all_entrypoints = bool(readiness.get("all_entrypoints_executed"))
    return {
        "all_entrypoints_run_publishable": status == "passed" and all_entrypoints,
        "focused_run": not all_entrypoints,
        "competition_exact_publishable": bool(proof_classes.get("all_entrypoints_competition_exact")),
        "target_artifacts_regenerable": True,
        "committed_release_evidence_refs": "Use validation/evidence manifests and config/competition-env profiles as committed anchors.",
    }


def build_semantic_evidence_rollup(run_report: dict[str, Any]) -> dict[str, Any]:
    summary_claim = source_summary_claim(run_report)
    return {
        "semantic_claim_source": summary_claim.get("semantic_claim_source", "validator-owned-artifacts"),
        "accepted_evidence_semantic_pass_count": 0,
        "translator_generated_semantic_pass_count": 0,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "source_generated_draft_semantic_pass": bool(summary_claim.get("generated_draft_semantic_pass")),
        "source_translation_coverage_numerator": int_or_zero(summary_claim.get("translation_coverage_numerator")),
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": (
            "Accepted-evidence semantic pass counts are context only. The bundle does not increase "
            "translator-generated semantic-pass counts or translation coverage."
        ),
    }


def build_unsafe_reduction_scope(sources: list[dict[str, Any]]) -> dict[str, Any]:
    total_units = sum(int_or_zero(source.get("units_total")) for source in sources)
    measured_sources = [source for source in sources if source.get("unsafe_reduction_status") == "measured"]
    measured_units = sum(int_or_zero(source.get("units_total")) for source in measured_sources)
    unmeasured = [
        source.get("entrypoint_id")
        for source in sources
        if source.get("unsafe_reduction_status") != "measured"
    ]
    all_sources_measured = bool(sources) and len(measured_sources) == len(sources)
    if not measured_sources:
        scope = "none"
    elif all_sources_measured:
        scope = "all"
    else:
        scope = "partial"
    return {
        "scope": scope,
        "all_sources_measured": all_sources_measured,
        "measured_units": measured_units,
        "total_units": total_units,
        "unmeasured_entrypoints": unmeasured,
        "boundary": "Unsafe reduction is only global when every workflow metrics source reports measured data.",
    }


def build_core_translation_quality_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = sorted(
        {
            str(source.get("final_gate_status"))
            for source in sources
            if isinstance(source.get("final_gate_status"), str)
        }
    )
    measured = [
        source.get("unsafe_reduction", {})
        for source in sources
        if isinstance(source.get("unsafe_reduction"), dict)
        and source.get("unsafe_reduction", {}).get("status") == "measured"
    ]
    baseline_values = [value.get("baseline_total_unsafe") for value in measured]
    current_values = [value.get("current_total_unsafe") for value in measured]
    reduced_values = [value.get("reduced_by") for value in measured]
    measured_complete = all(value is not None for value in baseline_values + current_values + reduced_values)
    return {
        "report_kind": "core-translation-quality-rollup",
        "sources": sources,
        "final_gate_statuses": statuses,
        "semantic_pass_count": sum(int_or_zero(source.get("semantic_pass_count")) for source in sources),
        "translation_coverage_numerator": max(
            [int_or_zero(source.get("translation_coverage_numerator")) for source in sources],
            default=0,
        ),
        "generated_draft_semantic_pass": any(bool(source.get("generated_draft_semantic_pass")) for source in sources),
        "unsafe_reduction": {
            "status": "measured" if measured else "not_measured",
            "baseline_total_unsafe": sum(baseline_values) if measured_complete else None,
            "current_total_unsafe": sum(current_values) if measured_complete else None,
            "reduced_by": sum(reduced_values) if measured_complete else None,
        },
        "boundary": (
            "This rollup exposes judge-facing before/after quality signals from evidence indexes. "
            "It does not convert accepted-evidence context into translator-generated semantic acceptance."
        ),
    }


def build_before_after_repair_exhibit_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    exhibit_sources: list[dict[str, Any]] = []
    for source in sources:
        translation = source.get("translation_before_after", {})
        repair = source.get("repair_summary", {})
        units = source.get("before_after_units", [])
        if not isinstance(translation, dict):
            translation = before_after_summary(None)
        if not isinstance(repair, dict):
            repair = repair_summary_for_bundle(None)
        if not isinstance(units, list):
            units = []
        has_exhibit = (
            bool(units)
            or repair.get("status") == "verified"
            or int_or_zero(repair.get("observed_repair_unit_count")) > 0
            or int_or_zero(repair.get("rollback_evidence_count")) > 0
        )
        if not has_exhibit:
            continue
        exhibit_sources.append(
            {
                "entrypoint_id": source.get("entrypoint_id"),
                "artifact": source.get("artifact"),
                "final_gate_status": source.get("final_gate_status"),
                "translation_before_after": translation,
                "before_after_units": units,
                "repair_summary": repair,
                "unsafe_reduction": source.get("unsafe_reduction", {}),
                "claim_boundary": {
                    "semantic_gate": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
            }
        )

    measured = [
        source.get("unsafe_reduction", {})
        for source in exhibit_sources
        if isinstance(source.get("unsafe_reduction"), dict)
        and source.get("unsafe_reduction", {}).get("status") == "measured"
    ]
    baseline_values = [value.get("baseline_total_unsafe") for value in measured]
    current_values = [value.get("current_total_unsafe") for value in measured]
    reduced_values = [value.get("reduced_by") for value in measured]
    measured_complete = bool(measured) and all(value is not None for value in baseline_values + current_values + reduced_values)
    return {
        "report_kind": "before-after-repair-exhibit-rollup",
        "sources": exhibit_sources,
        "rollup": {
            "source_count": len(exhibit_sources),
            "bound_unit_count": sum(
                len(source.get("before_after_units", []))
                for source in exhibit_sources
                if isinstance(source.get("before_after_units"), list)
            ),
            "measured_unsafe_unit_count": sum(
                sum(
                    1
                    for unit in source.get("before_after_units", [])
                    if isinstance(unit, dict)
                    and isinstance(unit.get("unsafe_reduction"), dict)
                    and unit.get("unsafe_reduction", {}).get("status") == "measured"
                )
                for source in exhibit_sources
                if isinstance(source.get("before_after_units"), list)
            ),
            "accepted_patch_unit_count": sum(
                sum(
                    1
                    for unit in source.get("before_after_units", [])
                    if isinstance(unit, dict) and isinstance(unit.get("accepted_patch"), dict)
                )
                for source in exhibit_sources
                if isinstance(source.get("before_after_units"), list)
            ),
            "verified_repair_source_count": sum(
                1
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
                and source.get("repair_summary", {}).get("status") == "verified"
            ),
            "observed_repair_unit_count": sum(
                int_or_zero(source.get("repair_summary", {}).get("observed_repair_unit_count"))
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
            ),
            "auto_recovered_unit_count": sum(
                int_or_zero(source.get("repair_summary", {}).get("auto_recovered_unit_count"))
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
            ),
            "rollback_evidence_count": sum(
                int_or_zero(source.get("repair_summary", {}).get("rollback_evidence_count"))
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
            ),
            "repair_round_cap": max(
                [
                    int_or_zero(source.get("repair_summary", {}).get("repair_round_cap"))
                    for source in exhibit_sources
                    if isinstance(source.get("repair_summary"), dict)
                ],
                default=0,
            ),
            "unsafe_reduced_by": sum(int_or_zero(value) for value in reduced_values),
            "unsafe_reduction": {
                "status": "measured" if measured else "not_measured",
                "baseline_total_unsafe": sum(baseline_values) if measured_complete else None,
                "current_total_unsafe": sum(current_values) if measured_complete else None,
                "reduced_by": sum(reduced_values) if measured_complete else None,
            },
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": (
            "This exhibit binds before/after unsafe-reduction and repair evidence for judge review. "
            "It is not a semantic gate and does not increase translator-generated coverage."
        ),
    }


def build_harness_architecture_summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    roles = sorted(
        {
            role
            for source in sources
            for role in source.get("roles", [])
            if isinstance(role, str)
        }
    )
    graph_nodes = next(
        (
            source.get("graph_nodes")
            for source in sources
            if isinstance(source.get("graph_nodes"), list) and source.get("graph_nodes")
        ),
        [],
    )
    return {
        "report_kind": "harness-architecture-summary",
        "sources": sources,
        "graph_runtime": first_string_value(sources, "graph_runtime"),
        "graph_nodes": graph_nodes,
        "worker_count": max([int_or_zero(source.get("worker_count")) for source in sources], default=0),
        "repair_round_cap": max([int_or_zero(source.get("repair_round_cap")) for source in sources], default=0),
        "repair_checkpoint": first_string_value(sources, "repair_checkpoint"),
        "roles": roles,
        "checkpoint_backend": first_string_value(sources, "checkpoint_backend"),
        "chat_output_is_evidence": any(source.get("chat_output_is_evidence") is True for source in sources),
        "semantic_gate": any(source.get("semantic_gate") is True for source in sources),
        "boundary": (
            "This summary documents the harness graph and agent contracts. Chat output and runtime logs "
            "remain diagnostic or command-contract evidence unless a validator-owned semantic gate accepts them."
        ),
    }


def build_opencode_evidence_policy(sources: list[dict[str, Any]]) -> dict[str, Any]:
    enabled = bool(sources)
    boundary_fields_explicit = all(bool(source.get("boundary_fields_explicit")) for source in sources) if sources else True
    chat_false = all(source.get("chat_output_is_evidence") is False for source in sources)
    semantic_false = all(source.get("semantic_gate") is False for source in sources)
    return {
        "enabled": enabled,
        "boundary_fields_explicit": boundary_fields_explicit,
        "chat_output_is_evidence_false": chat_false,
        "semantic_gate_false": semantic_false,
        "session_evidence_role": "command_contract_audit_only",
        "logs_evidence_role": "diagnostic_only",
        "semantic_gate": False,
        "boundary": "OpenCode session/log artifacts are command-contract and diagnostic evidence only.",
    }


def build_must_not_claim(opencode_runtime: dict[str, Any]) -> list[str]:
    claims = [
        "accepted_evidence_is_not_translator_generated_coverage",
        "blocked_repairs_are_not_translation_success",
        "before_after_exhibit_is_not_new_semantic_gate",
        "bundle_status_passed_is_not_project_level_translation_success",
        "local_simulation_is_not_competition_exact",
        "review_checklist_is_not_semantic_acceptance",
    ]
    if opencode_runtime.get("enabled_entrypoint_count", 0):
        claims.append("opencode_chat_output_is_semantic_evidence")
    return claims


def build_blocked_repairs_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    rollup = build_blocked_repairs_route_rollup(sources)
    rollup["source_count"] = len(sources)
    rollup["recorded_source_count"] = sum(
        1
        for source in sources
        if blocked_repairs_source_has_entries(source)
    )
    return {
        "report_kind": "blocked-repairs-rollup",
        "sources": [
            {
                "entrypoint_id": source.get("entrypoint_id"),
                "artifact": source.get("artifact"),
                "blocked_repairs": source.get("blocked_repairs", empty_blocked_repairs_rollup()),
            }
            for source in sources
        ],
        "rollup": rollup,
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": (
            "This rollup indexes validator-bound blocked-repair playbooks for judge review. It records "
            "fail-closed next steps for refused or blocked repair attempts. It is not a semantic acceptance "
            "gate, does not convert blocked or refused work into translation success, does not increase "
            "translator-generated coverage, and does not prove unsafe reduction."
        ),
    }


def blocked_repairs_source_has_entries(source: dict[str, Any]) -> bool:
    blocked = source.get("blocked_repairs", {})
    if not isinstance(blocked, dict):
        return False
    return int_or_zero(blocked.get("blocked_repair_count")) > 0


def build_known_gaps(*, proof_classes: dict[str, Any], opencode_runtime: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = [
        {
            "gap_id": "translator_generated_coverage_not_claimed",
            "boundary": "translation_coverage_numerator remains 0 for this bundle.",
        },
        {
            "gap_id": "accepted_evidence_not_translator_generated",
            "boundary": "Accepted-evidence semantic pass counts remain report context and do not become generated-draft acceptance.",
        },
        {
            "gap_id": "c2rust_baseline_output_still_not_verified_here",
            "boundary": "This bundle does not prove a new C2Rust compile-passed or verified unsafe baseline.",
        },
    ]
    if not proof_classes.get("has_competition_exact"):
        gaps.append(
            {
                "gap_id": "local_simulation_not_competition_exact",
                "boundary": "No entrypoint in this bundle has proof_class=competition-exact.",
            }
        )
    if opencode_runtime.get("enabled_entrypoint_count", 0):
        gaps.append(
            {
                "gap_id": "opencode_runtime_is_command_contract_evidence",
                "boundary": "OpenCode runtime/session evidence audits command execution; chat output is not semantic evidence.",
            }
        )
    return gaps


def build_reproduction_commands(
    *,
    run_report: dict[str, Any],
    run_report_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    run_report_rel = validator.repo_relative(run_report_path, repo_root)
    bundle_rel = validator.repo_relative(run_report_path.parent / "judge-milestone-bundle.json", repo_root)
    config = run_report.get("config") if isinstance(run_report.get("config"), dict) else {}
    config_path = config.get("path") if isinstance(config.get("path"), str) else None
    if config_path:
        runner_command = (
            "python -B -m validation.tools.run_judge_entrypoints "
            f"--config {config_path} --out {run_report_rel}"
        )
    else:
        runner_command = f"python -B -m validation.tools.run_judge_entrypoints --out {run_report_rel}"
    return {
        "run_judge_entrypoints": runner_command,
        "build_bundle": (
            "python -B -m validation.tools.judge_milestone_bundle "
            f"--run-report {run_report_rel} --out {bundle_rel}"
        ),
        "entrypoints": [
            {
                "id": entry.get("id"),
                "command": entry.get("command"),
            }
            for entry in run_report.get("entrypoints", [])
            if isinstance(entry, dict)
        ],
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
    per_unit_statuses = payload.get("per_unit_statuses") if isinstance(payload.get("per_unit_statuses"), list) else []
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "units_total": int_or_zero(payload.get("units_total")),
        "units_converged": int_or_zero(payload.get("units_converged")),
        "avg_repair_rounds": number_or_zero(payload.get("avg_repair_rounds")),
        "auto_recovery_rate": number_or_zero(payload.get("auto_recovery_rate")),
        "repair_history_unit_count": sum(
            1 for unit in per_unit_statuses if isinstance(unit, dict) and isinstance(unit.get("repair_history"), dict)
        ),
        "auto_recovered_unit_count": sum(
            1 for unit in per_unit_statuses if isinstance(unit, dict) and unit.get("auto_recovered") is True
        ),
        "human_interventions": int_or_zero(payload.get("human_interventions")),
        "llm_calls": int_or_zero(payload.get("llm_calls")),
        "unsafe_reduction_status": unsafe_reduction.get("status", "unknown"),
        "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
        "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
        "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
    }


def route_governance_metrics_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}
    s2 = metrics.get("s2_workflow_metrics", {}) if isinstance(metrics.get("s2_workflow_metrics"), dict) else {}
    unsafe_reduction = s2.get("unsafe_reduction", {}) if isinstance(s2.get("unsafe_reduction"), dict) else {}
    retention = payload.get("retention_policy", {}) if isinstance(payload.get("retention_policy"), dict) else {}
    target_artifacts = (
        retention.get("target_artifacts", {}) if isinstance(retention.get("target_artifacts"), dict) else {}
    )
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "status": payload.get("status", "unknown"),
        "translation_coverage_numerator": int_or_zero(metrics.get("translation_coverage_numerator")),
        "accepted_evidence_semantic_pass_count": int_or_zero(
            metrics.get("accepted_evidence_semantic_pass_count")
        ),
        "tracked_route_decision_artifacts": int_or_zero(metrics.get("tracked_route_decision_artifacts")),
        "tracked_slice_gate_contexts": int_or_zero(metrics.get("tracked_slice_gate_contexts")),
        "blocked_repairs": blocked_repairs_source(metrics.get("blocked_repairs")),
        "s2_workflow_run_count": int_or_zero(s2.get("run_count")),
        "s2_unsafe_reduction_status": unsafe_reduction.get("status", "unknown"),
        "s2_reduced_by": int_or_zero(unsafe_reduction.get("reduced_by")),
        "retention_policy_present": bool(retention),
        "target_artifacts_committed": target_artifacts.get("committed")
        if isinstance(target_artifacts.get("committed"), bool)
        else None,
        "target_artifacts_retention_class": target_artifacts.get("retention_class")
        if isinstance(target_artifacts.get("retention_class"), str)
        else None,
        "claim_boundary": payload.get("claim_boundary") if isinstance(payload.get("claim_boundary"), str) else None,
    }


def evidence_cost_retention_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    inventory = payload.get("inventory", {}) if isinstance(payload.get("inventory"), dict) else {}
    portability = payload.get("portability", {}) if isinstance(payload.get("portability"), dict) else {}
    runtime = inventory.get("runtime", {}) if isinstance(inventory.get("runtime"), dict) else {}
    retention_classes = inventory.get("retention_classes", {})
    if not isinstance(retention_classes, dict):
        retention_classes = {}
    pipelines = inventory.get("pipelines", [])
    pipeline_count = (
        len([pipeline for pipeline in pipelines if isinstance(pipeline, dict)])
        if isinstance(pipelines, list)
        else 0
    )
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "status": payload.get("status", "unknown"),
        "evidence_root": payload.get("evidence_root") if isinstance(payload.get("evidence_root"), str) else None,
        "failed_gates": payload.get("failed_gates") if isinstance(payload.get("failed_gates"), list) else [],
        "artifact_count": int_or_zero(inventory.get("file_count")),
        "total_bytes": int_or_zero(inventory.get("total_bytes")),
        "retention_classes": normalize_retention_classes(retention_classes),
        "pipeline_count": pipeline_count,
        "runtime_observation_count": int_or_zero(runtime.get("observation_count")),
        "runtime_total_duration_ms": int_or_zero(runtime.get("total_duration_ms")),
        "runtime_max_duration_ms": int_or_zero(runtime.get("max_duration_ms")),
        "portability_status": portability.get("status", "unknown"),
        "claim_anchor_issue_count": int_or_zero(portability.get("claim_anchor_issue_count")),
        "profile_hash_issue_count": int_or_zero(portability.get("profile_hash_issue_count")),
        "diagnostic_host_metadata_count": int_or_zero(portability.get("diagnostic_host_metadata_count")),
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
    chat_value = headline_runtime.get("chat_output_is_evidence", runtime.get("chat_output_is_evidence"))
    semantic_value = headline_runtime.get("semantic_gate", runtime.get("semantic_gate"))
    boundary_fields_explicit = isinstance(chat_value, bool) and isinstance(semantic_value, bool)
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "worker_count": int_or_zero(headline_runtime.get("worker_count", runtime.get("worker_count"))),
        "all_contracts_executed": bool(
            headline_runtime.get("all_contracts_executed", runtime.get("all_contracts_executed"))
        ),
        "chat_output_is_evidence": chat_value if isinstance(chat_value, bool) else None,
        "semantic_gate": semantic_value if isinstance(semantic_value, bool) else None,
        "boundary_fields_explicit": boundary_fields_explicit,
        "repair_round_cap": int_or_zero(headline.get("repair_round_cap")),
    }


def core_translation_quality_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    quality = payload.get("core_translation_quality")
    if not isinstance(quality, dict):
        return None
    unsafe_reduction = quality.get("unsafe_reduction", {})
    if not isinstance(unsafe_reduction, dict):
        unsafe_reduction = {}
    final_gate_status = quality.get("final_gate_status")
    translation_before_after = before_after_summary(quality.get("translation_before_after"))
    before_after_units = before_after_unit_summaries(quality.get("before_after_units"))
    repair_summary = repair_summary_for_bundle(quality.get("repair_summary"))
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "final_gate_status": final_gate_status if isinstance(final_gate_status, str) else "unknown",
        "semantic_pass_count": int_or_zero(quality.get("semantic_pass_count")),
        "translation_coverage_numerator": int_or_zero(quality.get("translation_coverage_numerator")),
        "generated_draft_semantic_pass": bool(quality.get("generated_draft_semantic_pass")),
        "translation_before_after": translation_before_after,
        "before_after_units": before_after_units,
        "repair_summary": repair_summary,
        "unsafe_reduction": {
            "status": unsafe_reduction.get("status", "unknown"),
            "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
            "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
            "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
        },
    }


def before_after_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "status": "not_provided",
            "unit_count": 0,
            "measured_unsafe_unit_count": 0,
            "accepted_patch_unit_count": 0,
        }
    status = value.get("status")
    return {
        "status": status if isinstance(status, str) else "unknown",
        "unit_count": int_or_zero(value.get("unit_count")),
        "measured_unsafe_unit_count": int_or_zero(value.get("measured_unsafe_unit_count")),
        "accepted_patch_unit_count": int_or_zero(value.get("accepted_patch_unit_count")),
    }


def artifact_binding_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    sha256 = value.get("sha256")
    if not isinstance(path, str) or not isinstance(sha256, str):
        return None
    return {"path": path, "sha256": sha256}


def before_after_unit_summaries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        unsafe_reduction = item.get("unsafe_reduction")
        if not isinstance(unsafe_reduction, dict):
            unsafe_reduction = {}
        unit: dict[str, Any] = {
            "unit_id": item.get("unit_id") if isinstance(item.get("unit_id"), str) else "unknown",
            "status": item.get("status") if isinstance(item.get("status"), str) else "unknown",
            "unsafe_reduction": {
                "status": unsafe_reduction.get("status", "unknown"),
                "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
                "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
                "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
            },
        }
        for key in ["baseline", "final", "accepted_patch", "oracle_evidence"]:
            binding = artifact_binding_summary(item.get(key))
            if binding is not None:
                unit[key] = binding
        result.append(unit)
    return result


def repair_summary_for_bundle(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "status": "not_provided",
            "repair_round_cap": 0,
            "observed_repair_unit_count": 0,
            "auto_recovered_unit_count": 0,
            "rollback_evidence_count": 0,
        }
    observed = int_or_zero(value.get("observed_repair_unit_count"))
    if observed == 0:
        observed = int_or_zero(value.get("repair_history_unit_count"))
    auto_recovered = int_or_zero(value.get("auto_recovered_unit_count"))
    if auto_recovered == 0:
        auto_recovered = int_or_zero(value.get("auto_recovered_units"))
    rollback_evidence_count = int_or_zero(value.get("rollback_evidence_count"))
    if rollback_evidence_count == 0 and isinstance(value.get("histories"), list):
        rollback_evidence_count = sum(
            len(history.get("repair_history", {}).get("rollback_ids", []))
            for history in value["histories"]
            if isinstance(history, dict) and isinstance(history.get("repair_history"), dict)
        )
    status = value.get("status")
    return {
        "status": status if isinstance(status, str) else "unknown",
        "repair_round_cap": int_or_zero(value.get("repair_round_cap")),
        "observed_repair_unit_count": observed,
        "auto_recovered_unit_count": auto_recovered,
        "rollback_evidence_count": rollback_evidence_count,
        "avg_repair_rounds": number_or_zero(value.get("avg_repair_rounds")),
        "auto_recovery_rate": number_or_zero(value.get("auto_recovery_rate")),
        "human_interventions": int_or_zero(value.get("human_interventions")),
    }


def harness_architecture_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    architecture = payload.get("harness_architecture")
    if not isinstance(architecture, dict):
        return None
    retry_policy = architecture.get("retry_policy", {})
    if not isinstance(retry_policy, dict):
        retry_policy = {}
    contracts = architecture.get("architecture_contracts", {})
    if not isinstance(contracts, dict):
        contracts = {}
    agent_contract = contracts.get("agent_coordination", {})
    if not isinstance(agent_contract, dict):
        agent_contract = {}
    graph_runtime = architecture.get("graph_runtime")
    graph_nodes = architecture.get("graph_nodes")
    roles = agent_contract.get("roles")
    repair_checkpoint = retry_policy.get("checkpoint")
    checkpoint_backend = agent_contract.get("checkpoint_backend")
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "graph_runtime": graph_runtime if isinstance(graph_runtime, str) else "unknown",
        "graph_nodes": [value for value in graph_nodes if isinstance(value, str)] if isinstance(graph_nodes, list) else [],
        "worker_count": int_or_zero(architecture.get("worker_count")),
        "repair_round_cap": int_or_zero(retry_policy.get("round_cap")),
        "repair_checkpoint": repair_checkpoint if isinstance(repair_checkpoint, str) else None,
        "roles": [value for value in roles if isinstance(value, str)] if isinstance(roles, list) else [],
        "checkpoint_backend": checkpoint_backend if isinstance(checkpoint_backend, str) else None,
        "chat_output_is_evidence": agent_contract.get("chat_output_is_evidence")
        if isinstance(agent_contract.get("chat_output_is_evidence"), bool)
        else None,
        "semantic_gate": agent_contract.get("semantic_gate")
        if isinstance(agent_contract.get("semantic_gate"), bool)
        else None,
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
            "repair_activity": build_repair_activity_rollup(sources),
            "unsafe_reduction": {
                "status": "measured" if measured_sources else "not_measured",
                "baseline_total_unsafe": sum(baseline_values) if measured_complete else None,
                "current_total_unsafe": sum(current_values) if measured_complete else None,
                "reduced_by": sum(reduced_values) if measured_complete else None,
            },
        },
    }


def build_repair_activity_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    units_total = sum(int_or_zero(source.get("units_total")) for source in sources)
    observed_sources = [
        source
        for source in sources
        if number_or_zero(source.get("avg_repair_rounds")) > 0
        or number_or_zero(source.get("auto_recovery_rate")) > 0
        or int_or_zero(source.get("repair_history_unit_count")) > 0
        or int_or_zero(source.get("auto_recovered_unit_count")) > 0
    ]
    return {
        "source_count": len(sources),
        "observed_source_count": len(observed_sources),
        "repair_history_unit_count": sum(int_or_zero(source.get("repair_history_unit_count")) for source in sources),
        "auto_recovered_unit_count": sum(int_or_zero(source.get("auto_recovered_unit_count")) for source in sources),
        "avg_repair_rounds": weighted_source_metric(sources, "avg_repair_rounds", units_total),
        "auto_recovery_rate": weighted_source_metric(sources, "auto_recovery_rate", units_total),
        "human_interventions": sum(int_or_zero(source.get("human_interventions")) for source in sources),
        "boundary": (
            "Repair activity summarizes hash-bound workflow metrics only. It is not a semantic gate, "
            "does not prove unsafe reduction without measured unsafe counts, and does not increase translation coverage."
        ),
    }


def weighted_source_metric(sources: list[dict[str, Any]], key: str, units_total: int) -> float:
    if units_total <= 0:
        return 0.0
    numerator = 0.0
    for source in sources:
        units = int_or_zero(source.get("units_total"))
        value = number_or_zero(source.get(key))
        numerator += float(value) * units
    return numerator / float(units_total)


def build_route_governance_metrics_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    all_retention_present = all(bool(source.get("retention_policy_present")) for source in sources) if sources else True
    all_reproducible = (
        all(
            source.get("target_artifacts_committed") is False
            and source.get("target_artifacts_retention_class") == "reproducible-local-output"
            for source in sources
        )
        if sources
        else True
    )
    return {
        "report_kind": "route-governance-metrics-rollup",
        "sources": sources,
        "rollup": {
            "source_count": len(sources),
            "translation_coverage_numerator": sum(
                int_or_zero(source.get("translation_coverage_numerator")) for source in sources
            ),
            "accepted_evidence_semantic_pass_count": sum(
                int_or_zero(source.get("accepted_evidence_semantic_pass_count")) for source in sources
            ),
            "tracked_route_decision_artifacts": sum(
                int_or_zero(source.get("tracked_route_decision_artifacts")) for source in sources
            ),
            "tracked_slice_gate_contexts": sum(
                int_or_zero(source.get("tracked_slice_gate_contexts")) for source in sources
            ),
            "s2_workflow_run_count": sum(int_or_zero(source.get("s2_workflow_run_count")) for source in sources),
            "s2_unsafe_reduction": {
                "status": "measured"
                if any(source.get("s2_unsafe_reduction_status") == "measured" for source in sources)
                else "not_measured",
                "reduced_by": sum(int_or_zero(source.get("s2_reduced_by")) for source in sources),
            },
            "blocked_repairs": build_blocked_repairs_route_rollup(sources),
            "all_retention_policies_present": all_retention_present,
            "all_target_artifacts_reproducible": all_reproducible,
        },
        "boundary": (
            "Route governance metrics constrain public claims and artifact retention. They are not a semantic gate "
            "and do not increase translator-generated translation coverage."
        ),
    }


def blocked_repairs_source(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return empty_blocked_repairs_rollup()
    return {
        "status": value.get("status") if isinstance(value.get("status"), str) else "unknown",
        "blocked_repair_count": int_or_zero(value.get("blocked_repair_count")),
        "slice_count": int_or_zero(value.get("slice_count")),
        "human_action_required_count": int_or_zero(value.get("human_action_required_count")),
        "human_intervention_points": string_list(value.get("human_intervention_points")),
        "blocked_callees": string_list(value.get("blocked_callees")),
        "ir_feature_gap_kinds": int_count_map(value.get("ir_feature_gap_kinds")),
        "forbidden_change_counts": int_count_map(value.get("forbidden_change_counts")),
        "blocked_reason_counts": int_count_map(value.get("blocked_reason_counts")),
        "source_span_kind_counts": int_count_map(value.get("source_span_kind_counts")),
        "smallest_next_tests": object_list(value.get("smallest_next_tests")),
        "next_actions": object_list(value.get("next_actions")),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def build_blocked_repairs_route_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    human_points: list[str] = []
    callees: list[str] = []
    status_counts: dict[str, int] = {}
    gap_kinds: dict[str, int] = {}
    forbidden_changes: dict[str, int] = {}
    blocked_reasons: dict[str, int] = {}
    source_span_kinds: dict[str, int] = {}
    smallest_tests: list[dict[str, Any]] = []
    next_actions: list[dict[str, Any]] = []
    blocked_repair_count = 0
    slice_count = 0
    human_action_required_count = 0
    for source in sources:
        blocked = source.get("blocked_repairs", {}) if isinstance(source.get("blocked_repairs"), dict) else {}
        blocked_repair_count += int_or_zero(blocked.get("blocked_repair_count"))
        slice_count += int_or_zero(blocked.get("slice_count"))
        human_action_required_count += int_or_zero(blocked.get("human_action_required_count"))
        increment_count(status_counts, blocked.get("status"))
        for point in string_list(blocked.get("human_intervention_points")):
            append_unique(human_points, point)
        for callee in string_list(blocked.get("blocked_callees")):
            append_unique(callees, callee)
        merge_int_counts(gap_kinds, blocked.get("ir_feature_gap_kinds"))
        merge_int_counts(forbidden_changes, blocked.get("forbidden_change_counts"))
        merge_int_counts(blocked_reasons, blocked.get("blocked_reason_counts"))
        merge_int_counts(source_span_kinds, blocked.get("source_span_kind_counts"))
        for test in object_list(blocked.get("smallest_next_tests")):
            append_unique_dict(smallest_tests, test)
        for action in object_list(blocked.get("next_actions")):
            enriched = dict(action)
            if isinstance(source.get("entrypoint_id"), str) and "entrypoint_id" not in enriched:
                enriched["entrypoint_id"] = source["entrypoint_id"]
            append_unique_dict(next_actions, enriched)
    return {
        "status": "observed" if blocked_repair_count else "none",
        "blocked_repair_count": blocked_repair_count,
        "slice_count": slice_count,
        "human_action_required_count": human_action_required_count,
        "status_counts": status_counts,
        "human_intervention_points": human_points,
        "blocked_callees": callees,
        "ir_feature_gap_kinds": gap_kinds,
        "forbidden_change_counts": forbidden_changes,
        "blocked_reason_counts": blocked_reasons,
        "source_span_kind_counts": source_span_kinds,
        "smallest_next_tests": smallest_tests,
        "next_actions": next_actions,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Blocked repairs summarize route-governance self-healing refusals only. They are not semantic "
            "acceptance and do not increase translator-generated coverage."
        ),
    }


def empty_blocked_repairs_rollup() -> dict[str, Any]:
    return {
        "status": "none",
        "blocked_repair_count": 0,
        "slice_count": 0,
        "human_action_required_count": 0,
        "status_counts": {},
        "human_intervention_points": [],
        "blocked_callees": [],
        "ir_feature_gap_kinds": {},
        "forbidden_change_counts": {},
        "blocked_reason_counts": {},
        "source_span_kind_counts": {},
        "smallest_next_tests": [],
        "next_actions": [],
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def build_evidence_cost_retention_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    retention_classes: dict[str, dict[str, int]] = {}
    for source in sources:
        classes = source.get("retention_classes", {})
        if not isinstance(classes, dict):
            continue
        for class_name, counts in classes.items():
            if not isinstance(counts, dict):
                continue
            target = retention_classes.setdefault(str(class_name), {"file_count": 0, "total_bytes": 0})
            target["file_count"] += int_or_zero(counts.get("file_count"))
            target["total_bytes"] += int_or_zero(counts.get("total_bytes"))
    return {
        "report_kind": "evidence-cost-retention-rollup",
        "sources": sources,
        "rollup": {
            "source_count": len(sources),
            "artifact_count": sum(int_or_zero(source.get("artifact_count")) for source in sources),
            "total_bytes": sum(int_or_zero(source.get("total_bytes")) for source in sources),
            "pipeline_count": sum(int_or_zero(source.get("pipeline_count")) for source in sources),
            "runtime_ms": {
                "observation_count": sum(
                    int_or_zero(source.get("runtime_observation_count")) for source in sources
                ),
                "total": sum(int_or_zero(source.get("runtime_total_duration_ms")) for source in sources),
                "max": max(
                    [int_or_zero(source.get("runtime_max_duration_ms")) for source in sources],
                    default=0,
                ),
            },
            "retention_classes": retention_classes,
            "all_sources_passed": all(source.get("status") == "passed" for source in sources) if sources else True,
            "portability_issue_count": sum(
                int_or_zero(source.get("claim_anchor_issue_count"))
                + int_or_zero(source.get("profile_hash_issue_count"))
                for source in sources
            ),
            "diagnostic_host_metadata_count": sum(
                int_or_zero(source.get("diagnostic_host_metadata_count")) for source in sources
            ),
        },
        "boundary": (
            "Evidence cost and retention metrics summarize artifact volume, runtime observations, and retention "
            "classes for review. They are not semantic acceptance evidence and do not increase translation coverage."
        ),
    }


def build_opencode_runtime_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "report_kind": "opencode-runtime-rollup",
        "sources": sources,
        "enabled_entrypoint_count": len(sources),
        "worker_count": sum(int_or_zero(source.get("worker_count")) for source in sources),
        "all_contracts_executed": bool(sources) and all(bool(source.get("all_contracts_executed")) for source in sources),
        "chat_output_is_evidence_false": all(source.get("chat_output_is_evidence") is False for source in sources),
        "semantic_gate_false": all(source.get("semantic_gate") is False for source in sources),
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


def normalize_retention_classes(value: dict[str, Any]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for class_name, counts in value.items():
        if not isinstance(counts, dict):
            continue
        result[str(class_name)] = {
            "file_count": int_or_zero(counts.get("file_count")),
            "total_bytes": int_or_zero(counts.get("total_bytes")),
        }
    return result


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def int_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int_or_zero(count) for key, count in value.items()}


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def merge_int_counts(target: dict[str, int], value: object) -> None:
    for key, count in int_count_map(value).items():
        target[key] = target.get(key, 0) + count


def increment_count(target: dict[str, int], value: object) -> None:
    if isinstance(value, str) and value:
        target[value] = target.get(value, 0) + 1


def append_unique(items: list[str], value: object) -> None:
    if isinstance(value, str) and value and value not in items:
        items.append(value)


def append_unique_dict(items: list[dict[str, Any]], value: dict[str, Any]) -> None:
    if value not in items:
        items.append(value)


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


def first_string_value(sources: list[dict[str, Any]], key: str) -> str | None:
    for source in sources:
        value = source.get(key)
        if isinstance(value, str):
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
