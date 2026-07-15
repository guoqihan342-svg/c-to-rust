from __future__ import annotations

from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Mapping

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir_validation_io import read_bound, strict_object
from .c2rust_project_baseline_artifacts import (
    BaselineArtifactRegistry, portable_tool,
)
from .c2rust_project_baseline_build_ir import (
    reopen_build_ir_compile_database,
)
from .c2rust_project_baseline_diagnostics import (
    has_transpiler_error_diagnostics,
)
from .c2rust_project_baseline_evidence import (
    C2RustBaselineEvidenceError, snapshot_generated_tree, write_cas_artifact,
)
from .c2rust_project_baseline_process import (
    Runner, executable_binding, minimal_process_environment,
    normalized_environment_overrides, run_recorded_process,
)
from .c2rust_project_baseline_report import C2RustProjectBaselineRun
from .c2rust_project_baseline_report_v3 import finish_build_ir_unit_run
from .c2rust_project_baseline_target_plan import project_terminal_target_plan
from .c2rust_project_baseline_target_export_evidence import (
    finish_target_export_inventory, project_snapshot_unit_inventory,
)


def run_c2rust_build_ir_unit_baseline(
    *, repo_root: Path, compile_commands: Path,
    build_ir_artifact_root: Path, build_ir_reference: Mapping[str, Any],
    c2rust_transpile: Path, out_root: Path, cargo: Path, rustc: Path,
    timeout_seconds: int = 300,
    environment_overrides: Mapping[str, str] | None = None,
    runner: Runner | None = None,
) -> C2RustProjectBaselineRun:
    repository = Path(repo_root).resolve(strict=True)
    output = Path(out_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    reopened = reopen_build_ir_compile_database(
        repo_root=repository, artifact_root=build_ir_artifact_root,
        build_ir_reference=build_ir_reference,
        compile_database=compile_commands,
    )
    build_ir_data = read_bound(
        Path(build_ir_artifact_root).resolve(strict=True),
        build_ir_reference, "build_ir",
    )
    build_ir = strict_object(build_ir_data, "build_ir")
    target_plan = project_terminal_target_plan(build_ir)
    metadata, object_owners = _unit_metadata(build_ir, target_plan)
    bound_ids = {item.unit_id for item in reopened.units}
    if set(metadata) != bound_ids or set(object_owners) != bound_ids:
        raise ValueError("c2rust_unit_target_coverage_invalid")

    runtime_tools = [
        executable_binding(c2rust_transpile, "c2rust-transpile"),
        executable_binding(cargo, "cargo"),
        executable_binding(rustc, "rustc"),
    ]
    tools = [portable_tool(item) for item in runtime_tools]
    selected_overrides = normalized_environment_overrides(environment_overrides)
    policy = {
        "mode": "build-ir-unit-transpile",
        "timeout_seconds": timeout_seconds,
        "minimal_environment": True,
        "per_unit_isolation": True,
        "fresh_unit_output": True,
        "overwrite_existing_scope": "fresh-unit-workspace-only",
        "cargo_executed": False,
        "environment_override_keys": sorted(selected_overrides),
        "environment_overrides_sha256": content_sha256(selected_overrides),
    }
    original_path = Path(compile_commands).resolve(strict=True)
    registry = BaselineArtifactRegistry()
    original_ref = write_cas_artifact(
        output, "compile-database", original_path.read_bytes(), suffix="json",
    )
    build_ir_ref = write_cas_artifact(
        output, "build-ir", build_ir_data, suffix="json",
    )
    plan_bytes = canonical_json_bytes(target_plan)
    plan_ref = write_cas_artifact(
        output, "target-plan", plan_bytes, suffix="json",
    )
    registry.add("compile-database", original_ref)
    registry.add("build-ir", build_ir_ref)
    registry.add("target-plan", plan_ref)
    run_id = content_sha256({
        "build_ir_sha256": build_ir_ref["sha256"],
        "build_ir_semantic_sha256": reopened.semantic_sha256,
        "target_plan_sha256": plan_ref["sha256"],
        "unit_databases": [
            {"unit_key": item.unit_key, "sha256": item.database_sha256}
            for item in sorted(reopened.units, key=lambda item: item.unit_key)
        ],
        "tools": tools,
        "policy": policy,
    })
    workspaces = output / "workspaces"
    workspaces.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(
        prefix=f"c2rust-build-ir-{run_id[:12]}-", dir=workspaces,
    )).resolve(strict=True)
    environment = minimal_process_environment(
        workspace / "runtime", transpiler=Path(runtime_tools[0]["executable_path"]),
        cargo=Path(runtime_tools[1]["executable_path"]),
        rustc=Path(runtime_tools[2]["executable_path"]),
        overrides=selected_overrides,
    )
    executions: list[dict[str, Any]] = []
    unit_results: list[dict[str, Any]] = []
    unit_inventories: list[dict[str, Any] | None] = []
    run_blockers: list[str] = []
    for bound in sorted(reopened.units, key=lambda item: item.unit_key):
        result, execution, refs, snapshot_files, unit_inventory = _transpile_unit(
            repository=repository, output=output, workspace=workspace,
            bound=bound, metadata=metadata[bound.unit_id],
            object_target_id=object_owners[bound.unit_id],
            transpiler=str(runtime_tools[0]["executable_path"]),
            environment=environment, timeout_seconds=timeout_seconds,
            runner=runner,
        )
        registry.add("unit-compile-database", result["compile_database_ref"])
        registry.add_process(refs)
        if result["generated_snapshot_ref"] is not None:
            registry.add("generated-snapshot", result["generated_snapshot_ref"])
            for reference in snapshot_files:
                registry.add("generated-file", reference)
        executions.append(execution)
        unit_results.append(result)
        unit_inventories.append(unit_inventory)
        run_blockers.extend(result["blockers"])
    sources = _source_bindings(metadata)
    key_by_unit = {item.unit_id: item.unit_key for item in reopened.units}
    occurrence_count = sum(
        len(item["unit_occurrences"])
        for item in target_plan["terminal_targets"]
    )
    target_boundary_count = sum(
        len(item["target_owned_boundaries"])
        for item in target_plan["terminal_targets"]
    )
    plan_summary = {
        "ref": plan_ref,
        "semantic_sha256": content_sha256(target_plan),
        "build_ir_status": build_ir["status"],
        "build_ir_boundary_count": len(build_ir["boundaries"]),
        "terminal_target_count": len(target_plan["terminal_targets"]),
        "unit_occurrence_count": occurrence_count,
        "target_owned_boundary_count": target_boundary_count,
        "covered_unit_keys": sorted(key_by_unit.values()),
    }
    _export_inventory, export_summary = finish_target_export_inventory(
        output, target_plan, unit_results, unit_inventories,
    )
    if export_summary["ref"] is not None:
        registry.add("target-export-inventory", export_summary["ref"])
    return finish_build_ir_unit_run(
        out_root=output, run_id=run_id, repo_root=repository,
        compile_commands=original_path, original_ref=original_ref,
        build_ir_ref=build_ir_ref,
        build_ir_semantic_sha256=reopened.semantic_sha256,
        sources=sources, tools=tools, policy=policy, executions=executions,
        units=unit_results, target_plan=plan_summary,
        target_exports=export_summary,
        artifacts=registry.values(), blockers=run_blockers,
    )


