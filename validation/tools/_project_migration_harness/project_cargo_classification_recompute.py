from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_raw_output_evidence import read_cargo_raw_output
from .gate_evidence import (
    read_content_addressed_json, require_content_addressed_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError
from .project_cargo_diagnostic_cohort import decide_cargo_diagnostic_cohort
from .project_cargo_diagnostic_intake import (
    CargoDiagnosticPartition, partition_cargo_diagnostics,
)
from .rust_project_ir import canonical_rust_project_ir_bytes
from .sandbox_diagnostics import cargo_check_diagnostics


def write_classification_ir(
    out_root: Path, out_root_rel: str, rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    canonical_rust_project_ir_bytes(rust_project_ir)
    reference = write_content_addressed_json(
        out_root, "project-diagnostic-classification/rust-project-ir",
        rust_project_ir,
    )
    return {**reference, "path": f"{out_root_rel}/{reference['path']}"}


def reopen_classification_ir(
    ledger_path: Path, reference: Mapping[str, Any], *,
    expected_ir_sha256: str, expected_interface_sha256: str,
) -> dict[str, Any]:
    try:
        require_classification_ir_reference(reference)
        value = read_content_addressed_json(
            ledger_path, str(reference["path"]), str(reference["sha256"]),
        )
        encoded = canonical_rust_project_ir_bytes(value)
    except (KeyError, TypeError, ValueError) as error:
        raise LedgerError("Cargo classification RustProjectIR is invalid") from error
    if (
        len(encoded) != reference["size_bytes"]
        or value["ir_sha256"] != expected_ir_sha256
        or value["interface_sha256"] != expected_interface_sha256
    ):
        raise LedgerError("Cargo classification RustProjectIR binding drifted")
    return value


def verify_live_classification(
    receipt: Mapping[str, Any], checks: Mapping[str, Mapping[str, Any]],
    rust_project_ir: Mapping[str, Any],
) -> None:
    canonical_rust_project_ir_bytes(rust_project_ir)
    _verify_candidate_binding(receipt["candidate_members"], rust_project_ir)
    verified_checks: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, str]] = {}
    partitions: dict[str, CargoDiagnosticPartition] = {}
    statuses = []
    for gate in receipt["gates"]:
        gate_kind = str(gate["gate_kind"])
        source = checks.get(gate_kind)
        if not gate["executed"]:
            if source is not None:
                raise LedgerError("Cargo classification hid a supplied gate")
            continue
        if not isinstance(source, Mapping):
            raise LedgerError("Cargo classification source gate is missing")
        diagnostics = source.get("diagnostics")
        if (
            not isinstance(diagnostics, list)
            or source.get("status") != gate["status"]
            or source.get("returncode") != gate["returncode"]
            or len(diagnostics) != gate["diagnostic_count"]
            or content_sha256(diagnostics)
            != gate["normalized_diagnostics_sha256"]
        ):
            raise LedgerError("Cargo classification source diagnostics drifted")
        status = str(gate["status"])
        partition = (
            partition_cargo_diagnostics(
                gate_kind=gate_kind, diagnostics=diagnostics,
                candidate_members=receipt["candidate_members"],
                rust_project_ir=rust_project_ir,
            )
            if status == "failed" else CargoDiagnosticPartition({}, [], None)
        )
        if _partition_binding(partition) != {
            "unit_partitions": gate["unit_partitions"],
            "project_diagnostic_sha256s": gate["project_diagnostic_sha256s"],
            "admission_blocker": gate["admission_blocker"],
        }:
            raise LedgerError("Cargo classification partition is not recomputable")
        verified_checks[gate_kind] = {
            "status": status, "diagnostics": diagnostics,
        }
        observations[gate_kind] = {"outcome": "executed"}
        partitions[gate_kind] = partition
        statuses.append(status)
    execution_status = "failed" if "failed" in statuses else "passed"
    expected = decide_cargo_diagnostic_cohort(
        execution_status=execution_status, checks=verified_checks,
        observations=observations, partitions=partitions,
        candidate_members=receipt["candidate_members"],
    ).payload()
    if expected != receipt["admission"]:
        raise LedgerError("Cargo classification admission is not recomputable")


def reopen_and_verify_classification(
    ledger_path: Path, receipt: Mapping[str, Any],
) -> dict[str, Any]:
    rust_project_ir = reopen_classification_ir(
        ledger_path, receipt["rust_project_ir_ref"],
        expected_ir_sha256=str(receipt["rust_project_ir_sha256"]),
        expected_interface_sha256=str(
            receipt["rust_project_interface_sha256"],
        ),
    )
    checks = {
        str(gate["gate_kind"]): _reopen_gate(ledger_path, gate)
        for gate in receipt["gates"] if gate["executed"]
    }
    verify_live_classification(receipt, checks, rust_project_ir)
    return rust_project_ir


def require_classification_ir_reference(value: Mapping[str, Any]) -> None:
    require_content_addressed_reference(value)
    parts = PurePosixPath(str(value["path"])).parts
    expected = (
        "verification", "project-diagnostic-classification",
        "rust-project-ir", f"{value['sha256']}.json",
    )
    if len(parts) <= len(expected) or tuple(parts[-4:]) != expected:
        raise LedgerError("Cargo classification RustProjectIR path is invalid")


def _reopen_gate(
    ledger_path: Path, gate: Mapping[str, Any],
) -> dict[str, Any]:
    raw: dict[str, bytes] = {}
    for stream in ("stdout", "stderr"):
        reference = gate[f"{stream}_ref"]
        raw[stream] = read_cargo_raw_output(
            ledger_path, reference, gate_kind=str(gate["gate_kind"]),
            stream=stream, expected_sha256=str(reference["sha256"]),
        )
    try:
        stdout = raw["stdout"].decode("utf-8")
    except UnicodeError as error:
        raise LedgerError("Cargo classification stdout is not UTF-8") from error
    diagnostics = cargo_check_diagnostics(
        stdout, str(gate["gate_kind"]).removeprefix("cargo-"),
        int(gate["returncode"]),
    )
    return {
        "status": gate["status"], "returncode": gate["returncode"],
        "diagnostics": diagnostics,
    }


def _partition_binding(partition: CargoDiagnosticPartition) -> dict[str, Any]:
    unit_partitions = [{
        "unit_id": identity[0], "artifact_id": identity[1],
        "event_sha256s": [
            content_sha256({"ordinal": index, "diagnostic": diagnostic})
            for index, diagnostic in enumerate(values)
        ],
    } for identity, values in sorted(partition.unit_diagnostics.items())]
    project_hashes = sorted(
        item["project_diagnostic"]["diagnostic_sha256"]
        for item in partition.project_diagnostics
    )
    return {
        "unit_partitions": unit_partitions,
        "project_diagnostic_sha256s": project_hashes,
        "admission_blocker": partition.admission_blocker,
    }


def _verify_candidate_binding(
    members: list[dict[str, str]], rust_project_ir: Mapping[str, Any],
) -> None:
    candidates = rust_project_ir["bindings"]["candidates"]
    expected = [
        (item["unit_id"], item["artifact_id"], item["content_sha256"])
        for item in members
    ]
    actual = sorted(
        (item["unit_id"], item["artifact_id"], item["source"]["sha256"])
        for item in candidates
    )
    if expected != actual:
        raise LedgerError("Cargo classification candidate IR binding drifted")


__all__ = [
    "reopen_and_verify_classification", "reopen_classification_ir",
    "require_classification_ir_reference", "verify_live_classification",
    "write_classification_ir",
]
