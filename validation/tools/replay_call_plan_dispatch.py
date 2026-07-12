from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools.replay_call_plan_fixture import _fixture_binding
from validation.tools.replay_call_plan_schema import _readonly_byte_slice_bool_contract
from validation.tools.replay_call_plan_v1_builder import _build_bound_plan


SUPPORTED_CONTRACT_KINDS = {
    "declarative_call_plan",
    "readonly_byte_slice_bool_return",
    "record_u32_field_constant_state",
    "record_u32_field_wrapping_add_state",
    "record_u32_field_scalar_wrapping_add_state",
    "record_u32_field_postfix_increment_state",
    "record_pointer_identity_return",
    "record_buffer_length_identity_return",
    "opaque_context_return_code",
    "record_interior_projection_u32_constant_state",
    "record_owner_interior_stats_sequence_state",
    "record_owner_interior_guarded_stats_sequence_state",
    "record_owner_interior_u32_to_usize_wrapping_add_state",
    "record_interior_projection_u32_reset_add_while_continue_state",
    "scripted_external_u32_call_bool_out",
    "scripted_external_record_u32_call_bool_state",
    "scripted_external_record_u32_sequence_do_while_state",
    "scripted_external_u32_call_interior_reset_add_while_continue_state",
}


def build_replay_call_plan(spec: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    contract = spec.get("replay_contract")
    if not isinstance(contract, dict):
        from validation.tools.replay_call_plan_scalar import build_implicit_scalar_contract

        contract = build_implicit_scalar_contract(spec)
    if not isinstance(contract, dict):
        implicit_output_plan = _build_implicit_output_plan(spec, repo_root)
        if implicit_output_plan is not None:
            return implicit_output_plan
    if not isinstance(contract, dict):
        return {"schema_version": 1, "status": "unavailable"}
    contract_kind = contract.get("kind")
    if contract_kind not in SUPPORTED_CONTRACT_KINDS:
        return {"schema_version": 1, "status": "unavailable"}
    try:
        resolved_root = repo_root.resolve()
        specialized = _build_specialized_plan(
            spec, contract, str(contract_kind), resolved_root
        )
        if specialized is not None:
            return specialized
        if contract_kind == "readonly_byte_slice_bool_return":
            contract = _readonly_byte_slice_bool_contract(contract)
        return _build_bound_plan(spec, contract, resolved_root)
    except ValueError as exc:
        return {"schema_version": 1, "status": "blocked", "reason": str(exc)}
    except (OSError, RuntimeError):
        return {
            "schema_version": 1,
            "status": "blocked",
            "reason": "declarative replay fixture cannot be resolved",
        }


def _build_implicit_output_plan(
    spec: dict[str, Any], repo_root: Path
) -> dict[str, Any] | None:
    from validation.tools.replay_call_plan_out import (
        build_implicit_i32_output_plan,
        supports_implicit_i32_output_plan,
    )

    if not supports_implicit_i32_output_plan(spec):
        return None
    try:
        return build_implicit_i32_output_plan(
            spec,
            _fixture_binding(spec, repo_root.resolve()),
        )
    except ValueError as exc:
        return {"schema_version": 1, "status": "blocked", "reason": str(exc)}
    except (OSError, RuntimeError):
        return {
            "schema_version": 1,
            "status": "blocked",
            "reason": "declarative replay fixture cannot be resolved",
        }


def _build_specialized_plan(
    spec: dict[str, Any],
    contract: dict[str, Any],
    contract_kind: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    fixture = None

    def fixture_binding() -> dict[str, Any]:
        nonlocal fixture
        if fixture is None:
            fixture = _fixture_binding(spec, repo_root)
        return fixture

    if contract_kind == "record_pointer_identity_return":
        from validation.tools.replay_call_plan_record_identity import (
            build_record_pointer_identity_plan,
        )

        return build_record_pointer_identity_plan(spec, contract, fixture_binding())
    if contract_kind == "record_buffer_length_identity_return":
        from validation.tools.replay_call_plan_record_buffer_identity import (
            build_record_buffer_identity_plan,
        )

        return build_record_buffer_identity_plan(spec, contract, fixture_binding())
    if contract_kind == "opaque_context_return_code":
        from validation.tools.replay_call_plan_opaque_context import (
            build_opaque_context_plan,
        )

        return build_opaque_context_plan(spec, contract, fixture_binding())
    if contract_kind.startswith("scripted_external_"):
        from validation.tools.replay_call_plan_v2 import build_scripted_external_plan

        return build_scripted_external_plan(
            spec,
            _validated_scripted_contract(spec, contract_kind),
            fixture_binding(),
        )
    if contract_kind in {
        "record_u32_field_constant_state",
        "record_u32_field_wrapping_add_state",
        "record_u32_field_scalar_wrapping_add_state",
        "record_u32_field_postfix_increment_state",
    }:
        from validation.tools.replay_call_plan_v2 import (
            build_record_u32_constant_state_plan,
        )

        return build_record_u32_constant_state_plan(spec, contract, fixture_binding())
    if contract_kind == "record_owner_interior_u32_to_usize_wrapping_add_state":
        from validation.tools.replay_call_plan_v2 import (
            build_record_owner_usize_wrapping_add_plan,
        )

        return build_record_owner_usize_wrapping_add_plan(
            spec, contract, fixture_binding()
        )
    if contract_kind == "record_interior_projection_u32_constant_state":
        from validation.tools.replay_call_plan_v2 import (
            build_record_interior_u32_constant_state_plan,
        )

        return build_record_interior_u32_constant_state_plan(
            spec, contract, fixture_binding()
        )
    if contract_kind == "record_interior_projection_u32_reset_add_while_continue_state":
        from validation.tools.replay_call_plan_v2 import (
            build_record_reset_add_while_continue_plan,
        )

        return build_record_reset_add_while_continue_plan(
            spec, contract, fixture_binding()
        )
    if contract_kind in {
        "record_owner_interior_stats_sequence_state",
        "record_owner_interior_guarded_stats_sequence_state",
    }:
        from validation.tools.replay_call_plan_v2 import (
            build_record_owner_stats_sequence_plan,
        )

        return build_record_owner_stats_sequence_plan(spec, contract, fixture_binding())
    return None


def _validated_scripted_contract(spec: dict[str, Any], kind: str) -> dict[str, Any]:
    from validation.tools import auto_migrate

    validators = {
        "scripted_external_u32_call_bool_out":
            auto_migrate.scripted_external_u32_call_bool_out_replay_contract,
        "scripted_external_record_u32_call_bool_state":
            auto_migrate.scripted_external_record_u32_call_bool_state_replay_contract,
        "scripted_external_record_u32_sequence_do_while_state":
            auto_migrate.scripted_external_record_u32_sequence_do_while_state_replay_contract,
        "scripted_external_u32_call_interior_reset_add_while_continue_state":
            auto_migrate.call_continue_state_replay_contract,
    }
    validator = validators[kind]
    validated = validator(spec, auto_migrate.oracle_fixture_binding(spec))
    if not isinstance(validated, dict):
        raise ValueError("scripted external replay contract is unavailable")
    return validated
