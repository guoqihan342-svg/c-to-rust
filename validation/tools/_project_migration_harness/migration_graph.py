"""Stable SCC migration DAGs derived only from indexed structural facts."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


def build_migration_graph(c_index: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve visible symbols, condense calls with Tarjan SCCs, and classify units."""
    nodes = _objects(c_index.get("nodes"), "c_index.nodes")
    globals_ = _objects(c_index.get("globals", []), "c_index.globals")
    by_id = {str(node.get("node_id")): node for node in nodes}
    if "None" in by_id or len(by_id) != len(nodes):
        raise ValueError("c_index.nodes must have unique node_id values")
    functions = _by_symbol(nodes)
    global_symbols = _by_symbol(globals_, key="symbol")
    ambiguous_definition_nodes = {
        str(item["node_id"])
        for definitions in functions.values()
        if len([item for item in definitions if item.get("linkage") == "external"]) > 1
        for item in definitions
        if item.get("linkage") == "external"
    }
    bindings: list[dict[str, Any]] = []
    edges: set[tuple[str, str]] = set()
    external_calls: list[dict[str, Any]] = []
    global_refs: list[dict[str, Any]] = []
    for node_id in sorted(by_id):
        node = by_id[node_id]
        resolved_calls: list[dict[str, str]] = []
        node_external: list[dict[str, Any]] = []
        for symbol in _strings(node.get("direct_calls", []), "direct_calls"):
            candidates = _visible_definitions(node, functions.get(symbol, []), "node_id")
            if len(candidates) == 1:
                callee = str(candidates[0]["node_id"])
                edges.add((node_id, callee))
                resolved_calls.append({"symbol": symbol, "callee_node_id": callee})
            else:
                status = "unresolved_external" if not candidates else "ambiguous_external"
                record = {"caller_node_id": node_id, "symbol": symbol, "status": status,
                          "candidate_node_ids": sorted(str(item["node_id"]) for item in candidates)}
                node_external.append(record)
                external_calls.append(record)
        node_globals: list[dict[str, Any]] = []
        for symbol in _strings(node.get("referenced_globals", []), "referenced_globals"):
            candidates = _visible_definitions(node, global_symbols.get(symbol, []), "global_id")
            declarations = [item for item in global_symbols.get(symbol, [])
                            if item.get("linkage") == "external_declaration"]
            if len(candidates) == 1:
                record = {"node_id": node_id, "symbol": symbol, "status": "resolved",
                          "global_ids": [str(candidates[0]["global_id"])]}
            else:
                status = "ambiguous_external" if candidates else "unresolved_external"
                possible = candidates or declarations
                record = {"node_id": node_id, "symbol": symbol, "status": status,
                          "global_ids": sorted(str(item["global_id"]) for item in possible)}
            node_globals.append(record)
            global_refs.append(record)
        bindings.append({"node_id": node_id,
                         "resolved_calls": sorted(resolved_calls, key=_call_key),
                         "external_calls": sorted(node_external, key=_external_key),
                         "global_references": sorted(node_globals, key=_global_key)})

    shared_users: dict[str, set[str]] = defaultdict(set)
    for binding in bindings:
        for reference in binding["global_references"]:
            if reference["status"] == "resolved":
                for global_id in reference["global_ids"]:
                    shared_users[global_id].add(binding["node_id"])
    shared_state_edges: set[tuple[str, str]] = set()
    for users in shared_users.values():
        ordered = sorted(users)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                shared_state_edges.add((left, right))

    adjacency = {node_id: set() for node_id in by_id}
    for caller, callee in edges:
        adjacency[caller].add(callee)
    for left, right in shared_state_edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    call_components = _tarjan({
        node_id: {callee for caller, callee in edges if caller == node_id}
        for node_id in by_id
    })
    recursive_nodes = {
        node_id for component in call_components
        if len(component) > 1 or any((node_id, node_id) in edges for node_id in component)
        for node_id in component
    }
    components = _tarjan(adjacency)
    component_of: dict[str, str] = {}
    component_nodes: dict[str, list[str]] = {}
    for member_ids in components:
        scc_id = _stable_id("scc", member_ids)
        component_nodes[scc_id] = member_ids
        component_of.update({node_id: scc_id for node_id in member_ids})
    dag_edges = {(component_of[caller], component_of[callee]) for caller, callee in edges
                 if component_of[caller] != component_of[callee]}
    dependencies = {scc_id: set() for scc_id in component_nodes}
    for caller_scc, callee_scc in dag_edges:
        dependencies[caller_scc].add(callee_scc)

    binding_by_node = {item["node_id"]: item for item in bindings}
    blocker_units = _blocker_units(c_index)
    sccs: list[dict[str, Any]] = []
    for scc_id in sorted(component_nodes):
        member_ids = component_nodes[scc_id]
        boundary: set[str] = set()
        context: set[str] = set()
        for node_id in member_ids:
            binding = binding_by_node[node_id]
            if binding["external_calls"]:
                boundary.add("unresolved_or_ambiguous_call")
            if node_id in ambiguous_definition_nodes:
                boundary.add("ambiguous_external_definition")
            if any(item["status"] != "resolved" for item in binding["global_references"]):
                boundary.add("unresolved_or_ambiguous_global")
            if str(by_id[node_id].get("unit_id")) in blocker_units:
                boundary.add("parser_blocker")
            if any(item["status"] == "resolved" for item in binding["global_references"]):
                context.add("global_state_context")
        if any(node_id in recursive_nodes for node_id in member_ids):
            context.add("recursive_call_component")
        if any(left in member_ids and right in member_ids for left, right in shared_state_edges):
            context.add("shared_global_state")
        classification = "boundary_required" if boundary else "context_group" if context else "independent"
        reasons = sorted(boundary if boundary else context if context else {"acyclic_closed_function"})
        sccs.append({"scc_id": scc_id, "node_ids": member_ids, "classification": classification,
                     "structural_reasons": reasons,
                     "dependency_scc_ids": sorted(dependencies[scc_id])})

    waves = _stable_waves(dependencies, component_nodes)
    parser = c_index.get("parser", {})
    limitations = list(parser.get("limitations", [])) if isinstance(parser, Mapping) else []
    blockers = list(parser.get("blockers", [])) if isinstance(parser, Mapping) else []
    return {
        "schema_version": 1,
        "status": "ready_with_boundaries" if blockers else "ready",
        "nodes": bindings,
        "resolved_call_edges": [
            {"caller_node_id": caller, "callee_node_id": callee}
            for caller, callee in sorted(edges)
        ],
        "shared_state_edges": [
            {"left_node_id": left, "right_node_id": right}
            for left, right in sorted(shared_state_edges)
        ],
        "external_calls": sorted(external_calls, key=_external_key),
        "global_references": sorted(global_refs, key=_global_key),
        "sccs": sccs,
        "dag_edges": [{"dependent_scc_id": caller, "dependency_scc_id": callee}
                       for caller, callee in sorted(dag_edges)],
        "waves": waves,
        "parser_limitations": limitations,
        "blockers": blockers,
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }


