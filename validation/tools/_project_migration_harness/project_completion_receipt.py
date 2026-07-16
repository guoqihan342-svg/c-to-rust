from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifact_verification import read_verified_json_object
from .artifacts import canonical_json_bytes, write_json_artifact
from .build_facts import is_linklike
from .ledger_security import LedgerError, assert_no_secrets
from .project_completion_receipt_finalization import (
    finalization_payload, validate_receipt_finalization,
)


COMPLETION_RECEIPT_PATH = "completion/completion-receipt.json"
MAX_COMPLETION_RECEIPT_BYTES = 2 * 1024 * 1024
_RECEIPT_KEYS_V1 = {
    "schema_version", "artifact_kind", "status", "run_id",
    "candidate_set_sha256", "project_final_record_id",
    "project_final_evidence", "build_ir_verifications",
    "project_test_evidence", "semantic_gate",
}
_RECEIPT_KEYS = _RECEIPT_KEYS_V1 | {"finalization"}
_REFERENCE_KEYS = {"path", "sha256", "size_bytes"}
_BUILD_PHASES = {
    "before_candidate_execution": "before-candidate-execution",
    "before_project_final": "before-project-final",
}


def completion_receipt_payload(
    *, run_id: str, candidate_set_sha256: str,
    project_final: Mapping[str, Any], project_test_evidence: Mapping[str, Any],
    initial_build_ir_ref: Mapping[str, Any],
    final_build_ir_ref: Mapping[str, Any],
    finalization: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "artifact_kind": "project-completion-receipt",
        "status": "completed",
        "run_id": run_id,
        "candidate_set_sha256": candidate_set_sha256,
        "project_final_record_id": project_final["record_id"],
        "project_final_evidence": project_final["evidence"],
        "build_ir_verifications": {
            "before_candidate_execution": dict(initial_build_ir_ref),
            "before_project_final": dict(final_build_ir_ref),
        },
        "project_test_evidence": dict(project_test_evidence),
        "finalization": finalization_payload(finalization),
        "semantic_gate": True,
    }


def write_durable_completion_receipt(
    out_root: Path, payload: Mapping[str, Any],
) -> dict[str, Any]:
    value = dict(payload)
    _validate_receipt_shape(value)
    _validate_build_ir_bindings(out_root, value)
    reference = write_json_artifact(out_root, COMPLETION_RECEIPT_PATH, value)
    target = out_root.resolve(strict=True) / COMPLETION_RECEIPT_PATH
    # Windows only exposes FlushFileBuffers through a writable descriptor.
    with target.open("r+b") as handle:
        os.fsync(handle.fileno())
    _fsync_directory(target.parent)
    _fsync_directory(target.parent.parent)
    reopened, actual = _read_receipt(out_root)
    if reopened != value or actual != reference:
        raise LedgerError("project completion receipt durable reopen drifted")
    return reference


