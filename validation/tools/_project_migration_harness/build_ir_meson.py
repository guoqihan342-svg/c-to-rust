from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

from .build_ir import (
    list_value,
    normalize_binding,
    stable_build_id,
    string_list,
    target_record,
)


_CANONICAL_TARGET_KINDS = {
    "executable": "link",
    "shared library": "link",
    "shared module": "link",
    "static library": "archive",
}


def merge_meson_targets(
    closure: Mapping[str, Any],
    targets: list[dict[str, Any]],
    owners: dict[str, str],
    external: list[dict[str, Any]],
) -> None:
    meson = _meson_report(closure)
    if meson is None:
        return
    by_id = {item["target_id"]: item for item in targets}
    meson_ids: dict[str, str] = {}
    raw_targets = [
        item for item in list_value(meson.get("targets"))
        if isinstance(item, Mapping)
    ]
    for raw in raw_targets:
        target_id = _merge_target(raw, targets, by_id, owners)
        if target_id is not None:
            meson_ids[str(raw.get("id"))] = target_id
    for raw in raw_targets:
        target_id = meson_ids.get(str(raw.get("id")))
        if target_id is None:
            continue
        target = by_id[target_id]
        _merge_source_evidence(raw, target, owners)
        _merge_dependencies(raw, target, meson_ids)
        _merge_external_dependencies(raw, target_id, external)


def _meson_report(closure: Mapping[str, Any]) -> Mapping[str, Any] | None:
    generated = closure.get("generated_stage_facts")
    meson = (
        generated.get("meson_introspection")
        if isinstance(generated, Mapping) else None
    )
    if not isinstance(meson, Mapping) or meson.get("status") != "ready":
        return None
    return meson


def _merge_target(
    raw: Mapping[str, Any],
    targets: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    owners: dict[str, str],
) -> str | None:
    outputs = [
        normalize_binding(value, materialized=value.get("materialized", True))
        for value in list_value(raw.get("outputs"))
        if isinstance(value, Mapping)
    ]
    if not outputs:
        return None
    matches = {owners[item["path"]] for item in outputs if item["path"] in owners}
    if len(matches) > 1:
        raise ValueError("build_ir_meson_target_ambiguous")
    kind = _canonical_kind(raw.get("type"))
    target_id = next(iter(matches), stable_build_id(
        "target", {"kind": kind, "outputs": [item["path"] for item in outputs]},
    ))
    if target_id in by_id:
        target = by_id[target_id]
        if target.get("kind") != kind:
            raise ValueError("build_ir_meson_target_kind_mismatch")
    else:
        target = target_record(
            target_id, outputs[0]["path"], kind, outputs,
            [], [], [], [], {"raw_fact_role": "generated-build-closure"},
        )
        targets.append(target)
        by_id[target_id] = target
        for output in outputs:
            if output["path"] in owners:
                raise ValueError("build_ir_target_output_duplicate")
            owners[output["path"]] = target_id
    target["provenance"].update({
        "meson_target_id": raw.get("id"),
        "meson_target_type": raw.get("type"),
    })
    return target_id


def _canonical_kind(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("build_ir_meson_target_kind_invalid")
    return _CANONICAL_TARGET_KINDS.get(value, value)


def _merge_source_evidence(
    raw: Mapping[str, Any],
    target: dict[str, Any],
    owners: Mapping[str, str],
) -> None:
    groups = [
        item for item in list_value(raw.get("source_groups"))
        if isinstance(item, Mapping)
    ]
    target["provenance"]["meson_source_groups"] = [
        {
            key: copy.deepcopy(group[key])
            for key in (
                "kind", "language", "machine", "compiler_summary",
                "linker_summary", "parameters_summary",
            )
            if key in group
        }
        for group in groups
    ]
    existing = {
        item["binding"]["path"] for item in target["ordered_inputs"]
    }
    for group in groups:
        if not target["ordered_inputs"]:
            _merge_source_inputs(group, target, owners, existing)
        _merge_generated_inputs(group, target, owners, existing)


def _merge_source_inputs(
    group: Mapping[str, Any],
    target: dict[str, Any],
    owners: Mapping[str, str],
    existing: set[str],
) -> None:
    for source in list_value(group.get("sources")):
        _append_input(source, "source", target, owners, existing)


def _merge_generated_inputs(
    group: Mapping[str, Any],
    target: dict[str, Any],
    owners: Mapping[str, str],
    existing: set[str],
) -> None:
    declared = target.get("declared_inputs", [])
    declared_paths = {item["binding"]["path"] for item in declared}
    for source in list_value(group.get("generated_sources")):
        if not isinstance(source, Mapping):
            continue
        binding = normalize_binding(
            source, materialized=source.get("materialized", True),
        )
        if binding["path"] in existing or binding["path"] in declared_paths:
            continue
        dependency = owners.get(binding["path"])
        if dependency == target["target_id"]:
            dependency = None
        target.setdefault("declared_inputs", declared).append({
            "ordinal": len(declared),
            "role": "generated-source",
            "binding": binding,
            "dependency_target_id": dependency,
        })
        declared_paths.add(binding["path"])
        if dependency and dependency not in target["dependency_target_ids"]:
            target["dependency_target_ids"].append(dependency)


def _append_input(
    source: Any,
    role: str,
    target: dict[str, Any],
    owners: Mapping[str, str],
    existing: set[str],
) -> None:
    if not isinstance(source, Mapping):
        return
    binding = normalize_binding(
        source, materialized=source.get("materialized", True),
    )
    if binding["path"] in existing:
        return
    dependency = owners.get(binding["path"])
    if dependency == target["target_id"]:
        dependency = None
    target["ordered_inputs"].append({
        "ordinal": len(target["ordered_inputs"]),
        "role": role,
        "binding": binding,
        "dependency_target_id": dependency,
    })
    existing.add(binding["path"])
    if dependency and dependency not in target["dependency_target_ids"]:
        target["dependency_target_ids"].append(dependency)


def _merge_dependencies(
    raw: Mapping[str, Any],
    target: dict[str, Any],
    meson_ids: Mapping[str, str],
) -> None:
    for dependency in string_list(raw.get("target_dependency_ids")):
        resolved = meson_ids.get(dependency)
        if resolved and resolved not in target["dependency_target_ids"]:
            target["dependency_target_ids"].append(resolved)


def _merge_external_dependencies(
    raw: Mapping[str, Any],
    target_id: str,
    external: list[dict[str, Any]],
) -> None:
    for name in string_list(raw.get("external_dependency_names")):
        external.append({
            "dependency_id": stable_build_id(
                "external", {"target": target_id, "name": name},
            ),
            "kind": "declared-external-dependency",
            "name": name,
            "consumer_target_ids": [target_id],
            "ordinal": None,
            "provenance": {"raw_fact_role": "generated-build-closure"},
        })


__all__ = ["merge_meson_targets"]
