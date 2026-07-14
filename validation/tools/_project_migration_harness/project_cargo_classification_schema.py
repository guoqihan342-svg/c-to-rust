from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_raw_output_evidence import validate_cargo_raw_output_reference
from .gate_evidence import require_content_addressed_reference
from .ledger_security import LedgerError
from .sandbox_execution_schema import is_sha256


GATES = ("cargo-check", "cargo-test")
_TOP_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id",
    "candidate_set_sha256", "project_input_sha256",
    "rust_project_ir_sha256", "rust_project_interface_sha256",
    "rust_project_ir_ref", "candidate_members", "gates", "admission",
    "claim_boundary",
}
_GATE_KEYS = {
    "gate_kind", "executed", "status", "returncode", "stdout_ref",
    "stderr_ref", "normalized_diagnostics_sha256", "diagnostic_count",
    "unit_partitions", "project_diagnostic_sha256s", "admission_blocker",
}


def validate_cargo_classification_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("Cargo classification receipt fields are invalid")
    result = json.loads(canonical_json_bytes(value).decode("utf-8"))
    if (
        result.get("schema_version") != 1
        or result.get("artifact_kind")
        != "host-cargo-diagnostic-classification"
        or result.get("authority_id") != "host.cargo-diagnostic-classifier.v1"
    ):
        raise ValueError("Cargo classification receipt identity is invalid")
    bounded_text(result.get("run_id"), "run_id")
    for field in (
        "candidate_set_sha256", "project_input_sha256",
        "rust_project_ir_sha256", "rust_project_interface_sha256",
    ):
        sha256_value(result.get(field))
    _validate_ir_reference(result.get("rust_project_ir_ref"))
    if result.get("candidate_members") != candidate_members(
        result.get("candidate_members"),
    ):
        raise ValueError("Cargo classification candidate cohort drifted")
    gates = result.get("gates")
    if (
        not isinstance(gates, list)
        or not all(isinstance(item, Mapping) for item in gates)
        or [item.get("gate_kind") for item in gates] != list(GATES)
    ):
        raise ValueError("Cargo classification gates are invalid")
    for gate in gates:
        _validate_gate(gate)
    if not gates[0]["executed"]:
        raise ValueError("Cargo classification check gate was not executed")
    member_identities = {
        (item["unit_id"], item["artifact_id"])
        for item in result["candidate_members"]
    }
    if any(
        (item["unit_id"], item["artifact_id"]) not in member_identities
        for gate in gates for item in gate["unit_partitions"]
    ):
        raise ValueError("Cargo classification partition owner is invalid")
    if result.get("admission") != admission_value(result.get("admission")):
        raise ValueError("Cargo classification admission drifted")
    if result.get("claim_boundary") != {
        "candidate_only": True, "semantic_gate": False,
        "semantic_pass": False, "translation_coverage_numerator": 0,
    }:
        raise ValueError("Cargo classification claim boundary is invalid")
    return result


def candidate_members(value: Any) -> list[dict[str, str]]:
    if (
        not isinstance(value, Sequence) or isinstance(value, (str, bytes))
        or not value
    ):
        raise ValueError("Cargo classification candidate members are invalid")
    members = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "unit_id", "artifact_id", "content_sha256",
        }:
            raise ValueError("Cargo classification candidate member is invalid")
        members.append({
            "unit_id": bounded_text(item.get("unit_id"), "unit_id"),
            "artifact_id": bounded_text(item.get("artifact_id"), "artifact_id"),
            "content_sha256": sha256_value(item.get("content_sha256")),
        })
    expected = sorted(
        members, key=lambda item: (item["unit_id"], item["artifact_id"]),
    )
    if (
        members != expected
        or len({item["unit_id"] for item in members}) != len(members)
    ):
        raise ValueError("Cargo classification candidate members are not canonical")
    return members


def admission_value(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"schema_version", "status", "blocker_code", "scope"}
        or value.get("schema_version") != 1
        or value.get("status") not in {"admitted", "blocked", "not-applicable"}
        or value.get("scope") != "whole-candidate-cohort"
    ):
        raise ValueError("Cargo classification admission is invalid")
    blocker = value.get("blocker_code")
    if (
        (value.get("status") == "blocked" and blocker is None)
        or (value.get("status") != "blocked" and blocker is not None)
    ):
        raise ValueError("Cargo classification admission blocker is invalid")
    if blocker is not None:
        bounded_text(blocker, "blocker_code")
    return dict(value)


def sha256_value(value: Any) -> str:
    if not is_sha256(value):
        raise ValueError("Cargo classification SHA-256 is invalid")
    return str(value)


