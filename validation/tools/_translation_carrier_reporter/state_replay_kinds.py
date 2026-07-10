from __future__ import annotations

from typing import Any

from .constant_state_contract import KIND as CONSTANT_STATE_KIND
from .field_add_contract import KIND as FIELD_ADD_KIND
from .field_scalar_add_contract import KIND as FIELD_SCALAR_ADD_KIND
from .interior_projection_contract import KIND as INTERIOR_PROJECTION_KIND


STATE_REPLAY_KINDS = frozenset(
    {CONSTANT_STATE_KIND, FIELD_ADD_KIND, FIELD_SCALAR_ADD_KIND, INTERIOR_PROJECTION_KIND}
)


def is_state_replay_kind(contract: dict[str, Any]) -> bool:
    return contract.get("kind") in STATE_REPLAY_KINDS


def expected_fixture_state_model(contract: dict[str, Any]) -> dict[str, Any]:
    kind = contract.get("kind")
    model: dict[str, Any] = {"kind": kind, "scope": "fixture_only"}
    if kind == CONSTANT_STATE_KIND:
        return {**model, "operation": "constant_assign", "value": 0}
    if kind == INTERIOR_PROJECTION_KIND:
        return {
            **model, "operation": "constant_assign", "value": 0,
            "projection_mode": "owner_interior_mutable",
            "pointer_root_count": 1,
        }
    if kind == FIELD_ADD_KIND:
        return {**model, "operation": "wrapping_add"}
    if kind == FIELD_SCALAR_ADD_KIND:
        update = contract["state_update"]
        return {
            **model,
            "operation": "wrapping_add",
            "record_field": update["record_field"],
            "scalar": update["scalar"],
        }
    raise ValueError(f"unsupported fixture state model kind: {kind}")
