from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .artifacts import write_bytes_artifact, write_json_artifact
from .build_facts import detect_build_system_facts, file_binding
from .build_ir import is_sha256
from .build_ir_toolchain_stage import (
    blocked_c_toolchain_stage, materialize_c_toolchain_stage,
)
from .build_ir_toolchains import make_tool_requests, merge_tool_requests
from .make_build_ir_closure_artifacts import project_make_closure_artifacts
from .make_build_ir_projection import (
    MAKE_RAW_ROLE, normalize_make_translation_units, project_make_build_ir,
)
from .make_dry_run_parser import MAX_COMMANDS
from .make_dry_run_report_io import (
    MAX_REPORT_BYTES, reopen_make_dry_run_report,
    verify_make_dry_run_report_inputs,
)


MAKE_INPUT_KIND = "explicit-make-dry-run-report"


@dataclass(frozen=True, slots=True)
class MakeReportSelection:
    path: Path
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, Path) or not is_sha256(self.sha256)
            or isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int)
            or not 0 < self.size_bytes <= MAX_REPORT_BYTES
        ):
            raise ValueError("make_report_selection_invalid")


def discover_make_project(
    repo_root: str | Path, selection: MakeReportSelection, max_units: int,
) -> dict[str, Any]:
    root = Path(repo_root)
    empty_facts = {
        "status": "unavailable", "systems": [], "markers": [], "blockers": [],
        "build_commands_executed": False,
    }
    if (
        isinstance(max_units, bool) or not isinstance(max_units, int) or max_units < 1
        or not root.exists() or not root.is_dir()
    ):
        return _discovery_report(
            empty_facts, selection, [], [], ["make_discovery_input_invalid"],
        )
    try:
        root = root.resolve(strict=True)
        reference = selection_reference(root, selection)
        report = reopen_make_dry_run_report(root, reference)
        units, rejected, blockers = normalize_make_translation_units(
            root, report, max_units,
        )
        build_facts = detect_build_system_facts(root)
        blockers.extend(build_facts.get("blockers", []))
    except (OSError, TypeError, ValueError):
        return _discovery_report(
            empty_facts, selection, [], [], ["make_report_reopen_blocked"],
        )
    return _discovery_report(build_facts, selection, units, rejected, blockers)


def materialize_make_build_ir_stage(
    repo_root: Path, output: Path, discovery: Mapping[str, Any],
    artifacts: dict[str, dict[str, Any]], selection: MakeReportSelection,
    profile: str = "development",
) -> dict[str, Any]:
    from .build_ir_validation import verify_build_ir_artifact

    if discovery.get("status") != "ready" or discovery.get("input_kind") != MAKE_INPUT_KIND:
        raise ValueError("make_build_ir_discovery_not_ready")
    source_reference = selection_reference(repo_root, selection)
    report = reopen_make_dry_run_report(repo_root, source_reference)
    report_data = _selected_report_bytes(repo_root, source_reference)
    report_reference = write_bytes_artifact(
        output, "plan/make-dry-run-report.json", report_data,
    )
    artifacts["make_dry_run_report"] = report_reference
    toolchain_evidence = materialize_c_toolchain_stage(
        output,
        artifacts,
        merge_tool_requests(make_tool_requests(report)),
        profile=profile,
    )
    if toolchain_evidence is not None and toolchain_evidence.get("status") != "ready":
        return blocked_c_toolchain_stage(output, artifacts, toolchain_evidence)
    build_ir = project_make_build_ir(
        repo_root,
        report,
        report_reference,
        max_units=MAX_COMMANDS,
        toolchain_evidence=toolchain_evidence,
        toolchain_reference=(
            artifacts.get("c_toolchain_evidence")
            if toolchain_evidence is not None else None
        ),
        report_inputs_verified=True,
    )
    artifacts["build_ir"] = write_json_artifact(
        output, "plan/build-ir.json", build_ir,
    )
    verification = verify_build_ir_artifact(repo_root, output, artifacts["build_ir"])
    artifacts["build_ir_verification"] = write_json_artifact(
        output, "plan/build-ir-verification.json", verification,
    )
    closure, closure_verification, closure_ready = (
        project_make_closure_artifacts(
            build_ir, artifacts["build_ir"], report_reference, verification,
        )
    )
    artifacts["generated_build_closure"] = write_json_artifact(
        output, "plan/make-target-closure.json", closure,
    )
    artifacts["generated_build_closure_verification"] = write_json_artifact(
        output, "plan/make-target-closure-verification.json",
        closure_verification,
    )
    return {
        "build_ir": build_ir,
        "closure": closure,
        "closure_verification": closure_verification,
        "closure_ready": closure_ready,
        "verification": verification,
    }


