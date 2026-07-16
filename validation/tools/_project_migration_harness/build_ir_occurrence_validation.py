from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .build_ir import validate_materialized_binding


_OCCURRENCE_KEYS = {
    "ordinal", "role", "binding", "dependency_target_id",
}


def validate_target_occurrences(
    targets: Sequence[Mapping[str, Any]], identifiers: set[str],
) -> None:
    owners: dict[str, tuple[str, dict[str, Any]]] = {}
    for target in targets:
        target_id = str(target["target_id"])
        dependencies = target.get("dependency_target_ids")
        if not _strings(dependencies) or len(dependencies) != len(set(dependencies)):
            raise ValueError("build_ir_target_dependencies_invalid")
        if target_id in dependencies or any(item not in identifiers for item in dependencies):
            raise ValueError("build_ir_target_dependencies_invalid")
        outputs = target.get("outputs")
        if not isinstance(outputs, list):
            raise ValueError("build_ir_target_outputs_invalid")
        for output in outputs:
            if not isinstance(output, Mapping):
                raise ValueError("build_ir_target_outputs_invalid")
            validate_materialized_binding(output, output.get("materialized"))
            path = str(output["path"])
            previous = owners.get(path)
            if previous is not None and previous[0] != target_id:
                raise ValueError("build_ir_target_output_duplicate")
            owners[path] = (target_id, dict(output))
    for target in targets:
        _validate_inputs(target, identifiers, owners)


def _validate_inputs(
    target: Mapping[str, Any], identifiers: set[str],
    owners: Mapping[str, tuple[str, dict[str, Any]]],
) -> None:
    inputs = target.get("ordered_inputs")
    if not isinstance(inputs, list):
        raise ValueError("build_ir_target_inputs_invalid")
    dependencies = set(target["dependency_target_ids"])
    for ordinal, item in enumerate(inputs):
        if not isinstance(item, Mapping) or set(item) != _OCCURRENCE_KEYS:
            raise ValueError("build_ir_target_input_invalid")
        if item.get("ordinal") != ordinal:
            raise ValueError("build_ir_target_input_order_invalid")
        role = item.get("role")
        if not isinstance(role, str) or not role or len(role.encode("utf-8")) > 256:
            raise ValueError("build_ir_target_input_role_invalid")
        binding = item.get("binding")
        if not isinstance(binding, Mapping):
            raise ValueError("build_ir_target_input_invalid")
        validate_materialized_binding(binding, binding.get("materialized"))
        dependency = item.get("dependency_target_id")
        owner = owners.get(str(binding["path"]))
        if dependency is None:
            if owner is not None:
                raise ValueError("build_ir_target_input_owner_missing")
            continue
        if not isinstance(dependency, str) or not dependency \
                or dependency not in identifiers or dependency not in dependencies:
            raise ValueError("build_ir_target_input_dependency_invalid")
        if owner is None or owner[0] != dependency or owner[1] != dict(binding):
            raise ValueError("build_ir_target_input_owner_mismatch")


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item) for item in value
    )


__all__ = ["validate_target_occurrences"]
