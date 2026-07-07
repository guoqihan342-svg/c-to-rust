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
            workflow_unsafe = measured_unsafe_reduction_tuple(workflow_unit.get("unsafe_reduction"))
            core_unsafe = measured_unsafe_reduction_tuple(core_unit.get("unsafe_reduction"))
            if workflow_unsafe is not None or core_unsafe is not None:
                if core_unsafe is None:
                    blockers.append(
                        f"before_after_exhibit_workflow_metrics_unsafe_reduction_missing:{entrypoint_id}:{unit_id}"
                    )
                elif workflow_unsafe is None or core_unsafe != workflow_unsafe:
                    blockers.append(
                        f"before_after_exhibit_workflow_metrics_unsafe_reduction_mismatch:{entrypoint_id}:{unit_id}"
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


def measured_unsafe_reduction_tuple(value: object) -> tuple[object, object, object, object] | None:
    if not isinstance(value, dict) or value.get("status") != "measured":
        return None
    return (
        value.get("status"),
        int_or_none(value.get("baseline_total_unsafe")),
        int_or_none(value.get("current_total_unsafe")),
        int_or_none(value.get("reduced_by")),
    )


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