def read_completion_receipt(
    database_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out_root = database_path.resolve().parent.parent
    receipt, reference = _read_receipt(out_root)
    _validate_build_ir_bindings(out_root, receipt)
    return receipt, reference


def validate_completion_receipt_bindings(
    receipt: Mapping[str, Any], reference: Mapping[str, Any], *,
    run_id: str, candidate_set_sha256: str,
    project_gate_records: Sequence[tuple[Any, Mapping[str, Any]]],
    finalization: Mapping[str, Any] | None = None,
) -> None:
    _validate_receipt_shape(receipt)
    if (
        reference.get("path") != COMPLETION_RECEIPT_PATH
        or receipt.get("run_id") != run_id
        or receipt.get("candidate_set_sha256") != candidate_set_sha256
    ):
        raise LedgerError("project completion receipt run/candidate binding drifted")
    by_kind = {
        str(row["gate_kind"]): (row, payload)
        for row, payload in project_gate_records
    }
    final = by_kind.get("final-verification")
    oracle = by_kind.get("oracle-replay")
    if final is None or oracle is None:
        raise LedgerError("project completion receipt gate bundle is incomplete")
    final_row, final_payload = final
    expected_final = {
        "path": str(final_row["evidence_path"]),
        "sha256": str(final_row["evidence_sha256"]),
        "size_bytes": len(canonical_json_bytes(final_payload)),
    }
    tests = receipt.get("project_test_evidence")
    summary = tests.get("summary") if isinstance(tests, Mapping) else None
    if (
        receipt.get("project_final_record_id") != str(final_row["record_id"])
        or receipt.get("project_final_evidence") != expected_final
        or not isinstance(tests, Mapping)
        or tests.get("artifact_kind") != "project-test-semantic-evidence-binding"
        or tests.get("status") != "verified"
        or tests.get("semantic_gate") is not False
        or tests.get("project_gate_record_id") != str(oracle[0]["record_id"])
        or not isinstance(summary, Mapping)
        or not _positive_int(summary.get("case_count"))
        or summary.get("mismatch_count") != 0
        or summary.get("crash_count") != 0
    ):
        raise LedgerError("project completion receipt host evidence binding drifted")
    if receipt.get("schema_version") == 2:
        validate_receipt_finalization(receipt, finalization)
    elif finalization is not None:
        raise LedgerError("legacy completion receipt cannot complete a finalizing run")


def _read_receipt(out_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = out_root.resolve(strict=True)
    target = root / COMPLETION_RECEIPT_PATH
    current = root
    for part in Path(COMPLETION_RECEIPT_PATH).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise LedgerError("project completion receipt path contains a link")
    if not target.is_file():
        raise LedgerError("project completion receipt is missing")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as error:
        raise LedgerError("project completion receipt cannot be opened safely") from error
    try:
        size = os.fstat(descriptor).st_size
        if size <= 0 or size > MAX_COMPLETION_RECEIPT_BYTES:
            raise LedgerError("project completion receipt size is invalid")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            data = handle.read(MAX_COMPLETION_RECEIPT_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) != size or len(data) > MAX_COMPLETION_RECEIPT_BYTES:
        raise LedgerError("project completion receipt changed while reading")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("project completion receipt is not canonical JSON") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        raise LedgerError("project completion receipt is not canonical JSON")
    _validate_receipt_shape(payload)
    return payload, {
        "path": COMPLETION_RECEIPT_PATH,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": size,
    }


def _validate_receipt_shape(receipt: Mapping[str, Any]) -> None:
    try:
        assert_no_secrets(receipt, "completion_receipt")
    except ValueError as error:
        raise LedgerError("project completion receipt contains sensitive data") from error
    final = receipt.get("project_final_evidence")
    builds = receipt.get("build_ir_verifications")
    version = receipt.get("schema_version")
    keys = _RECEIPT_KEYS if version == 2 else _RECEIPT_KEYS_V1
    if (
        set(receipt) != keys
        or version not in {1, 2}
        or receipt.get("artifact_kind") != "project-completion-receipt"
        or receipt.get("status") != "completed"
        or receipt.get("semantic_gate") is not True
        or not _nonempty(receipt.get("run_id"))
        or not _sha(receipt.get("candidate_set_sha256"))
        or not _nonempty(receipt.get("project_final_record_id"))
        or not _reference(final)
        or not isinstance(builds, Mapping)
        or set(builds) != set(_BUILD_PHASES)
        or not all(_reference(builds.get(key)) for key in _BUILD_PHASES)
        or not isinstance(receipt.get("project_test_evidence"), Mapping)
    ):
        raise LedgerError("project completion receipt schema is invalid")


def _validate_build_ir_bindings(out_root: Path, receipt: Mapping[str, Any]) -> None:
    builds = receipt["build_ir_verifications"]
    for key, phase in _BUILD_PHASES.items():
        reference = builds[key]
        expected_path = f"completion/project-final-build-ir-{phase}.json"
        if reference.get("path") != expected_path:
            raise LedgerError("project completion BuildIR receipt path is invalid")
        try:
            payload = read_verified_json_object(
                out_root, reference, max_bytes=MAX_COMPLETION_RECEIPT_BYTES,
            )
        except (OSError, TypeError, ValueError) as error:
            raise LedgerError("project completion BuildIR receipt drifted") from error
        if (
            payload.get("artifact_kind") != "project-final-build-ir-verification"
            or payload.get("status") != "verified"
            or payload.get("verification_phase") != phase
        ):
            raise LedgerError("project completion BuildIR receipt is not verified")


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reference(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == _REFERENCE_KEYS
        and _nonempty(value.get("path"))
        and _sha(value.get("sha256"))
        and _positive_int(value.get("size_bytes"))
    )


def _sha(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


__all__ = [
    "COMPLETION_RECEIPT_PATH", "completion_receipt_payload",
    "read_completion_receipt", "validate_completion_receipt_bindings",
    "write_durable_completion_receipt",
]
