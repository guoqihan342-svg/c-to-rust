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
) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(target.get("ordered_inputs", [])):
        if not isinstance(item, Mapping) or item.get("ordinal") != index:
            raise ValueError("rust_project_ir_v3_topology_input_occurrence_invalid")
        binding = item.get("binding")
        role = item.get("role")
        if not isinstance(binding, Mapping) or not isinstance(role, str) or not role:
            raise ValueError("rust_project_ir_v3_topology_input_occurrence_invalid")
        dependency = item.get("dependency_target_id")
        result.append({
            "ordinal": index,
            "role": role,
            "dependency_target_id": (
                products[dependency]["target_id"] if dependency in products else None
            ),
            "binding_sha256": content_sha256(dict(binding)),
        })
    return result


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
    "derive_product_topology", "project_input_occurrences", "stable_topology_id",
]
