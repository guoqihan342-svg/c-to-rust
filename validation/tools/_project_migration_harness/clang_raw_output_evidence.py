from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .artifacts import checked_relative_path
from .bounded_artifact_io import (
    BoundedArtifactIOError, read_bounded_artifact, write_immutable_artifact,
)
from .clang_interface_fact_evidence import MAX_AST_BYTES
from .clang_record_layout_fact_evidence import (
    MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES,
)
from .ledger_security import LedgerError


MAX_CLANG_AST_RAW_OUTPUT_BYTES = MAX_AST_BYTES
MAX_CLANG_RECORD_LAYOUT_RAW_OUTPUT_BYTES = (
    MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES
)
CLANG_RAW_OUTPUT_GATES = ("clang-ast", "clang-record-layout")
CLANG_RAW_OUTPUT_STREAMS = ("stdout", "stderr")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UNIT_ID = re.compile(r"[^\r\n\x00]{1,1024}\Z")
_PAIR_FIELDS = {
    "schema_version", "gate_kind", "plan_sha256", "unit_id",
    "unit_id_sha256", "stdout_ref", "stdout_sha256", "stderr_ref",
    "stderr_sha256",
}


def write_clang_raw_output(
    out_root: Path, out_root_rel: str, *, gate_kind: str,
    stream: str, plan_sha256: str, unit_id: str, data: bytes,
) -> dict[str, Any]:
    limit = _gate_stream_limit(gate_kind, stream)
    plan, unit_digest = clang_raw_output_identity(plan_sha256, unit_id)
    if type(data) is not bytes or len(data) > limit:
        raise ValueError("Clang raw output exceeds the bounded byte contract")
    digest = hashlib.sha256(data).hexdigest()
    relative = checked_relative_path(
        f"verification/raw-output/clang/{plan}/{unit_digest}/"
        f"{gate_kind}/{stream}/{digest}.bin"
    )
    prefix = checked_relative_path(out_root_rel)
    root = Path(out_root).resolve()
    _require_root_suffix(root, PurePosixPath(prefix).parts)
    try:
        write_immutable_artifact(root, PurePosixPath(relative), data, limit)
    except BoundedArtifactIOError as error:
        raise LedgerError("content-addressed Clang raw output is immutable") from error
    return {
        "path": f"{prefix}/{relative}",
        "sha256": digest,
        "size_bytes": len(data),
    }


def write_clang_raw_outputs(
    out_root: Path, out_root_rel: str, *, gate_kind: str,
    plan_sha256: str, unit_id: str, stdout: bytes, stderr: bytes,
) -> dict[str, Any]:
    _validate_pair_bytes(gate_kind, stdout, stderr)
    plan, unit_digest = clang_raw_output_identity(plan_sha256, unit_id)
    result: dict[str, Any] = {
        "schema_version": 1, "gate_kind": gate_kind,
        "plan_sha256": plan, "unit_id": unit_id,
        "unit_id_sha256": unit_digest,
    }
    for stream, data in (("stdout", stdout), ("stderr", stderr)):
        reference = write_clang_raw_output(
            out_root, out_root_rel, gate_kind=gate_kind,
            stream=stream, plan_sha256=plan, unit_id=unit_id, data=data,
        )
        result[f"{stream}_sha256"] = reference["sha256"]
        result[f"{stream}_ref"] = reference
    return result


def validate_clang_raw_output_reference(
    value: Any, *, gate_kind: str, stream: str,
    plan_sha256: str, unit_id: str, expected_sha256: str,
) -> dict[str, Any]:
    limit = _gate_stream_limit(gate_kind, stream)
    plan, unit_digest = clang_raw_output_identity(plan_sha256, unit_id)
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("Clang raw output reference schema is invalid")
    path_value = value.get("path")
    digest = value.get("sha256")
    size = value.get("size_bytes")
    if (
        type(path_value) is not str or type(digest) is not str
        or type(expected_sha256) is not str
        or _SHA256.fullmatch(digest) is None
        or _SHA256.fullmatch(expected_sha256) is None
        or digest != expected_sha256
        or type(size) is not int or not 0 <= size <= limit
    ):
        raise ValueError("Clang raw output reference binding is invalid")
    path = _relative_path(
        path_value, digest, gate_kind, stream, plan, unit_digest,
    )
    return {"path": path.as_posix(), "sha256": digest, "size_bytes": size}


