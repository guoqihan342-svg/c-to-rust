from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .call_continue_contract import behavior_fields
from .call_continue_model import comparison_mutated_outputs, continue_mutated_outputs
from .errors import ReporterError


def build_negative_report(
    context: Any, common: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    scenarios = execution.get("scenarios")
    if not isinstance(scenarios, list) or [item.get("scenario_id") for item in scenarios] != [
        "comparison-equality-flip", "continue-noop"
    ]:
        raise ReporterError("call-continue negative scenarios drifted")
    all_ids = [str(case["id"]) for case in context.cases]
    hit_ids = [str(case["id"]) for case in context.cases if case["expected_outputs"][behavior_fields(context.contract)[0]]]
    miss_ids = [case_id for case_id in all_ids if case_id not in hit_ids]
    expected = ((all_ids, []), (hit_ids, miss_ids))
    mismatches: list[dict[str, Any]] = []
    for scenario, (detected, passed) in zip(scenarios, expected, strict=True):
        partition = scenario["partition_replay"]
        if partition.get("detected_case_ids") != detected or partition.get("passed_case_ids") != passed:
            raise ReporterError(f"{scenario['scenario_id']} partition detection drifted")
        if scenario.get("expected_detected_case_ids") != detected:
            raise ReporterError(f"{scenario['scenario_id']} expected detection drifted")
        model = (
            comparison_mutated_outputs
            if scenario["scenario_id"] == "comparison-equality-flip"
            else continue_mutated_outputs
        )
        for case in context.cases:
            mutated = model(case, context.contract)
            changed = [
                field for field in behavior_fields(context.contract)
                if mutated[field] != case["expected_outputs"][field]
            ]
            if (str(case["id"]) in detected) != bool(changed):
                raise ReporterError(f"{scenario['scenario_id']} declarative partition drifted")
            for field in changed:
                mismatches.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "case_id": case["id"],
                        "field": field,
                        "accepted_value": case["expected_outputs"][field],
                        "mutated_value": mutated[field],
                    }
                )
    if not mismatches:
        raise ReporterError("call-continue negative scenarios produced no mismatch")
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation_manifest": mutation_manifest(execution),
        "detected_case_ids": all_ids,
        "partition_detection": {
            "comparison-equality-flip": {"detected_case_ids": all_ids, "passed_case_ids": []},
            "continue-noop": {"detected_case_ids": hit_ids, "passed_case_ids": miss_ids},
        },
        "actual_mutation_execution": execution,
        "first_mismatch": mismatches[0],
        "mismatches": mismatches,
    }


def build_report_claim(context: Any) -> dict[str, Any]:
    contract = context.contract
    return {
        "scope": "source_fragment_only",
        "whole_function_semantics_verified": False,
        "external_callee_semantics_verified": False,
        "verified_behavior": (
            "Three renamed entry arguments preserve mutable db, by-value local, and mutable owner; "
            "one direct fixture-only external call observes ordered root/local/owner-alias snapshots; "
            "exact u32 sentinel hits reset the alias, wrapping-add owner state, and continue, while misses return false."
        ),
        "external_callee": contract["external_callee"]["name"],
        "argument_modes": [item["mode"] for item in contract["external_callee"]["arguments"]],
        "noalias_required": contract["noalias_required"],
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }


def evidence_identity(
    context: Any, runtime: dict[str, Any], negative_execution: dict[str, Any]
) -> dict[str, Any]:
    refs = runtime["refs"]
    fragment = context.spec["translation_carrier"]["real_source"]["fragment"]
    line_start = fragment.get("line_start")
    line_end = fragment.get("line_end")
    declared_fragment_sha = fragment.get("sha256")
    recomputed_fragment_sha = context.refs["real_source"].get("source_fragment_sha256")
    if not _sha(declared_fragment_sha) or declared_fragment_sha != recomputed_fragment_sha:
        raise ReporterError("translation carrier source fragment sha256 drifted")
    if isinstance(line_start, bool) or not isinstance(line_start, int) or isinstance(line_end, bool) or not isinstance(line_end, int) or line_start < 1 or line_end < line_start:
        raise ReporterError("translation carrier source fragment line range drifted")
    manifest = mutation_manifest(negative_execution)
    material = {
        "schema_version": 2,
        "target_id": context.spec["target_id"],
        "slice_id": context.spec["slice_id"],
        "source_commit": context.spec["source_commit"],
        "replay_contract_kind": context.contract["kind"],
        "bindings": {
            "slice_spec_sha256": context.refs["slice_spec"]["sha256"],
            "fixture_sha256": context.refs["fixture"]["sha256"],
            "real_source_sha256": context.refs["real_source"]["sha256"],
            "source_fragment_sha256": recomputed_fragment_sha,
            "source_fragment_line_start": line_start,
            "source_fragment_line_end": line_end,
            "carrier_source_sha256": context.spec["translation_carrier"]["carrier_source_sha256"],
            "c_oracle_harness_sha256": refs["c_oracle_harness"]["sha256"],
            "generated_rust_draft_sha256": refs["generated_rust_draft"]["sha256"],
            "generated_replay_test_sha256": refs["generated_replay_test"]["sha256"],
            "negative_mutation_manifest_sha256": manifest["sha256"],
        },
    }
    for key, value in material["bindings"].items():
        if key.endswith("sha256") and not _sha(value):
            raise ReporterError(f"evidence identity {key} is not a sha256")
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**material, "identity_sha256": hashlib.sha256(encoded).hexdigest(), "recomputed": True}


def mutation_manifest(execution: dict[str, Any]) -> dict[str, Any]:
    scenarios = execution.get("scenarios")
    if not isinstance(scenarios, list):
        raise ReporterError("negative mutation scenarios are missing")
    entries = []
    for scenario in scenarios:
        mutation = scenario.get("mutation", {})
        original = mutation.get("original_draft", {})
        mutated = mutation.get("mutated_draft", {})
        entry = {
            "scenario_id": scenario.get("scenario_id"),
            "operator_from": mutation.get("operator_from"),
            "operator_to": mutation.get("operator_to"),
            "mutation_count": mutation.get("mutation_count"),
            "byte_offset": mutation.get("byte_offset"),
            "original_draft_sha256": original.get("sha256"),
            "mutated_draft_sha256": mutated.get("sha256"),
            "expected_detected_case_ids": scenario.get("expected_detected_case_ids"),
        }
        if not _sha(entry["original_draft_sha256"]) or not _sha(entry["mutated_draft_sha256"]):
            raise ReporterError("negative mutation draft sha256 drifted")
        entries.append(entry)
    material = {"schema_version": 1, "scenarios": entries}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**material, "sha256": hashlib.sha256(encoded).hexdigest(), "recomputed": True}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
