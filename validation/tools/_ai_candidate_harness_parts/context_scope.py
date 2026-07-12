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


def prompt_scope_for_context(context_pack: dict[str, Any]) -> list[str]:
    scopes = {"slice_spec", "source_spans"}
    artifacts = context_pack.get("deterministic_artifacts")
    if isinstance(artifacts, dict):
        for name, artifact in artifacts.items():
            if not isinstance(name, str) or not isinstance(artifact, dict):
                continue
            if artifact.get("status") == "loaded" and "context_excerpt" in artifact:
                for suffix, scope in ARTIFACT_SCOPE_SUFFIXES.items():
                    if name.endswith(suffix):
                        scopes.add(scope)
            failure_summary = artifact.get("failure_summary")
            if isinstance(failure_summary, list) and failure_summary:
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
        isinstance(item, dict) for item in external_callees
    ):
        return True
    signatures = payload.get("signatures")
    if isinstance(signatures, list) and any(
        isinstance(item, dict) and item.get("role") == "external_direct_callee"
        for item in signatures
    ):
        return True
    dependencies = payload.get("direct_dependencies")
    if isinstance(dependencies, list) and any(
        isinstance(item, dict) and item.get("kind") == "callee"
        for item in dependencies
    ):
        return True
    call_contract = payload.get("call_expression_contract")
    return isinstance(call_contract, dict) and bool(call_contract)


__all__ = ["prompt_scope_for_context"]
