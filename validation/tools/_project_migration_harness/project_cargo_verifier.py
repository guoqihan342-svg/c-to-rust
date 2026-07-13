from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .artifacts import content_sha256
from .controller_gates import record_candidate_gate
from .gate_candidate_sets import current_candidate_members
from .integration_generation import GenerationCommitError
from .ledger import ProjectLedger
from .project_cargo_evidence import project_cargo_observation
from .project_host_gates import record_host_project_observation
from .project_verification import (
    managed_project_input_sha256, run_cargo_project_gates,
)


def verify_project_cargo(
    *, ledger: ProjectLedger, run_id: str, project_root: Path,
    runtime_root: Path, out_root: Path, out_root_rel: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    candidate_set = ledger.bind_current_candidate_set(run_id=run_id)
    execution = run_cargo_project_gates(
        project_root,
        runtime_root=runtime_root,
        cargo_command="cargo",
        timeout_seconds=timeout_seconds,
    )
    raw_checks = execution.get("checks")
    checks: dict[str, dict[str, Any]] = {}
    if isinstance(raw_checks, list):
        for command in ("check", "test"):
            matches = [
                item for item in raw_checks
                if isinstance(item, dict) and _command_stage(item) == command
            ]
            if len(matches) == 1:
                checks[command] = matches[0]
    try:
        project_input_sha256 = managed_project_input_sha256(project_root)
    except (GenerationCommitError, OSError, ValueError):
        project_input_sha256 = None
    records = []
    for gate_kind, command in (("cargo-check", "check"), ("cargo-test", "test")):
        check = checks.get(command)
        diagnostics = _diagnostic_codes(execution, check, gate_kind)
        observation = project_cargo_observation(
            execution,
            check,
            gate_kind=gate_kind,
            expected_input_sha256=project_input_sha256,
        )
        records.append(record_host_project_observation(
            ledger=ledger,
            out_root=out_root,
            out_root_rel=out_root_rel,
            run_id=run_id,
            gate_kind=gate_kind,
            candidate_set_sha256=candidate_set,
            observation=observation,
            diagnostic_codes=diagnostics,
        ))
    repairs = _bridge_compile_failures(
        ledger=ledger,
        run_id=run_id,
        out_root=out_root,
        out_root_rel=out_root_rel,
        check=checks.get("check"),
        project_record=records[0],
    )
    return {
        "schema_version": 1,
        "status": (
            "passed" if all(item["gate_status"] == "passed" for item in records)
            else "blocked" if execution.get("status") == "blocked"
            else "failed"
        ),
        "run_id": run_id,
        "candidate_set_sha256": candidate_set,
        "records": records,
        "candidate_repair_gates": repairs,
        "execution": execution,
        "semantic_gate": False,
    }


def _command_stage(check: dict[str, Any]) -> str | None:
    command = check.get("command")
    if (
        not isinstance(command, list)
        or len(command) < 2
        or command[0] != "cargo"
        or command[1] not in {"check", "test"}
    ):
        return None
    return str(command[1])


def _diagnostic_codes(
    execution: dict[str, Any], check: Any, gate_kind: str,
) -> list[str]:
    diagnostics = check.get("diagnostics") if isinstance(check, dict) else None
    if not isinstance(diagnostics, list):
        diagnostics = execution.get("diagnostics")
    codes = {
        str(item.get("code"))
        for item in diagnostics or []
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    if not codes:
        codes.add(f"{gate_kind}-not-executed")
    return sorted(codes)[:64]


def _bridge_compile_failures(
    *, ledger: ProjectLedger, run_id: str, out_root: Path, out_root_rel: str,
    check: Any, project_record: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(check, dict) or check.get("status") != "failed":
        return []
    diagnostics = check.get("diagnostics")
    if not isinstance(diagnostics, list):
        return []
    with ledger.connect() as connection:
        members = current_candidate_members(connection, run_id)
    by_sha = {item["content_sha256"]: item for item in members}
    grouped: dict[str, list[dict[str, Any]]] = {}
    pattern = re.compile(r"^src/unit_([0-9a-f]{64})\.rs$")
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            continue
        matched = pattern.fullmatch(str(diagnostic.get("file", "")))
        if matched is not None and matched.group(1) in by_sha:
            grouped.setdefault(matched.group(1), []).append(diagnostic)
    results = []
    for digest, values in sorted(grouped.items()):
        member = by_sha[digest]
        record_id = "host-compile-" + content_sha256({
            "run_id": run_id,
            "unit_id": member["unit_id"],
            "candidate_artifact_id": member["artifact_id"],
            "project_record_id": project_record["record_id"],
        })[:24]
        results.append(record_candidate_gate(
            ledger=ledger,
            out_root=out_root,
            out_root_rel=out_root_rel,
            run_id=run_id,
            unit_id=member["unit_id"],
            candidate_artifact_id=member["artifact_id"],
            record_id=record_id,
            kind="verifier",
            gate_family="compile",
            status="failed",
            verifier_id="host-derived",
            diagnostics=values[:32],
        ))
    return results


__all__ = ["verify_project_cargo"]
