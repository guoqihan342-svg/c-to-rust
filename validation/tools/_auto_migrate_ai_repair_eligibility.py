from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def classify_ai_repair_eligibility(result: Mapping[str, Any]) -> dict[str, Any]:
    oracle = result.get("oracle_proof")
    if not isinstance(oracle, Mapping) or oracle.get("status") != "passed":
        return {
            "status": "skipped",
            "reason": "fresh_oracle_not_passed",
            "provider_invocations": 0,
            "semantic_gate": False,
        }
    if not isinstance(oracle.get("target_contract"), Mapping):
        return {
            "status": "skipped",
            "reason": "target_contract_missing",
            "provider_invocations": 0,
            "semantic_gate": False,
        }
    failures = result.get("repair_validation_result")
    if not isinstance(failures, Mapping) or failures.get("status") != "failed":
        return {
            "status": "skipped",
            "reason": "structured_candidate_failure_missing",
            "provider_invocations": 0,
            "semantic_gate": False,
        }
    return {
        "status": "eligible",
        "reason": "fresh_oracle_and_target_contract_bound",
        "provider_invocations": 0,
        "semantic_gate": False,
    }


__all__ = ["classify_ai_repair_eligibility"]
