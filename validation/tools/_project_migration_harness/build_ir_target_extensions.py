from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .build_ir import validate_materialized_binding


def validate_target_extensions(target: Mapping[str, Any]) -> None:
    _validate_archive_semantics(target)
    _validate_declared_inputs(target.get("declared_inputs", []))


def _validate_archive_semantics(target: Mapping[str, Any]) -> None:
    archive = target.get("archive_semantics")
    if target.get("kind") != "archive":
        if archive is not None:
            raise ValueError("build_ir_archive_semantics_invalid")
        return
    if not isinstance(archive, Mapping) or set(archive) != {
        "operation", "ranlib_passes",
    }:
        raise ValueError("build_ir_archive_semantics_invalid")
    operation = archive.get("operation")
    ranlib_passes = archive.get("ranlib_passes")
    if (
        not isinstance(operation, str)
        or not operation
        or isinstance(ranlib_passes, bool)
        or not isinstance(ranlib_passes, int)
        or ranlib_passes < 0
    ):
        raise ValueError("build_ir_archive_semantics_invalid")


def _validate_declared_inputs(value: Any) -> None:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError("build_ir_target_declared_inputs_invalid")
    if [item.get("ordinal") for item in value] != list(range(len(value))):
        raise ValueError("build_ir_target_declared_input_order_invalid")
    for item in value:
        if item.get("role") != "generated-source":
            raise ValueError("build_ir_target_declared_input_invalid")
        binding = item.get("binding")
        if not isinstance(binding, Mapping):
            raise ValueError("build_ir_target_declared_input_invalid")
        validate_materialized_binding(binding, binding.get("materialized"))


__all__ = ["validate_target_extensions"]
