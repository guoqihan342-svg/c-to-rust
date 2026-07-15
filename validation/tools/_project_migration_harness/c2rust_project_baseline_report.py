from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .artifacts import content_sha256
from .c2rust_project_baseline_evidence import (
    reopen_c2rust_project_baseline, write_baseline_report,
)


@dataclass(frozen=True, slots=True)
class C2RustProjectBaselineRun:
    report: dict[str, Any]
    report_ref: dict[str, Any]


def finish_baseline_run(
    out_root: Path, run_id: str, repo_root: Path, compile_commands: Path,
    original_ref: Mapping[str, Any], normalized_ref: Mapping[str, Any],
    sources: tuple[dict[str, Any], ...], tools: list[dict[str, Any]],
    policy: dict[str, Any], executions: list[dict[str, Any]],
    generated: dict[str, Any],
    artifacts: dict[tuple[str, str, int], dict[str, Any]],
    blockers: list[str],
) -> C2RustProjectBaselineRun:
    unique_blockers = list(dict.fromkeys(blockers))
    status = "blocked" if unique_blockers else "passed"
    compile_path = compile_commands.relative_to(repo_root).as_posix()
    report = {
        "schema_version": 1,
        "artifact_kind": "c2rust-project-baseline-report",
        "status": status,
        "blockers": unique_blockers,
        "run_id": run_id,
        "inputs": {
            "repository_identity_sha256": content_sha256({
                "compile_commands_path": compile_path,
                "source_bindings": list(sources),
            }),
            "compile_commands_path": compile_path,
            "original_compile_database_ref": dict(original_ref),
            "normalized_compile_database_ref": dict(normalized_ref),
            "source_bindings": list(sources),
        },
        "tools": tools,
        "policy": policy,
        "executions": executions,
        "generated": generated,
        "artifact_refs": sorted(
            artifacts.values(), key=lambda item: (
                item["role"], item["ref"]["path"],
            ),
        ),
        "claims": {
            "classification": "execution-evidence-only",
            "publication_scope": "portable-summary-only",
            "referenced_artifact_visibility": "private-local",
            "host_absolute_paths_in_report": False,
            "real_process_exit_zero": status == "passed",
            "ai_translation": False,
            "final_semantic_gate": False,
        },
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    report_ref = write_baseline_report(out_root, report)
    reopened = reopen_c2rust_project_baseline(out_root, report_ref)
    return C2RustProjectBaselineRun(reopened, report_ref)


__all__ = ["C2RustProjectBaselineRun", "finish_baseline_run"]
