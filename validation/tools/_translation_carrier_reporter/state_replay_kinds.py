from __future__ import annotations

from typing import Any

from .constant_state_contract import KIND as CONSTANT_STATE_KIND
from .field_add_contract import KIND as FIELD_ADD_KIND
from .field_scalar_add_contract import KIND as FIELD_SCALAR_ADD_KIND
from .field_postfix_increment_contract import KIND as FIELD_POSTFIX_INCREMENT_KIND
from .owner_interior_usize_add_contract import KIND as OWNER_INTERIOR_USIZE_ADD_KIND
from .interior_projection_contract import KIND as INTERIOR_PROJECTION_KIND
from .reset_add_while_continue_contract import KIND as RESET_ADD_CONTINUE_KIND
from .reset_add_while_continue_model import expected_fixture_state_model as reset_add_model


STATE_REPLAY_KINDS = frozenset(
    {
        CONSTANT_STATE_KIND, FIELD_ADD_KIND, FIELD_SCALAR_ADD_KIND,
        FIELD_POSTFIX_INCREMENT_KIND,
        OWNER_INTERIOR_USIZE_ADD_KIND,
        INTERIOR_PROJECTION_KIND, RESET_ADD_CONTINUE_KIND,
    }
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
    if kind == RESET_ADD_CONTINUE_KIND:
        return reset_add_model(contract)
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
    if kind == FIELD_POSTFIX_INCREMENT_KIND:
        return {**model, "operation": "wrapping_add", "increment": 1}
    if kind == OWNER_INTERIOR_USIZE_ADD_KIND:
        return {
            **model,
            "operation": "wrapping_add",
            "projection_mode": "owner_interior_mutable",
            "pointer_root_count": 1,
            "conversion": "u32_to_usize",
            "source_bits": 32,
            "target_bits": 64,
        }
    raise ValueError(f"unsupported fixture state model kind: {kind}")