def materialize_selected_build_ir_stage(
    repo_root: Path, output: Path, discovery: Mapping[str, Any],
    artifacts: dict[str, dict[str, Any]], selection: MakeReportSelection | None,
    profile: str = "development",
) -> dict[str, Any]:
    if discovery.get("input_kind") == MAKE_INPUT_KIND:
        if not isinstance(selection, MakeReportSelection):
            raise ValueError("make_report_selection_missing")
        return materialize_make_build_ir_stage(
            repo_root, output, discovery, artifacts, selection, profile,
        )
    from .generated_closure import materialize_build_ir_stage
    return materialize_build_ir_stage(
        repo_root, output, dict(discovery), artifacts, profile,
    )


def reproject_make_build_ir(
    repo_root: str | Path, report: Mapping[str, Any],
    report_reference: Mapping[str, Any],
    toolchain_evidence: Mapping[str, Any] | None = None,
    toolchain_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve(strict=True)
    checked = verify_make_dry_run_report_inputs(root, report)
    return project_make_build_ir(
        root,
        checked,
        report_reference,
        max_units=MAX_COMMANDS,
        toolchain_evidence=toolchain_evidence,
        toolchain_reference=toolchain_reference,
        report_inputs_verified=True,
    )


def selection_reference(
    repo_root: Path, selection: MakeReportSelection,
) -> dict[str, Any]:
    if not isinstance(selection, MakeReportSelection):
        raise ValueError("make_report_selection_invalid")
    reference = file_binding(
        repo_root.resolve(strict=True), selection.path, max_bytes=MAX_REPORT_BYTES,
    )
    if (
        reference["sha256"] != selection.sha256
        or reference["size_bytes"] != selection.size_bytes
    ):
        raise ValueError("make_report_selection_drift")
    return reference


def _selected_report_bytes(
    repo_root: Path, reference: Mapping[str, Any],
) -> bytes:
    root = repo_root.resolve(strict=True)
    path = root.joinpath(*Path(str(reference["path"])).parts).resolve(strict=True)
    path.relative_to(root)
    data = path.read_bytes()
    if (
        len(data) != reference["size_bytes"]
        or hashlib.sha256(data).hexdigest() != reference["sha256"]
    ):
        raise ValueError("make_report_selection_drift")
    return data


def _discovery_report(
    build_facts: Mapping[str, Any], selection: MakeReportSelection,
    units: list[dict[str, Any]], rejected: list[dict[str, Any]],
    blockers: list[str],
) -> dict[str, Any]:
    unique = sorted(set(blockers))
    status = "ready" if units and not unique else "blocked"
    return {
        "schema_version": 1,
        "status": status,
        "input_kind": MAKE_INPUT_KIND,
        "build_system_facts": dict(build_facts),
        "compile_database": {
            "status": "not-selected", "selection": "explicit-make-dry-run",
        },
        "make_report": {
            "selection": "explicit", "sha256": selection.sha256,
            "size_bytes": selection.size_bytes,
        },
        "translation_units": units,
        "rejected_entries": rejected,
        "generated_build_closure": {
            "schema_version": 1,
            "status": "ready_with_boundaries" if status == "ready" else "blocked",
            "command_graph_complete": status == "ready",
            "repository_input_closure_complete": False,
            "blockers": [{"kind": item} for item in unique],
        },
        "blockers": unique,
        "claim_boundary": {
            "role": "repository_input_discovery_only",
            "selected_translation_units_complete": status == "ready",
            "command_graph_complete": status == "ready",
            "generated_build_closure_complete": False,
            "make_fact_collection_precollected": True,
            "build_commands_executed": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }


__all__ = [
    "MAKE_INPUT_KIND", "MAKE_RAW_ROLE", "MakeReportSelection",
    "discover_make_project", "materialize_make_build_ir_stage",
    "materialize_selected_build_ir_stage",
    "reproject_make_build_ir", "selection_reference",
]
