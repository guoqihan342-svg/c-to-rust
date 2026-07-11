#!/usr/bin/env python3
"""Generate hash-bound AI Rust candidates without granting semantic status."""

from validation.tools._ai_candidate_harness_parts.cli import main
from validation.tools._ai_candidate_harness_parts.context import build_context_pack
from validation.tools._ai_candidate_harness_parts.provider import (
    ProviderExecution,
    apply_generated_candidate,
    generate_candidate,
    parse_candidate_response,
)

__all__ = [
    "ProviderExecution",
    "apply_generated_candidate",
    "build_context_pack",
    "generate_candidate",
    "main",
    "parse_candidate_response",
]


if __name__ == "__main__":
    raise SystemExit(main())
