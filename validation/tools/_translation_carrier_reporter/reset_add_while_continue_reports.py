from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .errors import ReporterError
from .reset_add_while_continue_contract import behavior_fields
from .reset_add_while_continue_model import mutated_outputs
from .source_binding import StaticContext


def build_negative_report(
    context: StaticContext, common: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    expected_ids = [str(case["id"]) for case in context.cases]
    actual_ids = [str(item["case_id"]) for item in execution["partition_replay"]["case_runs"]]
    if actual_ids != expected_ids:
        raise ReporterError("continue negative replay case ids drifted")
    if execution["partition_replay"]["observable_mismatch_case_ids"] != expected_ids:
        raise ReporterError("continue mutation was not detected by every fixture case")
    return_field = behavior_fields(context.contract)[0]
    mismatches = []
    for case in context.cases:
        mutated = mutated_outputs(case, context.contract)
        if mutated[return_field] == case["expected_outputs"][return_field]:
            raise ReporterError("continue mutation is not observable")
        mismatches.append(
            {
                "case_id": case["id"],
                "field": return_field,
                "accepted_value": True,
                "mutated_value": False,
            }
        )
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation": "unique continue replaced by equal-length valid no-op",
        "detected_case_ids": expected_ids,
        "partition_detection": {"observable_mismatch_case_ids": expected_ids},
        "actual_mutation_execution": execution,
        "first_mismatch": mismatches[0],
        "mismatches": mismatches,
    }


def build_report_claim(context: StaticContext) -> dict[str, Any]:
    contract = context.contract
    return {
        "scope": "source_fragment_only",
        "whole_function_semantics_verified": False,
        "external_callee_semantics_verified": False,
        "verified_behavior": (
            "A readonly source and mutable owner use the exact source-owner noalias pair; "
            "an owner interior alias resets nested u32 state, owner u32 state uses wrapping_add, "
            "and one current-level continue reaches the terminal true return."
        ),
        "external_callee": None,
        "reset_add_while_continue": {
            "owner_parameter": contract["owner_parameter"],
            "projection": contract["projection"],
            "reset_state": contract["reset_state"],
            "add_state": contract["add_state"],
            "control_flow": contract["control_flow"],
            "noalias_required": contract["noalias_required"],
        },
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }


def evidence_identity(context: StaticContext, runtime: dict[str, Any]) -> dict[str, Any]:
    refs = runtime["refs"]
    fragment = (
        context.spec.get("translation_carrier", {})
        .get("real_source", {})
        .get("fragment")
    )
    if not isinstance(fragment, dict):
        raise ReporterError("translation carrier source fragment identity is missing")
    declared_fragment_sha = fragment.get("sha256")
    recomputed_fragment_sha = context.refs["real_source"].get("source_fragment_sha256")
    if (
        not isinstance(declared_fragment_sha, str)
        or re.fullmatch(r"[0-9a-f]{64}", declared_fragment_sha) is None
        or recomputed_fragment_sha != declared_fragment_sha
    ):
        raise ReporterError("translation carrier source fragment sha256 drifted")
    line_start = fragment.get("line_start")
    line_end = fragment.get("line_end")
    if (
        isinstance(line_start, bool)
        or not isinstance(line_start, int)
        or isinstance(line_end, bool)
        or not isinstance(line_end, int)
        or line_start < 1
        or line_start > line_end
    ):
        raise ReporterError("translation carrier source fragment line range drifted")
    material = {
        "schema_version": 1,
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
        },
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**material, "identity_sha256": hashlib.sha256(encoded).hexdigest(), "recomputed": True}