def validate_clang_raw_output_references(
    value: Any, *, gate_kind: str, plan_sha256: str, unit_id: str,
) -> dict[str, Any]:
    _gate_stream_limit(gate_kind, "stdout")
    if not isinstance(value, Mapping) or set(value) != _PAIR_FIELDS:
        raise ValueError("Clang raw output reference pair schema is invalid")
    plan, unit_digest = clang_raw_output_identity(plan_sha256, unit_id)
    if value.get("schema_version") != 1 or any((
        value.get("gate_kind") != gate_kind,
        value.get("plan_sha256") != plan,
        value.get("unit_id") != unit_id,
        value.get("unit_id_sha256") != unit_digest,
    )):
        raise ValueError("Clang raw output execution binding is invalid")
    result: dict[str, Any] = {}
    for stream in CLANG_RAW_OUTPUT_STREAMS:
        digest = value.get(f"{stream}_sha256")
        reference = validate_clang_raw_output_reference(
            value.get(f"{stream}_ref"), gate_kind=gate_kind, stream=stream,
            plan_sha256=plan, unit_id=unit_id, expected_sha256=digest,
        )
        result[f"{stream}_sha256"] = digest
        result[f"{stream}_ref"] = reference
    _validate_pair_sizes(
        gate_kind, result["stdout_ref"]["size_bytes"],
        result["stderr_ref"]["size_bytes"],
    )
    return result


def read_clang_raw_output(
    ledger_path: Path, value: Mapping[str, Any], *, gate_kind: str,
    stream: str, plan_sha256: str, unit_id: str, expected_sha256: str,
) -> bytes:
    reference = validate_clang_raw_output_reference(
        value, gate_kind=gate_kind, stream=stream,
        plan_sha256=plan_sha256, unit_id=unit_id,
        expected_sha256=expected_sha256,
    )
    relative = PurePosixPath(reference["path"])
    database = Path(ledger_path).resolve()
    if database.parent.name != "state":
        raise LedgerError("Clang raw output requires the fixed ledger state root")
    root = database.parent.parent.resolve(strict=True)
    plan, unit_digest = clang_raw_output_identity(plan_sha256, unit_id)
    prefix, suffix = _split_reference(
        relative, gate_kind, stream, plan, unit_digest,
    )
    try:
        _require_root_suffix(root, prefix)
    except ValueError as error:
        raise LedgerError("Clang raw output evidence root binding drifted") from error
    target = root.joinpath(*suffix)
    try:
        data = read_bounded_artifact(
            root, target, _gate_stream_limit(gate_kind, stream),
        )
    except BoundedArtifactIOError as error:
        raise LedgerError("Clang raw output is not safely readable") from error
    if (
        len(data) != reference["size_bytes"]
        or hashlib.sha256(data).hexdigest() != reference["sha256"]
    ):
        raise LedgerError("Clang raw output content binding changed")
    return data


def read_clang_raw_outputs(
    ledger_path: Path, value: Mapping[str, Any], *, gate_kind: str,
    plan_sha256: str, unit_id: str,
) -> dict[str, bytes]:
    try:
        references = validate_clang_raw_output_references(
            value, gate_kind=gate_kind, plan_sha256=plan_sha256,
            unit_id=unit_id,
        )
    except (TypeError, ValueError) as error:
        raise LedgerError("Clang raw output reference pair is invalid") from error
    result = {}
    for stream in CLANG_RAW_OUTPUT_STREAMS:
        result[stream] = read_clang_raw_output(
            ledger_path, references[f"{stream}_ref"], gate_kind=gate_kind,
            stream=stream, plan_sha256=plan_sha256, unit_id=unit_id,
            expected_sha256=references[f"{stream}_sha256"],
        )
    return result


def verify_clang_raw_outputs(
    ledger_path: Path, value: Mapping[str, Any], *, gate_kind: str,
    plan_sha256: str, unit_id: str,
) -> None:
    read_clang_raw_outputs(
        ledger_path, value, gate_kind=gate_kind,
        plan_sha256=plan_sha256, unit_id=unit_id,
    )


