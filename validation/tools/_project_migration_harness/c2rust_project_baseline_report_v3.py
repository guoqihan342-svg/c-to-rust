from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .artifacts import content_sha256
from .c2rust_project_baseline_evidence import (
    reopen_c2rust_project_baseline, write_baseline_report,
)
from .c2rust_project_baseline_report import C2RustProjectBaselineRun


PENDING_CARGO_BLOCKER = "c2rust_target_cargo_assembly_pending"


def finish_build_ir_unit_run(
    *, out_root: Path, run_id: str, repo_root: Path,
    compile_commands: Path, original_ref: Mapping[str, Any],
    build_ir_ref: Mapping[str, Any], build_ir_semantic_sha256: str,
    sources: list[dict[str, Any]], tools: list[dict[str, Any]],
    policy: dict[str, Any], executions: list[dict[str, Any]],
    units: list[dict[str, Any]], target_plan: dict[str, Any],
    target_exports: dict[str, Any],
    artifacts: list[dict[str, Any]], blockers: list[str],
) -> C2RustProjectBaselineRun:
    selected_blockers = list(dict.fromkeys([
        *blockers, *target_exports["blockers"], PENDING_CARGO_BLOCKER,
    ]))
    compile_path = compile_commands.relative_to(repo_root).as_posix()
    report = {
        "schema_version": 3,
        "artifact_kind": "c2rust-project-baseline-report",
        "status": "blocked",
        "blockers": selected_blockers,
        "run_id": run_id,
        "inputs": {
            "repository_identity_sha256": content_sha256({
                "compile_commands_path": compile_path,
                "source_bindings": sources,
                "build_ir_semantic_sha256": build_ir_semantic_sha256,
            }),
            "compile_commands_path": compile_path,
            "original_compile_database_ref": dict(original_ref),
            "build_ir_ref": dict(build_ir_ref),
            "build_ir_semantic_sha256": build_ir_semantic_sha256,
            "source_bindings": sources,
        },
        "tools": tools,
        "policy": policy,
        "executions": executions,
        "unit_transpiles": units,
        "target_plan": target_plan,
        "target_exports": target_exports,
        "artifact_refs": sorted(
            artifacts, key=lambda item: (item["role"], item["ref"]["path"]),
        ),
        "claims": {
            "classification": "candidate-generation-evidence-only",
            "publication_scope": "portable-summary-only",
            "referenced_artifact_visibility": "private-local",
            "host_absolute_paths_in_report": False,
            "real_process_exit_zero": all(
                item.get("returncode") == 0 for item in executions
            ),
            "ai_translation": False,
            "cargo_executed": False,
            "final_semantic_gate": False,
        },
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    report_ref = write_baseline_report(out_root, report)
    reopened = reopen_c2rust_project_baseline(out_root, report_ref)
    return C2RustProjectBaselineRun(reopened, report_ref)


__all__ = ["PENDING_CARGO_BLOCKER", "finish_build_ir_unit_run"]
