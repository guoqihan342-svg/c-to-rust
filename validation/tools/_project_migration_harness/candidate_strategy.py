from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256


AUTHORITY = "host-strategy-planner-v1"
_CATALOG = {
    "initial": (
        ("dependency-first-safe-port", [
            "Preserve the bound public interface and dependency direction.",
            "Prefer explicit ownership and safe Rust data structures.",
        ]),
        ("interface-first-safe-port", [
            "Reconstruct bound types and interfaces before function bodies.",
            "Keep unresolved external behavior behind explicit boundaries.",
        ]),
        ("state-first-safe-port", [
            "Model global and mutable state ownership before control flow.",
            "Keep initialization order explicit and deterministic.",
        ]),
    ),
    "compile": (
        ("minimal-type-correction", [
            "Correct only host-reported type, symbol, and module inconsistencies.",
            "Preserve already bound behavior and interfaces.",
        ]),
        ("interface-reconstruction", [
            "Re-derive signatures and shared types from the bound context.",
            "Remove conflicting local glue instead of masking diagnostics.",
        ]),
        ("ownership-first-reconstruction", [
            "Rebuild ownership and borrowing before adapting call sites.",
            "Avoid new unsafe operations unless the boundary requires them.",
        ]),
    ),
    "oracle-replay-diff": (
        ("behavioral-dataflow-repair", [
            "Trace input, state, and return data flow from bound source facts.",
            "Do not infer or reproduce withheld expected values.",
        ]),
        ("control-state-reconstruction", [
            "Reconstruct branch, loop, and state-transition semantics explicitly.",
            "Preserve integer and pointer edge behavior from the bound contract.",
        ]),
        ("dependency-contract-repair", [
            "Reconcile callee contracts and side effects across the unit boundary.",
            "Do not replace external behavior with local fixture shims.",
        ]),
    ),
    "negative": (
        ("error-path-repair", [
            "Reconstruct failure branches and return conventions explicitly.",
            "Preserve state on rejected inputs according to bound source facts.",
        ]),
        ("boundary-validation-repair", [
            "Validate lengths, nullability, and ranges at the owning boundary.",
            "Do not invent accepted inputs or expected outputs.",
        ]),
        ("invariant-preserving-repair", [
            "Restore invariants on every early return and cleanup path.",
            "Keep error handling deterministic and allocation-safe.",
        ]),
    ),
    "unsafe-alias": (
        ("ownership-alias-repair", [
            "Replace unproven aliasing with explicit ownership or bounded borrowing.",
            "Keep raw pointers confined to verified FFI boundaries.",
        ]),
        ("lifetime-reconstruction", [
            "Derive lifetimes from ownership and call relationships.",
            "Do not extend references beyond bound storage lifetimes.",
        ]),
        ("safe-container-reconstruction", [
            "Use safe containers for bounded storage and mutation.",
            "Preserve identity only where the interface contract requires it.",
        ]),
    ),
    "abi-layout": (
        ("layout-preserving-repair", [
            "Preserve field order, size, alignment, and representation evidence.",
            "Keep layout-sensitive types explicit.",
        ]),
        ("ffi-boundary-repair", [
            "Confine ABI-sensitive declarations to explicit FFI boundaries.",
            "Keep calling convention and symbol visibility bound.",
        ]),
        ("shared-type-reconciliation", [
            "Use one project-owned declaration for each shared layout.",
            "Remove duplicate or conflicting local type definitions.",
        ]),
    ),
    "final-verification": (
        ("minimal-final-repair", [
            "Repair only the bound final-verification blocker.",
            "Do not broaden public APIs or add fixture-specific behavior.",
        ]),
        ("cross-unit-final-repair", [
            "Reconcile project interfaces and initialization order as one change.",
            "Keep unaffected unit candidates unchanged.",
        ]),
        ("clean-room-final-reconstruction", [
            "Re-derive the unit from verified build, API, and ownership facts.",
            "Retain no unverified glue from the failed candidate.",
        ]),
    ),
}


def select_candidate_strategy(
    *, gate_family: str | None, attempt_count: int,
    failure_fingerprint_sha256: str | None,
) -> dict[str, Any]:
    family = gate_family or "initial"
    if family not in _CATALOG:
        raise ValueError("candidate strategy gate family is unsupported")
    if isinstance(attempt_count, bool) or not isinstance(attempt_count, int) or attempt_count < 0:
        raise ValueError("candidate strategy attempt_count is invalid")
    if failure_fingerprint_sha256 is not None and (
        not isinstance(failure_fingerprint_sha256, str)
        or len(failure_fingerprint_sha256) != 64
        or any(char not in "0123456789abcdef" for char in failure_fingerprint_sha256)
    ):
        raise ValueError("candidate strategy failure fingerprint is invalid")
    if family == "initial" and failure_fingerprint_sha256 is not None:
        raise ValueError("initial candidate strategy cannot bind a failure")
    if family != "initial" and failure_fingerprint_sha256 is None:
        raise ValueError("repair candidate strategy requires a failure fingerprint")
    offset = attempt_count if family == "initial" else max(0, attempt_count - 1)
    variant_index = offset % len(_CATALOG[family])
    strategy_id, guidance = _CATALOG[family][variant_index]
    core = {
        "schema_version": 1,
        "authority": AUTHORITY,
        "strategy_family": family,
        "strategy_id": strategy_id,
        "variant_index": variant_index,
        "failure_fingerprint_sha256": failure_fingerprint_sha256,
        "guidance": guidance,
        "model_self_score_allowed": False,
        "semantic_acceptance": False,
    }
    return {**core, "strategy_sha256": content_sha256(core)}


def validate_candidate_strategy(value: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "authority", "strategy_family", "strategy_id",
        "variant_index", "failure_fingerprint_sha256", "guidance",
        "model_self_score_allowed", "semantic_acceptance", "strategy_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("candidate strategy fields are invalid")
    family = value.get("strategy_family")
    index = value.get("variant_index")
    if (
        family not in _CATALOG or isinstance(index, bool) or not isinstance(index, int)
        or not 0 <= index < len(_CATALOG[str(family)])
    ):
        raise ValueError("candidate strategy family/index is invalid")
    expected_id, guidance = _CATALOG[str(family)][index]
    core = {key: value[key] for key in fields if key != "strategy_sha256"}
    if (
        value.get("schema_version") != 1
        or value.get("authority") != AUTHORITY
        or value.get("strategy_id") != expected_id
        or value.get("guidance") != guidance
        or value.get("model_self_score_allowed") is not False
        or value.get("semantic_acceptance") is not False
        or value.get("strategy_sha256") != content_sha256(core)
    ):
        raise ValueError("candidate strategy binding is invalid")
    failure = value.get("failure_fingerprint_sha256")
    select_candidate_strategy(
        gate_family=None if family == "initial" else str(family),
        attempt_count=index if family == "initial" else index + 1,
        failure_fingerprint_sha256=failure,
    )
    return dict(value)


__all__ = ["select_candidate_strategy", "validate_candidate_strategy"]
