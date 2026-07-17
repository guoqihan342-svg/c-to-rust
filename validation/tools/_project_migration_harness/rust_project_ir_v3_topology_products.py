from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256


def derive_product_topology(
    targets: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    products: dict[str, dict[str, Any]] = {}
    blockers = set()
    non_objects = 0
    for raw_id in sorted(targets):
        entry = targets[raw_id]
        raw = entry["target"]
        if raw.get("kind") == "object":
            continue
        non_objects += 1
        classification = _classify_product(raw, entry["build"])
        if isinstance(classification, str):
            blockers.add(classification)
            continue
        product_kind, rust_kind, crate_types = classification
        identity = {
            "build_ir_semantic_sha256": entry["semantic_sha256"],
            "build_ir_target_id": raw_id,
        }
        products[raw_id] = {
            "raw": raw,
            "build": entry["build"],
            "semantic_sha256": entry["semantic_sha256"],
            "evidence_sha256": entry["evidence_sha256"],
            "package_id": stable_topology_id("package", identity),
            "target_id": stable_topology_id(
                "target", {**identity, "kind": rust_kind},
            ),
            "namespace_id": stable_topology_id("target-namespace", identity),
            "product_kind": product_kind,
            "rust_kind": rust_kind,
            "crate_types": crate_types,
        }
    if non_objects == 0:
        blockers.add("build_ir_object_only")
    return products, sorted(blockers)


def project_input_occurrences(
    target: Mapping[str, Any], products: Mapping[str, Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, Any]],
    object_bindings: Mapping[str, Mapping[str, Any]],
    *, build_ir_artifact_sha256: str, consumer_target_id: str,
) -> list[dict[str, Any]]:
    result = []
    seen_objects = set()
    for index, item in enumerate(target.get("ordered_inputs", [])):
        if not isinstance(item, Mapping) or item.get("ordinal") != index:
            raise ValueError("rust_project_ir_v3_topology_input_occurrence_invalid")
        binding = item.get("binding")
        role = item.get("role")
        if not isinstance(binding, Mapping) or not isinstance(role, str) or not role:
            raise ValueError("rust_project_ir_v3_topology_input_occurrence_invalid")
        dependency = item.get("dependency_target_id")
        if dependency is not None and not isinstance(dependency, str):
            raise ValueError("rust_project_ir_v3_topology_input_occurrence_invalid")
        occurrence = {
            "ordinal": index,
            "occurrence_id": input_occurrence_id(
                build_ir_artifact_sha256, consumer_target_id, index,
            ),
            "role": role,
            "dependency_target_id": None,
            "object_target_id": None,
            "source_unit_id": None,
            "module_id": None,
            "binding_sha256": content_sha256(dict(binding)),
        }
        if dependency in products:
            occurrence["dependency_target_id"] = products[dependency]["target_id"]
        elif dependency in object_bindings:
            seen_objects.add(dependency)
            owner = object_bindings[dependency]
            occurrence.update({
                "object_target_id": dependency,
                "source_unit_id": owner["source_unit_id"],
                "module_id": owner["module_id"],
            })
        elif dependency is None:
            raise ValueError("rust_project_ir_v3_topology_native_input_unsupported")
        elif dependency not in targets:
            raise ValueError("rust_project_ir_v3_topology_input_dependency_unknown")
        elif targets[dependency]["target"].get("kind") == "object":
            raise ValueError("rust_project_ir_v3_topology_object_input_unowned")
        else:
            raise ValueError(
                "rust_project_ir_v3_topology_input_dependency_unrepresentable"
            )
        result.append(occurrence)
    if seen_objects != set(object_bindings):
        raise ValueError("rust_project_ir_v3_topology_object_occurrence_closure_drift")
    _validate_object_order(result, object_bindings)
    return result


def input_occurrence_id(
    build_ir_artifact_sha256: str, consumer_target_id: str, ordinal: int,
) -> str:
    return stable_topology_id("input-occurrence", {
        "build_ir_artifact_sha256": build_ir_artifact_sha256,
        "consumer_target_id": consumer_target_id,
        "ordinal": ordinal,
    })


def _validate_object_order(
    occurrences: list[dict[str, Any]],
    bindings: Mapping[str, Mapping[str, Any]],
) -> None:
    by_module: dict[str, list[tuple[int, str]]] = {}
    expected: dict[str, list[str]] = {}
    seen_objects = set()
    for item in occurrences:
        module_id = item["module_id"]
        if module_id is None:
            continue
        object_id = item["object_target_id"]
        if object_id in seen_objects:
            continue
        seen_objects.add(object_id)
        values = by_module.setdefault(module_id, [])
        values.append((len(values), item["source_unit_id"]))
    for owner in bindings.values():
        module_id = str(owner["module_id"])
        sources = list(owner["module_source_unit_ids"])
        if module_id in expected and expected[module_id] != sources:
            raise ValueError("rust_project_ir_v3_topology_object_owner_conflict")
        expected[module_id] = sources
    if set(by_module) != set(expected):
        raise ValueError("rust_project_ir_v3_topology_object_occurrence_closure_drift")
    for module_id, values in by_module.items():
        ordinals = [ordinal for ordinal, _source in values]
        if (
            [source for _ordinal, source in values] != expected[module_id]
            or ordinals != list(range(ordinals[0], ordinals[0] + len(ordinals)))
        ):
            raise ValueError("rust_project_ir_v3_topology_object_occurrence_order_invalid")


def stable_topology_id(kind: str, value: Any) -> str:
    return f"{kind}-{content_sha256(value)[:24]}"


def _classify_product(
    target: Mapping[str, Any], build: Mapping[str, Any],
) -> tuple[str, str, list[str]] | str:
    kind = target.get("kind")
    if kind == "archive":
        return "static-library", "lib", ["rlib", "staticlib"]
    if kind != "link":
        return "build_ir_product_kind_unknown"
    arguments = target.get("ordered_link_arguments", [])
    if any(item in {"-r", "--relocatable"} for item in arguments):
        return "build_ir_relocatable_product_unsupported"
    if any(
        item in {"-shared", "--shared"} or item.casefold() == "/dll"
        for item in arguments
    ):
        return "shared-library", "cdylib", ["cdylib"]
    toolchain_id = target.get("toolchain_id")
    toolchain = next((
        item for item in build.get("toolchains", [])
        if isinstance(item, Mapping) and item.get("toolchain_id") == toolchain_id
    ), None)
    if toolchain is None or toolchain.get("role") != "linker-driver":
        return "build_ir_product_kind_unknown"
    return "executable", "bin", ["bin"]


__all__ = [
    "derive_product_topology", "input_occurrence_id", "project_input_occurrences",
    "stable_topology_id",
]
