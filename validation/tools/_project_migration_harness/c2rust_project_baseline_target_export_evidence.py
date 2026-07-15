from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import canonical_json_bytes
from .c2rust_project_baseline_evidence import (
    C2RustBaselineEvidenceError, read_cas_artifact, read_cas_object,
    write_cas_artifact,
)
from .c2rust_project_baseline_target_export_unit import (
    baseline_unit_export_identity, project_unit_export_inventory,
)
from .c2rust_project_baseline_target_exports import (
    project_target_export_inventory, target_export_summary,
    unavailable_target_export_summary,
)


def project_snapshot_unit_inventory(
    out_root: Path, snapshot: Mapping[str, Any], unit: Mapping[str, Any],
) -> dict[str, Any]:
    tree = snapshot_generated_tree(out_root, snapshot)
    identity = baseline_unit_export_identity(unit)
    return project_unit_export_inventory(identity["unit_id"], tree, identity)


def finish_target_export_inventory(
    out_root: Path, target_plan: Mapping[str, Any],
    units: Sequence[Mapping[str, Any]],
    inventories: Sequence[Mapping[str, Any] | None],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if (
        len(units) != len(inventories)
        or any(item.get("status") != "passed" for item in units)
        or any(item is None for item in inventories)
    ):
        return None, unavailable_target_export_summary()
    complete = [dict(item) for item in inventories if item is not None]
    inventory = project_target_export_inventory(target_plan, complete)
    reference = write_cas_artifact(
        out_root, "target-export-inventory",
        canonical_json_bytes(inventory), suffix="json",
    )
    return inventory, target_export_summary(inventory, reference)


def validate_target_export_reopen(
    out_root: Path, report: Mapping[str, Any],
) -> None:
    summary = report.get("target_exports")
    units = report.get("unit_transpiles")
    if not isinstance(summary, Mapping) or not isinstance(units, list):
        _fail("c2rust_target_export_report_invalid")
    if summary.get("status") == "unavailable":
        if all(
            isinstance(unit, Mapping)
            and unit.get("status") == "passed"
            and unit.get("generated_snapshot_ref") is not None
            for unit in units
        ):
            _fail("c2rust_target_export_inventory_suppressed")
        return
    reference = summary.get("ref")
    if not isinstance(reference, Mapping):
        _fail("c2rust_target_export_reference_invalid")
    plan = read_cas_object(
        out_root, report["target_plan"]["ref"],
        role="target-plan", label="target_plan",
    )
    inventories = []
    for unit in units:
        if not isinstance(unit, Mapping):
            _fail("c2rust_target_export_unit_invalid")
        snapshot_ref = unit.get("generated_snapshot_ref")
        if snapshot_ref is None:
            _fail("c2rust_target_export_snapshot_missing")
        snapshot = read_cas_object(
            out_root, snapshot_ref,
            role="generated-snapshot", label="generated_snapshot",
        )
        try:
            inventories.append(project_snapshot_unit_inventory(
                out_root, snapshot, unit,
            ))
        except (OSError, TypeError, ValueError) as error:
            raise C2RustBaselineEvidenceError(
                "c2rust_target_export_recompute_failed"
            ) from error
    expected = project_target_export_inventory(plan, inventories)
    actual = read_cas_artifact(
        out_root, reference, role="target-export-inventory",
    )
    expected_summary = target_export_summary(expected, reference)
    if canonical_json_bytes(expected) != actual or dict(summary) != expected_summary:
        _fail("c2rust_target_export_inventory_drifted")


def snapshot_generated_tree(
    out_root: Path, snapshot: Mapping[str, Any],
) -> dict[str, bytes]:
    files = snapshot.get("files")
    if not isinstance(files, list):
        _fail("c2rust_target_export_snapshot_invalid")
    tree: dict[str, bytes] = {}
    for item in files:
        if not isinstance(item, Mapping):
            _fail("c2rust_target_export_snapshot_invalid")
        path = item.get("path")
        if not isinstance(path, str) or path in tree:
            _fail("c2rust_target_export_snapshot_invalid")
        tree[path] = read_cas_artifact(
            out_root, item.get("content_ref"), role="generated-file",
        )
    if not tree:
        _fail("c2rust_target_export_snapshot_invalid")
    return tree


def _fail(code: str) -> None:
    raise C2RustBaselineEvidenceError(code)


__all__ = [
    "finish_target_export_inventory", "project_snapshot_unit_inventory",
    "snapshot_generated_tree", "validate_target_export_reopen",
]
