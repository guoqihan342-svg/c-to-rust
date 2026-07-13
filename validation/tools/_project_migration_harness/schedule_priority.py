from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY = "external-verifier"
_KEY = "scheduler_evidence"
_ALLOWED = {
    "schema_version",
    "authority",
    "failure_fingerprint_sha256",
    "previous_failure_fingerprint_sha256",
    "effective_input_sha256",
    "previous_effective_input_sha256",
    "strategy_sha256",
    "previous_strategy_sha256",
    "uncertainty_count",
    "estimated_token_cost",
    "convergence_attempts",
}


def scheduling_priority(
    facts: Mapping[str, Any], *, critical_path_weight: int,
) -> dict[str, Any] | None:
    """Return a deterministic priority derived only from verifier-owned facts."""
    raw = facts.get(_KEY)
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"{_KEY} must be an object")
    unknown = set(raw) - _ALLOWED
    if unknown:
        raise ValueError(f"{_KEY} contains unsupported fields: {sorted(unknown)}")
    if raw.get("schema_version") != 1 or raw.get("authority") != _AUTHORITY:
        raise ValueError(f"{_KEY} must be schema 1 evidence from {_AUTHORITY}")

    failure = _hash(raw, "failure_fingerprint_sha256")
    previous_failure = _hash(raw, "previous_failure_fingerprint_sha256")
    effective_input = _hash(raw, "effective_input_sha256")
    previous_input = _hash(raw, "previous_effective_input_sha256")
    strategy = _hash(raw, "strategy_sha256")
    previous_strategy = _hash(raw, "previous_strategy_sha256")
    if (
        isinstance(critical_path_weight, bool)
        or not isinstance(critical_path_weight, int)
        or not 0 <= critical_path_weight <= 1_000
    ):
        raise ValueError("host-derived critical_path_weight is invalid")
    critical_path = critical_path_weight
    uncertainty = _bounded_int(raw, "uncertainty_count", 0, 1_000, 0)
    token_cost = _bounded_int(raw, "estimated_token_cost", 1, 10_000_000, 1)
    convergence = _bounded_int(raw, "convergence_attempts", 0, 1_000, 0)

    fresh_failure = failure is not None and failure != previous_failure
    input_changed = effective_input is not None and effective_input != previous_input
    strategy_changed = strategy is not None and strategy != previous_strategy
    comparable = all(value is not None for value in (
        failure,
        previous_failure,
        effective_input,
        previous_input,
        strategy,
        previous_strategy,
    ))
    stalled = bool(
        convergence > 0
        and comparable
        and not fresh_failure
        and not input_changed
        and not strategy_changed
    )

    novelty = (4 * int(fresh_failure)) + (2 * int(input_changed)) + int(strategy_changed)
    score = (
        novelty * 1_000_000
        + critical_path * 1_000
        + uncertainty * 100
        - min(token_cost // 1_000, 9_999)
        - convergence * 10_000
    )
    return {
        "authority": _AUTHORITY,
        "score": score,
        "fresh_failure": fresh_failure,
        "input_changed": input_changed,
        "strategy_changed": strategy_changed,
        "critical_path_weight": critical_path,
        "uncertainty_count": uncertainty,
        "estimated_token_cost": token_cost,
        "convergence_attempts": convergence,
        "stalled": stalled,
    }


def _hash(values: Mapping[str, Any], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{_KEY}.{key} must be a lowercase SHA-256")
    return value


def _bounded_int(
    values: Mapping[str, Any], key: str, minimum: int, maximum: int, default: int,
) -> int:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{_KEY}.{key} must be an integer in [{minimum}, {maximum}]")
    return value


__all__ = ["scheduling_priority"]
