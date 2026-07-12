from __future__ import annotations

import json
from typing import Any


def render_boundary_contract(context_pack: dict[str, Any]) -> str:
    function_name = context_pack.get("function_name")
    c_payload = boundary_payload(context_pack.get("c_boundary"))
    rust_payload = boundary_payload(context_pack.get("rust_boundary"))
    signatures = c_payload.get("signatures")
    selected_signature = None
    if isinstance(signatures, list):
        selected_signature = next(
            (
                signature
                for signature in signatures
                if isinstance(signature, dict)
                and signature.get("function") == function_name
            ),
            None,
        )
    contract = {
        "function_name": function_name,
        "c_signature": selected_signature,
        "rust_public_api": rust_payload.get("public_api"),
        "raw_pointer_policy": rust_payload.get("raw_pointer_policy"),
        "unsafe_policy": rust_payload.get("unsafe_policy"),
    }
    replay_contract = context_pack.get("replay_api_contract")
    call_plan = replay_contract.get("call_plan") if isinstance(replay_contract, dict) else None
    if isinstance(call_plan, dict):
        contract["replay_call_plan_binding"] = {
            "api_name": call_plan.get("api_name"),
            "plan_sha256": call_plan.get("plan_sha256"),
        }
    return json.dumps(contract, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def render_replay_api_contract(context_pack: dict[str, Any]) -> str:
    contract = context_pack.get("replay_api_contract")
    if isinstance(contract, dict):
        contract = dict(contract)
        source = contract.get("source")
        if isinstance(source, dict):
            source = dict(source)
            source["content"] = "<withheld-oracle-bearing-replay-source>"
            contract["source"] = source
        required_api = contract.get("required_candidate_api")
        if isinstance(required_api, dict):
            contract["required_candidate_api"] = _required_candidate_api_placeholder(required_api)
        contract = _withhold_oracle_values(contract)
    return json.dumps(contract, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def render_required_candidate_api(context_pack: dict[str, Any]) -> str:
    contract = context_pack.get("replay_api_contract")
    required_api = contract.get("required_candidate_api") if isinstance(contract, dict) else None
    return json.dumps(required_api, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def render_candidate_source_rule(context_pack: dict[str, Any]) -> str:
    contract = context_pack.get("replay_api_contract")
    required_api = contract.get("required_candidate_api") if isinstance(contract, dict) else None
    source_contract = (
        required_api.get("candidate_source_contract")
        if isinstance(required_api, dict)
        else None
    )
    if not isinstance(source_contract, dict):
        return ""
    return (
        "Candidate source assembly: candidate.source must be self-contained. "
        "When supporting_types_source is non-empty, include it exactly once before the required "
        "function. The harness injects no missing types. Treat those declarations as the complete "
        "closed type model; do not replace them with alternate FFI, extern, or opaque types."
    )


def render_replay_behavior_rule(context_pack: dict[str, Any]) -> str:
    contract = context_pack.get("replay_api_contract")
    if not isinstance(contract, dict) or contract.get("status") != "bound":
        return ""
    return (
        "Required replay discipline: concrete replay assertions and oracle values are intentionally "
        "withheld from model input. Implement behavior only from the bound C source, compile context, "
        "structured call plan, and source-backed external-callee definitions. Do not infer or invent "
        "expected values, branch on project/function/case identifiers, or implement fixture lookup tables."
    )


def render_external_callee_source_rule(context_pack: dict[str, Any]) -> str:
    context = context_pack.get("external_callee_source_context")
    if not isinstance(context, dict) or not context.get("blocks"):
        return ""
    behavior = context.get("source_backed_behavior")
    behavior_contract = (
        json.dumps(behavior, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if isinstance(behavior, dict) and behavior.get("rules")
        else "null"
    )
    return (
        f"Source-backed external-callee behavior contract: {behavior_contract}\n"
        "Source-backed external callees: ContextPack.external_callee_source_context.blocks contains "
        "the hash-bound C definitions and dependencies from the declared source root. Implement every "
        "applicable rule in the behavior contract above. Resolved constants may come only from those "
        "source rules. They are candidate context only and keep semantics_verified=false; they cannot "
        "replace oracle, replay, diff, or final verification."
    )


def context_without_replay_source(context_pack: dict[str, Any]) -> dict[str, Any]:
    context = dict(context_pack)
    contract = context_pack.get("replay_api_contract")
    if not isinstance(contract, dict):
        return context
    contract_copy = dict(contract)
    source = contract.get("source")
    if isinstance(source, dict):
        source_copy = dict(source)
        source_copy["content"] = "<presented-in-required-replay-api-contract>"
        contract_copy["source"] = source_copy
    call_plan = contract.get("call_plan")
    if isinstance(call_plan, dict):
        contract_copy["call_plan"] = {
            "status": "presented-in-required-replay-api-contract",
            "api_name": call_plan.get("api_name"),
            "plan_sha256": call_plan.get("plan_sha256"),
        }
    required_api = contract.get("required_candidate_api")
    if isinstance(required_api, dict):
        contract_copy["required_candidate_api"] = _required_candidate_api_placeholder(required_api)
    context["replay_api_contract"] = contract_copy
    callee_context = context_pack.get("external_callee_source_context")
    if isinstance(callee_context, dict):
        callee_context_copy = dict(callee_context)
        behavior = callee_context.get("source_backed_behavior")
        if isinstance(behavior, dict):
            callee_context_copy["source_backed_behavior"] = {
                "status": "presented-in-source-backed-external-callee-behavior-contract",
                "behavior_sha256": behavior.get("behavior_sha256"),
            }
        context["external_callee_source_context"] = callee_context_copy
    return _withhold_oracle_values(context, preserve_source_backed=True)


def _withhold_oracle_values(value: Any, *, preserve_source_backed: bool = False) -> Any:
    withheld_keys = {
        "actual",
        "expected",
        "expected_outputs",
        "first_mismatch",
        "observed",
    }
    if isinstance(value, dict):
        projected = {}
        for key, item in value.items():
            if preserve_source_backed and key == "external_callee_source_context":
                projected[key] = item
            elif key in withheld_keys:
                projected[key] = "<withheld-oracle-value>"
            else:
                projected[key] = _withhold_oracle_values(item)
        return projected
    if isinstance(value, list):
        return [_withhold_oracle_values(item) for item in value]
    return value


def _required_candidate_api_placeholder(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "presented-in-required-candidate-api",
        "api_name": value.get("api_name"),
        "plan_sha256": value.get("plan_sha256"),
        "contract_sha256": value.get("contract_sha256"),
    }


def boundary_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else value


__all__ = [
    "context_without_replay_source",
    "render_boundary_contract",
    "render_candidate_source_rule",
    "render_external_callee_source_rule",
    "render_replay_behavior_rule",
    "render_replay_api_contract",
    "render_required_candidate_api",
]
