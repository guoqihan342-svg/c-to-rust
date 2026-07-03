#!/usr/bin/env python3
"""Render judge milestone bundle data as public-facing Markdown release notes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_BUNDLE = Path("target/competition-out-flashdb-judge-entrypoints/summary/judge-milestone-bundle.json")
DEFAULT_OUT = Path("target/competition-out-flashdb-judge-entrypoints/summary/milestone-release-notes.md")


BASELINE_LABELS = {
    "raw_c2rust": "raw C2Rust",
    "c2rust_repair": "C2Rust + repair",
    "typed_ir_route": "Typed IR route",
    "opencode_llm_worker": "OpenCode/LLM worker",
    "handwritten_reference": "Handwritten reference",
}

COMPETITION_OPENCODE_COMMAND = "opencode"
COMPETITION_OPENCODE_MODEL = "GLM-5.1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    bundle = json.loads(args.bundle.read_text(encoding="utf-8-sig"))
    notes = build_release_notes(bundle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(notes, encoding="utf-8")
    print(notes)
    return 0


def build_release_notes(bundle: dict[str, Any]) -> str:
    require_bundle_contract(bundle)
    publication = object_or_empty(bundle.get("publication_manifest"))
    scorecard = object_or_empty(bundle.get("quantitative_evaluation"))
    architecture = object_or_empty(bundle.get("harness_architecture_summary"))
    evidence_cost = object_or_empty(bundle.get("evidence_cost_retention"))
    workflow = object_or_empty(bundle.get("workflow_metrics"))
    core_quality = object_or_empty(bundle.get("core_translation_quality"))
    progress_delta = object_or_empty(bundle.get("progress_delta_ledger"))

    lines = [
        "# FlashDB Harness MVP Release Notes",
        "",
        f"Status: `{text(bundle.get('status'), 'unknown')}`",
        f"Readiness: `{text(object_or_empty(bundle.get('publishability')).get('status'), 'unknown')}`",
        f"Repository commit: `{commit_text(publication)}`",
        f"FlashDB source pin: `{source_pin_text(publication)}`",
        f"Proof class rollup: `{proof_class_text(bundle)}`",
        f"Bundle: `{text(object_or_empty(publication.get('judge_milestone_bundle')).get('path'), 'unknown')}`",
        "",
        "## Judge Packet Index",
        "",
        *packet_index_lines(publication),
        "",
        "## Competition Config Archive",
        "",
        *competition_config_archive_lines(object_or_empty(publication.get("competition_config_archive"))),
        "",
        "## Publication Readiness Contract",
        "",
        *publishability_lines(object_or_empty(bundle.get("publishability"))),
        "",
        "## Competition Host Readiness",
        "",
        *competition_host_readiness_lines(object_or_empty(bundle.get("competition_host_readiness"))),
        "",
        "## Release Tag Readiness",
        "",
        *release_tag_readiness_lines(object_or_empty(publication.get("release_tag_readiness"))),
        "",
        "## Readiness Blockers",
        "",
        *blocker_lines(bundle.get("blockers")),
        "",
        "## What This Milestone Demonstrates",
        "",
        "- One-command judge entrypoints for competition environment smoke, before/after exhibit, multi-worker evaluate, and OpenCode multi-worker evaluate.",
        "- Hash-bound context pack, agent index, workflow metrics, route-governance metrics, OpenCode runtime policy, and judge evidence index.",
        "- A bounded before/after safety exhibit that keeps semantic acceptance owned by validators and accepted evidence.",
        "",
        "## Claim Boundary",
        "",
        f"- Semantic gate: `{false_text(object_or_empty(bundle.get('claim_boundary')).get('semantic_gate'))}`",
        f"- Generated draft semantic pass: `{false_text(object_or_empty(bundle.get('claim_boundary')).get('generated_draft_semantic_pass'))}`",
        f"- Translation coverage numerator: `{int_text(object_or_empty(bundle.get('claim_boundary')).get('translation_coverage_numerator'))}`",
        "- This release note is a human-readable index over existing evidence; it is not a new semantic gate.",
        "",
        "## OpenCode GLM Preflight",
        "",
        *opencode_preflight_lines(object_or_empty(object_or_empty(bundle.get("opencode_runtime")).get("preflight_proof_summary"))),
        "",
        "## Harness Architecture",
        "",
        *architecture_lines(architecture, workflow),
        "",
        "## Evidence Cost and Retention",
        "",
        *evidence_cost_retention_lines(evidence_cost),
        "",
        "## Quantitative Scorecard",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Workflow units | {nested_int(scorecard, 'project_slice_counts', 'workflow_units_converged')} / {nested_int(scorecard, 'project_slice_counts', 'workflow_units_total')} |",
        f"| Before/after bound units | {nested_int(scorecard, 'project_slice_counts', 'before_after_bound_unit_count')} |",
        f"| Accepted-evidence semantic pass count | {nested_int(scorecard, 'outcome_counts', 'accepted_evidence_semantic_pass_count')} |",
        f"| Translator-generated semantic pass count | {nested_int(scorecard, 'outcome_counts', 'translator_generated_semantic_pass_count')} |",
        f"| Blocked repair count | {nested_int(scorecard, 'outcome_counts', 'blocked_repair_count')} |",
        f"| Human interventions | {nested_int(scorecard, 'outcome_counts', 'human_interventions')} |",
        f"| Auto-recovered units | {nested_int(scorecard, 'outcome_counts', 'auto_recovered_unit_count')} |",
        f"| Unsafe reduction | {unsafe_reduction_text(scorecard.get('unsafe_reduction'), core_quality.get('unsafe_reduction'))} |",
        "",
        "## Self-Heal Classification",
        "",
        *self_heal_classification_lines(object_or_empty(scorecard.get("self_heal_classification"))),
        "",
        "## Progress Delta Ledger",
        "",
        *progress_delta_lines(progress_delta),
        "",
        "## Baseline Comparison",
        "",
        "| Baseline | Status | Semantic acceptance claimed | Translation coverage numerator | Baseline manifest evidence |",
        "| --- | --- | --- | ---: | --- |",
        *baseline_rows(object_or_empty(scorecard.get("baseline_comparison"))),
        "",
        "## Reproduction Commands",
        "",
        *command_lines(object_or_empty(bundle.get("reproduction_commands"))),
        "",
        "## Supported Subset",
        "",
        *bullet_lines(object_or_empty(publication.get("supported_subset")).get("claims")),
        "",
        "## Known Gaps",
        "",
        *gap_lines(bundle.get("known_gaps")),
        "",
        "## Do Not Claim",
        "",
        *bullet_lines(bundle.get("must_not_claim")),
        "",
        "## Known Non-Goals",
        "",
        *bullet_lines(publication.get("known_non_goals")),
        "",
    ]
    return "\n".join(lines)


def require_bundle_contract(bundle: dict[str, Any]) -> None:
    require(bundle.get("schema_version") == 1, "schema_version must be 1")
    require(bundle.get("report_kind") == "judge-milestone-bundle", "report_kind must be judge-milestone-bundle")
    status = bundle.get("status")
    require(status in {"passed", "blocked"}, "status must be passed or blocked")
    blockers = bundle.get("blockers")
    require(
        isinstance(blockers, list) and all(isinstance(blocker, str) for blocker in blockers),
        "blockers must be a string list",
    )
    if status == "passed":
        require(not blockers, "blockers must be empty when status is passed")
    if status == "blocked":
        require(bool(blockers), "blockers must be present when status is blocked")
    require_false_field(bundle, "claim_boundary", "semantic_gate")
    require_false_field(bundle, "claim_boundary", "generated_draft_semantic_pass")
    require_zero_field(bundle, "claim_boundary", "translation_coverage_numerator")
    require_false_field(bundle, "claim_boundary", "bundle_is_semantic_gate", optional=True)
    require_false_field(bundle, "core_translation_quality", "generated_draft_semantic_pass", optional=True)
    require_zero_field(bundle, "core_translation_quality", "translation_coverage_numerator", optional=True)
    require_false_field(bundle, "progress_delta_ledger", "semantic_gate")
    require_false_field(bundle, "progress_delta_ledger", "generated_draft_semantic_pass")
    require_zero_field(bundle, "progress_delta_ledger", "translation_coverage_numerator")

    require_false_field(bundle, "quantitative_evaluation", "semantic_gate")
    require_false_field(bundle, "quantitative_evaluation", "generated_draft_semantic_pass")
    require_zero_field(bundle, "quantitative_evaluation", "translation_coverage_numerator")
    scorecard = object_or_empty(bundle.get("quantitative_evaluation"))
    outcome_counts = object_or_empty(scorecard.get("outcome_counts"))
    require_zero_value(
        outcome_counts.get("translator_generated_semantic_pass_count"),
        "quantitative_evaluation.outcome_counts.translator_generated_semantic_pass_count",
    )
    require_false_value(
        outcome_counts.get("generated_draft_semantic_pass"),
        "quantitative_evaluation.outcome_counts.generated_draft_semantic_pass",
    )
    require_zero_value(
        outcome_counts.get("translation_coverage_numerator"),
        "quantitative_evaluation.outcome_counts.translation_coverage_numerator",
    )
    require_false_field(scorecard, "claim_boundary", "semantic_gate")
    require_false_field(scorecard, "claim_boundary", "scorecard_is_semantic_gate")
    require_false_field(scorecard, "claim_boundary", "generated_draft_semantic_pass")
    require_zero_field(scorecard, "claim_boundary", "translation_coverage_numerator")
    self_heal = object_or_empty(scorecard.get("self_heal_classification"))
    require_false_value(
        self_heal.get("semantic_gate"),
        "quantitative_evaluation.self_heal_classification.semantic_gate",
    )
    require_false_value(
        self_heal.get("generated_draft_semantic_pass"),
        "quantitative_evaluation.self_heal_classification.generated_draft_semantic_pass",
    )
    require_zero_value(
        self_heal.get("translation_coverage_numerator"),
        "quantitative_evaluation.self_heal_classification.translation_coverage_numerator",
    )
    baseline = object_or_empty(scorecard.get("baseline_comparison"))
    for name, row in baseline.items():
        if not isinstance(row, dict):
            raise SystemExit(f"baseline_comparison.{name} must be an object")
        require_false_value(row.get("semantic_acceptance_claimed"), f"baseline_comparison.{name}.semantic_acceptance_claimed")
        require_false_value(row.get("generated_draft_semantic_pass"), f"baseline_comparison.{name}.generated_draft_semantic_pass")
        require_zero_value(row.get("translation_coverage_numerator"), f"baseline_comparison.{name}.translation_coverage_numerator")
        if "chat_output_is_evidence" in row:
            require_false_value(row.get("chat_output_is_evidence"), f"baseline_comparison.{name}.chat_output_is_evidence")
        if "counts_as_translator_generated_coverage" in row:
            require_false_value(
                row.get("counts_as_translator_generated_coverage"),
                f"baseline_comparison.{name}.counts_as_translator_generated_coverage",
            )

    publication = object_or_empty(bundle.get("publication_manifest"))
    require_false_field(publication, "claim_boundary", "semantic_gate", prefix="publication_manifest")
    require_false_field(
        publication,
        "claim_boundary",
        "publication_manifest_is_semantic_gate",
        prefix="publication_manifest",
    )
    require_false_field(publication, "claim_boundary", "generated_draft_semantic_pass", prefix="publication_manifest")
    require_zero_field(publication, "claim_boundary", "translation_coverage_numerator", prefix="publication_manifest")
    require_release_tag_readiness_contract(object_or_empty(publication.get("release_tag_readiness")))
    require_publishability_contract(bundle, blockers=blockers)
    require_competition_host_readiness_contract(object_or_empty(bundle.get("competition_host_readiness")))
    require_opencode_runtime_contract(bundle)
    require_opencode_evidence_policy_contract(bundle)
    require_evidence_cost_retention_contract(bundle)


def require_publishability_contract(bundle: dict[str, Any], *, blockers: list[str]) -> None:
    publishability = bundle.get("publishability")
    require(isinstance(publishability, dict), "publishability must be an object")
    readiness = publishability.get("status")
    require(
        readiness in {"blocked", "internal_preview", "external_release_ready"},
        "publishability.status must be blocked, internal_preview, or external_release_ready",
    )
    scope = publishability.get("scope")
    require(scope in {"blocked", "partial", "full"}, "publishability.scope must be blocked, partial, or full")
    publication_scope = publishability.get("publication_scope")
    require(
        publication_scope in {"blocked", "partial", "internal_preview_full", "full"},
        "publishability.publication_scope must be blocked, partial, internal_preview_full, or full",
    )
    expected_publication_scope = (
        "internal_preview_full"
        if readiness == "internal_preview" and scope == "full"
        else scope
    )
    require(
        publication_scope == expected_publication_scope,
        "publishability.publication_scope must match external readiness",
    )
    blocker_count = publishability.get("blocker_count")
    require(
        isinstance(blocker_count, int) and blocker_count == len(blockers),
        "publishability.blocker_count must match blockers",
    )
    if "blockers" in publishability:
        require(publishability.get("blockers") == blockers, "publishability.blockers must match bundle blockers")
    require(publishability.get("required_agent_tool") == "opencode", "publishability.required_agent_tool must be opencode")
    require(publishability.get("required_model") == "GLM-5.1", "publishability.required_model must be GLM-5.1")
    require_true_value(publishability.get("opencode_glm51_required"), "publishability.opencode_glm51_required")
    require(
        isinstance(publishability.get("opencode_glm51_preflight_status"), str)
        and bool(publishability.get("opencode_glm51_preflight_status")),
        "publishability.opencode_glm51_preflight_status must be present",
    )
    opencode_ready = publishability.get("opencode_glm51_publishable") is True
    external_milestone = publishability.get("external_milestone") is True
    external_claim = publishability.get("external_milestone_claim_ready") is True
    if bundle.get("status") == "blocked":
        require(readiness == "blocked", "publishability.status must be blocked when bundle is blocked")
        require(scope == "blocked", "publishability.scope must be blocked when bundle is blocked")
        require(not external_claim, "publishability.external_milestone_claim_ready must be false when blocked")
        require(not external_milestone, "publishability.external_milestone must be false when blocked")
    if readiness == "internal_preview":
        require(not external_claim, "publishability.external_milestone_claim_ready must be false for internal_preview")
        require(not external_milestone, "publishability.external_milestone must be false for internal_preview")
    if readiness == "external_release_ready":
        require(external_claim, "publishability.external_milestone_claim_ready must be true for external_release_ready")
        require(external_milestone, "publishability.external_milestone must be true for external_release_ready")
        require(opencode_ready, "publishability.opencode_glm51_publishable must be true for external_release_ready")
        require(
            publishability.get("all_entrypoints_run_publishable") is True,
            "publishability.all_entrypoints_run_publishable must be true for external_release_ready",
        )
        require(
            publishability.get("competition_exact_publishable") is True,
            "publishability.competition_exact_publishable must be true for external_release_ready",
        )
        require(
            publishability.get("focused_run") is False,
            "publishability.focused_run must be false for external_release_ready",
        )
        host_readiness = object_or_empty(bundle.get("competition_host_readiness"))
        require(
            host_readiness.get("status") == "ready",
            "competition_host_readiness.status must be ready for external_release_ready",
        )
        require(
            host_readiness.get("competition_exact_host_verified") is True,
            "competition_host_readiness.competition_exact_host_verified must be true for external_release_ready",
        )
    require_false_value(publishability.get("semantic_gate"), "publishability.semantic_gate")
    require_zero_value(publishability.get("translation_coverage_numerator"), "publishability.translation_coverage_numerator")


def require_release_tag_readiness_contract(readiness: dict[str, Any]) -> None:
    require(readiness.get("report_kind") == "release-tag-readiness", "release_tag_readiness.report_kind must be release-tag-readiness")
    require(readiness.get("status") == "not_tagged", "release_tag_readiness.status must be not_tagged")
    require_false_value(readiness.get("tag_matches_repo_commit"), "release_tag_readiness.tag_matches_repo_commit")
    require(
        readiness.get("remote_release_notes_status") == "not_published",
        "release_tag_readiness.remote_release_notes_status must be not_published",
    )
    require(
        readiness.get("external_review_record_status") == "not_recorded",
        "release_tag_readiness.external_review_record_status must be not_recorded",
    )
    require_false_value(
        readiness.get("external_milestone_claim_ready"),
        "release_tag_readiness.external_milestone_claim_ready",
    )
    require_false_value(readiness.get("semantic_gate"), "release_tag_readiness.semantic_gate")
    require_zero_value(
        readiness.get("translation_coverage_numerator"),
        "release_tag_readiness.translation_coverage_numerator",
    )
    require(
        isinstance(readiness.get("boundary"), str) and bool(readiness.get("boundary")),
        "release_tag_readiness.boundary must be present",
    )


def require_competition_host_readiness_contract(readiness: dict[str, Any]) -> None:
    require(
        readiness.get("report_kind") == "competition-host-readiness",
        "competition_host_readiness.report_kind must be competition-host-readiness",
    )
    require(readiness.get("status") in {"blocked", "ready"}, "competition_host_readiness.status must be blocked or ready")
    require(readiness.get("required_agent_tool") == "opencode", "competition_host_readiness.required_agent_tool must be opencode")
    require(readiness.get("required_model") == COMPETITION_OPENCODE_MODEL, "competition_host_readiness.required_model must be GLM-5.1")
    require(readiness.get("required_variant") == "max", "competition_host_readiness.required_variant must be max")
    require(
        readiness.get("required_proof_class") == "competition-exact",
        "competition_host_readiness.required_proof_class must be competition-exact",
    )
    missing = readiness.get("missing_requirements")
    require(isinstance(missing, list) and all(isinstance(item, str) for item in missing), "competition_host_readiness.missing_requirements must be a string list")
    require(
        readiness.get("blocker_count") == len(missing),
        "competition_host_readiness.blocker_count must match missing_requirements",
    )
    if readiness.get("status") == "ready":
        require(not missing, "competition_host_readiness.ready must have no missing requirements")
        require_true_value(
            readiness.get("all_entrypoints_run_publishable"),
            "competition_host_readiness.all_entrypoints_run_publishable",
        )
        require_true_value(
            readiness.get("all_entrypoints_competition_exact"),
            "competition_host_readiness.all_entrypoints_competition_exact",
        )
        require_true_value(
            readiness.get("competition_exact_host_verified"),
            "competition_host_readiness.competition_exact_host_verified",
        )
        require_true_value(
            readiness.get("opencode_glm51_publishable"),
            "competition_host_readiness.opencode_glm51_publishable",
        )
        require_true_value(
            readiness.get("external_milestone_claim_ready"),
            "competition_host_readiness.external_milestone_claim_ready",
        )
    else:
        require(bool(missing), "competition_host_readiness.blocked must list missing requirements")
    require_false_value(readiness.get("semantic_gate"), "competition_host_readiness.semantic_gate")
    require_zero_value(
        readiness.get("translation_coverage_numerator"),
        "competition_host_readiness.translation_coverage_numerator",
    )
    require(
        isinstance(readiness.get("boundary"), str) and bool(readiness.get("boundary")),
        "competition_host_readiness.boundary must be present",
    )


def require_opencode_runtime_contract(bundle: dict[str, Any]) -> None:
    runtime = bundle.get("opencode_runtime")
    require(isinstance(runtime, dict), "opencode_runtime must be an object")
    require_true_value(runtime.get("chat_output_is_evidence_false"), "opencode_runtime.chat_output_is_evidence_false")
    require_true_value(runtime.get("semantic_gate_false"), "opencode_runtime.semantic_gate_false")
    enabled_entrypoint_count = runtime.get("enabled_entrypoint_count")
    require(
        isinstance(enabled_entrypoint_count, int) and enabled_entrypoint_count >= 0,
        "opencode_runtime.enabled_entrypoint_count must be a non-negative integer",
    )
    if enabled_entrypoint_count > 0:
        require_opencode_preflight_proof_summary_contract(
            runtime.get("preflight_proof_summary"),
            "opencode_runtime.preflight_proof_summary",
        )


def require_opencode_preflight_proof_summary_contract(summary: Any, label: str) -> None:
    require(isinstance(summary, dict), f"{label} must be an object")
    require(summary.get("status") == "passed", f"{label}.status must be passed")
    require_true_value(
        summary.get("required_when_opencode_runtime_enabled"),
        f"{label}.required_when_opencode_runtime_enabled",
    )
    require_false_value(summary.get("chat_output_is_evidence"), f"{label}.chat_output_is_evidence")
    require_false_value(summary.get("semantic_gate"), f"{label}.semantic_gate")
    require_zero_value(summary.get("translation_coverage_numerator"), f"{label}.translation_coverage_numerator")
    require(
        summary.get("opencode_command") == COMPETITION_OPENCODE_COMMAND,
        f"{label}.opencode_command must be {COMPETITION_OPENCODE_COMMAND}",
    )
    require(
        summary.get("opencode_model") == COMPETITION_OPENCODE_MODEL,
        f"{label}.opencode_model must be {COMPETITION_OPENCODE_MODEL}",
    )
    require(
        summary.get("required_model") == COMPETITION_OPENCODE_MODEL,
        f"{label}.required_model must be {COMPETITION_OPENCODE_MODEL}",
    )
    require(summary.get("model_availability_status") == "available", f"{label}.model_availability_status must be available")
    require_true_value(summary.get("model_listed"), f"{label}.model_listed")
    require(summary.get("model_probe_argv") == ["opencode", "models"], f"{label}.model_probe_argv must be opencode models")
    require(summary.get("process_returncode") == 0, f"{label}.process_returncode must be 0")
    require(summary.get("contract_status") == "executed", f"{label}.contract_status must be executed")
    require_true_value(summary.get("marker_exists"), f"{label}.marker_exists")
    require_true_value(summary.get("opencode_run_launched"), f"{label}.opencode_run_launched")
    require_true_value(summary.get("opencode_run_argv_bound"), f"{label}.opencode_run_argv_bound")
    require(
        summary.get("proof_class") != "competition-exact",
        f"{label}.proof_class must not claim competition-exact without host attestation",
    )
    require(isinstance(summary.get("preflight_report"), dict), f"{label}.preflight_report must be an object")
    logs = summary.get("model_probe_logs")
    require(isinstance(logs, dict), f"{label}.model_probe_logs must be an object")
    require(isinstance(logs.get("stdout"), dict), f"{label}.model_probe_logs.stdout must be an object")
    require(isinstance(logs.get("stderr"), dict), f"{label}.model_probe_logs.stderr must be an object")
    require(isinstance(summary.get("boundary"), str) and bool(summary.get("boundary")), f"{label}.boundary must be present")


def require_opencode_evidence_policy_contract(bundle: dict[str, Any]) -> None:
    policy = bundle.get("opencode_evidence_policy")
    require(isinstance(policy, dict), "opencode_evidence_policy must be an object")
    require_true_value(policy.get("boundary_fields_explicit"), "opencode_evidence_policy.boundary_fields_explicit")
    require_true_value(policy.get("chat_output_is_evidence_false"), "opencode_evidence_policy.chat_output_is_evidence_false")
    require_true_value(policy.get("semantic_gate_false"), "opencode_evidence_policy.semantic_gate_false")
    require_false_value(policy.get("semantic_gate"), "opencode_evidence_policy.semantic_gate")


def require_evidence_cost_retention_contract(bundle: dict[str, Any]) -> None:
    evidence_cost = bundle.get("evidence_cost_retention")
    require(isinstance(evidence_cost, dict), "evidence_cost_retention must be an object")
    require(
        evidence_cost.get("report_kind") == "evidence-cost-retention-rollup",
        "evidence_cost_retention.report_kind must be evidence-cost-retention-rollup",
    )
    require(isinstance(evidence_cost.get("sources"), list), "evidence_cost_retention.sources must be an array")
    require(
        isinstance(evidence_cost.get("boundary"), str) and bool(evidence_cost.get("boundary")),
        "evidence_cost_retention.boundary must be present",
    )
    rollup = evidence_cost.get("rollup")
    require(isinstance(rollup, dict), "evidence_cost_retention.rollup must be an object")
    for key in ["source_count", "artifact_count", "total_bytes", "pipeline_count", "portability_issue_count"]:
        require_non_negative_int(rollup.get(key), f"evidence_cost_retention.rollup.{key}")
    if "diagnostic_host_metadata_count" in rollup:
        require_non_negative_int(
            rollup.get("diagnostic_host_metadata_count"),
            "evidence_cost_retention.rollup.diagnostic_host_metadata_count",
        )
    require(isinstance(rollup.get("all_sources_passed"), bool), "evidence_cost_retention.rollup.all_sources_passed must be boolean")

    runtime = rollup.get("runtime_ms")
    require(isinstance(runtime, dict), "evidence_cost_retention.rollup.runtime_ms must be an object")
    for key in ["observation_count", "total", "max"]:
        require_non_negative_int(runtime.get(key), f"evidence_cost_retention.rollup.runtime_ms.{key}")

    retention_classes = rollup.get("retention_classes")
    require(isinstance(retention_classes, dict), "evidence_cost_retention.rollup.retention_classes must be an object")
    for name, retention_class in retention_classes.items():
        require(isinstance(retention_class, dict), f"evidence_cost_retention.rollup.retention_classes.{name} must be an object")
        require_non_negative_int(
            retention_class.get("file_count"),
            f"evidence_cost_retention.rollup.retention_classes.{name}.file_count",
        )
        require_non_negative_int(
            retention_class.get("total_bytes"),
            f"evidence_cost_retention.rollup.retention_classes.{name}.total_bytes",
        )

    policy = rollup.get("policy_compliance")
    require(isinstance(policy, dict), "evidence_cost_retention.rollup.policy_compliance must be an object")
    require(
        isinstance(policy.get("all_sources_policy_passed"), bool),
        "evidence_cost_retention.rollup.policy_compliance.all_sources_policy_passed must be boolean",
    )
    for key in ["tier_counts", "failed_gate_counts"]:
        value = policy.get(key)
        require(isinstance(value, dict), f"evidence_cost_retention.rollup.policy_compliance.{key} must be an object")
        for name, count in value.items():
            require_non_negative_int(count, f"evidence_cost_retention.rollup.policy_compliance.{key}.{name}")


def require_false_field(
    payload: dict[str, Any],
    section: str,
    key: str,
    *,
    optional: bool = False,
    prefix: str | None = None,
) -> None:
    container = payload.get(section)
    if container is None and optional:
        return
    require(isinstance(container, dict), f"{section} must be an object")
    if key not in container and optional:
        return
    require_false_value(container.get(key), dotted_path(prefix, section, key))


def require_zero_field(
    payload: dict[str, Any],
    section: str,
    key: str,
    *,
    optional: bool = False,
    prefix: str | None = None,
) -> None:
    container = payload.get(section)
    if container is None and optional:
        return
    require(isinstance(container, dict), f"{section} must be an object")
    if key not in container and optional:
        return
    require_zero_value(container.get(key), dotted_path(prefix, section, key))


def dotted_path(prefix: str | None, section: str, key: str) -> str:
    return ".".join(part for part in [prefix, section, key] if part)


def require_false_value(value: Any, field: str) -> None:
    require(value is False, f"{field} must be false")


def require_zero_value(value: Any, field: str) -> None:
    require(value == 0, f"{field} must be 0")


def require_true_value(value: Any, field: str) -> None:
    require(value is True, f"{field} must be true")


def require_non_negative_int(value: Any, field: str) -> None:
    require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{field} must be a non-negative integer")


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def architecture_lines(architecture: dict[str, Any], workflow: dict[str, Any]) -> list[str]:
    rollup = object_or_empty(architecture.get("rollup"))
    workflow_rollup = object_or_empty(workflow.get("rollup"))
    repair = object_or_empty(workflow_rollup.get("repair_activity"))
    return [
        f"- Entrypoint sources: `{int_text(rollup.get('source_count'))}`",
        f"- Worker count: `{int_text(rollup.get('worker_count'))}`",
        f"- Repair round cap: `{int_text(rollup.get('repair_round_cap'))}`",
        f"- Roles: `{', '.join(string_list(rollup.get('roles'))) or 'unknown'}`",
        f"- Repair histories: `{int_text(repair.get('repair_history_unit_count'))}`; auto-recovered units: `{int_text(repair.get('auto_recovered_unit_count'))}`",
    ]


def evidence_cost_retention_lines(evidence_cost: dict[str, Any]) -> list[str]:
    rollup = object_or_empty(evidence_cost.get("rollup"))
    runtime = object_or_empty(rollup.get("runtime_ms"))
    policy = object_or_empty(rollup.get("policy_compliance"))
    return [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Source count | {int_text(rollup.get('source_count'))} |",
        f"| Artifact count | {int_text(rollup.get('artifact_count'))} |",
        f"| Total bytes | {int_text(rollup.get('total_bytes'))} |",
        f"| Pipeline count | {int_text(rollup.get('pipeline_count'))} |",
        f"| Runtime observations | {int_text(runtime.get('observation_count'))} |",
        f"| Runtime total ms | {int_text(runtime.get('total'))} |",
        f"| Runtime max ms | {int_text(runtime.get('max'))} |",
        f"| Retention classes | {retention_class_text(rollup.get('retention_classes'))} |",
        f"| All sources passed | {bool_text(rollup.get('all_sources_passed'))} |",
        f"| Policy compliant | {bool_text(policy.get('all_sources_policy_passed'))} |",
        f"| Policy tiers | {count_map_text(policy.get('tier_counts'))} |",
        f"| Policy failed gates | {count_map_text(policy.get('failed_gate_counts'))} |",
        f"| Portability issues | {int_text(rollup.get('portability_issue_count'))} |",
        f"| Diagnostic host metadata | {int_text(rollup.get('diagnostic_host_metadata_count'))} |",
    ]


def opencode_preflight_lines(summary: dict[str, Any]) -> list[str]:
    return [
        "| Check | Value |",
        "| --- | --- |",
        f"| Status | {text(summary.get('status'), 'unknown')} |",
        f"| OpenCode command | {text(summary.get('opencode_command'), 'unknown')} |",
        f"| Required model | {text(summary.get('required_model'), 'unknown')} |",
        f"| Runtime model | {text(summary.get('opencode_model'), 'unknown')} |",
        f"| Model availability | {text(summary.get('model_availability_status'), 'unknown')} |",
        f"| Model listed by `opencode models` | {bool_text(summary.get('model_listed'))} |",
        f"| Model probe argv | `{command_text(summary.get('model_probe_argv'))}` |",
        f"| Model probe return code | {int_text(summary.get('process_returncode'))} |",
        f"| Preflight contract | {text(summary.get('contract_status'), 'unknown')} |",
        f"| Marker exists | {bool_text(summary.get('marker_exists'))} |",
        f"| OpenCode run launched | {bool_text(summary.get('opencode_run_launched'))} |",
        f"| OpenCode run argv bound | {bool_text(summary.get('opencode_run_argv_bound'))} |",
        f"| Proof class | {text(summary.get('proof_class'), 'unknown')} |",
        f"| Chat output is evidence | {bool_text(summary.get('chat_output_is_evidence'))} |",
        f"| Semantic gate | {bool_text(summary.get('semantic_gate'))} |",
        f"| Translation coverage numerator | {int_text(summary.get('translation_coverage_numerator'))} |",
    ]


def self_heal_classification_lines(classification: dict[str, Any]) -> list[str]:
    return [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Status | {text(classification.get('status'), 'unknown')} |",
        f"| Blocked repairs | {int_text(classification.get('blocked_repair_count'))} |",
        f"| Human action required | {int_text(classification.get('human_action_required_count'))} |",
        f"| Status counts | {count_map_text(classification.get('status_counts'))} |",
        f"| Blocked reasons | {count_map_text(classification.get('blocked_reason_counts'))} |",
        f"| IR feature gaps | {count_map_text(classification.get('ir_feature_gap_kinds'))} |",
        f"| Forbidden changes | {count_map_text(classification.get('forbidden_change_counts'))} |",
        f"| Source span kinds | {count_map_text(classification.get('source_span_kind_counts'))} |",
        f"| Routes | {count_map_text(classification.get('route_counts'))} |",
        f"| Next actions | {count_map_text(classification.get('next_action_counts'))} |",
        f"| Smallest next tests | {count_map_text(classification.get('smallest_next_test_kind_counts'))} |",
        f"| Next action samples | {int_text(classification.get('next_action_count'))} |",
        f"| Sample next-action limit | {int_text(classification.get('sample_next_action_limit'))} |",
        f"| Semantic gate | {bool_text(classification.get('semantic_gate'))} |",
        f"| Translation coverage numerator | {int_text(classification.get('translation_coverage_numerator'))} |",
    ]


def progress_delta_lines(progress_delta: dict[str, Any]) -> list[str]:
    capability = object_or_empty(progress_delta.get("capability_delta"))
    governance = object_or_empty(progress_delta.get("governance_delta"))
    workflow = object_or_empty(progress_delta.get("workflow_delta"))
    return [
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Capability delta count | {int_text(capability.get('delta_count'))} |",
        f"| Governance delta count | {int_text(governance.get('delta_count'))} |",
        f"| Verification commands | {int_text(governance.get('verification_command_count'))} |",
        f"| Route decision artifacts | {int_text(governance.get('route_decision_artifacts'))} |",
        f"| Workflow units converged | {int_text(workflow.get('workflow_units_converged'))} / {int_text(workflow.get('workflow_units_total'))} |",
        f"| Repair-history units | {int_text(workflow.get('repair_history_unit_count'))} |",
        f"| Observed repair units | {int_text(workflow.get('observed_repair_unit_count'))} |",
        f"| Auto-recovered units | {int_text(workflow.get('auto_recovered_unit_count'))} |",
        f"| Rollback evidence count | {int_text(workflow.get('rollback_evidence_count'))} |",
        f"| Before/after repair sources | {int_text(workflow.get('before_after_repair_source_count'))} |",
        f"| Repair delta sources | {int_text(workflow.get('repair_delta_source_count'))} |",
    ]


def packet_index_lines(publication: dict[str, Any]) -> list[str]:
    rows = [
        packet_index_row("Judge config", object_or_empty(publication.get("judge_config"))),
        packet_index_row(
            "Competition config archive",
            object_or_empty(object_or_empty(publication.get("competition_config_archive")).get("bundle_manifest")),
        ),
        packet_index_row("Judge run report", object_or_empty(publication.get("judge_entrypoints_run_report"))),
        packet_index_row("Readiness report", object_or_empty(publication.get("readiness_report"))),
        packet_index_row("Judge milestone bundle", object_or_empty(publication.get("judge_milestone_bundle"))),
    ]
    highlighted_refs = [
        ref
        for ref in publication.get("published_artifact_refs", [])
        if isinstance(ref, dict)
        and ref.get("artifact_name")
        in {"resume_manifest", "judge_evidence_index", "context_pack", "agent_index"}
    ]
    for ref in highlighted_refs:
        rows.append(packet_index_row(str(ref.get("artifact_name")), ref))
    return [
        "| Artifact | Path | SHA/status | Role status |",
        "| --- | --- | --- | --- |",
        *rows,
    ]


def packet_index_row(label: str, ref: dict[str, Any]) -> str:
    path = text(ref.get("path"), "unknown")
    sha_or_boundary = short_sha_or_boundary(ref)
    status = text(ref.get("status"), "unknown")
    return f"| {label} | {path} | {sha_or_boundary} | {status} |"


def competition_config_archive_lines(archive: dict[str, Any]) -> list[str]:
    lines = [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Status | {text(archive.get('status'), 'unknown')} |",
        f"| Root | {text(archive.get('root'), 'unknown')} |",
        f"| Config files | {int_text(archive.get('file_count'))} |",
        f"| External refs | {int_text(archive.get('external_ref_count'))} |",
        "",
        "| Role | Path | SHA/status | Status |",
        "| --- | --- | --- | --- |",
    ]
    external_refs = object_or_empty(archive.get("external_refs"))
    if not external_refs:
        lines.append("| none | none | missing | unknown |")
        return lines
    for path in sorted(external_refs):
        ref = object_or_empty(external_refs.get(path))
        lines.append(
            f"| {text(ref.get('role'), 'unknown')} | {text(ref.get('path') or path, 'unknown')} | "
            f"{short_sha_or_boundary(ref)} | {text(ref.get('status'), 'unknown')} |"
        )
    return lines


def publishability_lines(publishability: dict[str, Any]) -> list[str]:
    return [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Status | {text(publishability.get('status'), 'unknown')} |",
        f"| Scope | {text(publishability.get('scope'), 'unknown')} |",
        f"| Required agent tool | {text(publishability.get('required_agent_tool'), 'unknown')} |",
        f"| Required model | {text(publishability.get('required_model'), 'unknown')} |",
        f"| OpenCode GLM preflight status | {text(publishability.get('opencode_glm51_preflight_status'), 'unknown')} |",
        f"| OpenCode GLM publishable | {bool_text(publishability.get('opencode_glm51_publishable'))} |",
        f"| All entrypoints run publishable | {bool_text(publishability.get('all_entrypoints_run_publishable'))} |",
        f"| Competition-exact publishable | {bool_text(publishability.get('competition_exact_publishable'))} |",
        f"| External milestone claim ready | {bool_text(publishability.get('external_milestone_claim_ready'))} |",
        f"| External milestone | {bool_text(publishability.get('external_milestone'))} |",
        f"| Target artifacts regenerable | {bool_text(publishability.get('target_artifacts_regenerable'))} |",
        f"| Semantic gate | {bool_text(publishability.get('semantic_gate'))} |",
        f"| Translation coverage numerator | {int_text(publishability.get('translation_coverage_numerator'))} |",
    ]


def release_tag_readiness_lines(readiness: dict[str, Any]) -> list[str]:
    return [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Status | {text(readiness.get('status'), 'unknown')} |",
        f"| Tag name | {text(readiness.get('tag_name'), 'none')} |",
        f"| Tag target commit | {text(readiness.get('tag_target_commit'), 'none')} |",
        f"| Repo commit | {text(readiness.get('repo_commit'), 'unknown')} |",
        f"| Tag matches repo commit | {bool_text(readiness.get('tag_matches_repo_commit'))} |",
        f"| Remote release notes | {text(readiness.get('remote_release_notes_status'), 'unknown')} |",
        f"| External review record | {text(readiness.get('external_review_record_status'), 'unknown')} |",
        f"| External milestone claim ready | {bool_text(readiness.get('external_milestone_claim_ready'))} |",
        f"| Semantic gate | {bool_text(readiness.get('semantic_gate'))} |",
        f"| Translation coverage numerator | {int_text(readiness.get('translation_coverage_numerator'))} |",
    ]


def competition_host_readiness_lines(readiness: dict[str, Any]) -> list[str]:
    return [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Status | {text(readiness.get('status'), 'unknown')} |",
        f"| Required agent tool | {text(readiness.get('required_agent_tool'), 'unknown')} |",
        f"| Required model | {text(readiness.get('required_model'), 'unknown')} |",
        f"| Required variant | {text(readiness.get('required_variant'), 'unknown')} |",
        f"| Required proof class | {text(readiness.get('required_proof_class'), 'unknown')} |",
        f"| Actual highest proof class | {text(readiness.get('actual_highest_proof_class'), 'unknown')} |",
        f"| All entrypoints run publishable | {bool_text(readiness.get('all_entrypoints_run_publishable'))} |",
        f"| All entrypoints competition-exact | {bool_text(readiness.get('all_entrypoints_competition_exact'))} |",
        f"| Competition exact host verified | {bool_text(readiness.get('competition_exact_host_verified'))} |",
        f"| OpenCode GLM preflight status | {text(readiness.get('opencode_glm51_preflight_status'), 'unknown')} |",
        f"| OpenCode GLM publishable | {bool_text(readiness.get('opencode_glm51_publishable'))} |",
        f"| External milestone claim ready | {bool_text(readiness.get('external_milestone_claim_ready'))} |",
        f"| Missing requirements | {string_list_text(readiness.get('missing_requirements'))} |",
        f"| Semantic gate | {bool_text(readiness.get('semantic_gate'))} |",
        f"| Translation coverage numerator | {int_text(readiness.get('translation_coverage_numerator'))} |",
    ]


def blocker_lines(blockers: Any) -> list[str]:
    values = [blocker for blocker in blockers if isinstance(blocker, str)] if isinstance(blockers, list) else []
    if not values:
        return ["- none"]
    return [f"- `{blocker}`" for blocker in values]


def short_sha_or_boundary(ref: dict[str, Any]) -> str:
    sha = ref.get("sha256")
    if isinstance(sha, str) and len(sha) >= 12:
        return sha[:12]
    status = ref.get("status")
    if isinstance(status, str) and status == "self":
        return "self"
    boundary = ref.get("hash_boundary")
    if isinstance(boundary, str) and boundary:
        return "boundary"
    return "missing"


def baseline_rows(baseline: dict[str, Any]) -> list[str]:
    rows = []
    for key in ["raw_c2rust", "c2rust_repair", "typed_ir_route", "opencode_llm_worker", "handwritten_reference"]:
        row = object_or_empty(baseline.get(key))
        label = BASELINE_LABELS.get(key, key)
        accepted = "yes" if row.get("semantic_acceptance_claimed") is True else "no"
        rows.append(
            f"| {label} | {text(row.get('status'), 'unknown')} | {accepted} | {int_text(row.get('translation_coverage_numerator'))} | {baseline_manifest_evidence_text(row)} |"
        )
    return rows


def baseline_manifest_evidence_text(row: dict[str, Any]) -> str:
    rollup = object_or_empty(row.get("c2rust_baseline_rollup"))
    if not rollup:
        return "n/a"
    return (
        f"{int_text(rollup.get('unique_manifest_count'))} manifests / "
        f"{int_text(rollup.get('source_report_count'))} sources / "
        f"{int_text(rollup.get('compile_passed_count'))} compile-pass"
    )


def command_lines(commands: dict[str, Any]) -> list[str]:
    lines = []
    for key in ["run_judge_entrypoints", "build_bundle", "validate_judge_entrypoints"]:
        value = commands.get(key)
        if isinstance(value, str) and value:
            lines.extend([f"- `{key}`:", "", f"```bash\n{value}\n```"])
    entrypoints = commands.get("entrypoints")
    if isinstance(entrypoints, list) and entrypoints:
        lines.append("- Focused entrypoints:")
        for entry in entrypoints:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("command"), str):
                lines.append(f"  - `{entry['id']}`: `{entry['command']}`")
    return lines or ["- No reproduction command was published in the bundle."]


def bullet_lines(values: Any) -> list[str]:
    if isinstance(values, list) and values:
        return [f"- {text(value, 'unknown')}" for value in values]
    return ["- None recorded."]


def gap_lines(values: Any) -> list[str]:
    if not isinstance(values, list) or not values:
        return ["- None recorded."]
    lines = []
    for item in values:
        if isinstance(item, dict):
            lines.append(f"- `{text(item.get('gap_id'), 'unknown')}`: {text(item.get('status'), 'unknown')}")
        else:
            lines.append(f"- {text(item, 'unknown')}")
    return lines


def proof_class_text(bundle: dict[str, Any]) -> str:
    proof_classes = object_or_empty(bundle.get("proof_classes"))
    rollup = object_or_empty(proof_classes.get("rollup"))
    trusted = string_list(rollup.get("trusted_proof_classes"))
    if trusted:
        return ", ".join(trusted)
    present = string_list(rollup.get("present"))
    return ", ".join(present) if present else "unknown"


def commit_text(publication: dict[str, Any]) -> str:
    repo_commit = object_or_empty(publication.get("repo_commit"))
    return text(repo_commit.get("commit"), "unknown")


def source_pin_text(publication: dict[str, Any]) -> str:
    pin = object_or_empty(publication.get("target_source_pin"))
    target = text(pin.get("target_id"), "unknown")
    branch = text(pin.get("branch"), "unknown")
    commit = text(pin.get("canonical_commit") or pin.get("commit"), "unknown")
    return f"{target}:{branch}@{commit}"


def unsafe_reduction_text(*candidates: Any) -> str:
    for candidate in candidates:
        unsafe = object_or_empty(candidate)
        if unsafe.get("status") == "measured":
            return (
                f"{int_text(unsafe.get('baseline_total_unsafe'))} -> "
                f"{int_text(unsafe.get('current_total_unsafe'))} "
                f"(reduced by {int_text(unsafe.get('reduced_by'))})"
            )
    return "not measured"


def nested_int(payload: dict[str, Any], section: str, key: str) -> str:
    return int_text(object_or_empty(payload.get(section)).get(key))


def false_text(value: Any) -> str:
    return "false" if value is False else text(value, "unknown")


def bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return text(value, "unknown")


def command_text(value: Any) -> str:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return " ".join(value)
    return text(value, "unknown")


def string_list_text(value: Any) -> str:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value) if value else "none"
    return "unknown"


def int_text(value: Any) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    return "0"


def count_map_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    parts = []
    for key in sorted(value):
        count = value.get(key)
        if isinstance(count, bool):
            count_text = str(int(count))
        elif isinstance(count, (int, float)):
            count_text = str(int(count))
        else:
            count_text = "0"
        parts.append(f"`{key}`: {count_text}")
    return ", ".join(parts)


def retention_class_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    parts = []
    for key in sorted(value):
        retention_class = object_or_empty(value.get(key))
        parts.append(
            f"`{key}`: {int_text(retention_class.get('file_count'))} files / "
            f"{int_text(retention_class.get('total_bytes'))} bytes"
        )
    return ", ".join(parts)


def text(value: Any, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float, bool)):
        return str(value).lower() if isinstance(value, bool) else str(value)
    return default


def object_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