def _objects(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} entries must be objects")
    return list(value)


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} entries must be non-empty strings")
    return sorted(set(value))


def _by_symbol(items: Sequence[Mapping[str, Any]], key: str = "symbol") -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        symbol = item.get(key)
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(f"indexed {key} must be a non-empty string")
        result.setdefault(symbol, []).append(item)
    return result


def _visible_definitions(caller: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]],
                         id_key: str) -> list[Mapping[str, Any]]:
    local = [item for item in candidates if item.get("linkage") == "internal"
             and item.get("unit_id") == caller.get("unit_id")]
    visible = local or [item for item in candidates if item.get("linkage") == "external"]
    return sorted(visible, key=lambda item: str(item.get(id_key)))


def _tarjan(adjacency: Mapping[str, set[str]]) -> list[list[str]]:
    """Iterative Tarjan traversal avoids recursion limits on large projects."""
    counter = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    for root in sorted(adjacency):
        if root in indices:
            continue
        frames: list[list[Any]] = [[root, iter(sorted(adjacency[root])), None, False]]
        while frames:
            node, neighbors, parent, entered = frames[-1]
            if not entered:
                indices[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
                frames[-1][3] = True
            try:
                neighbor = next(neighbors)
                if neighbor not in indices:
                    frames.append([neighbor, iter(sorted(adjacency[neighbor])), node, False])
                elif neighbor in on_stack:
                    low[node] = min(low[node], indices[neighbor])
            except StopIteration:
                frames.pop()
                if parent is not None:
                    low[parent] = min(low[parent], low[node])
                if low[node] == indices[node]:
                    component: list[str] = []
                    while True:
                        member = stack.pop()
                        on_stack.remove(member)
                        component.append(member)
                        if member == node:
                            break
                    components.append(sorted(component))
    return sorted(components)


def _stable_waves(dependencies: Mapping[str, set[str]],
                  members: Mapping[str, list[str]]) -> list[dict[str, Any]]:
    remaining = set(dependencies)
    completed: set[str] = set()
    waves: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(item for item in remaining if dependencies[item] <= completed)
        if not ready:
            raise ValueError("condensed SCC graph must be acyclic")
        waves.append({"wave_index": len(waves), "scc_ids": ready,
                      "node_ids": sorted(node for item in ready for node in members[item])})
        completed.update(ready)
        remaining.difference_update(ready)
    return waves


def _blocker_units(c_index: Mapping[str, Any]) -> set[str]:
    parser = c_index.get("parser", {})
    if not isinstance(parser, Mapping):
        return set()
    blockers = parser.get("blockers", [])
    return {str(item.get("unit_id")) for item in blockers if isinstance(item, Mapping)}


def _stable_id(kind: str, values: Sequence[str]) -> str:
    encoded = json.dumps(sorted(values), separators=(",", ":")).encode("ascii")
    return f"{kind}-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _call_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return str(item["symbol"]), str(item["callee_node_id"])


def _external_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(item["caller_node_id"]), str(item["symbol"]), str(item["status"])


def _global_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(item["node_id"]), str(item["symbol"]), str(item["status"])


build_migration_dag = build_migration_graph

__all__ = ["build_migration_dag", "build_migration_graph"]
