#!/usr/bin/env python3
"""Generate hash-bound AI Rust candidates without granting semantic status."""

from validation.tools._ai_candidate_harness_parts.cli import main
from validation.tools._ai_candidate_harness_parts.context import build_context_pack, canonical_json_bytes
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

__all__ = [
    "MAX_PROVIDER_STDOUT_BYTES",
    "ProviderExecution",
    "DEFAULT_MAX_REPAIR_ROUNDS",
    "HARD_MAX_REPAIR_ROUNDS",
    "apply_generated_candidate",
    "build_context_pack",
    "coordinate_repairs",
    "canonical_json_bytes",
    "generate_candidate",
    "main",
    "parse_candidate_response",
    "parse_repair_response",
]


if __name__ == "__main__":
    raise SystemExit(main())
