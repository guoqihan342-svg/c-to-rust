#!/usr/bin/env python3
"""Build a judge-facing external milestone bundle from entrypoint evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import validate_judge_entrypoints as validator


DEFAULT_RUN_REPORT = Path("target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json")
DEFAULT_BUNDLE = Path("target/competition-out-flashdb-judge-entrypoints/summary/judge-milestone-bundle.json")
SELF_HEAL_SAMPLE_NEXT_ACTION_LIMIT = 5
BEFORE_AFTER_ARTIFACT_REF_FIELDS = ("baseline", "final", "accepted_patch", "oracle_evidence")


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
    remove_stale_publication_siblings(out_path)
    run_report = validator.load_json(run_report_path)
    entrypoints = [entry for entry in run_report.get("entrypoints", []) if isinstance(entry, dict)]
    readiness = run_report.get("summary", {}).get("readiness", {}) if isinstance(run_report.get("summary"), dict) else {}
    claim_boundary = milestone_claim_boundary(run_report)
    validated_artifacts = validation_artifacts_by_entrypoint(run_report.get("validation"))
    validated_artifact_contract_errors = validated_artifact_ref_blockers(
        validated_artifacts,
        repo_root=repo_root,
    )
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
    exact_host_revalidation = build_exact_host_revalidation(
        run_report,
        entrypoint_reports,
        repo_root=repo_root,
    )
    exact_host_revalidation_errors = exact_host_revalidation_blockers(exact_host_revalidation)
    proof_classes = proof_classes_after_exact_host_revalidation(
        proof_classes,
        exact_host_revalidation,
    )
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
    progress_delta_ledger = build_progress_delta_ledger(
        route_governance_metrics=route_governance_metrics,
        workflow_metrics=workflow_metrics,
        before_after_repair_exhibit=before_after_repair_exhibit,
    )
    semantic_evidence = build_semantic_evidence_rollup(run_report)
    blockers = milestone_blockers(
        run_report,
        readiness,
        claim_boundary,
        run_report_contract=run_report_contract,
        proof_class_contract_errors=proof_class_contract_errors,
        exact_host_revalidation_errors=exact_host_revalidation_errors,
        opencode_policy=opencode_policy,
        core_translation_quality=core_translation_quality,
        before_after_repair_exhibit=before_after_repair_exhibit,
        blocked_repairs_rollup=blocked_repairs_rollup,
        route_governance_metrics=route_governance_metrics,
        evidence_cost_retention=evidence_cost_retention,
        opencode_runtime=opencode_runtime,
    )
    blockers.extend(before_after_workflow_metrics_ref_blockers(core_quality_sources, workflow_sources))
    blockers.extend(c2rust_baseline_manifest_ref_blockers(route_governance_sources, repo_root=repo_root))
    blockers.extend(validated_artifact_contract_errors)
    blockers.extend(publication_artifact_ref_blockers(entrypoint_reports))
    status = "passed" if not blockers else "blocked"
    claim_scope = build_claim_scope(status=status, proof_classes=proof_classes, semantic_evidence=semantic_evidence)
    publishability = build_publishability(
        status=status,
        readiness=readiness,
        proof_classes=proof_classes,
        blockers=blockers,
        opencode_runtime=opencode_runtime,
    )
    competition_host_readiness = build_competition_host_readiness(
        proof_classes=proof_classes,
        publishability=publishability,
    )
    reproduction_commands = build_reproduction_commands(
        run_report=run_report,
        run_report_path=run_report_path,
        repo_root=repo_root,
    )
    must_not_claim = build_must_not_claim(opencode_runtime)
    known_gaps = build_known_gaps(
        proof_classes=proof_classes,
        opencode_runtime=opencode_runtime,
        before_after_repair_exhibit=before_after_repair_exhibit,
    )
    quantitative_evaluation = build_quantitative_evaluation(
        workflow_metrics=workflow_metrics,
        route_governance_metrics=route_governance_metrics,
        before_after_repair_exhibit=before_after_repair_exhibit,
        blocked_repairs_rollup=blocked_repairs_rollup,
        unsafe_scope=unsafe_scope,
        semantic_evidence=semantic_evidence,
        opencode_runtime=opencode_runtime,
        proof_classes=proof_classes,
        publishability=publishability,
    )
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
            publishability=publishability,
        ),
        "claim_boundary": claim_boundary,
        "claim_scope": claim_scope,
        "proof_classes": proof_classes,
        "proof_class_rollup": proof_classes,
        "exact_host_revalidation": exact_host_revalidation,
        "publishability": publishability,
        "competition_host_readiness": competition_host_readiness,
        "semantic_evidence_rollup": semantic_evidence,
        "core_translation_quality": core_translation_quality,
        "before_after_repair_exhibit": before_after_repair_exhibit,
        "blocked_repairs_rollup": blocked_repairs_rollup,
        "harness_architecture_summary": harness_architecture_summary,
        "route_governance_metrics": route_governance_metrics,
        "progress_delta_ledger": progress_delta_ledger,
        "evidence_cost_retention": evidence_cost_retention,
        "entrypoints": entrypoint_reports,
        "workflow_metrics": workflow_metrics,
        "unsafe_reduction_scope": unsafe_scope,
        "opencode_runtime": opencode_runtime,
        "opencode_evidence_policy": opencode_policy,
        "must_not_claim": must_not_claim,
        "known_gaps": known_gaps,
        "reproduction_commands": reproduction_commands,
        "quantitative_evaluation": quantitative_evaluation,
        "publication_manifest": build_publication_manifest(
            run_report=run_report,
            run_report_path=run_report_path,
            out_path=out_path,
            judge_entrypoints_run_report=artifact_ref(run_report_path, repo_root=repo_root),
            entrypoint_reports=entrypoint_reports,
            claim_boundary=claim_boundary,
            claim_scope=claim_scope,
            proof_classes=proof_classes,
            publishability=publishability,
            harness_architecture_summary=harness_architecture_summary,
            before_after_repair_exhibit=before_after_repair_exhibit,
            opencode_runtime=opencode_runtime,
            reproduction_commands=reproduction_commands,
            must_not_claim=must_not_claim,
            known_gaps=known_gaps,
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
        proof_class=proof_class,
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
    host_attestation = competition_host_attestation_from_artifacts(artifacts, repo_root=repo_root)
    return (
        {
            "id": entry.get("id"),
            "purpose": entry.get("purpose"),
            "status": entry.get("status"),
            "exit_code": entry.get("exit_code"),
            "proof_class": proof_class,
            "source_proof_class": entry.get("proof_class", "unknown"),
            "run_id": entry.get("run_id", "unknown"),
            "competition_exact_host_attested": host_attestation.get("competition_exact_host_attested") is True,
            "host_attestation": host_attestation,
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


def competition_host_attestation_from_artifacts(artifacts: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    smoke_artifact = artifacts.get("competition_smoke_summary")
    payload = load_present_json_artifact(smoke_artifact, repo_root=repo_root)
    if payload is None:
        return {
            "status": "missing",
            "competition_exact_host_attested": False,
        }
    environment = payload.get("execution_environment") if isinstance(payload.get("execution_environment"), dict) else {}
    attested = environment.get("competition_exact_host_attested") is True
    result = {
        "status": "attested" if attested else "not_attested",
        "competition_exact_host_attested": attested,
        "proof_class": payload.get("proof_class", "unknown"),
        "run_id": payload.get("run_id", "unknown"),
        "execution_environment_kind": environment.get("kind", "unknown"),
    }
    if isinstance(smoke_artifact, dict):
        result["source_artifact"] = {
            key: smoke_artifact[key]
            for key in ("path", "sha256", "status")
            if key in smoke_artifact
        }
    return result


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


def validated_artifact_ref_blockers(validated_artifacts: dict[str, dict[str, Any]], *, repo_root: Path) -> list[str]:
    blockers: list[str] = []
    for entrypoint_id, artifacts in sorted(validated_artifacts.items()):
        for artifact_name, raw_ref in sorted(artifacts.items()):
            ref = artifact_ref_from_existing(raw_ref, repo_root=repo_root)
            if ref is None:
                continue
            status = ref.get("status")
            if status == "sha256_mismatch":
                blockers.append(f"validated_artifact_sha256_mismatch:{entrypoint_id}:{artifact_name}")
            elif status == "status_mismatch":
                blockers.append(f"validated_artifact_status_mismatch:{entrypoint_id}:{artifact_name}")
            elif status == "missing_expected_sha256":
                blockers.append(f"validated_artifact_missing_sha256:{entrypoint_id}:{artifact_name}")
    return blockers


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
    exact_host_revalidation_errors: list[str],
    opencode_policy: dict[str, Any],
    core_translation_quality: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
    blocked_repairs_rollup: dict[str, Any],
    route_governance_metrics: dict[str, Any],
    evidence_cost_retention: dict[str, Any],
    opencode_runtime: dict[str, Any],
) -> list[str]:
    blockers: list[str] = (
        list(run_report_contract)
        + list(proof_class_contract_errors)
        + list(exact_host_revalidation_errors)
    )
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
    preflight_summary = (
        opencode_runtime.get("preflight_proof_summary", {})
        if isinstance(opencode_runtime.get("preflight_proof_summary"), dict)
        else {}
    )
    if int_or_zero(opencode_runtime.get("enabled_entrypoint_count")) > 0 and preflight_summary.get("status") != "passed":
        blockers.append("opencode_preflight_proof_summary_missing")
    if bool(core_translation_quality.get("generated_draft_semantic_pass")):
        blockers.append("core_quality_generated_draft_semantic_pass_must_be_false")
    if int_or_zero(core_translation_quality.get("translation_coverage_numerator")) != 0:
        blockers.append("core_quality_translation_coverage_numerator_must_be_zero")
    blockers.extend(nested_artifact_ref_blockers(before_after_repair_exhibit))
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
    policy_rollup = (
        evidence_rollup.get("policy_compliance", {})
        if isinstance(evidence_rollup.get("policy_compliance"), dict)
        else {}
    )
    if int_or_zero(evidence_rollup.get("source_count")) > 0 and not policy_rollup.get("all_sources_policy_passed"):
        blockers.append("evidence_policy_compliance_must_pass")
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
    bound_units = int_or_zero(rollup.get("bound_unit_count"))
    verified_baseline_units = int_or_zero(rollup.get("verified_baseline_unit_count"))
    missing_verified_baseline_units = int_or_zero(rollup.get("missing_verified_baseline_unit_count"))
    all_units_verified_baseline_bound = rollup.get("all_units_verified_baseline_bound")
    unsafe_reduction = rollup.get("unsafe_reduction", {}) if isinstance(rollup.get("unsafe_reduction"), dict) else {}
    baseline_total_unsafe = int_or_none(unsafe_reduction.get("baseline_total_unsafe"))
    unit_unsafe_totals = before_after_unit_unsafe_reduction_totals(before_after_repair_exhibit)
    if auto_recovered > observed:
        blockers.append("repair_accounting_auto_recovered_exceeds_observed")
    if baseline_total_unsafe is not None and unsafe_reduced_by > baseline_total_unsafe:
        blockers.append("repair_accounting_unsafe_reduced_by_exceeds_measured_baseline")
    if unit_unsafe_totals is not None:
        unit_rollup_matches = (
            unit_unsafe_totals["complete"]
            and int_or_zero(rollup.get("measured_unsafe_unit_count")) == unit_unsafe_totals["unit_count"]
            and unsafe_reduction.get("status") == "measured"
            and baseline_total_unsafe == unit_unsafe_totals["baseline_total_unsafe"]
            and int_or_none(unsafe_reduction.get("current_total_unsafe")) == unit_unsafe_totals["current_total_unsafe"]
            and int_or_none(unsafe_reduction.get("reduced_by")) == unit_unsafe_totals["reduced_by"]
            and unsafe_reduced_by == unit_unsafe_totals["reduced_by"]
        )
        if not unit_rollup_matches:
            blockers.append("repair_accounting_unsafe_reduction_rollup_mismatch")
    if observed > 0 and rollback_evidence_count == 0:
        blockers.append("repair_accounting_rollback_evidence_missing_for_observed_repairs")
    if verified_baseline_units + missing_verified_baseline_units != bound_units:
        blockers.append("repair_accounting_verified_baseline_counts_mismatch")
    expected_all_units_verified = (
        bound_units > 0 and verified_baseline_units == bound_units and missing_verified_baseline_units == 0
    )
    if all_units_verified_baseline_bound is not expected_all_units_verified:
        blockers.append("repair_accounting_verified_baseline_all_bound_mismatch")
    return blockers


def nested_artifact_ref_blockers(before_after_repair_exhibit: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for source in object_list(before_after_repair_exhibit.get("sources")):
        for blocker in source.get("nested_artifact_ref_blockers", []):
            if isinstance(blocker, str) and blocker:
                blockers.append(blocker)
    return blockers


def before_after_workflow_metrics_ref_blockers(
    core_sources: list[dict[str, Any]],
    workflow_sources: list[dict[str, Any]],
) -> list[str]:
    workflow_by_entrypoint = {
        source["entrypoint_id"]: source
        for source in workflow_sources
        if isinstance(source.get("entrypoint_id"), str)
    }
    blockers: list[str] = []
    for core_source in core_sources:
        entrypoint_id = core_source.get("entrypoint_id")
        if not isinstance(entrypoint_id, str):
            continue
        workflow_source = workflow_by_entrypoint.get(entrypoint_id)
        if workflow_source is None:
            continue
        workflow_units = before_after_units_by_id(workflow_source.get("before_after_units"))
        if not workflow_units:
            continue
        core_units = before_after_units_by_id(core_source.get("before_after_units"))
        for unit_id, workflow_unit in workflow_units.items():
            if not unit_has_before_after_artifact_ref(workflow_unit):
                continue
            core_unit = core_units.get(unit_id)
            if core_unit is None:
                blockers.append(f"before_after_exhibit_workflow_metrics_unit_missing:{entrypoint_id}:{unit_id}")
                continue
            for field in BEFORE_AFTER_ARTIFACT_REF_FIELDS:
                workflow_ref = workflow_unit.get(field)
                if not isinstance(workflow_ref, dict):
                    continue
                core_ref = core_unit.get(field)
                if not isinstance(core_ref, dict):
                    blockers.append(
                        f"before_after_exhibit_workflow_metrics_ref_missing:{entrypoint_id}:{unit_id}:{field}"
                    )
                    continue
                if ref_binding_tuple(core_ref) != ref_binding_tuple(workflow_ref):
                    blockers.append(
                        f"before_after_exhibit_workflow_metrics_ref_mismatch:{entrypoint_id}:{unit_id}:{field}"
                    )
    return blockers


def c2rust_baseline_manifest_ref_blockers(
    route_governance_sources: list[dict[str, Any]],
    *,
    repo_root: Path,
) -> list[str]:
    blockers: list[str] = []
    for source in route_governance_sources:
        entrypoint_id = str(source.get("entrypoint_id", "unknown"))
        baseline = source.get("c2rust_baseline")
        if not isinstance(baseline, dict) or baseline.get("report_kind") != "c2rust-baseline-rollup":
            continue
        manifest_count = int_or_zero(baseline.get("manifest_count"))
        manifests = object_list(baseline.get("manifests"))
        if manifest_count > 0 and not manifests:
            blockers.append(f"c2rust_baseline_manifest_count_without_bound_refs:{entrypoint_id}")
        if manifests and manifest_count != len(manifests):
            blockers.append(f"c2rust_baseline_manifest_count_mismatch:{entrypoint_id}")
        for index, manifest in enumerate(manifests):
            manifest_path = manifest.get("path") if isinstance(manifest.get("path"), str) else f"manifest:{index}"
            ref = artifact_ref_from_existing(manifest, repo_root=repo_root)
            if ref is None:
                blockers.append(f"c2rust_baseline_manifest_ref_not_present:{entrypoint_id}:{manifest_path}")
                continue
            status = ref.get("status")
            if status == "sha256_mismatch":
                blockers.append(f"c2rust_baseline_manifest_ref_sha256_mismatch:{entrypoint_id}:{manifest_path}")
            elif status == "missing_expected_sha256":
                blockers.append(f"c2rust_baseline_manifest_ref_missing_sha256:{entrypoint_id}:{manifest_path}")
            elif status != "present":
                blockers.append(f"c2rust_baseline_manifest_ref_not_present:{entrypoint_id}:{manifest_path}")
    return blockers


def before_after_units_by_id(value: object) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for unit in object_list(value):
        unit_id = unit.get("unit_id")
        if isinstance(unit_id, str) and unit_id and unit_id not in result:
            result[unit_id] = unit
    return result


def unit_has_before_after_artifact_ref(value: dict[str, Any]) -> bool:
    return any(isinstance(value.get(field), dict) for field in BEFORE_AFTER_ARTIFACT_REF_FIELDS)


def ref_binding_tuple(value: dict[str, Any]) -> tuple[object, object]:
    return value.get("path"), value.get("sha256")


def before_after_unit_unsafe_reduction_totals(before_after_repair_exhibit: dict[str, Any]) -> dict[str, Any] | None:
    unit_count = 0
    baseline_total = 0
    current_total = 0
    reduced_total = 0
    complete = True
    for source in object_list(before_after_repair_exhibit.get("sources")):
        for unit in object_list(source.get("before_after_units")):
            unsafe_reduction = unit.get("unsafe_reduction")
            if not isinstance(unsafe_reduction, dict) or unsafe_reduction.get("status") != "measured":
                continue
            unit_count += 1
            baseline = int_or_none(unsafe_reduction.get("baseline_total_unsafe"))
            current = int_or_none(unsafe_reduction.get("current_total_unsafe"))
            reduced_by = int_or_none(unsafe_reduction.get("reduced_by"))
            if baseline is None or current is None or reduced_by is None:
                complete = False
                continue
            baseline_total += baseline
            current_total += current
            reduced_total += reduced_by
    if unit_count == 0:
        return None
    return {
        "unit_count": unit_count,
        "complete": complete,
        "baseline_total_unsafe": baseline_total,
        "current_total_unsafe": current_total,
        "reduced_by": reduced_total,
    }


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
    if not isinstance(validation, dict):
        blockers.append("run_report_validation_missing")
    elif validation.get("status") != "passed":
        blockers.append("run_report_validation_not_passed")
    else:
        validated_artifacts = validation_artifacts_by_entrypoint(validation)
        for entry in entrypoints:
            entrypoint_id = str(entry.get("id", "unknown"))
            key_artifacts = entry.get("key_artifacts")
            if not isinstance(key_artifacts, dict):
                continue
            expected_artifacts = validated_artifacts.get(entrypoint_id, {})
            for artifact_name, artifact_value in sorted(key_artifacts.items()):
                if artifact_value in (None, ""):
                    continue
                if artifact_name not in expected_artifacts:
                    blockers.append(f"validated_artifact_binding_missing:{entrypoint_id}:{artifact_name}")
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
    publishability: dict[str, Any],
) -> dict[str, Any]:
    executed = int_or_zero(readiness.get("executed_count"))
    configured = int_or_zero(readiness.get("configured_count"))
    external_milestone_claim_ready = publishability.get("external_milestone_claim_ready") is True
    return {
        "report_kind": "judge-milestone-bundle-summary",
        "headline": (
            f"External milestone bundle {status}: judge entrypoints {run_report.get('status', 'unknown')}; "
            f"{executed}/{configured} executed; semantic_gate=false"
        ),
        "source_run_headline": run_report.get("summary", {}).get("headline")
        if isinstance(run_report.get("summary"), dict)
        else None,
        "external_milestone_claim_ready": external_milestone_claim_ready,
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
            "competition_exact_host_attested": entrypoint_competition_host_attested(entry),
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
    missing_host_attestation = [
        str(entry.get("id", "unknown"))
        for entry in entrypoint_proofs
        if entry.get("proof_class") == "competition-exact"
        and entry.get("competition_exact_host_attested") is not True
    ]
    return {
        "all": proof_classes,
        "highest_proof_class": highest,
        "has_competition_exact": "competition-exact" in proof_classes,
        "all_entrypoints_competition_exact": bool(entrypoint_proofs) and not non_exact,
        "competition_exact_host_verified": bool(entrypoint_proofs) and not non_exact and not missing_host_attestation,
        "host_attestation_missing_entrypoints": missing_host_attestation,
        "non_exact_entrypoints": non_exact,
        "entrypoints": entrypoint_proofs,
        "boundary": (
            "Proof class describes the execution environment for this bundle. "
            "local-simulation, wsl-local-simulation, and ci-approximation must not be described as competition-exact."
        ),
    }


def build_exact_host_revalidation(
    run_report: dict[str, Any],
    entrypoints: list[dict[str, Any]],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    claimed_entrypoint_ids = [
        str(entry.get("id", "unknown"))
        for entry in entrypoints
        if entry.get("proof_class") == "competition-exact"
        and entrypoint_competition_host_attested(entry)
    ]
    result: dict[str, Any] = {
        "report_kind": "exact-host-revalidation",
        "required": bool(claimed_entrypoint_ids),
        "status": "skipped",
        "entrypoint_ids": claimed_entrypoint_ids,
        "require_local_artifacts": True,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Competition-exact host attestation from a run report is publishable only after "
            "revalidating the bound judge config with local artifacts."
        ),
    }
    if not claimed_entrypoint_ids:
        result["reason"] = "no_competition_exact_host_attestation_claim"
        return result

    config_ref = run_report.get("config")
    if not isinstance(config_ref, dict) or not isinstance(config_ref.get("path"), str):
        result.update({"status": "failed", "errors": ["run_report.config.path missing"]})
        return result

    try:
        validator.validate_ref(config_ref, repo_root=repo_root)
    except ValueError as error:
        result.update({"status": "failed", "errors": [f"run_report.config {error}"]})
        return result

    config_path = str(config_ref["path"])
    try:
        validation = validator.validate_config(
            resolve_input_path(Path(config_path), repo_root=repo_root),
            require_local_artifacts=True,
            repo_root=repo_root,
            entrypoint_ids=claimed_entrypoint_ids,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result.update({"status": "failed", "errors": [str(error)]})
        return result

    result["validation_status"] = validation.get("status")
    result["validated_config"] = validation.get("config", {})
    result["validator_errors"] = validation.get("errors", [])
    proof_contract = validation.get("proof_class_contract") if isinstance(validation, dict) else {}
    if isinstance(proof_contract, dict):
        result["proof_class_contract_status"] = proof_contract.get("status")
        contract_entrypoints = proof_contract.get("entrypoints")
        if isinstance(contract_entrypoints, dict):
            result["proof_class_entrypoints"] = {
                entrypoint_id: contract_entrypoints.get(entrypoint_id)
                for entrypoint_id in claimed_entrypoint_ids
            }
    all_claimed_still_exact = all(
        result.get("proof_class_entrypoints", {}).get(entrypoint_id) == "competition-exact"
        for entrypoint_id in claimed_entrypoint_ids
    )
    if validation.get("status") == "passed" and all_claimed_still_exact:
        result["status"] = "passed"
    else:
        result["status"] = "failed"
        errors = list(result.get("validator_errors", []))
        if not all_claimed_still_exact:
            errors.append("proof_class_contract did not revalidate all claimed competition-exact entrypoints")
        result["errors"] = errors or ["exact host revalidation failed"]
    return result


def exact_host_revalidation_blockers(revalidation: dict[str, Any]) -> list[str]:
    if revalidation.get("required") is True and revalidation.get("status") != "passed":
        return ["run_report_exact_host_revalidation_failed"]
    return []


def proof_classes_after_exact_host_revalidation(
    proof_classes: dict[str, Any],
    revalidation: dict[str, Any],
) -> dict[str, Any]:
    if revalidation.get("required") is not True or revalidation.get("status") == "passed":
        return proof_classes
    adjusted = deepcopy(proof_classes)
    adjusted["competition_exact_host_verified"] = False
    adjusted["exact_host_revalidation_status"] = revalidation.get("status")
    adjusted["exact_host_revalidation_failed_entrypoints"] = list(revalidation.get("entrypoint_ids", []))
    return adjusted


def entrypoint_competition_host_attested(entry: dict[str, Any]) -> bool:
    if entry.get("competition_exact_host_attested") is True:
        return True
    host_attestation = entry.get("host_attestation")
    if isinstance(host_attestation, dict) and host_attestation.get("competition_exact_host_attested") is True:
        return True
    environment = entry.get("execution_environment")
    return isinstance(environment, dict) and environment.get("competition_exact_host_attested") is True


def build_claim_scope(
    *,
    status: str,
    proof_classes: dict[str, Any],
    semantic_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "external_review_index_ready": status == "passed",
        "semantic_acceptance_ready": False,
        "competition_exact_ready": bool(proof_classes.get("competition_exact_host_verified")),
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
    blockers: list[str],
    opencode_runtime: dict[str, Any],
) -> dict[str, Any]:
    all_entrypoints = bool(readiness.get("all_entrypoints_executed"))
    blocked = status != "passed" or bool(blockers)
    all_entrypoints_run_publishable = not blocked and all_entrypoints
    competition_exact_publishable = all_entrypoints_run_publishable and bool(
        proof_classes.get("all_entrypoints_competition_exact")
    ) and bool(
        proof_classes.get("competition_exact_host_verified")
    )
    scope = "full" if all_entrypoints_run_publishable else "partial" if status == "passed" else "blocked"
    preflight_summary = (
        opencode_runtime.get("preflight_proof_summary", {})
        if isinstance(opencode_runtime.get("preflight_proof_summary"), dict)
        else {}
    )
    opencode_enabled = int_or_zero(opencode_runtime.get("enabled_entrypoint_count")) > 0
    preflight_status = preflight_summary.get("status") if opencode_enabled else "not-required"
    if not isinstance(preflight_status, str) or not preflight_status:
        preflight_status = "missing"
    opencode_glm51_publishable = opencode_enabled and opencode_preflight_summary_publishable(preflight_summary)
    external_ready = competition_exact_publishable and opencode_glm51_publishable
    publication_scope_value = (
        "full"
        if external_ready
        else "internal_preview_full"
        if all_entrypoints_run_publishable
        else scope
    )
    return {
        "status": "blocked"
        if blocked
        else "external_release_ready"
        if external_ready
        else "internal_preview",
        "scope": scope,
        "publication_scope": publication_scope_value,
        "external_milestone_claim_ready": external_ready,
        "external_milestone": external_ready,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "all_entrypoints_run_publishable": all_entrypoints_run_publishable,
        "focused_run": not all_entrypoints,
        "competition_exact_publishable": competition_exact_publishable,
        "required_agent_tool": validator.COMPETITION_OPENCODE_COMMAND,
        "required_agent": validator.COMPETITION_OPENCODE_AGENT,
        "required_model": validator.COMPETITION_OPENCODE_MODEL,
        "required_variant": validator.COMPETITION_OPENCODE_VARIANT,
        "opencode_glm51_required": True,
        "opencode_glm51_preflight_status": preflight_status,
        "opencode_glm51_publishable": opencode_glm51_publishable,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "target_artifacts_regenerable": True,
        "committed_release_evidence_refs": "Use validation/evidence manifests and config/competition-env profiles as committed anchors.",
        "boundary": (
            "Publishability is a review-package readiness contract. Competition-facing agent evidence requires "
            "OpenCode with GLM-5.1 and does not convert chat/session output into semantic acceptance."
        ),
    }


def build_competition_host_readiness(
    *,
    proof_classes: dict[str, Any],
    publishability: dict[str, Any],
) -> dict[str, Any]:
    all_entrypoints_run_publishable = publishability.get("all_entrypoints_run_publishable") is True
    all_entrypoints_competition_exact = proof_classes.get("all_entrypoints_competition_exact") is True
    competition_exact_host_verified = proof_classes.get("competition_exact_host_verified") is True
    opencode_glm51_publishable = publishability.get("opencode_glm51_publishable") is True
    external_milestone_claim_ready = publishability.get("external_milestone_claim_ready") is True
    missing_requirements = []
    if not all_entrypoints_run_publishable:
        missing_requirements.append("all_entrypoints_run_publishable")
    if not all_entrypoints_competition_exact:
        missing_requirements.append("all_entrypoints_competition_exact")
    if not competition_exact_host_verified:
        missing_requirements.append("competition_exact_host_verified")
    if not opencode_glm51_publishable:
        missing_requirements.append("opencode_glm51_publishable")
    if not external_milestone_claim_ready:
        missing_requirements.append("external_milestone_claim_ready")
    return {
        "report_kind": "competition-host-readiness",
        "status": "ready" if not missing_requirements else "blocked",
        "required_agent_tool": validator.COMPETITION_OPENCODE_COMMAND,
        "required_agent": validator.COMPETITION_OPENCODE_AGENT,
        "required_model": validator.COMPETITION_OPENCODE_MODEL,
        "required_variant": validator.COMPETITION_OPENCODE_VARIANT,
        "required_proof_class": "competition-exact",
        "actual_highest_proof_class": proof_classes.get("highest_proof_class", "unknown"),
        "all_entrypoints_run_publishable": all_entrypoints_run_publishable,
        "all_entrypoints_competition_exact": all_entrypoints_competition_exact,
        "competition_exact_host_verified": competition_exact_host_verified,
        "opencode_glm51_preflight_status": publishability.get("opencode_glm51_preflight_status", "unknown"),
        "opencode_glm51_publishable": opencode_glm51_publishable,
        "external_milestone_claim_ready": external_milestone_claim_ready,
        "missing_requirements": missing_requirements,
        "blocker_count": len(missing_requirements),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Competition host readiness is the P0-H9 launch contract for OpenCode + GLM-5.1 + c2rust-migrator + max. "
            "It is not semantic acceptance and does not increase translator-generated coverage."
        ),
    }


def opencode_preflight_summary_publishable(summary: dict[str, Any]) -> bool:
    if summary.get("status") != "passed":
        return False
    if summary.get("required_when_opencode_runtime_enabled") is not True:
        return False
    if summary.get("chat_output_is_evidence") is not False:
        return False
    if summary.get("semantic_gate") is not False:
        return False
    if int_or_zero(summary.get("translation_coverage_numerator")) != 0:
        return False
    if summary.get("opencode_command") != validator.COMPETITION_OPENCODE_COMMAND:
        return False
    if summary.get("opencode_agent") != validator.COMPETITION_OPENCODE_AGENT:
        return False
    if summary.get("opencode_model") != validator.COMPETITION_OPENCODE_MODEL:
        return False
    if summary.get("opencode_variant") != validator.COMPETITION_OPENCODE_VARIANT:
        return False
    if summary.get("required_model") != validator.COMPETITION_OPENCODE_MODEL:
        return False
    if summary.get("model_availability_status") != "available":
        return False
    if summary.get("model_listed") is not True:
        return False
    if int_or_zero(summary.get("process_returncode")) != 0:
        return False
    if summary.get("contract_status") != "executed":
        return False
    if summary.get("marker_exists") is not True:
        return False
    if summary.get("opencode_run_launched") is not True:
        return False
    if summary.get("opencode_run_argv_bound") is not True:
        return False
    if not validator.opencode_models_argv_matches(
        summary.get("model_probe_argv"),
        expected_command=validator.COMPETITION_OPENCODE_COMMAND,
    ):
        return False
    runtime_env = summary.get("opencode_runtime_env")
    if not isinstance(runtime_env, dict):
        return False
    if summary.get("opencode_runtime_env_sha256") != runtime_env.get("env_sha256"):
        return False
    return True


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
            or bool(source.get("nested_artifact_ref_blockers"))
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
                "nested_artifact_ref_blockers": [
                    blocker
                    for blocker in source.get("nested_artifact_ref_blockers", [])
                    if isinstance(blocker, str) and blocker
                ],
                "repair_summary": repair,
                "unsafe_reduction": source.get("unsafe_reduction", {}),
                "claim_boundary": {
                    "semantic_gate": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
            }
        )

    before_after_units = [
        unit
        for source in exhibit_sources
        for unit in source.get("before_after_units", [])
        if isinstance(unit, dict)
    ]
    verified_baseline_unit_count = sum(
        1
        for unit in before_after_units
        if before_after_unit_has_verified_unsafe_baseline(unit)
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
            "verified_baseline_unit_count": verified_baseline_unit_count,
            "missing_verified_baseline_unit_count": len(before_after_units) - verified_baseline_unit_count,
            "all_units_verified_baseline_bound": bool(before_after_units)
            and verified_baseline_unit_count == len(before_after_units),
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
    contract_matrix = build_harness_contract_matrix(sources=sources, graph_nodes=graph_nodes, roles=roles)
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
        "contract_matrix": contract_matrix,
        "chat_output_is_evidence": any(source.get("chat_output_is_evidence") is True for source in sources),
        "semantic_gate": any(source.get("semantic_gate") is True for source in sources),
        "boundary": (
            "This summary documents the harness graph and agent contracts. Chat output and runtime logs "
            "remain diagnostic or command-contract evidence unless a validator-owned semantic gate accepts them."
        ),
    }


def build_harness_contract_matrix(
    *,
    sources: list[dict[str, Any]],
    graph_nodes: list[Any],
    roles: list[str],
) -> list[dict[str, Any]]:
    observed_artifacts = sorted(
        {
            artifact
            for source in sources
            for artifact in source.get("evidence_artifact_names", [])
            if isinstance(artifact, str)
        }
    )
    opencode_enabled = any(source.get("opencode_runtime_enabled") is True for source in sources)
    matrix = [
        contract_matrix_entry(
            stage="plan",
            graph_nodes=matching_graph_nodes(graph_nodes, ["load_plan", "fanout_workers"]),
            roles=matching_roles(roles, ["planner"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["worker_plan", "context_pack", "agent_index", "batch_profile_report"],
            ),
            validators=["validate_worker_plan_contract", "validate_context_ledger_contract"],
            boundary="Planner artifacts select worker assignments and context indexes only.",
        ),
        contract_matrix_entry(
            stage="translate",
            graph_nodes=matching_graph_nodes(graph_nodes, ["worker"]),
            roles=matching_roles(roles, ["worker"]),
            artifacts=observed_or_default(
                observed_artifacts,
                [
                    "assignment_request",
                    "worker_report",
                    "handoff_contract",
                    "opencode_session_evidence",
                    "opencode_preflight_report",
                ],
                extra=["opencode_contract_verification"] if opencode_enabled else [],
            ),
            validators=[
                "validate_opencode_agent_runtime_contract",
                "opencode_contract_verification",
                "validate_competition_summary_entrypoint_contract",
            ],
            boundary="Worker and OpenCode artifacts are command-contract evidence until validator-owned gates accept outputs.",
        ),
        contract_matrix_entry(
            stage="verify",
            graph_nodes=matching_graph_nodes(graph_nodes, ["merge"]),
            roles=matching_roles(roles, ["verifier"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["competition_summary", "workflow_metrics", "route_governance_metrics_report", "before_after_exhibit"],
            ),
            validators=[
                "validate_competition_summary_entrypoint_contract",
                "validate_route_governance_metrics_artifact",
            ],
            boundary="Verifier artifacts bind oracle, replay, diff, unsafe, and route metrics without creating a new semantic gate.",
        ),
        contract_matrix_entry(
            stage="repair",
            graph_nodes=matching_graph_nodes(graph_nodes, ["repair_retry"]),
            roles=matching_roles(roles, ["repairer"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["repair_hints", "rollback_evidence", "resume_manifest"],
            ),
            validators=["validate_repair_self_heal_contract", "validate_resume_manifest_contract"],
            boundary="Repair artifacts explain retries, rollback, and blocked next actions only.",
        ),
        contract_matrix_entry(
            stage="report",
            graph_nodes=matching_graph_nodes(graph_nodes, ["report"]),
            roles=matching_roles(roles, ["reporter"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["judge_evidence_index", "evaluate_report", "milestone_release_report", "judge_milestone_bundle"],
            ),
            validators=["validate_judge_evidence_index_contract", "validate_public_release_packet"],
            boundary="Reporter artifacts publish hashes, commands, and claim boundaries for judge review.",
        ),
    ]
    return matrix


def contract_matrix_entry(
    *,
    stage: str,
    graph_nodes: list[str],
    roles: list[str],
    artifacts: list[str],
    validators: list[str],
    boundary: str,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "graph_nodes": graph_nodes,
        "roles": roles,
        "artifacts": artifacts,
        "validators": validators,
        "semantic_gate": False,
        "chat_output_is_evidence": False,
        "translation_coverage_numerator": 0,
        "boundary": boundary,
    }


def matching_graph_nodes(graph_nodes: list[Any], candidates: list[str]) -> list[str]:
    observed = [node for node in graph_nodes if isinstance(node, str)]
    return [candidate for candidate in candidates if candidate in observed]


def matching_roles(roles: list[str], candidates: list[str]) -> list[str]:
    return [candidate for candidate in candidates if candidate in roles]


def observed_or_default(observed: list[str], defaults: list[str], *, extra: list[str] | None = None) -> list[str]:
    selected = [artifact for artifact in defaults if artifact in observed or artifact in defaults]
    for artifact in extra or []:
        if artifact not in selected:
            selected.append(artifact)
    return selected


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
        "quantitative_scorecard_is_not_semantic_acceptance",
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


def before_after_exhibit_has_verified_unsafe_baseline(before_after_repair_exhibit: dict[str, Any]) -> bool:
    observed_unit = False
    for source in object_list(before_after_repair_exhibit.get("sources")):
        for unit in object_list(source.get("before_after_units")):
            observed_unit = True
            if not before_after_unit_has_verified_unsafe_baseline(unit):
                return False
    return observed_unit


def before_after_unit_has_verified_unsafe_baseline(unit: dict[str, Any]) -> bool:
    baseline = unit.get("baseline_verification")
    if not isinstance(baseline, dict):
        return False
    path = baseline.get("path")
    sha256 = baseline.get("sha256")
    return (
        isinstance(path, str)
        and bool(path)
        and isinstance(sha256, str)
        and len(sha256) == 64
        and baseline.get("status") == "passed"
        and baseline.get("semantic_pass") is True
        and baseline.get("semantic_claim_source") == "verified_unsafe_baseline_gates"
        and baseline.get("generated_draft_semantic_pass") is False
    )


def build_known_gaps(
    *,
    proof_classes: dict[str, Any],
    opencode_runtime: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = [
        {
            "gap_id": "translator_generated_coverage_not_claimed",
            "boundary": "translation_coverage_numerator remains 0 for this bundle.",
        },
        {
            "gap_id": "accepted_evidence_not_translator_generated",
            "boundary": "Accepted-evidence semantic pass counts remain report context and do not become generated-draft acceptance.",
        },
    ]
    if not before_after_exhibit_has_verified_unsafe_baseline(before_after_repair_exhibit):
        gaps.append(
            {
                "gap_id": "c2rust_baseline_output_still_not_verified_here",
                "boundary": "This bundle does not prove a new C2Rust compile-passed or verified unsafe baseline.",
            }
        )
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


def build_quantitative_evaluation(
    *,
    workflow_metrics: dict[str, Any],
    route_governance_metrics: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
    blocked_repairs_rollup: dict[str, Any],
    unsafe_scope: dict[str, Any],
    semantic_evidence: dict[str, Any],
    opencode_runtime: dict[str, Any],
    proof_classes: dict[str, Any],
    publishability: dict[str, Any],
) -> dict[str, Any]:
    workflow_rollup = (
        workflow_metrics.get("rollup", {}) if isinstance(workflow_metrics.get("rollup"), dict) else {}
    )
    route_rollup = (
        route_governance_metrics.get("rollup", {})
        if isinstance(route_governance_metrics.get("rollup"), dict)
        else {}
    )
    before_after_rollup = (
        before_after_repair_exhibit.get("rollup", {})
        if isinstance(before_after_repair_exhibit.get("rollup"), dict)
        else {}
    )
    blocked_rollup = (
        blocked_repairs_rollup.get("rollup", {})
        if isinstance(blocked_repairs_rollup.get("rollup"), dict)
        else {}
    )
    repair_activity = (
        workflow_rollup.get("repair_activity", {}) if isinstance(workflow_rollup.get("repair_activity"), dict) else {}
    )
    unsafe_reduction = (
        workflow_rollup.get("unsafe_reduction", {}) if isinstance(workflow_rollup.get("unsafe_reduction"), dict) else {}
    )
    accepted_evidence_count = int_or_zero(route_rollup.get("accepted_evidence_semantic_pass_count"))
    c2rust_baseline_rollup = (
        route_rollup.get("c2rust_baseline")
        if isinstance(route_rollup.get("c2rust_baseline"), dict)
        else empty_c2rust_baseline_milestone_rollup()
    )
    tracked_route_decisions = int_or_zero(route_rollup.get("tracked_route_decision_artifacts"))
    tracked_slice_contexts = int_or_zero(route_rollup.get("tracked_slice_gate_contexts"))
    opencode_enabled = int_or_zero(opencode_runtime.get("enabled_entrypoint_count")) > 0
    opencode_status = (
        "command_contract_executed"
        if opencode_enabled and bool(opencode_runtime.get("all_contracts_executed"))
        else "command_contract_incomplete"
        if opencode_enabled
        else "not_enabled"
    )
    return {
        "report_kind": "quantitative-evaluation-scorecard",
        "evaluation_scope": "bounded-mvp",
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "project_slice_counts": {
            "entrypoint_count": len(
                [
                    entry
                    for entry in proof_classes.get("entrypoints", [])
                    if isinstance(entry, dict)
                ]
            ),
            "workflow_source_count": int_or_zero(workflow_rollup.get("source_count")),
            "workflow_units_total": int_or_zero(workflow_rollup.get("units_total")),
            "workflow_units_converged": int_or_zero(workflow_rollup.get("units_converged")),
            "before_after_bound_unit_count": int_or_zero(before_after_rollup.get("bound_unit_count")),
            "tracked_route_decision_artifacts": tracked_route_decisions,
            "tracked_slice_gate_contexts": tracked_slice_contexts,
        },
        "outcome_counts": {
            "accepted_evidence_semantic_pass_count": accepted_evidence_count,
            "translator_generated_semantic_pass_count": int_or_zero(
                semantic_evidence.get("translator_generated_semantic_pass_count")
            ),
            "translation_coverage_numerator": 0,
            "generated_draft_semantic_pass": False,
            "blocked_repair_count": int_or_zero(blocked_rollup.get("blocked_repair_count")),
            "human_action_required_count": int_or_zero(blocked_rollup.get("human_action_required_count")),
            "human_interventions": int_or_zero(workflow_rollup.get("human_interventions")),
            "llm_calls": int_or_zero(workflow_rollup.get("llm_calls")),
            "auto_recovered_unit_count": int_or_zero(before_after_rollup.get("auto_recovered_unit_count")),
            "rollback_evidence_count": int_or_zero(before_after_rollup.get("rollback_evidence_count")),
        },
        "unsafe_reduction": {
            "status": unsafe_reduction.get("status", "unknown"),
            "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
            "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
            "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
            "scope": unsafe_scope.get("scope", "unknown"),
            "all_sources_measured": bool(unsafe_scope.get("all_sources_measured")),
            "measured_units": int_or_zero(unsafe_scope.get("measured_units")),
            "total_units": int_or_zero(unsafe_scope.get("total_units")),
        },
        "repair_activity": {
            "observed_source_count": int_or_zero(repair_activity.get("observed_source_count")),
            "repair_history_unit_count": int_or_zero(repair_activity.get("repair_history_unit_count")),
            "auto_recovered_unit_count": int_or_zero(repair_activity.get("auto_recovered_unit_count")),
            "avg_repair_rounds": number_or_zero(repair_activity.get("avg_repair_rounds")),
            "auto_recovery_rate": number_or_zero(repair_activity.get("auto_recovery_rate")),
            "human_interventions": int_or_zero(repair_activity.get("human_interventions")),
        },
        "self_heal_classification": build_self_heal_classification(blocked_rollup),
        "baseline_comparison": {
            "raw_c2rust": comparison_row(
                status="manifest_status_observed"
                if int_or_zero(c2rust_baseline_rollup.get("unique_manifest_count")) > 0
                else "not_verified_here",
                evidence_role="baseline_or_candidate_context_only",
                boundary="Raw C2Rust baseline manifests are counted as candidate context only; no output is accepted by this milestone bundle.",
                c2rust_baseline_rollup=c2rust_baseline_rollup,
            ),
            "c2rust_repair": comparison_row(
                status="not_verified_here",
                evidence_role="baseline_or_repair_context_only",
                boundary="C2Rust repair remains subject to the same validators and is not accepted by this scorecard.",
            ),
            "typed_ir_route": comparison_row(
                status="route_governance_tracked",
                evidence_role="candidate_generation_and_refusal_governance",
                boundary="Typed-IR route metrics are governance signals, not semantic acceptance.",
                tracked_route_decision_artifacts=tracked_route_decisions,
                tracked_slice_gate_contexts=tracked_slice_contexts,
            ),
            "opencode_llm_worker": comparison_row(
                status=opencode_status,
                evidence_role="command_contract_and_worker_runtime",
                boundary="OpenCode worker evidence records command-contract execution; chat output is not semantic evidence.",
                worker_count=int_or_zero(opencode_runtime.get("worker_count")),
                chat_output_is_evidence=False,
                chat_output_boundary_ok=bool(opencode_runtime.get("chat_output_is_evidence_false")),
            ),
            "handwritten_reference": comparison_row(
                status="accepted_evidence_context",
                evidence_role="oracle_or_reference_context",
                boundary="Accepted evidence may validate a case but does not become translator-generated coverage.",
                accepted_evidence_semantic_pass_count=accepted_evidence_count,
                counts_as_translator_generated_coverage=False,
            ),
        },
        "proof_class_summary": {
            "highest_proof_class": proof_classes.get("highest_proof_class", "unknown"),
            "competition_exact_publishable": bool(publishability.get("competition_exact_publishable")),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "scorecard_is_semantic_gate": False,
            "baseline_comparison_is_semantic_acceptance": False,
        },
        "boundary": (
            "This scorecard summarizes existing validator-owned artifacts for judge review. It is not a new "
            "semantic gate, does not increase translator-generated coverage, and does not claim competition-exact proof."
        ),
    }


def build_self_heal_classification(blocked_rollup: dict[str, Any]) -> dict[str, Any]:
    next_actions = object_list(blocked_rollup.get("next_actions"))
    route_counts: Counter[str] = Counter()
    next_action_counts: Counter[str] = Counter()
    smallest_next_test_kind_counts: Counter[str] = Counter()
    for action in next_actions:
        route = action.get("route")
        if isinstance(route, str) and route:
            route_counts[route] += 1
        next_action = action.get("next_action")
        if isinstance(next_action, str) and next_action:
            next_action_counts[next_action] += 1
        smallest_next_test_kind = action.get("smallest_next_test_kind")
        if isinstance(smallest_next_test_kind, str) and smallest_next_test_kind:
            smallest_next_test_kind_counts[smallest_next_test_kind] += 1
    if not smallest_next_test_kind_counts:
        for test in object_list(blocked_rollup.get("smallest_next_tests")):
            kind = test.get("kind")
            if isinstance(kind, str) and kind:
                smallest_next_test_kind_counts[kind] += 1
    return {
        "report_kind": "self-heal-classification",
        "source": "blocked_repairs_rollup",
        "status": blocked_rollup.get("status") if isinstance(blocked_rollup.get("status"), str) else "unknown",
        "blocked_repair_count": int_or_zero(blocked_rollup.get("blocked_repair_count")),
        "human_action_required_count": int_or_zero(blocked_rollup.get("human_action_required_count")),
        "status_counts": int_count_map(blocked_rollup.get("status_counts")),
        "blocked_reason_counts": int_count_map(blocked_rollup.get("blocked_reason_counts")),
        "ir_feature_gap_kinds": int_count_map(blocked_rollup.get("ir_feature_gap_kinds")),
        "forbidden_change_counts": int_count_map(blocked_rollup.get("forbidden_change_counts")),
        "source_span_kind_counts": int_count_map(blocked_rollup.get("source_span_kind_counts")),
        "route_counts": sorted_int_counter(route_counts),
        "next_action_counts": sorted_int_counter(next_action_counts),
        "smallest_next_test_kind_counts": sorted_int_counter(smallest_next_test_kind_counts),
        "next_action_count": len(next_actions),
        "sample_next_action_limit": SELF_HEAL_SAMPLE_NEXT_ACTION_LIMIT,
        "sample_next_actions": next_actions[:SELF_HEAL_SAMPLE_NEXT_ACTION_LIMIT],
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Self-heal classification is derived from fail-closed blocked-repair playbooks. It describes "
            "repair categories and next actions for judge review only; it is not a semantic gate and does "
            "not increase translator-generated coverage."
        ),
    }


def comparison_row(
    *,
    status: str,
    evidence_role: str,
    boundary: str,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "status": status,
        "evidence_role": evidence_role,
        "semantic_acceptance_claimed": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": boundary,
    }
    row.update(extra)
    return row


def build_publication_manifest(
    *,
    run_report: dict[str, Any],
    run_report_path: Path,
    out_path: Path,
    judge_entrypoints_run_report: dict[str, Any],
    entrypoint_reports: list[dict[str, Any]],
    claim_boundary: dict[str, Any],
    claim_scope: dict[str, Any],
    proof_classes: dict[str, Any],
    publishability: dict[str, Any],
    harness_architecture_summary: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
    opencode_runtime: dict[str, Any],
    reproduction_commands: dict[str, Any],
    must_not_claim: list[str],
    known_gaps: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    config = run_report.get("config") if isinstance(run_report.get("config"), dict) else {}
    archive = (
        run_report.get("competition_config_archive")
        if isinstance(run_report.get("competition_config_archive"), dict)
        else None
    )
    artifact_refs = publication_artifact_refs(entrypoint_reports)
    if not artifact_refs and judge_entrypoints_run_report.get("status") == "present":
        artifact_refs.append(
            {
                **json.loads(json.dumps(judge_entrypoints_run_report)),
                "artifact_name": "judge_entrypoints_run_report",
                "entrypoint_id": "judge_entrypoints_run",
            }
        )
    repo_commit = source_commit_ref(repo_root=repo_root)
    return {
        "report_kind": "publication-manifest",
        "bundle_version": 1,
        "publication_scope": publication_scope(
            claim_scope=claim_scope,
            publishability=publishability,
        ),
        "source_commit": repo_commit,
        "repo_commit": repo_commit,
        "target_source_pin": publication_source_pin_ref(run_report),
        "judge_config": publication_config_ref(config),
        "competition_config_archive": publication_archive_ref(archive),
        "judge_entrypoints_run_report": judge_entrypoints_run_report,
        "readiness_report": artifact_ref_from_existing(run_report.get("readiness_report"), repo_root=repo_root)
        or {"path": "unknown", "status": "absent"},
        "judge_milestone_bundle": {
            "path": validator.repo_relative(out_path, repo_root),
            "status": "self",
            "hash_boundary": "The bundle does not embed its own sha256 because that would make the hash recursive.",
        },
        "run_report_path": validator.repo_relative(run_report_path, repo_root),
        "supported_subset": {
            "entrypoint_count": len([entry for entry in run_report.get("entrypoints", []) if isinstance(entry, dict)]),
            "entrypoint_ids": [
                entry.get("id")
                for entry in run_report.get("entrypoints", [])
                if isinstance(entry, dict)
            ],
            "proof_classes": proof_classes,
            "harness_graph_runtime": harness_architecture_summary.get("graph_runtime"),
            "harness_roles": harness_architecture_summary.get("roles", []),
            "repair_round_cap": int_or_zero(harness_architecture_summary.get("repair_round_cap")),
            "before_after_bound_unit_count": int_or_zero(
                before_after_repair_exhibit.get("rollup", {}).get("bound_unit_count")
                if isinstance(before_after_repair_exhibit.get("rollup"), dict)
                else 0
            ),
            "opencode_runtime_enabled": int_or_zero(opencode_runtime.get("enabled_entrypoint_count")) > 0,
        },
        "published_entrypoints": publication_entrypoints(entrypoint_reports),
        "published_artifact_refs": artifact_refs,
        "published_artifact_count": len(artifact_refs),
        "publishability": publishability,
        "release_tag_readiness": build_release_tag_readiness(
            repo_commit=repo_commit,
            publishability=publishability,
        ),
        "claim_scope": claim_scope,
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "publication_manifest_is_semantic_gate": False,
            "boundary": (
                "This manifest indexes the external review package. It does not create semantic acceptance, "
                "competition-exact proof, or translator-generated coverage."
            ),
            "source_boundary": claim_boundary.get("boundary"),
        },
        "reproduction_commands": reproduction_commands,
        "known_gaps": known_gaps,
        "known_non_goals": [
            "semantic acceptance",
            "competition-exact proof without competition host attestation",
            "translator-generated coverage increase",
            "project-level C-to-Rust completeness",
            "OpenCode chat output as semantic evidence",
        ],
        "must_not_claim": must_not_claim,
    }


def build_release_tag_readiness(*, repo_commit: dict[str, Any], publishability: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_kind": "release-tag-readiness",
        "status": "not_tagged",
        "tag_name": None,
        "tag_target_commit": None,
        "repo_commit": repo_commit.get("commit") if isinstance(repo_commit.get("commit"), str) else None,
        "tag_matches_repo_commit": False,
        "remote_release_notes_status": "not_published",
        "external_review_record_status": "not_recorded",
        "external_milestone_claim_ready": False,
        "publishability_status": publishability.get("status"),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Tag, remote release notes, and external review records are publication readiness evidence only. "
            "They do not create semantic acceptance or translator-generated coverage."
        ),
    }


def publication_scope(*, claim_scope: dict[str, Any], publishability: dict[str, Any]) -> str:
    if publishability.get("external_milestone_claim_ready"):
        return "full"
    if publishability.get("all_entrypoints_run_publishable"):
        return "internal_preview_full"
    if claim_scope.get("external_review_index_ready"):
        return "partial"
    return "blocked"


def publication_entrypoints(entrypoint_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": entry.get("id"),
            "status": entry.get("status"),
            "proof_class": entry.get("proof_class"),
            "run_id": entry.get("run_id"),
        }
        for entry in entrypoint_reports
    ]


def publication_artifact_refs(entrypoint_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for entry in entrypoint_reports:
        artifacts = entry.get("artifacts", {})
        if not isinstance(artifacts, dict):
            continue
        for artifact_name, artifact in artifacts.items():
            if not isinstance(artifact, dict):
                continue
            path = artifact.get("path")
            sha256 = artifact.get("sha256")
            if not isinstance(path, str):
                continue
            key = (path, sha256 if isinstance(sha256, str) else None)
            if key in seen:
                continue
            seen.add(key)
            ref = dict(artifact)
            ref["artifact_name"] = artifact_name
            ref["entrypoint_id"] = entry.get("id")
            refs.append(ref)
    return refs


def publication_artifact_ref_blockers(entrypoint_reports: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for entry in entrypoint_reports:
        entrypoint_id = str(entry.get("id", "unknown"))
        artifacts = entry.get("artifacts", {})
        if not isinstance(artifacts, dict):
            continue
        for artifact_name, artifact in sorted(artifacts.items()):
            if not isinstance(artifact, dict):
                continue
            status = artifact.get("status")
            if status not in {"present", "passed"}:
                blockers.append(f"published_artifact_not_present:{entrypoint_id}:{artifact_name}:{status}")
    return blockers


def source_commit_ref(*, repo_root: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return {"status": "absent", "reason": f"{type(exc).__name__}: {exc}"}
    commit = completed.stdout.strip()
    if completed.returncode == 0 and len(commit) == 40 and all(char in "0123456789abcdef" for char in commit):
        return {"status": "present", "commit": commit}
    return {
        "status": "absent",
        "reason": (completed.stderr or completed.stdout or "git rev-parse HEAD failed").strip(),
    }


def publication_config_ref(config: dict[str, Any]) -> dict[str, Any]:
    path = config.get("path") if isinstance(config.get("path"), str) else "unknown"
    ref = {
        "path": path,
        "status": config.get("status", "present" if path != "unknown" else "absent"),
    }
    if isinstance(config.get("sha256"), str):
        ref["sha256"] = config["sha256"]
    return ref


def publication_source_pin_ref(run_report: dict[str, Any]) -> dict[str, Any]:
    validation = run_report.get("validation")
    if isinstance(validation, dict):
        contract = validation.get("source_pin_contract")
        if isinstance(contract, dict):
            return {
                "status": contract.get("status", "unknown"),
                "target_id": contract.get("target_id"),
                "repository": contract.get("repository"),
                "branch": contract.get("branch"),
                "canonical_commit": contract.get("canonical_commit"),
            }
    return {"status": "absent"}


def publication_archive_ref(archive: dict[str, Any] | None) -> dict[str, Any]:
    if archive is None:
        return {"status": "absent"}
    ref = {
        "status": archive.get("status", "present"),
        "root": archive.get("root"),
        "file_count": int_or_zero(archive.get("file_count")),
        "report_kind": archive.get("report_kind"),
    }
    files = archive.get("files")
    if isinstance(files, dict):
        ref["file_count"] = len(files)
        manifest = files.get("config/competition-env/bundle-manifest.json")
        if isinstance(manifest, dict):
            ref["bundle_manifest"] = {
                "path": manifest.get("path"),
                "sha256": manifest.get("sha256"),
                "status": manifest.get("status"),
            }
    materialized_manifest = archive.get("materialized_manifest")
    if isinstance(materialized_manifest, dict):
        ref["materialized_manifest"] = {
            "path": materialized_manifest.get("path"),
            "sha256": materialized_manifest.get("sha256"),
            "status": materialized_manifest.get("status"),
        }
    external_refs = archive.get("external_refs")
    if isinstance(external_refs, dict):
        ref["external_ref_count"] = len(external_refs)
        ref["external_refs"] = {
            path: {
                "path": entry.get("path"),
                "sha256": entry.get("sha256"),
                "status": entry.get("status"),
                "role": entry.get("role"),
            }
            for path, entry in sorted(external_refs.items())
            if isinstance(entry, dict)
        }
    return ref


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
            "python3 -B -m validation.tools.run_judge_entrypoints "
            f"--config {config_path} --out {run_report_rel}"
        )
    else:
        runner_command = f"python3 -B -m validation.tools.run_judge_entrypoints --out {run_report_rel}"
    return {
        "run_judge_entrypoints": runner_command,
        "build_bundle": (
            "python3 -B -m validation.tools.judge_milestone_bundle "
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
    expected_sha256: str | None = None
    expected_status: str | None = None
    if isinstance(value, str):
        path_text = value
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        path_text = value["path"]
        if isinstance(value.get("sha256"), str):
            expected_sha256 = value["sha256"]
        if isinstance(value.get("status"), str):
            expected_status = value["status"]
    if path_text is None:
        return None
    try:
        path = resolve_input_path(Path(path_text), repo_root=repo_root)
    except (OSError, ValueError):
        return {"path": path_text, "status": "invalid"}
    ref = artifact_ref(path, repo_root=repo_root)
    if expected_status == "present" and ref.get("status") != "present":
        ref["status"] = "status_mismatch"
        ref["expected_status"] = expected_status
        ref["current_status"] = "missing"
        return ref
    if expected_status == "present" and expected_sha256 is None:
        ref["status"] = "missing_expected_sha256"
        return ref
    if expected_sha256 is not None and ref.get("sha256") != expected_sha256:
        ref["status"] = "sha256_mismatch"
        ref["expected_sha256"] = expected_sha256
        if isinstance(ref.get("sha256"), str):
            ref["current_sha256"] = ref["sha256"]
        return ref
    return ref


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
        "before_after_units": workflow_before_after_unit_summaries(per_unit_statuses),
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
    inputs = payload.get("inputs", {}) if isinstance(payload.get("inputs"), dict) else {}
    evidence_governance = (
        inputs.get("evidence_governance", {}) if isinstance(inputs.get("evidence_governance"), dict) else {}
    )
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
        "tracked_capability_delta_ledgers": int_or_zero(metrics.get("tracked_capability_delta_ledgers")),
        "tracked_capability_delta_count": int_or_zero(metrics.get("tracked_capability_delta_count")),
        "capability_delta_ledger": capability_delta_ledger_source(metrics.get("capability_delta_ledger")),
        "evidence_root": evidence_governance.get("evidence_root")
        if isinstance(evidence_governance.get("evidence_root"), str)
        else None,
        "c2rust_baseline": c2rust_baseline_source(metrics.get("c2rust_baseline")),
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
    policy_compliance = (
        payload.get("policy_compliance") if isinstance(payload.get("policy_compliance"), dict) else {}
    )
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
        "policy_compliance": {
            "policy_tier": policy_compliance.get("policy_tier", "unknown"),
            "status": policy_compliance.get("status", "unknown"),
            "failed_gates": policy_compliance.get("failed_gates")
            if isinstance(policy_compliance.get("failed_gates"), list)
            else [],
        },
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
    proof_class: str,
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
        "preflight_proof_summary": opencode_preflight_proof_summary_from_index(
            payload,
            entrypoint_id=entrypoint_id,
            proof_class=proof_class,
            repo_root=repo_root,
        ),
    }


def opencode_preflight_proof_summary_from_index(
    payload: dict[str, Any],
    *,
    entrypoint_id: str,
    proof_class: str,
    repo_root: Path,
) -> dict[str, Any]:
    runtime = payload.get("opencode_agent_runtime") if isinstance(payload.get("opencode_agent_runtime"), dict) else {}
    refs = payload.get("evidence_artifact_refs") if isinstance(payload.get("evidence_artifact_refs"), dict) else {}
    raw_ref = runtime.get("opencode_preflight_report")
    if not isinstance(raw_ref, dict):
        raw_ref = refs.get("opencode_preflight_report")
    preflight_ref = artifact_ref_from_existing(raw_ref, repo_root=repo_root)
    if preflight_ref is None:
        return opencode_preflight_absent_summary(required=True, entrypoint_id=entrypoint_id)

    result: dict[str, Any] = {
        "status": "missing" if preflight_ref.get("status") != "present" else "failed",
        "required_when_opencode_runtime_enabled": True,
        "entrypoint_id": entrypoint_id,
        "preflight_report": preflight_ref,
        "proof_class": proof_class,
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "OpenCode preflight proves GLM-5.1 command-contract availability only; "
            "it is not semantic acceptance or translator coverage."
        ),
    }
    if preflight_ref.get("status") != "present":
        return result

    try:
        preflight_payload = validator.load_json(resolve_input_path(Path(str(preflight_ref["path"])), repo_root=repo_root))
    except (OSError, ValueError, json.JSONDecodeError):
        result["status"] = "read_failed"
        return result

    availability = (
        preflight_payload.get("opencode_model_availability")
        if isinstance(preflight_payload.get("opencode_model_availability"), dict)
        else {}
    )
    launch_policy = (
        preflight_payload.get("launch_policy") if isinstance(preflight_payload.get("launch_policy"), dict) else {}
    )
    contract = (
        preflight_payload.get("contract_verification")
        if isinstance(preflight_payload.get("contract_verification"), dict)
        else {}
    )
    runtime_env = None
    try:
        runtime_env = validator.validate_opencode_runtime_env_contract(
            preflight_payload.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary",
        )
    except ValueError:
        runtime_env = None
    result.update(
        {
            "run_id": preflight_payload.get("run_id"),
            "opencode_command": availability.get("opencode_command"),
            "opencode_agent": launch_policy.get("opencode_agent"),
            "opencode_model": launch_policy.get("opencode_model"),
            "opencode_variant": launch_policy.get("opencode_variant"),
            "required_model": availability.get("required_model"),
            "model_availability_status": availability.get("status"),
            "model_listed": availability.get("model_listed"),
            "model_probe_argv": availability.get("argv") if isinstance(availability.get("argv"), list) else [],
            "process_returncode": int_or_none(availability.get("process_returncode")),
            "model_probe_logs": opencode_model_probe_log_refs(availability, repo_root=repo_root),
            "contract_status": contract.get("status"),
            "marker_exists": preflight_payload.get("marker_exists"),
            "opencode_run_launched": preflight_payload.get("opencode_run_launched"),
            "opencode_run_argv_bound": opencode_preflight_session_contract_passed(
                preflight_payload,
                contract=contract,
                repo_root=repo_root,
            ),
        }
    )
    if runtime_env is not None:
        result["opencode_runtime_env"] = runtime_env
        result["opencode_runtime_env_sha256"] = runtime_env["env_sha256"]
    result["status"] = (
        "passed"
        if opencode_preflight_summary_passed(
            result,
            availability,
            preflight_payload=preflight_payload,
            contract=contract,
            repo_root=repo_root,
        )
        else "failed"
    )
    return result


def opencode_preflight_absent_summary(*, required: bool, entrypoint_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "absent",
        "required_when_opencode_runtime_enabled": required,
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "opencode_agent": validator.COMPETITION_OPENCODE_AGENT,
        "opencode_variant": validator.COMPETITION_OPENCODE_VARIANT,
        "opencode_run_argv_bound": False,
        "boundary": (
            "OpenCode preflight proof is absent; runtime output is not semantic evidence "
            "and does not increase translator coverage."
        ),
    }
    if entrypoint_id is not None:
        result["entrypoint_id"] = entrypoint_id
    return result


def opencode_model_probe_log_refs(availability: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    logs = availability.get("logs") if isinstance(availability.get("logs"), dict) else {}
    result: dict[str, Any] = {}
    for stream in ("stdout", "stderr"):
        path_text = logs.get(stream)
        if not isinstance(path_text, str):
            result[stream] = {"path": "unknown", "status": "absent"}
            continue
        try:
            result[stream] = artifact_ref(resolve_input_path(Path(path_text), repo_root=repo_root), repo_root=repo_root)
        except (OSError, ValueError):
            result[stream] = {"path": path_text, "status": "invalid"}
    return result


def opencode_preflight_summary_passed(
    summary: dict[str, Any],
    availability: dict[str, Any],
    *,
    preflight_payload: dict[str, Any],
    contract: dict[str, Any],
    repo_root: Path,
) -> bool:
    if summary.get("opencode_command") != validator.COMPETITION_OPENCODE_COMMAND:
        return False
    if summary.get("opencode_agent") != validator.COMPETITION_OPENCODE_AGENT:
        return False
    if summary.get("opencode_model") != validator.COMPETITION_OPENCODE_MODEL:
        return False
    if summary.get("opencode_variant") != validator.COMPETITION_OPENCODE_VARIANT:
        return False
    if summary.get("required_model") != validator.COMPETITION_OPENCODE_MODEL:
        return False
    if summary.get("model_availability_status") != "available":
        return False
    if summary.get("model_listed") is not True:
        return False
    if int_or_zero(summary.get("process_returncode")) != 0:
        return False
    if summary.get("contract_status") != "executed":
        return False
    if summary.get("marker_exists") is not True:
        return False
    if summary.get("opencode_run_launched") is not True:
        return False
    if summary.get("opencode_run_argv_bound") is not True:
        return False
    if not isinstance(summary.get("opencode_runtime_env"), dict):
        return False
    if summary.get("opencode_runtime_env_sha256") != summary["opencode_runtime_env"].get("env_sha256"):
        return False
    if not validator.opencode_models_argv_matches(
        summary.get("model_probe_argv"),
        expected_command=validator.COMPETITION_OPENCODE_COMMAND,
    ):
        return False
    try:
        validator.validate_opencode_model_probe_log_hashes(
            availability,
            "opencode_preflight_proof_summary",
            repo_root=repo_root,
        )
    except ValueError:
        return False
    if not opencode_preflight_session_contract_passed(
        preflight_payload,
        contract=contract,
        repo_root=repo_root,
    ):
        return False
    return True


def opencode_preflight_session_contract_passed(
    preflight_payload: dict[str, Any],
    *,
    contract: dict[str, Any],
    repo_root: Path,
) -> bool:
    try:
        if preflight_payload.get("process_returncode") != 0:
            return False
        preflight_runtime_env = validator.validate_opencode_runtime_env_contract(
            preflight_payload.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary",
        )
        handoff_binding = validator.validate_hash_bound_artifact_binding(
            preflight_payload.get("handoff_contract"),
            "opencode_preflight_proof_summary.handoff_contract",
            repo_root=repo_root,
        )
        handoff_payload = validator.require_object(
            validator.load_json(validator.repo_path(handoff_binding["path"], repo_root=repo_root)),
            "opencode_preflight_proof_summary.handoff_contract file",
        )
        if handoff_payload.get("runner_kind") != "opencode-preflight":
            return False
        if handoff_payload.get("run_id") != preflight_payload.get("run_id"):
            return False
        handoff_runtime_env = validator.validate_opencode_runtime_env_contract(
            handoff_payload.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary.handoff_contract",
        )
        if handoff_runtime_env != preflight_runtime_env:
            return False
        handoff_policy = validator.validate_opencode_launch_policy_binding(
            handoff_payload.get("launch_policy"),
            handoff_payload.get("launch_policy_sha256"),
            "opencode_preflight_proof_summary.handoff_contract",
        )
        preflight_policy = validator.validate_opencode_launch_policy_binding(
            preflight_payload.get("launch_policy"),
            preflight_payload.get("launch_policy_sha256"),
            "opencode_preflight_proof_summary.preflight_report",
        )
        if handoff_policy != preflight_policy:
            return False
        worker_command = handoff_payload.get("worker_command")
        if not isinstance(worker_command, list) or not worker_command or not all(
            isinstance(item, str) and item for item in worker_command
        ):
            return False
        worker_command_line = validator.require_string(
            handoff_payload.get("worker_command_line"),
            "opencode_preflight_proof_summary.handoff_contract.worker_command_line",
        )
        if worker_command_line != validator.shell_command_line(worker_command):
            return False
        if handoff_payload.get("worker_command_sha256") != validator.sha256_text(worker_command_line):
            return False
        report_argv = validator.require_string_argv(
            preflight_payload.get("argv"),
            "opencode_preflight_proof_summary.preflight_report.argv",
        )
        handoff_argv = validator.require_string_argv(
            handoff_payload.get("opencode_argv"),
            "opencode_preflight_proof_summary.handoff_contract.opencode_argv",
        )
        if report_argv != handoff_argv:
            return False
        validator.validate_opencode_run_argv_binding(
            report_argv,
            "opencode_preflight_proof_summary.preflight_report.argv",
            launch_policy=preflight_policy,
        )
        handoff_command_line = validator.require_string(
            handoff_payload.get("opencode_command_line"),
            "opencode_preflight_proof_summary.handoff_contract.opencode_command_line",
        )
        if handoff_command_line != validator.shell_command_line(handoff_argv):
            return False
        handoff_prompt = validator.require_string(
            handoff_payload.get("prompt"),
            "opencode_preflight_proof_summary.handoff_contract.prompt",
        )
        if handoff_prompt != handoff_argv[-1]:
            return False
        marker_path_text = validator.require_string(
            preflight_payload.get("marker_path"),
            "opencode_preflight_proof_summary.marker_path",
        )
        expected_marker_path = validator.require_string(
            handoff_payload.get("expected_marker_path"),
            "opencode_preflight_proof_summary.handoff_contract.expected_marker_path",
        )
        if marker_path_text != expected_marker_path:
            return False
        marker_path = validator.repo_path(marker_path_text, repo_root=repo_root)
        if not marker_path.is_file():
            return False
        session_binding = validator.validate_hash_bound_artifact_binding(
            preflight_payload.get("opencode_session_evidence"),
            "opencode_preflight_proof_summary.opencode_session_evidence",
            repo_root=repo_root,
        )
        session_evidence = validator.require_object(
            validator.load_json(validator.repo_path(session_binding["path"], repo_root=repo_root)),
            "opencode_preflight_proof_summary.opencode_session_evidence file",
        )
        validator.validate_opencode_session_evidence_contract(
            session_evidence,
            "opencode_preflight_proof_summary.opencode_session_evidence",
            repo_root=repo_root,
        )
        session_runtime_env = validator.validate_opencode_runtime_env_contract(
            session_evidence.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary.opencode_session_evidence",
        )
        if session_runtime_env != preflight_runtime_env:
            return False
        validator.validate_opencode_contract_recomputed_from_session(
            embedded_verification=contract,
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=marker_path,
            label="opencode_preflight_proof_summary",
            repo_root=repo_root,
        )
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return False
    return True


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
    overlay_result = before_after_exhibit_unit_overlay_result(
        payload,
        entrypoint_id=entrypoint_id,
        repo_root=repo_root,
    )
    before_after_units = merge_before_after_exhibit_unit_overlays(
        before_after_units,
        overlay_result["overlays"],
    )
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
        "nested_artifact_ref_blockers": overlay_result["blockers"],
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


def before_after_exhibit_unit_overlay_result(
    payload: dict[str, Any],
    *,
    entrypoint_id: str,
    repo_root: Path,
) -> dict[str, Any]:
    refs = payload.get("evidence_artifact_refs")
    if not isinstance(refs, dict):
        return {"overlays": {}, "blockers": []}
    result: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for ref_name in ["before_after_exhibit", "before_after_exhibit_report"]:
        ref = artifact_ref_from_existing(refs.get(ref_name), repo_root=repo_root)
        if ref is None:
            continue
        status = ref.get("status")
        if status == "sha256_mismatch":
            blockers.append(f"nested_artifact_sha256_mismatch:{entrypoint_id}:{ref_name}")
            continue
        if status == "missing_expected_sha256":
            blockers.append(f"nested_artifact_missing_sha256:{entrypoint_id}:{ref_name}")
            continue
        if status == "status_mismatch":
            blockers.append(f"nested_artifact_status_mismatch:{entrypoint_id}:{ref_name}")
            continue
        if status != "present":
            blockers.append(f"nested_artifact_not_present:{entrypoint_id}:{ref_name}:{status}")
            continue
        exhibit = load_present_json_artifact(ref, repo_root=repo_root)
        if not isinstance(exhibit, dict):
            continue
        units = exhibit.get("units")
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            unit_id = unit.get("unit_id")
            if not isinstance(unit_id, str) or unit_id in result:
                continue
            overlay: dict[str, Any] = {}
            baseline_verification = baseline_verification_summary(unit.get("baseline_verification"))
            if baseline_verification is not None:
                overlay["baseline_verification"] = baseline_verification
            repair_history = repair_history_summary(unit.get("repair_history"))
            if repair_history is not None:
                overlay["repair_history"] = repair_history
            repair_rounds = int_or_none(unit.get("repair_rounds"))
            if repair_rounds is not None:
                overlay["repair_rounds"] = repair_rounds
            if isinstance(unit.get("auto_recovered"), bool):
                overlay["auto_recovered"] = unit["auto_recovered"]
            root_cause_key = unit.get("root_cause_key")
            if isinstance(root_cause_key, str) and root_cause_key:
                overlay["root_cause_key"] = root_cause_key
            patch_origin = patch_origin_summary(unit.get("patch_origin"))
            if patch_origin is not None:
                overlay["patch_origin"] = patch_origin
            safety_loop_provenance = safety_loop_provenance_summary(unit.get("safety_loop_provenance"))
            if safety_loop_provenance is not None:
                overlay["safety_loop_provenance"] = safety_loop_provenance
            if overlay:
                result[unit_id] = overlay
    return {"overlays": result, "blockers": blockers}


def merge_before_after_exhibit_unit_overlays(
    units: list[dict[str, Any]],
    overlays: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not overlays:
        return units
    for unit in units:
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or unit_id not in overlays:
            continue
        for key, value in overlays[unit_id].items():
            if key not in unit:
                unit[key] = deepcopy(value)
    return units


def artifact_binding_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    sha256 = value.get("sha256")
    if not isinstance(path, str) or not isinstance(sha256, str):
        return None
    return {"path": path, "sha256": sha256}


def baseline_verification_summary(value: object) -> dict[str, Any] | None:
    binding = artifact_binding_summary(value)
    if binding is None or not isinstance(value, dict):
        return None
    status = value.get("status")
    semantic_pass = value.get("semantic_pass")
    semantic_claim_source = value.get("semantic_claim_source")
    generated_draft_semantic_pass = value.get("generated_draft_semantic_pass")
    if isinstance(status, str):
        binding["status"] = status
    if isinstance(semantic_pass, bool):
        binding["semantic_pass"] = semantic_pass
    if isinstance(semantic_claim_source, str):
        binding["semantic_claim_source"] = semantic_claim_source
    if isinstance(generated_draft_semantic_pass, bool):
        binding["generated_draft_semantic_pass"] = generated_draft_semantic_pass
    return binding


def repair_history_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    patch_events_path = value.get("patch_events_path")
    patch_events_sha256 = value.get("patch_events_sha256")
    if not isinstance(patch_events_path, str) or not isinstance(patch_events_sha256, str):
        return None
    result: dict[str, Any] = {
        "patch_events_path": patch_events_path,
        "patch_events_sha256": patch_events_sha256,
    }
    statuses = value.get("statuses")
    if isinstance(statuses, list):
        result["statuses"] = [status for status in statuses if isinstance(status, str)]
    rollback_ids = value.get("rollback_ids")
    if isinstance(rollback_ids, list):
        result["rollback_ids"] = [rollback_id for rollback_id in rollback_ids if isinstance(rollback_id, str)]
    if isinstance(value.get("verified"), bool):
        result["verified"] = value["verified"]
    return result


def patch_origin_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    source = value.get("source")
    if not isinstance(source, str) or not source:
        return None
    result: dict[str, Any] = {"source": source}
    for key in [
        "accepted_patch_bound",
        "opencode_session_bound",
        "repair_history_bound",
        "generated_draft_semantic_pass",
        "semantic_gate",
    ]:
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    semantic_claim_source = value.get("semantic_claim_source")
    if isinstance(semantic_claim_source, str) and semantic_claim_source:
        result["semantic_claim_source"] = semantic_claim_source
    translation_coverage_numerator = int_or_none(value.get("translation_coverage_numerator"))
    if translation_coverage_numerator is not None:
        result["translation_coverage_numerator"] = translation_coverage_numerator
    return result


def safety_loop_provenance_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    if not isinstance(status, str) or not status:
        return None
    result: dict[str, Any] = {"status": status}
    patch_source = value.get("patch_source")
    if isinstance(patch_source, str) and patch_source:
        result["patch_source"] = patch_source
    baseline_verification_status = value.get("baseline_verification_status")
    if isinstance(baseline_verification_status, str) and baseline_verification_status:
        result["baseline_verification_status"] = baseline_verification_status
    unsafe_delta = unsafe_reduction_summary(value.get("unsafe_delta"))
    if unsafe_delta is not None:
        result["unsafe_delta"] = unsafe_delta
    for key in [
        "opencode_session_bound",
        "repair_history_bound",
        "auto_recovered",
        "semantic_gate",
    ]:
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    repair_rounds = int_or_none(value.get("repair_rounds"))
    if repair_rounds is not None:
        result["repair_rounds"] = repair_rounds
    translation_coverage_numerator = int_or_none(value.get("translation_coverage_numerator"))
    if translation_coverage_numerator is not None:
        result["translation_coverage_numerator"] = translation_coverage_numerator
    return result


def unsafe_reduction_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "status": value.get("status", "unknown"),
        "baseline_total_unsafe": int_or_none(value.get("baseline_total_unsafe")),
        "current_total_unsafe": int_or_none(value.get("current_total_unsafe")),
        "reduced_by": int_or_none(value.get("reduced_by")),
    }


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
        baseline_verification = baseline_verification_summary(item.get("baseline_verification"))
        if baseline_verification is not None:
            unit["baseline_verification"] = baseline_verification
        repair_history = repair_history_summary(item.get("repair_history"))
        if repair_history is not None:
            unit["repair_history"] = repair_history
        repair_rounds = int_or_none(item.get("repair_rounds"))
        if repair_rounds is not None:
            unit["repair_rounds"] = repair_rounds
        if isinstance(item.get("auto_recovered"), bool):
            unit["auto_recovered"] = item["auto_recovered"]
        root_cause_key = item.get("root_cause_key")
        if isinstance(root_cause_key, str) and root_cause_key:
            unit["root_cause_key"] = root_cause_key
        patch_origin = patch_origin_summary(item.get("patch_origin"))
        if patch_origin is not None:
            unit["patch_origin"] = patch_origin
        safety_loop_provenance = safety_loop_provenance_summary(item.get("safety_loop_provenance"))
        if safety_loop_provenance is not None:
            unit["safety_loop_provenance"] = safety_loop_provenance
        result.append(unit)
    return result


def workflow_before_after_unit_summaries(value: object) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in object_list(value):
        source = item.get("translation_before_after")
        if not isinstance(source, dict):
            source = item
        unit: dict[str, Any] = {
            "unit_id": item.get("unit_id") if isinstance(item.get("unit_id"), str) else "unknown",
        }
        status = source.get("status")
        if isinstance(status, str):
            unit["status"] = status
        for key in BEFORE_AFTER_ARTIFACT_REF_FIELDS:
            binding = artifact_binding_summary(source.get(key))
            if binding is not None:
                unit[key] = binding
        unsafe_reduction = unsafe_reduction_summary(source.get("unsafe_reduction"))
        if unsafe_reduction is not None:
            unit["unsafe_reduction"] = unsafe_reduction
        if any(key in unit for key in BEFORE_AFTER_ARTIFACT_REF_FIELDS) or "unsafe_reduction" in unit:
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
    artifact_refs = payload.get("evidence_artifact_refs")
    evidence_artifact_names = sorted(artifact_refs.keys()) if isinstance(artifact_refs, dict) else []
    opencode_runtime = payload.get("opencode_agent_runtime")
    if not isinstance(opencode_runtime, dict):
        opencode_runtime = {}
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
        "evidence_artifact_names": evidence_artifact_names,
        "opencode_runtime_enabled": opencode_runtime.get("runtime") == "opencode"
        or opencode_runtime.get("worker_count") is not None,
        "opencode_worker_count": int_or_zero(opencode_runtime.get("worker_count")),
        "opencode_all_contracts_executed": opencode_runtime.get("all_contracts_executed")
        if isinstance(opencode_runtime.get("all_contracts_executed"), bool)
        else None,
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
            "tracked_capability_delta_ledgers": sum(
                int_or_zero(source.get("tracked_capability_delta_ledgers")) for source in sources
            ),
            "tracked_capability_delta_count": sum(
                int_or_zero(source.get("tracked_capability_delta_count")) for source in sources
            ),
            "capability_vs_governance_delta": build_capability_vs_governance_delta(sources),
            "s2_workflow_run_count": sum(int_or_zero(source.get("s2_workflow_run_count")) for source in sources),
            "s2_unsafe_reduction": {
                "status": "measured"
                if any(source.get("s2_unsafe_reduction_status") == "measured" for source in sources)
                else "not_measured",
                "reduced_by": sum(int_or_zero(source.get("s2_reduced_by")) for source in sources),
            },
            "c2rust_baseline": build_c2rust_baseline_milestone_rollup(sources),
            "blocked_repairs": build_blocked_repairs_route_rollup(sources),
            "all_retention_policies_present": all_retention_present,
            "all_target_artifacts_reproducible": all_reproducible,
        },
        "boundary": (
            "Route governance metrics constrain public claims and artifact retention. They are not a semantic gate "
            "and do not increase translator-generated translation coverage."
        ),
    }


def capability_delta_ledger_source(value: object) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "ledger_count": int_or_zero(payload.get("ledger_count")),
        "delta_count": int_or_zero(payload.get("delta_count")),
        "governance_delta_count": int_or_zero(payload.get("governance_delta_count")),
        "verification_command_count": int_or_zero(payload.get("verification_command_count")),
        "translator_generated_semantic_pass_count": int_or_zero(
            payload.get("translator_generated_semantic_pass_count")
        ),
        "semantic_pass_count": int_or_zero(payload.get("semantic_pass_count")),
        "accepted_evidence_semantic_pass_count": int_or_zero(payload.get("accepted_evidence_semantic_pass_count")),
        "generated_candidate_status": int_count_map(payload.get("generated_candidate_status")),
        "route_levels": int_count_map(payload.get("route_levels")),
        "route_statuses": int_count_map(payload.get("route_statuses")),
        "by_construct": int_count_map(payload.get("by_construct")),
        "blocked_callee_count": int_or_zero(payload.get("blocked_callee_count")),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
    }


def build_capability_vs_governance_delta(sources: list[dict[str, Any]]) -> dict[str, Any]:
    ledgers = [
        source.get("capability_delta_ledger")
        for source in sources
        if isinstance(source.get("capability_delta_ledger"), dict)
    ]
    return {
        "capability_ledger_count": sum(int_or_zero(ledger.get("ledger_count")) for ledger in ledgers),
        "capability_delta_count": sum(int_or_zero(ledger.get("delta_count")) for ledger in ledgers),
        "governance_delta_count": sum(int_or_zero(ledger.get("governance_delta_count")) for ledger in ledgers),
        "verification_command_count": sum(int_or_zero(ledger.get("verification_command_count")) for ledger in ledgers),
        "translator_generated_semantic_pass_count": sum(
            int_or_zero(ledger.get("translator_generated_semantic_pass_count")) for ledger in ledgers
        ),
        "accepted_evidence_semantic_pass_count": sum(
            int_or_zero(ledger.get("accepted_evidence_semantic_pass_count")) for ledger in ledgers
        ),
        "route_decision_artifacts": sum(int_or_zero(source.get("tracked_route_decision_artifacts")) for source in sources),
        "slice_gate_contexts": sum(int_or_zero(source.get("tracked_slice_gate_contexts")) for source in sources),
        "blocked_callee_count": sum(int_or_zero(ledger.get("blocked_callee_count")) for ledger in ledgers),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Capability and governance deltas are review metrics only. They separate translator capability changes "
            "from evidence, route, and reproduction governance work, and do not create semantic acceptance."
        ),
    }


def build_progress_delta_ledger(
    *,
    route_governance_metrics: dict[str, Any],
    workflow_metrics: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
) -> dict[str, Any]:
    route_rollup = (
        route_governance_metrics.get("rollup", {})
        if isinstance(route_governance_metrics.get("rollup"), dict)
        else {}
    )
    delta = (
        route_rollup.get("capability_vs_governance_delta", {})
        if isinstance(route_rollup.get("capability_vs_governance_delta"), dict)
        else {}
    )
    workflow_rollup = (
        workflow_metrics.get("rollup", {}) if isinstance(workflow_metrics.get("rollup"), dict) else {}
    )
    repair_progress = build_workflow_repair_progress_delta(
        workflow_metrics=workflow_metrics,
        before_after_repair_exhibit=before_after_repair_exhibit,
    )
    return {
        "report_kind": "progress-delta-ledger",
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "capability_delta": {
            "ledger_count": int_or_zero(delta.get("capability_ledger_count")),
            "delta_count": int_or_zero(delta.get("capability_delta_count")),
            "translator_generated_semantic_pass_count": int_or_zero(
                delta.get("translator_generated_semantic_pass_count")
            ),
            "accepted_evidence_semantic_pass_count": int_or_zero(
                delta.get("accepted_evidence_semantic_pass_count")
            ),
        },
        "governance_delta": {
            "delta_count": int_or_zero(delta.get("governance_delta_count")),
            "verification_command_count": int_or_zero(delta.get("verification_command_count")),
            "route_decision_artifacts": int_or_zero(delta.get("route_decision_artifacts")),
            "slice_gate_contexts": int_or_zero(delta.get("slice_gate_contexts")),
            "blocked_callee_count": int_or_zero(delta.get("blocked_callee_count")),
        },
        "workflow_delta": {
            "workflow_source_count": int_or_zero(workflow_rollup.get("source_count")),
            "workflow_units_total": int_or_zero(workflow_rollup.get("units_total")),
            "workflow_units_converged": int_or_zero(workflow_rollup.get("units_converged")),
            "repair_history_unit_count": repair_progress["repair_history_unit_count"],
            "observed_repair_unit_count": repair_progress["observed_repair_unit_count"],
            "auto_recovered_unit_count": repair_progress["auto_recovered_unit_count"],
            "rollback_evidence_count": repair_progress["rollback_evidence_count"],
            "before_after_repair_source_count": repair_progress["before_after_repair_source_count"],
            "repair_delta_source_count": repair_progress["repair_delta_source_count"],
            "human_interventions": int_or_zero(workflow_rollup.get("human_interventions")),
            "llm_calls": int_or_zero(workflow_rollup.get("llm_calls")),
        },
        "boundary": (
            "Progress deltas distinguish translator capability movement from governance and workflow evidence. "
            "They are reviewer navigation metrics only, not semantic gates or translation coverage numerator."
        ),
    }


def build_workflow_repair_progress_delta(
    *,
    workflow_metrics: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
) -> dict[str, int]:
    by_source: dict[str, dict[str, int]] = {}
    workflow_sources = object_list(workflow_metrics.get("sources"))
    before_after_sources = object_list(before_after_repair_exhibit.get("sources"))

    for index, source in enumerate(workflow_sources):
        key = repair_progress_source_key(source, prefix="workflow", index=index)
        entry = by_source.setdefault(key, empty_repair_progress_source())
        repair_history_units = int_or_zero(source.get("repair_history_unit_count"))
        entry["repair_history_unit_count"] = max(entry["repair_history_unit_count"], repair_history_units)
        entry["observed_repair_unit_count"] = max(entry["observed_repair_unit_count"], repair_history_units)
        entry["auto_recovered_unit_count"] = max(
            entry["auto_recovered_unit_count"],
            int_or_zero(source.get("auto_recovered_unit_count")),
        )

    for index, source in enumerate(before_after_sources):
        key = repair_progress_source_key(source, prefix="before_after", index=index)
        entry = by_source.setdefault(key, empty_repair_progress_source())
        repair_summary = source.get("repair_summary") if isinstance(source.get("repair_summary"), dict) else {}
        observed = int_or_zero(repair_summary.get("observed_repair_unit_count"))
        auto_recovered = int_or_zero(repair_summary.get("auto_recovered_unit_count"))
        rollback = int_or_zero(repair_summary.get("rollback_evidence_count"))
        verified_source = 1 if repair_summary.get("status") == "verified" or observed > 0 or rollback > 0 else 0
        entry["repair_history_unit_count"] = max(entry["repair_history_unit_count"], observed)
        entry["observed_repair_unit_count"] = max(entry["observed_repair_unit_count"], observed)
        entry["auto_recovered_unit_count"] = max(entry["auto_recovered_unit_count"], auto_recovered)
        entry["rollback_evidence_count"] = max(entry["rollback_evidence_count"], rollback)
        entry["before_after_repair_source_count"] = max(entry["before_after_repair_source_count"], verified_source)

    if by_source:
        return sum_repair_progress_sources(by_source.values())

    workflow_rollup = (
        workflow_metrics.get("rollup", {}) if isinstance(workflow_metrics.get("rollup"), dict) else {}
    )
    repair_activity = (
        workflow_rollup.get("repair_activity", {}) if isinstance(workflow_rollup.get("repair_activity"), dict) else {}
    )
    before_after_rollup = (
        before_after_repair_exhibit.get("rollup", {})
        if isinstance(before_after_repair_exhibit.get("rollup"), dict)
        else {}
    )
    return {
        "repair_history_unit_count": max(
            int_or_zero(repair_activity.get("repair_history_unit_count")),
            int_or_zero(before_after_rollup.get("observed_repair_unit_count")),
        ),
        "observed_repair_unit_count": max(
            int_or_zero(repair_activity.get("repair_history_unit_count")),
            int_or_zero(before_after_rollup.get("observed_repair_unit_count")),
        ),
        "auto_recovered_unit_count": max(
            int_or_zero(repair_activity.get("auto_recovered_unit_count")),
            int_or_zero(before_after_rollup.get("auto_recovered_unit_count")),
        ),
        "rollback_evidence_count": int_or_zero(before_after_rollup.get("rollback_evidence_count")),
        "before_after_repair_source_count": int_or_zero(before_after_rollup.get("verified_repair_source_count")),
        "repair_delta_source_count": int_or_zero(repair_activity.get("observed_source_count"))
        + int_or_zero(before_after_rollup.get("verified_repair_source_count")),
    }


def empty_repair_progress_source() -> dict[str, int]:
    return {
        "repair_history_unit_count": 0,
        "observed_repair_unit_count": 0,
        "auto_recovered_unit_count": 0,
        "rollback_evidence_count": 0,
        "before_after_repair_source_count": 0,
    }


def repair_progress_source_key(source: dict[str, Any], *, prefix: str, index: int) -> str:
    entrypoint_id = source.get("entrypoint_id")
    if isinstance(entrypoint_id, str) and entrypoint_id:
        return f"entrypoint:{entrypoint_id}"
    artifact = source.get("artifact")
    if isinstance(artifact, dict) and isinstance(artifact.get("path"), str) and artifact["path"]:
        return f"artifact:{artifact['path']}"
    return f"{prefix}:{index}"


def sum_repair_progress_sources(sources: Iterable[dict[str, int]]) -> dict[str, int]:
    result = empty_repair_progress_source()
    repair_delta_source_count = 0
    for source in sources:
        has_repair_delta = False
        for field in result:
            value = int_or_zero(source.get(field))
            result[field] += value
            if value > 0:
                has_repair_delta = True
        if has_repair_delta:
            repair_delta_source_count += 1
    result["repair_delta_source_count"] = repair_delta_source_count
    return result


def c2rust_baseline_source(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return empty_c2rust_baseline_route_source()
    return {
        "report_kind": value.get("report_kind")
        if isinstance(value.get("report_kind"), str)
        else "c2rust-baseline-rollup",
        "status": value.get("status") if isinstance(value.get("status"), str) else "unknown",
        "manifest_count": int_or_zero(value.get("manifest_count")),
        "generated_output_count": int_or_zero(value.get("generated_output_count")),
        "skipped_without_output_count": int_or_zero(value.get("skipped_without_output_count")),
        "compile_attempted_count": int_or_zero(value.get("compile_attempted_count")),
        "compile_passed_count": int_or_zero(value.get("compile_passed_count")),
        "compile_semantic_pass_count": 0,
        "status_counts": int_count_map(value.get("status_counts")),
        "output_status_counts": int_count_map(value.get("output_status_counts")),
        "compile_status_counts": int_count_map(value.get("compile_status_counts")),
        "manifests": object_list(value.get("manifests")),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": value.get("boundary")
        if isinstance(value.get("boundary"), str)
        else "C2Rust baseline status is candidate context only.",
    }


def empty_c2rust_baseline_route_source() -> dict[str, Any]:
    return {
        "report_kind": "c2rust-baseline-rollup",
        "status": "none",
        "manifest_count": 0,
        "generated_output_count": 0,
        "skipped_without_output_count": 0,
        "compile_attempted_count": 0,
        "compile_passed_count": 0,
        "compile_semantic_pass_count": 0,
        "status_counts": {},
        "output_status_counts": {},
        "compile_status_counts": {},
        "manifests": [],
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": "C2Rust baseline status is candidate context only.",
    }


def build_c2rust_baseline_milestone_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    report_sources = [
        source
        for source in sources
        if isinstance(source.get("c2rust_baseline"), dict)
        and source.get("c2rust_baseline", {}).get("report_kind") == "c2rust-baseline-rollup"
    ]
    by_evidence_root: dict[str, dict[str, Any]] = {}
    conflict_roots: list[str] = []
    for index, source in enumerate(report_sources):
        key = source.get("evidence_root") if isinstance(source.get("evidence_root"), str) else f"entrypoint:{index}"
        baseline = source["c2rust_baseline"]
        if key in by_evidence_root:
            if comparable_c2rust_baseline_payload(by_evidence_root[key]) != comparable_c2rust_baseline_payload(baseline):
                conflict_roots.append(key)
            continue
        by_evidence_root[key] = baseline

    status_counts: Counter[str] = Counter()
    output_status_counts: Counter[str] = Counter()
    compile_status_counts: Counter[str] = Counter()
    manifests_by_key: dict[str, dict[str, Any]] = {}
    generated_output_count = 0
    skipped_without_output_count = 0
    compile_attempted_count = 0
    compile_passed_count = 0

    for baseline in by_evidence_root.values():
        status_counts.update(int_count_map(baseline.get("status_counts")))
        output_status_counts.update(int_count_map(baseline.get("output_status_counts")))
        compile_status_counts.update(int_count_map(baseline.get("compile_status_counts")))
        generated_output_count += int_or_zero(baseline.get("generated_output_count"))
        skipped_without_output_count += int_or_zero(baseline.get("skipped_without_output_count"))
        compile_attempted_count += int_or_zero(baseline.get("compile_attempted_count"))
        compile_passed_count += int_or_zero(baseline.get("compile_passed_count"))
        for manifest in object_list(baseline.get("manifests")):
            manifest_key = manifest_identity(manifest)
            if manifest_key:
                manifests_by_key.setdefault(manifest_key, manifest)

    unique_manifest_count = len(manifests_by_key)
    if unique_manifest_count == 0:
        unique_manifest_count = sum(int_or_zero(baseline.get("manifest_count")) for baseline in by_evidence_root.values())
    return {
        "report_kind": "c2rust-baseline-milestone-rollup",
        "status": "conflict" if conflict_roots else "observed" if report_sources else "none",
        "source_report_count": len(report_sources),
        "unique_evidence_root_count": len(by_evidence_root),
        "unique_manifest_count": unique_manifest_count,
        "generated_output_count": generated_output_count,
        "skipped_without_output_count": skipped_without_output_count,
        "compile_attempted_count": compile_attempted_count,
        "compile_passed_count": compile_passed_count,
        "compile_semantic_pass_count": 0,
        "status_counts": sorted_int_counter(status_counts),
        "output_status_counts": sorted_int_counter(output_status_counts),
        "compile_status_counts": sorted_int_counter(compile_status_counts),
        "manifests": [manifests_by_key[key] for key in sorted(manifests_by_key)],
        "conflict_evidence_roots": sorted(set(conflict_roots)),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "C2Rust baseline manifest, output, and compile status are candidate-context observations only; "
            "compile success is not semantic equivalence and does not increase translator-generated coverage."
        ),
    }


def empty_c2rust_baseline_milestone_rollup() -> dict[str, Any]:
    return build_c2rust_baseline_milestone_rollup([])


def comparable_c2rust_baseline_payload(value: dict[str, Any]) -> str:
    comparable = {
        "manifest_count": int_or_zero(value.get("manifest_count")),
        "generated_output_count": int_or_zero(value.get("generated_output_count")),
        "skipped_without_output_count": int_or_zero(value.get("skipped_without_output_count")),
        "compile_attempted_count": int_or_zero(value.get("compile_attempted_count")),
        "compile_passed_count": int_or_zero(value.get("compile_passed_count")),
        "status_counts": int_count_map(value.get("status_counts")),
        "output_status_counts": int_count_map(value.get("output_status_counts")),
        "compile_status_counts": int_count_map(value.get("compile_status_counts")),
        "manifests": object_list(value.get("manifests")),
    }
    return json.dumps(comparable, sort_keys=True)


def manifest_identity(manifest: dict[str, Any]) -> str | None:
    path = manifest.get("path")
    if not isinstance(path, str) or not path:
        return None
    sha = manifest.get("sha256")
    return f"{path}@{sha}" if isinstance(sha, str) and sha else path


def sorted_int_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


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
    policy_tier_counts: dict[str, int] = {}
    policy_failed_gate_counts: dict[str, int] = {}
    for source in sources:
        policy = source.get("policy_compliance") if isinstance(source.get("policy_compliance"), dict) else {}
        tier = str(policy.get("policy_tier", "unknown"))
        policy_tier_counts[tier] = policy_tier_counts.get(tier, 0) + 1
        failed_gates = policy.get("failed_gates") if isinstance(policy.get("failed_gates"), list) else []
        for gate in failed_gates:
            gate_name = str(gate)
            policy_failed_gate_counts[gate_name] = policy_failed_gate_counts.get(gate_name, 0) + 1
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
            "policy_compliance": {
                "all_sources_policy_passed": all(
                    isinstance(source.get("policy_compliance"), dict)
                    and source["policy_compliance"].get("status") == "passed"
                    for source in sources
                )
                if sources
                else True,
                "tier_counts": {key: policy_tier_counts[key] for key in sorted(policy_tier_counts)},
                "failed_gate_counts": {
                    key: policy_failed_gate_counts[key] for key in sorted(policy_failed_gate_counts)
                },
            },
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
        "preflight_proof_summary": build_opencode_preflight_proof_rollup(sources),
    }


def build_opencode_preflight_proof_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not sources:
        return opencode_preflight_absent_summary(required=False)
    summaries = [
        source.get("preflight_proof_summary")
        for source in sources
        if isinstance(source.get("preflight_proof_summary"), dict)
    ]
    passed = [summary for summary in summaries if summary.get("status") == "passed"]
    selected = deepcopy(passed[0] if passed else summaries[0]) if summaries else opencode_preflight_absent_summary(required=True)
    selected["required_when_opencode_runtime_enabled"] = True
    selected["source_count"] = len(sources)
    selected["passed_source_count"] = len(passed)
    if len(passed) != len(sources):
        selected["status"] = "failed"
    return selected


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


def remove_stale_publication_siblings(out_path: Path) -> None:
    for filename in ("public-release-packet.json", "milestone-release-notes.md"):
        (out_path.parent / filename).unlink(missing_ok=True)


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