def _relative_path(
    value: str, digest: str, gate_kind: str, stream: str,
    plan_sha256: str, unit_id_sha256: str,
) -> PurePosixPath:
    try:
        normalized = checked_relative_path(value)
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError("Clang raw output path is invalid") from error
    path = PurePosixPath(normalized)
    suffix = (
        "verification", "raw-output", "clang", plan_sha256, unit_id_sha256,
        gate_kind, stream, f"{digest}.bin",
    )
    if len(path.parts) <= len(suffix) or tuple(path.parts[-8:]) != suffix:
        raise ValueError("Clang raw output path binding is invalid")
    return path


def _gate_stream_limit(gate_kind: str, stream: str) -> int:
    if type(gate_kind) is not str or gate_kind not in CLANG_RAW_OUTPUT_GATES:
        raise ValueError("Clang raw output gate is invalid")
    if type(stream) is not str or stream not in CLANG_RAW_OUTPUT_STREAMS:
        raise ValueError("Clang raw output stream is invalid")
    return (
        MAX_CLANG_AST_RAW_OUTPUT_BYTES
        if gate_kind == "clang-ast"
        else MAX_CLANG_RECORD_LAYOUT_RAW_OUTPUT_BYTES
    )


def _validate_pair_bytes(gate_kind: str, stdout: Any, stderr: Any) -> None:
    if type(stdout) is not bytes or type(stderr) is not bytes:
        raise TypeError("Clang raw stdout and stderr must be bytes")
    for stream, data in (("stdout", stdout), ("stderr", stderr)):
        if len(data) > _gate_stream_limit(gate_kind, stream):
            raise ValueError("Clang raw output exceeds the bounded byte contract")
    _validate_pair_sizes(gate_kind, len(stdout), len(stderr))


def _validate_pair_sizes(gate_kind: str, stdout: int, stderr: int) -> None:
    if (
        gate_kind == "clang-record-layout"
        and stdout + stderr > MAX_CLANG_RECORD_LAYOUT_RAW_OUTPUT_BYTES
    ):
        raise ValueError("Clang record-layout raw outputs exceed the parser byte contract")


def _split_reference(
    path: PurePosixPath, gate_kind: str, stream: str,
    plan_sha256: str, unit_id_sha256: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    suffix = (
        "verification", "raw-output", "clang", plan_sha256, unit_id_sha256,
        gate_kind, stream, path.name,
    )
    if tuple(path.parts[-8:]) != suffix:
        raise LedgerError("Clang raw output path binding is invalid")
    return tuple(path.parts[:-8]), suffix


def _require_root_suffix(root: Path, prefix: tuple[str, ...]) -> None:
    if not prefix or len(root.parts) < len(prefix):
        raise ValueError("Clang raw output evidence root is invalid")
    actual = tuple(part.casefold() for part in root.parts[-len(prefix):])
    expected = tuple(part.casefold() for part in prefix)
    if actual != expected:
        raise ValueError("Clang raw output evidence root binding drifted")


def clang_raw_output_identity(plan_sha256: Any, unit_id: Any) -> tuple[str, str]:
    if type(plan_sha256) is not str or _SHA256.fullmatch(plan_sha256) is None:
        raise ValueError("Clang raw output plan SHA-256 is invalid")
    if type(unit_id) is not str or _UNIT_ID.fullmatch(unit_id) is None:
        raise ValueError("Clang raw output unit identity is invalid")
    digest = hashlib.sha256(
        b"clang-raw-output-unit-v1\0" + unit_id.encode("utf-8")
    ).hexdigest()
    return plan_sha256, digest


__all__ = [
    "CLANG_RAW_OUTPUT_GATES", "CLANG_RAW_OUTPUT_STREAMS",
    "clang_raw_output_identity",
    "MAX_CLANG_AST_RAW_OUTPUT_BYTES",
    "MAX_CLANG_RECORD_LAYOUT_RAW_OUTPUT_BYTES", "read_clang_raw_output",
    "read_clang_raw_outputs", "validate_clang_raw_output_reference",
    "validate_clang_raw_output_references", "verify_clang_raw_outputs",
    "write_clang_raw_output", "write_clang_raw_outputs",
]