def _transpile_unit(
    *, repository: Path, output: Path, workspace: Path, bound: Any,
    metadata: Mapping[str, Any], object_target_id: str, transpiler: str,
    environment: Mapping[str, str], timeout_seconds: int,
    runner: Runner | None,
) -> tuple[
    dict[str, Any], dict[str, Any], tuple[Any, ...],
    list[dict[str, Any]], dict[str, Any] | None,
]:
    database_ref = write_cas_artifact(
        output, "unit-compile-database", bound.database_bytes, suffix="json",
    )
    runtime_database = workspace.joinpath(
        *PurePosixPath(bound.database_binding["path"]).parts
    )
    runtime_database.parent.mkdir(parents=True, exist_ok=False)
    runtime_database.write_bytes(bound.database_bytes)
    unit_root = runtime_database.parents[1]
    generated_root = unit_root / "generated-output"
    purpose = f"c2rust-transpile-unit-{bound.unit_key}"
    execution, refs = run_recorded_process(
        [
            transpiler, runtime_database.as_posix(), "--emit-build-files",
            "--preserve-unused-functions", "--overwrite-existing",
            "--output-dir", generated_root.as_posix(),
        ],
        cwd=repository, environment=environment,
        timeout_seconds=timeout_seconds, out_root=output, purpose=purpose,
        portable_argv=[
            "c2rust-transpile", f"private-local:unit-db:{bound.unit_key}",
            "--emit-build-files", "--preserve-unused-functions",
            "--overwrite-existing", "--output-dir",
            f"private-local:unit-output:{bound.unit_key}",
        ],
        portable_working_directory="repository-root", runner=runner,
    )
    blockers: list[str] = []
    if execution["status"] != "passed":
        blockers.append("c2rust_unit_transpile_execution_failed")
    try:
        if has_transpiler_error_diagnostics(output, execution["stderr_ref"]):
            blockers.append("c2rust_unit_transpile_diagnostics_failed")
    except ValueError:
        blockers.append("c2rust_unit_transpile_diagnostics_unavailable")
    snapshot_ref = None
    snapshot = None
    snapshot_files: list[dict[str, Any]] = []
    try:
        snapshot, snapshot_ref = snapshot_generated_tree(generated_root, output)
        snapshot_files = [item["content_ref"] for item in snapshot["files"]]
    except (C2RustBaselineEvidenceError, OSError, ValueError):
        blockers.append("c2rust_unit_generated_snapshot_invalid")
    result: dict[str, Any] = {
        "unit_id": bound.unit_id,
        "unit_key": bound.unit_key,
        "variant": {
            "index": metadata["variant_index"],
            "count": metadata["variant_count"],
        },
        "source": _source_binding(metadata["source"]),
        "object_target_id": object_target_id,
        "compile_database_ref": database_ref,
        "generated_snapshot_ref": snapshot_ref,
        "execution_purpose": purpose,
    }
    unit_inventory = None
    if snapshot is not None:
        try:
            unit_inventory = project_snapshot_unit_inventory(
                output, snapshot, result,
            )
        except (C2RustBaselineEvidenceError, OSError, TypeError, ValueError):
            blockers.append("c2rust_unit_export_inventory_invalid")
    result.update({
        "status": "passed" if not blockers else "failed",
        "blockers": list(dict.fromkeys(blockers)),
    })
    return result, execution, refs, snapshot_files, unit_inventory


def _unit_metadata(
    build_ir: Mapping[str, Any], target_plan: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    units = build_ir.get("translation_units")
    if not isinstance(units, list):
        raise ValueError("c2rust_build_ir_units_invalid")
    metadata = {str(item["unit_id"]): item for item in units}
    owners: dict[str, str] = {}
    for terminal in target_plan["terminal_targets"]:
        for occurrence in terminal["unit_occurrences"]:
            unit_id = str(occurrence["unit_id"])
            object_id = str(occurrence["object_target_id"])
            previous = owners.setdefault(unit_id, object_id)
            if previous != object_id:
                raise ValueError("c2rust_unit_object_target_conflict")
    return metadata, owners


def _source_bindings(
    metadata: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    for unit in metadata.values():
        source = _source_binding(unit["source"])
        previous = by_path.setdefault(source["path"], source)
        if previous != source:
            raise ValueError("c2rust_source_binding_conflict")
    return [by_path[path] for path in sorted(by_path)]


def _source_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": value["path"], "sha256": value["sha256"],
        "size_bytes": value["size_bytes"],
    }


__all__ = ["run_c2rust_build_ir_unit_baseline"]
