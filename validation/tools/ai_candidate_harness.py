#!/usr/bin/env python3
"""Generate hash-bound AI Rust candidates without granting semantic status."""

from validation.tools._ai_candidate_harness_parts.cli import main
from validation.tools._ai_candidate_harness_parts.context import build_context_pack, canonical_json_bytes
from validation.tools._ai_candidate_harness_parts.gate_feedback import extract_gate_failure_facts
from validation.tools._ai_candidate_harness_parts.fresh_oracle import prove_fresh_oracle
from validation.tools._ai_candidate_harness_parts.exact_validation import validate_exact_candidate
from validation.tools._ai_candidate_harness_parts.provider import (
    MAX_PROVIDER_STDOUT_BYTES,
    ProviderExecution,
    apply_generated_candidate,
    generate_candidate,
    parse_candidate_response,
)
from validation.tools._ai_candidate_harness_parts.repair import (
    DEFAULT_MAX_REPAIR_ROUNDS,
    HARD_MAX_REPAIR_ROUNDS,
    coordinate_repairs,
)
from validation.tools._ai_candidate_harness_parts.repair_contract import parse_repair_response
from validation.tools._ai_candidate_harness_parts.router import (
    ALLOWED_SOURCES,
    DEFAULT_PROVIDER_INVOCATION_BUDGET,
    HARD_MAX_PROVIDER_INVOCATIONS,
    MAX_CANDIDATE_ID_BYTES,
    MAX_CANDIDATES,
    REQUIRED_GATES,
    SOURCE_ORDER,
    build_selection_policy,
    recompute_router_metrics,
    route_candidates,
    selection_policy_sha256,
)

__all__ = [
    "MAX_PROVIDER_STDOUT_BYTES",
    "ProviderExecution",
    "DEFAULT_MAX_REPAIR_ROUNDS",
    "DEFAULT_PROVIDER_INVOCATION_BUDGET",
    "HARD_MAX_REPAIR_ROUNDS",
    "HARD_MAX_PROVIDER_INVOCATIONS",
    "MAX_CANDIDATE_ID_BYTES",
    "MAX_CANDIDATES",
    "REQUIRED_GATES",
    "SOURCE_ORDER",
    "ALLOWED_SOURCES",
    "apply_generated_candidate",
    "build_selection_policy",
    "build_context_pack",
    "coordinate_repairs",
    "canonical_json_bytes",
    "extract_gate_failure_facts",
    "validate_exact_candidate",
    "generate_candidate",
    "main",
    "parse_candidate_response",
    "parse_repair_response",
    "prove_fresh_oracle",
    "recompute_router_metrics",
    "route_candidates",
    "selection_policy_sha256",
]


if __name__ == "__main__":
    raise SystemExit(main())
