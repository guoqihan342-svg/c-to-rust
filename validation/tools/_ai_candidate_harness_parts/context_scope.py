from __future__ import annotations

from typing import Any

from .context_typed_ir import typed_ir_summary_is_valid


PROMPT_SCOPE_ORDER = (
    "slice_spec",
    "source_spans",
    "generated_replay_api_contract",
    "type_map_excerpt",
    "cfg_excerpt",
    "typed_ir_excerpt",
    "pointer_graph_excerpt",
    "root_cause_summary",
    "direct_caller_callee_facts",
    "external_callee_source_blocks",
)

ARTIFACT_SCOPE_SUFFIXES = {
    "-type-map.json": "type_map_excerpt",
    "-cfg.json": "cfg_excerpt",
    "-clang-lowering-report.json": "typed_ir_excerpt",
    "-pointer-graph.json": "pointer_graph_excerpt",
}

FAILURE_STATUS_MARKERS = (
    "blocked",
    "error",
    "fail",
    "invalid",
    "reject",
    "unsupported",
)
SUCCESS_STATUS_MARKERS = ("ok", "pass", "ready", "success")


def prompt_scope_for_context(context_pack: dict[str, Any]) -> list[str]:
    scopes = {"slice_spec", "source_spans"}
    replay_contract = context_pack.get("replay_api_contract")
    if (
        isinstance(replay_contract, dict)
        and replay_contract.get("status") == "bound"
        and isinstance(replay_contract.get("source"), dict)
        and value_has_facts(replay_contract["source"].get("content"))
    ):
        scopes.add("generated_replay_api_contract")
    artifacts = context_pack.get("deterministic_artifacts")
    if isinstance(artifacts, dict):
        for name, artifact in artifacts.items():
            if not isinstance(name, str) or not isinstance(artifact, dict):
                continue
            if artifact.get("status") == "loaded" and value_has_facts(
                artifact.get("context_excerpt")
            ):
                for suffix, scope in ARTIFACT_SCOPE_SUFFIXES.items():
                    if name.endswith(suffix):
                        if scope != "typed_ir_excerpt" or artifact_has_valid_typed_ir(artifact):
                            scopes.add(scope)
            failure_summary = artifact.get("failure_summary")
            if failure_summary_has_facts(failure_summary):
                scopes.add("root_cause_summary")
    if has_direct_caller_callee_facts(context_pack.get("c_boundary")):
        scopes.add("direct_caller_callee_facts")
    callee_context = context_pack.get("external_callee_source_context")
    if (
        isinstance(callee_context, dict)
        and callee_context.get("status") in {"bound", "partial"}
        and value_has_facts(callee_context.get("blocks"))
    ):
        scopes.add("external_callee_source_blocks")
    return [scope for scope in PROMPT_SCOPE_ORDER if scope in scopes]


def has_direct_caller_callee_facts(c_boundary: Any) -> bool:
    if not isinstance(c_boundary, dict):
        return False
    payload = c_boundary.get("payload")
    if not isinstance(payload, dict):
        return False
    external_callees = payload.get("external_direct_callees")
    if isinstance(external_callees, list) and any(
        isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and bool(item["name"].strip())
        for item in external_callees
    ):
        return True
    signatures = payload.get("signatures")
    if isinstance(signatures, list) and any(
        isinstance(item, dict) and item.get("role") == "external_direct_callee"
        and isinstance(item.get("function"), str)
        and bool(item["function"].strip())
        for item in signatures
    ):
        return True
    dependencies = payload.get("direct_dependencies")
    if isinstance(dependencies, list) and any(
        isinstance(item, dict) and item.get("kind") == "callee"
        and isinstance(item.get("name"), str)
        and bool(item["name"].strip())
        for item in dependencies
    ):
        return True
    call_contract = payload.get("call_expression_contract")
    return isinstance(call_contract, dict) and any(
        key in call_contract and value_has_facts(call_contract[key], scalar_is_fact=True)
        for key in ("callee_scope", "contexts", "direct_call_only", "unsupported")
    )


def artifact_has_valid_typed_ir(artifact: dict[str, Any]) -> bool:
    excerpt = artifact.get("context_excerpt")
    lowering = excerpt.get("lowering_report") if isinstance(excerpt, dict) else None
    summary = lowering.get("function_ir_summary") if isinstance(lowering, dict) else None
    return typed_ir_summary_is_valid(summary)


def failure_summary_has_facts(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    status_values = [
        str(item.get("value", "")).lower()
        for item in value
        if isinstance(item, dict) and str(item.get("path", "")).lower().endswith(".status")
    ]
    if any(
        any(marker in status for marker in FAILURE_STATUS_MARKERS)
        for status in status_values
    ):
        return True
    successful = bool(status_values) and all(
        any(marker in status for marker in SUCCESS_STATUS_MARKERS)
        for status in status_values
    )
    for item in value:
        if not isinstance(item, dict) or not value_has_facts(
            item.get("value"), scalar_is_fact=True
        ):
            continue
        path = str(item.get("path", "")).lower()
        if path.endswith(".status"):
            continue
        if successful and path.rsplit(".", 1)[-1] in {"diagnostic", "diagnostics"}:
            continue
        return True
    return False


def value_has_facts(value: Any, *, scalar_is_fact: bool = False) -> bool:
    if isinstance(value, dict):
        if value.get("status") == "omitted_too_large":
            return False
        return any(value_has_facts(item, scalar_is_fact=True) for item in value.values())
    if isinstance(value, list):
        return any(value_has_facts(item, scalar_is_fact=True) for item in value)
    if isinstance(value, str):
        return bool(value.strip())
    if value is None:
        return False
    return scalar_is_fact


__all__ = ["prompt_scope_for_context", "value_has_facts"]
