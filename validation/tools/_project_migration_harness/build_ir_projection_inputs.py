from __future__ import annotations

import copy
from typing import Any

from .build_ir import list_value, normalize_binding


def source_inputs(
    units: list[dict[str, Any]], targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    values = [unit["source"] for unit in units]
    values.extend(
        item["binding"]
        for target in targets
        for item in target["ordered_inputs"]
        if item["role"] == "source" and item["binding"]["materialized"]
    )
    return unique_bindings(values)


def generated_inputs(
    closure: dict[str, Any] | Any, targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for value in list_value(closure.get("generated_include_roots")):
        records.append({
            "binding": normalize_binding(value, materialized=True),
            "role": "include-root",
            "producer_target_id": None,
            "consumer_target_ids": [],
            "provenance": {"raw_fact_role": "generated-build-closure"},
        })
    for target in targets:
        for value in target["outputs"]:
            records.append({
                "binding": copy.deepcopy(value),
                "role": "target-output",
                "producer_target_id": target["target_id"],
                "consumer_target_ids": [],
                "provenance": {
                    "raw_fact_role": target["provenance"]["raw_fact_role"],
                },
            })
        for item in target["ordered_inputs"]:
            if item["role"] == "generated-source":
                records.append({
                    "binding": copy.deepcopy(item["binding"]),
                    "role": item["role"],
                    "producer_target_id": item["dependency_target_id"],
                    "consumer_target_ids": [target["target_id"]],
                    "provenance": {"raw_fact_role": "generated-build-closure"},
                })
        for item in list_value(target.get("declared_inputs")):
            if not isinstance(item, dict) or item.get("role") != "generated-source":
                continue
            records.append({
                "binding": copy.deepcopy(item["binding"]),
                "role": item["role"],
                "producer_target_id": item.get("dependency_target_id"),
                "consumer_target_ids": [target["target_id"]],
                "provenance": {"raw_fact_role": "generated-build-closure"},
            })
    keyed = {item["binding"]["path"]: item for item in records}
    return [keyed[path] for path in sorted(keyed)]


def unique_bindings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed: dict[str, dict[str, Any]] = {}
    for value in values:
        path = str(value["path"])
        if path in keyed and keyed[path] != value:
            raise ValueError("build_ir_source_binding_conflict")
        keyed[path] = copy.deepcopy(value)
    return [keyed[path] for path in sorted(keyed)]


__all__ = ["generated_inputs", "source_inputs", "unique_bindings"]
