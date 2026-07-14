from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_security import LedgerError, LeaseConflict


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CLAIM_KEYS = {
    "schema_version", "run_id", "unit_id", "worker_id", "role",
    "assignment_sha256", "unit_state", "context_frontier", "sha256",
}
_ROLE_STATES = {
    "planner": frozenset({"pending", "retry-ready"}),
    "translator": frozenset({"pending", "candidate-ready"}),
    "reviewer": frozenset({"candidate-ready", "gate-pending"}),
    "repairer": frozenset({"retry-ready"}),
}


def require_launch_claim(
    *, run_id: str, assignment: Mapping[str, Any], unit: Mapping[str, Any],
    frontier: Mapping[str, Any] | None, claim: Mapping[str, Any] | None,
    schedule_sha256: str | None,
) -> dict[str, Any] | None:
    if frontier is None:
        if claim is not None or schedule_sha256 is not None:
            raise LeaseConflict("legacy attempt received a frontier launch claim")
        return None
    if not isinstance(claim, Mapping) or set(claim) != _CLAIM_KEYS:
        raise LeaseConflict("portfolio-bound attempt requires a launch claim")
    if not _sha(schedule_sha256):
        raise LeaseConflict("portfolio-bound attempt requires a schedule SHA-256")
    status = unit.get("status")
    role = assignment.get("role")
    if role not in _ROLE_STATES or status not in _ROLE_STATES[role]:
        raise LeaseConflict("worker role is not ready for the current unit state")
    state_version = unit.get("state_version")
    if (
        isinstance(state_version, bool) or not isinstance(state_version, int)
        or state_version < 0
    ):
        raise LeaseConflict("unit state version is invalid")
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "unit_id": assignment.get("unit_id"),
        "worker_id": assignment.get("worker_id"),
        "role": role,
        "assignment_sha256": content_sha256(assignment),
        "unit_state": {
            "status": status,
            "resumable_status": unit.get("resumable_status"),
            "state_version": state_version,
        },
        "context_frontier": dict(frontier),
    }
    if claim.get("sha256") != content_sha256(payload) or {
        key: claim[key] for key in payload
    } != payload:
        raise LeaseConflict("launch claim is stale or drifted")
    return {**payload, "sha256": claim["sha256"], "schedule_sha256": schedule_sha256}


def require_assignment_digest(metadata_json: str, assignment: Mapping[str, Any]) -> None:
    run_metadata = metadata(metadata_json)
    binding = run_metadata.get("runtime_binding")
    records = binding.get("assignments") if isinstance(binding, Mapping) else None
    if not isinstance(records, list):
        raise LedgerError("run has no immutable runtime assignment binding")
    digest = content_sha256(assignment)
    matches = [
        item for item in records if isinstance(item, Mapping)
        and item.get("worker_id") == assignment.get("worker_id")
    ]
    if len(matches) != 1 or matches[0].get("assignment_sha256") != digest:
        raise LedgerError("assignment does not match the immutable run binding")


def metadata(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(value) if isinstance(value, str) else None
    except json.JSONDecodeError as error:
        raise LedgerError("ledger metadata is invalid JSON") from error
    if not isinstance(result, dict):
        raise LedgerError("ledger metadata must be an object")
    return result


def text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"assignment {key} is invalid")
    return result


def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


__all__ = [
    "metadata", "require_assignment_digest", "require_launch_claim", "text",
]
