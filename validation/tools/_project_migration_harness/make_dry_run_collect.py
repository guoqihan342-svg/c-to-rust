from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any

from .make_dry_run_collect_io import (
    make_command_input_refs, persist_make_raw_outputs, persist_make_static,
    validate_make_collection_inputs,
)
from .make_dry_run_cas import (
    make_cas_reference, write_make_cas,
)
from .make_dry_run_contract import (
    MAX_STDERR_BYTES, canonical_make_dry_run_report_bytes,
    create_make_dry_run_report,
)
from .make_dry_run_host_evidence import canonical_make_host_preflight_bytes
from .make_dry_run_linux import (
    MakeDryRunBackendDiscovery, canonical_make_toolchain_evidence_bytes,
    discover_make_dry_run_backend,
)
from .make_dry_run_parser import MAX_STDOUT_BYTES, parse_make_dry_run_stdout
from .make_dry_run_report_io import MAX_REPORT_BYTES, reopen_make_dry_run_report
from .make_dry_run_runner import (
    canonical_make_dry_run_plan_bytes, create_make_dry_run_plan,
    run_make_dry_run,
)
from .make_dry_run_snapshot import (
    MAX_SNAPSHOT_MANIFEST_BYTES, canonical_repository_snapshot_bytes,
    capture_repository_snapshot, snapshot_file_map,
    verify_repository_snapshot,
)


MAKE_COLLECTION_KIND = "project-migration-make-facts-collection"
MAX_MAKE_METADATA_BYTES = 2 * 1024 * 1024


