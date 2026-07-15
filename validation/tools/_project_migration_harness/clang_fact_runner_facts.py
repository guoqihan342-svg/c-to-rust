from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .clang_interface_fact_evidence import build_clang_interface_fact_evidence
from .clang_record_layout_selection import (
    parse_selected_clang_record_layout_fact_evidence,
)


def derive_clang_fact_evidence(
    plan: Mapping[str, Any], *, stdout: bytes, stderr: bytes,
    allowed_sources: Mapping[str, str],
    interface_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive candidate facts only from the just-captured raw streams."""
    gate = plan.get("gate")
    if gate == "clang-ast":
        if interface_evidence is not None:
            raise ValueError("clang_fact_runner_ast_dependency_forbidden")
        return build_clang_interface_fact_evidence(
            stdout, allowed_sources, str(plan["compile_context_sha256"]),
            str(plan["target_context_sha256"]),
        )
    if gate == "clang-record-layout":
        if not isinstance(interface_evidence, Mapping):
            raise ValueError("clang_fact_runner_ast_dependency_required")
        return parse_selected_clang_record_layout_fact_evidence(
            stdout, stderr, str(plan["toolchain_portable_sha256"]),
            str(plan["target_context_sha256"]), interface_evidence,
        )
    raise ValueError("clang_fact_runner_gate_invalid")


def clang_fact_evidence_ready(gate: str, evidence: Mapping[str, Any]) -> bool:
    if gate == "clang-ast":
        return evidence.get("status") in {"parsed", "parsed_with_blockers"}
    if gate == "clang-record-layout":
        return evidence.get("status") == "facts-ready"
    return False


__all__ = ["clang_fact_evidence_ready", "derive_clang_fact_evidence"]
