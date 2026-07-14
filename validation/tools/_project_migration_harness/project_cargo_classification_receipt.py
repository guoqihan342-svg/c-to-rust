from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .gate_evidence import (
    read_content_addressed_json, require_content_addressed_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError
from .project_cargo_diagnostic_intake import CargoDiagnosticPartition
from .project_cargo_classification_recompute import (
    reopen_and_verify_classification, verify_live_classification,
    write_classification_ir,
)
from .project_cargo_classification_schema import (
    GATES as _GATES,
    admission_value as _admission,
    bounded_text as _text,
    candidate_members as _members,
    sha256_value as _sha,
    validate_cargo_classification_receipt,
)


def write_cargo_classification_receipt(
    out_root: Path, out_root_rel: str, *, run_id: str,
    candidate_set_sha256: str, project_input_sha256: str,
    rust_project_ir: Mapping[str, Any],
    candidate_members: Sequence[Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Any]],
    partitions: Mapping[str, CargoDiagnosticPartition],
    admission: Mapping[str, Any],
) -> dict[str, Any]:
    gates = [
        _gate_payload(gate, checks.get(gate), partitions.get(gate))
        for gate in _GATES
    ]
    ir_reference = write_classification_ir(
        out_root, out_root_rel, rust_project_ir,
    )
    payload = {
        "schema_version": 1,
        "artifact_kind": "host-cargo-diagnostic-classification",
        "authority_id": "host.cargo-diagnostic-classifier.v1",
        "run_id": _text(run_id, "run_id"),
        "candidate_set_sha256": _sha(candidate_set_sha256),
        "project_input_sha256": _sha(project_input_sha256),
        "rust_project_ir_sha256": _sha(str(rust_project_ir.get("ir_sha256"))),
        "rust_project_interface_sha256": _sha(
            str(rust_project_ir.get("interface_sha256")),
        ),
        "rust_project_ir_ref": ir_reference,
        "candidate_members": _members(candidate_members),
        "gates": gates,
        "admission": _admission(admission),
        "claim_boundary": {
            "candidate_only": True,
            "semantic_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }
    validate_cargo_classification_receipt(payload)
    verify_live_classification(payload, checks, rust_project_ir)
    reference = write_content_addressed_json(
        out_root, "project-diagnostic-classification", payload,
    )
    return {**reference, "path": f"{out_root_rel}/{reference['path']}"}


def verify_cargo_classification_receipt(
    ledger_path: Path, reference: Mapping[str, Any], *,
    run_id: str, candidate_set_sha256: str, project_input_sha256: str,
    observation: Mapping[str, Any], gate_kind: str,
    rust_project_ir_sha256: str | None = None,
    rust_project_interface_sha256: str | None = None,
) -> dict[str, Any]:
    try:
        require_cargo_classification_reference(reference)
        receipt = validate_cargo_classification_receipt(
            read_content_addressed_json(
                ledger_path, str(reference["path"]), str(reference["sha256"]),
            )
        )
    except (TypeError, ValueError) as error:
        raise LedgerError("Cargo classification receipt is invalid") from error
    if (
        receipt["run_id"] != run_id
        or receipt["candidate_set_sha256"] != candidate_set_sha256
        or receipt["project_input_sha256"] != project_input_sha256
        or (
            rust_project_ir_sha256 is not None
            and receipt["rust_project_ir_sha256"] != rust_project_ir_sha256
        )
        or (
            rust_project_interface_sha256 is not None
            and receipt["rust_project_interface_sha256"]
            != rust_project_interface_sha256
        )
    ):
        raise LedgerError("Cargo classification receipt binding drifted")
    reopen_and_verify_classification(ledger_path, receipt)
    target = next(item for item in receipt["gates"] if item["gate_kind"] == gate_kind)
    _bind_observation(target, observation)
    return receipt


def _gate_payload(
    gate_kind: str, check: Mapping[str, Any] | None,
    partition: CargoDiagnosticPartition | None,
) -> dict[str, Any]:
    diagnostics = check.get("diagnostics") if isinstance(check, Mapping) else []
    if not isinstance(diagnostics, list) or len(diagnostics) > 64:
        raise ValueError("Cargo classification diagnostics are invalid")
    executed = isinstance(check, Mapping)
    unit_partitions = []
    project_hashes: list[str] = []
    blocker = None
    if partition is not None:
        blocker = partition.admission_blocker
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
    partitioned = sum(len(item["event_sha256s"]) for item in unit_partitions) + len(project_hashes)
    if blocker is None and executed and check.get("status") == "failed" and partitioned != len(diagnostics):
        raise ValueError("Cargo classification does not cover every diagnostic")
    return {
        "gate_kind": gate_kind,
        "executed": executed,
        "status": str(check.get("status")) if executed else "not-executed",
        "returncode": check.get("returncode") if executed else None,
        "stdout_ref": check.get("stdout_ref") if executed else None,
        "stderr_ref": check.get("stderr_ref") if executed else None,
        "normalized_diagnostics_sha256": content_sha256(diagnostics),
        "diagnostic_count": len(diagnostics),
        "unit_partitions": unit_partitions,
        "project_diagnostic_sha256s": project_hashes,
        "admission_blocker": blocker,
    }


def _bind_observation(gate: Mapping[str, Any], observation: Mapping[str, Any]) -> None:
    check = observation.get("check")
    if observation.get("outcome") == "executed":
        if not gate["executed"] or not isinstance(check, Mapping):
            raise LedgerError("Cargo classification hid its gate observation")
        changed = next((
            field for field in (
                "status", "returncode", "stdout_ref", "stderr_ref",
            )
            if check.get(field) != gate.get(field)
        ), None)
        if changed is not None:
            raise LedgerError(
                f"Cargo classification changed gate field: {changed}"
            )
    elif gate["executed"]:
        raise LedgerError("Cargo classification hid an executed gate")


def require_cargo_classification_reference(value: Mapping[str, Any]) -> None:
    require_content_addressed_reference(value)
    parts = PurePosixPath(str(value["path"])).parts
    expected = (
        "verification", "project-diagnostic-classification",
        f"{value['sha256']}.json",
    )
    if len(parts) <= len(expected) or tuple(parts[-3:]) != expected:
        raise LedgerError("Cargo classification receipt path is invalid")


__all__ = [
    "require_cargo_classification_reference",
    "validate_cargo_classification_receipt",
    "verify_cargo_classification_receipt",
    "write_cargo_classification_receipt",
]