def collect_make_facts(
    repo_root: str | Path, *, working_directory: str, makefile: str,
    targets: Sequence[str], out_root: str, timeout_seconds: int = 300,
    discovery: MakeDryRunBackendDiscovery | None = None,
) -> dict[str, Any]:
    try:
        root, workdir, makefile_path, selected_targets, output = (
            validate_make_collection_inputs(
            repo_root, working_directory, makefile, targets, out_root,
            timeout_seconds,
            )
        )
    except (OSError, TypeError, ValueError):
        return _blocked("make_collection_input_invalid")
    selected = discovery or discover_make_dry_run_backend()
    if (
        not isinstance(selected, MakeDryRunBackendDiscovery)
        or selected.backend is None or selected.make_binary is None
        or selected.toolchain_evidence is None
    ):
        reason = (
            selected.reason_code
            if isinstance(selected, MakeDryRunBackendDiscovery)
            and selected.reason_code else "make_dry_run_host_backend_unavailable"
        )
        return _blocked(reason)
    artifacts: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="make-dry-run-collection-") as temporary:
        temporary_root = Path(temporary)
        workspace = temporary_root / "workspace"
        runtime = temporary_root / "runtime"
        runtime.mkdir(mode=0o700)
        try:
            snapshot = capture_repository_snapshot(
                root, workspace, collector_output_root=output,
            )
            files = snapshot_file_map(snapshot)
            makefile_ref = files[makefile_path]
            if not (workspace / Path(*PurePosixPath(workdir).parts)).is_dir() and workdir != ".":
                raise ValueError("make_collection_working_directory_missing")
        except (KeyError, OSError, TypeError, ValueError):
            return _blocked("make_collection_snapshot_blocked")
        try:
            toolchain_bytes = canonical_make_toolchain_evidence_bytes(
                selected.toolchain_evidence,
            )
            snapshot_bytes = canonical_repository_snapshot_bytes(snapshot)
            toolchain_ref = make_cas_reference(
                output, "toolchain", toolchain_bytes, suffix="json",
            )
            snapshot_ref = make_cas_reference(
                output, "repository-snapshot", snapshot_bytes, suffix="json",
            )
            plan = create_make_dry_run_plan(
                makefile_ref=makefile_ref,
                input_refs=[],
                toolchain_ref=toolchain_ref,
                targets=selected_targets,
                timeout_seconds=timeout_seconds,
                working_directory=workdir,
                repository_snapshot_ref=snapshot_ref,
            )
            plan_bytes = canonical_make_dry_run_plan_bytes(plan)
            plan_ref = make_cas_reference(
                output, "execution-plan", plan_bytes, suffix="json",
            )
            artifacts.update(persist_make_static(
                root, output,
                toolchain=(toolchain_bytes, toolchain_ref, MAX_MAKE_METADATA_BYTES),
                repository_snapshot=(
                    snapshot_bytes, snapshot_ref, MAX_SNAPSHOT_MANIFEST_BYTES,
                ),
                execution_plan=(plan_bytes, plan_ref, MAX_MAKE_METADATA_BYTES),
            ))
        except (OSError, TypeError, ValueError):
            return _blocked(
                "make_collection_artifact_persistence_blocked",
                artifacts=artifacts,
            )
        try:
            preflight = selected.backend.preflight(
                plan, project_root=workspace, runtime_root=runtime,
            )
            preflight_bytes = canonical_make_host_preflight_bytes(
                preflight.payload(),
            )
            sandbox_ref = write_make_cas(
                root, output, "sandbox-preflight", preflight_bytes,
                suffix="json", limit=MAX_MAKE_METADATA_BYTES,
            )
            artifacts["sandbox_preflight"] = sandbox_ref
        except (OSError, TypeError, ValueError):
            return _blocked(
                "make_host_capability_unavailable", artifacts=artifacts,
            )
        outcome = run_make_dry_run(
            plan,
            project_root=workspace,
            runtime_root=runtime,
            make_binary=selected.make_binary,
            toolchain_ref=toolchain_ref,
            sandbox_ref=sandbox_ref,
            backend=selected.backend,
            preflight=preflight,
        )
        try:
            raw_refs = persist_make_raw_outputs(root, output, outcome)
            artifacts.update(raw_refs)
        except (OSError, TypeError, ValueError):
            return _blocked(
                "make_collection_raw_output_persistence_blocked",
                artifacts=artifacts, make_started=outcome.make_started,
            )
        if outcome.status != "ready":
            return _blocked(
                outcome.blocker or "make_collection_execution_blocked",
                artifacts=artifacts, make_started=outcome.make_started,
                outcome=outcome.payload(),
            )
        try:
            assert outcome.stdout is not None
            parsed = parse_make_dry_run_stdout(
                outcome.stdout, working_directory=workdir,
            )
            kinds = {item["kind"] for item in parsed["commands"]}
            if not {"compile", "link"}.issubset(kinds):
                raise ValueError("make_collection_compile_link_incomplete")
            source_refs, input_refs = make_command_input_refs(
                parsed["commands"], files, output,
            )
            verify_repository_snapshot(root, snapshot)
        except (OSError, TypeError, ValueError):
            return _blocked(
                "make_collection_output_unrepresentable",
                artifacts=artifacts, make_started=True,
                outcome=outcome.payload(),
            )
        try:
            report = create_make_dry_run_report(
                outcome=outcome,
                raw_stdout_ref=artifacts["raw_stdout"],
                raw_stderr_ref=artifacts["raw_stderr"],
                makefile_ref=makefile_ref,
                source_refs=source_refs,
                input_refs=input_refs,
                repository_snapshot_ref=snapshot_ref,
                toolchain_ref=toolchain_ref,
                sandbox_ref=sandbox_ref,
                execution_plan_ref=plan_ref,
                targets=selected_targets,
                working_directory=workdir,
            )
            report_bytes = canonical_make_dry_run_report_bytes(report)
            report_ref = write_make_cas(
                root, output, "report", report_bytes,
                suffix="json", limit=MAX_REPORT_BYTES,
            )
            reopen_make_dry_run_report(root, report_ref)
            artifacts["make_report"] = report_ref
        except (OSError, TypeError, ValueError):
            return _blocked(
                "make_collection_report_blocked",
                artifacts=artifacts, make_started=True,
                outcome=outcome.payload(),
            )
    return {
        "schema_version": 1,
        "artifact_kind": MAKE_COLLECTION_KIND,
        "status": "ready",
        "working_directory": workdir,
        "makefile": makefile_path,
        "targets": selected_targets,
        "make_started": True,
        "artifacts": artifacts,
        "make_report": report_ref,
        "plan_make_report_args": [
            "--make-report", report_ref["path"],
            "--make-report-sha256", report_ref["sha256"],
            "--make-report-size-bytes", str(report_ref["size_bytes"]),
        ],
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def _blocked(
    blocker: str, *, artifacts: Mapping[str, Any] | None = None,
    make_started: bool = False, outcome: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": MAKE_COLLECTION_KIND,
        "status": "blocked",
        "blockers": [blocker],
        "make_started": make_started,
        "artifacts": dict(artifacts or {}),
        "runner_outcome": dict(outcome) if outcome is not None else None,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


__all__ = ["MAKE_COLLECTION_KIND", "collect_make_facts"]