def bounded_text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 512
        or "\x00" in value
    ):
        raise ValueError(f"Cargo classification {label} is invalid")
    return value


def _validate_gate(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _GATE_KEYS:
        raise ValueError("Cargo classification gate fields are invalid")
    gate = value.get("gate_kind")
    if gate not in GATES or type(value.get("executed")) is not bool:
        raise ValueError("Cargo classification gate identity is invalid")
    if value["executed"]:
        if (
            value.get("status") not in {"passed", "failed"}
            or type(value.get("returncode")) is not int
        ):
            raise ValueError("Cargo classification execution is invalid")
        for stream in ("stdout", "stderr"):
            reference = value.get(f"{stream}_ref")
            expected = reference.get("sha256") if isinstance(reference, Mapping) else None
            validate_cargo_raw_output_reference(
                reference, gate_kind=str(gate), stream=stream,
                expected_sha256=str(expected),
            )
    elif (
        value.get("status") != "not-executed"
        or any(
            value.get(field) is not None
            for field in ("returncode", "stdout_ref", "stderr_ref")
        )
    ):
        raise ValueError("unexecuted Cargo classification is invalid")
    if not is_sha256(value.get("normalized_diagnostics_sha256")):
        raise ValueError("Cargo classification diagnostic hash is invalid")
    count = value.get("diagnostic_count")
    if (
        isinstance(count, bool) or not isinstance(count, int)
        or not 0 <= count <= 64
    ):
        raise ValueError("Cargo classification diagnostic count is invalid")
    partitioned = _partition_fields(value)
    blocker = value.get("admission_blocker")
    if blocker is not None:
        bounded_text(blocker, "admission_blocker")
    if not value["executed"]:
        if (
            count != 0 or partitioned != 0 or blocker is not None
            or value["normalized_diagnostics_sha256"] != content_sha256([])
        ):
            raise ValueError("unexecuted Cargo classification has diagnostics")
    elif value["status"] == "passed":
        if (
            value["returncode"] != 0 or count != 0
            or partitioned != 0 or blocker is not None
        ):
            raise ValueError("passed Cargo classification is inconsistent")
    elif (
        value["returncode"] == 0
        or blocker is None and partitioned != count
        or blocker is not None and partitioned != 0
    ):
        raise ValueError("failed Cargo classification is inconsistent")


def _partition_fields(value: Mapping[str, Any]) -> int:
    units = value.get("unit_partitions")
    projects = value.get("project_diagnostic_sha256s")
    if not isinstance(units, list) or not isinstance(projects, list):
        raise ValueError("Cargo classification partitions are invalid")
    if not all(isinstance(item, Mapping) for item in units):
        raise ValueError("Cargo classification unit partition is invalid")
    if units != sorted(
        units, key=lambda item: (item.get("unit_id"), item.get("artifact_id")),
    ):
        raise ValueError("Cargo classification unit partitions are not canonical")
    for item in units:
        if not isinstance(item, Mapping) or set(item) != {
            "unit_id", "artifact_id", "event_sha256s",
        }:
            raise ValueError("Cargo classification unit partition is invalid")
        bounded_text(item.get("unit_id"), "unit_id")
        bounded_text(item.get("artifact_id"), "artifact_id")
        if (
            not isinstance(item.get("event_sha256s"), list)
            or not all(is_sha256(sha) for sha in item["event_sha256s"])
        ):
            raise ValueError("Cargo classification unit events are invalid")
    event_hashes = [sha for item in units for sha in item["event_sha256s"]]
    if (
        len(event_hashes) != len(set(event_hashes))
        or projects != sorted(projects)
        or len(projects) != len(set(projects))
        or not all(is_sha256(sha) for sha in projects)
    ):
        raise ValueError("Cargo classification project diagnostics are invalid")
    return len(event_hashes) + len(projects)


def _validate_ir_reference(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("Cargo classification RustProjectIR reference is invalid")
    try:
        require_content_addressed_reference(value)
    except (TypeError, ValueError, LedgerError) as error:
        raise ValueError(
            "Cargo classification RustProjectIR reference is invalid"
        ) from error
    parts = str(value.get("path", "")).replace("\\", "/").split("/")
    expected = [
        "verification", "project-diagnostic-classification",
        "rust-project-ir", f"{value.get('sha256')}.json",
    ]
    if len(parts) <= len(expected) or parts[-4:] != expected:
        raise ValueError("Cargo classification RustProjectIR path is invalid")


__all__ = [
    "GATES", "admission_value", "bounded_text", "candidate_members",
    "sha256_value", "validate_cargo_classification_receipt",
]
