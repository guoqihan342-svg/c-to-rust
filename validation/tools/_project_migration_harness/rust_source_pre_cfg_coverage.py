from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


_SIGNATURE_ITEMS = {
    "function", "foreign-function", "impl-function", "trait-function",
}
_TYPE_ITEMS = {
    "enum", "foreign-type", "impl-type", "struct", "trait", "trait-alias",
    "trait-type", "type-alias", "union",
}
_GLOBAL_ITEMS = {"const", "foreign-static", "impl-const", "static", "trait-const"}


def validate_rust_source_pre_cfg_coverage(value: Mapping[str, Any]) -> None:
    item_kinds = {item["item_id"]: item["kind"] for item in value["items"]}
    _exact_fact_coverage(
        value["signatures"],
        {item_id for item_id, kind in item_kinds.items() if kind in _SIGNATURE_ITEMS},
        "signature",
    )
    _exact_fact_coverage(
        value["types"],
        {item_id for item_id, kind in item_kinds.items() if kind in _TYPE_ITEMS},
        "type",
    )
    _exact_fact_coverage(
        value["globals"],
        {item_id for item_id, kind in item_kinds.items() if kind in _GLOBAL_ITEMS},
        "global",
    )
    initialization_ids = [item["item_id"] for item in value["initialization"]]
    if len(initialization_ids) != len(set(initialization_ids)):
        _fail("rust_source_pre_cfg_initialization_coverage_invalid")
    required_initialization = {
        item["item_id"] for item in value["globals"] if item["has_initializer"]
    }
    actual_initialization = set(initialization_ids)
    if not required_initialization <= actual_initialization:
        _fail("rust_source_pre_cfg_initialization_coverage_invalid")
    for record in value["initialization"]:
        item_kind = item_kinds.get(record["item_id"])
        if record["item_id"] not in required_initialization and not (
            item_kind == "impl" and record["kind"] == "drop-impl"
        ):
            _fail("rust_source_pre_cfg_initialization_coverage_invalid")
    module_item_paths = Counter(
        item["item_path"] for item in value["items"] if item["kind"] == "module"
    )
    module_paths = Counter(
        item["module_path"] for item in value["modules"] if item["kind"] != "root"
    )
    if module_item_paths != module_paths:
        _fail("rust_source_pre_cfg_module_coverage_invalid")


def _exact_fact_coverage(
    records: list[Mapping[str, Any]], expected: set[str], label: str,
) -> None:
    actual = [item["item_id"] for item in records]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        _fail(f"rust_source_pre_cfg_{label}_coverage_invalid")


def _fail(code: str) -> None:
    raise ValueError(code)


__all__ = ["validate_rust_source_pre_cfg_coverage"]
