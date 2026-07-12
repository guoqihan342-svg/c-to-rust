from __future__ import annotations

from typing import Any


PROMPT_SCOPE_ORDER = (
    "slice_spec",
    "source_spans",
    "type_map_excerpt",
    "cfg_excerpt",
    "pointer_graph_excerpt",
    "root_cause_summary",
    "direct_caller_callee_facts",
)

ARTIFACT_SCOPE_SUFFIXES = {
    "-type-map.json": "type_map_excerpt",
    "-cfg.json": "cfg_excerpt",
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


def prompt_scope_for_context(context_pack: dict[str, Any]) -> list[str]:
    scopes = {"slice_spec", "source_spans"}
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
                        scopes.add(scope)
            failure_summary = artifact.get("failure_summary")
            if failure_summary_has_facts(failure_summary):
                scopes.add("root_cause_summary")
    if has_direct_caller_callee_facts(context_pack.get("c_boundary")):
        scopes.add("direct_caller_callee_facts")
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


def failure_summary_has_facts(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict) or not value_has_facts(
            item.get("value"), scalar_is_fact=True
        ):
            continue
        path = str(item.get("path", "")).lower()
        if path.endswith(".status"):
            status = str(item["value"]).lower()
            if any(marker in status for marker in FAILURE_STATUS_MARKERS):
                return True
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
