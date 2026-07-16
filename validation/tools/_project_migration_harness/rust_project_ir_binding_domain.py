from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .build_ir import canonical_build_ir_bytes
from .build_ir_validation import BuildIRValidationError, validate_build_ir
from .rust_project_ir_compilation_facts import validate_dag_metadata
from .rust_project_ir_cohort import PARENT_DAG_KEY, validate_cohort_dag
from .rust_project_ir_binding_io import artifact_identity, fail
from .rust_project_ir_validation import RustProjectIRError


_DAG_REQUIRED_KEYS = {"schema_version", "dag", "dag_order"}
_DAG_ALLOWED_KEYS = _DAG_REQUIRED_KEYS | {
    "unsafe_policy", "generated_build_closure", "build_ir", "claim_boundary",
    "c_compilation_facts", "profile", PARENT_DAG_KEY,
    "migration_graph", "target_scopes", "project_test_inventory",
}


def validate_bound_build_ir(payload: Mapping[str, Any], data: bytes) -> None:
    try:
        validate_build_ir(payload)
        if canonical_build_ir_bytes(payload) != data:
            raise BuildIRValidationError("build_ir_not_canonical")
    except (BuildIRValidationError, TypeError, ValueError) as error:
        raise RustProjectIRError(f"bound BuildIR validation failed: {error}") from error


def validate_bound_migration_dag(
    payload: Mapping[str, Any], artifact_root: Path,
) -> set[str]:
    keys = set(payload)
    if (
        not _DAG_REQUIRED_KEYS <= keys
        or not keys <= _DAG_ALLOWED_KEYS
        or payload.get("schema_version") != 1
    ):
        fail("bound migration DAG schema is invalid")
    dag, order = payload.get("dag"), payload.get("dag_order")
    if not isinstance(dag, Mapping) or not dag or not isinstance(order, list):
        fail("bound migration DAG closure is invalid")
    units = set(dag)
    if not all(isinstance(unit, str) and unit for unit in units):
        fail("bound migration DAG unit identity is invalid")
    if (
        len(order) != len(units)
        or not all(isinstance(unit, str) for unit in order)
        or len(order) != len(set(order))
        or set(order) != units
    ):
        fail("bound migration DAG order does not cover its units")
    positions = {unit: index for index, unit in enumerate(order)}
    for unit in sorted(units):
        dependencies = dag.get(unit)
        if (
            not isinstance(dependencies, list)
            or not all(isinstance(item, str) and item for item in dependencies)
            or dependencies != sorted(set(dependencies))
            or any(item not in units or item == unit for item in dependencies)
            or any(positions[item] >= positions[unit] for item in dependencies)
        ):
            fail("bound migration DAG dependency closure is invalid")
    try:
        validate_dag_metadata(payload, artifact_identity)
        _validate_project_test_inventory_binding(
            payload.get("project_test_inventory")
        )
        validate_cohort_dag(payload, artifact_root)
    except ValueError as error:
        raise RustProjectIRError(str(error)) from error
    return units


def _validate_project_test_inventory_binding(value: Any) -> None:
    if value is None:
        return
    if (
        not isinstance(value, Mapping)
        or set(value) != {"status", "artifact"}
        or value.get("status") != "bound"
    ):
        raise ValueError("project_test_inventory_manifest_binding_invalid")
    artifact_identity(value.get("artifact"))


def validate_embedded_build_ir(
    dag: Mapping[str, Any], references: Sequence[Mapping[str, Any]],
) -> None:
    binding = dag.get("build_ir")
    if binding is None:
        return
    if (
        not isinstance(binding, Mapping)
        or set(binding) != {
            "status", "artifact", "verification", "worker_admission",
        }
        or binding.get("status") != "bound"
    ):
        fail("bound migration DAG BuildIR binding is invalid")
    bound_identity = artifact_identity(binding.get("artifact"))
    artifact_identity(binding.get("verification"))
    artifact_identity(binding.get("worker_admission"))
    if bound_identity not in {artifact_identity(item) for item in references}:
        fail("migration DAG and RustProjectIR bind different BuildIR artifacts")


__all__ = [
    "validate_bound_build_ir", "validate_bound_migration_dag",
    "validate_embedded_build_ir",
]
