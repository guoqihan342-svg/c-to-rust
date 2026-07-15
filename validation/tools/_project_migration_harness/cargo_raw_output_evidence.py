from __future__ import annotations

import hashlib
from copy import deepcopy
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .artifacts import checked_relative_path
from .bounded_artifact_io import (
    BoundedArtifactIOError, read_bounded_artifact, write_immutable_artifact,
)
from .ledger_security import LedgerError


MAX_CARGO_RAW_OUTPUT_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GATES = {"cargo-check", "cargo-test"}
_STREAMS = {"stdout", "stderr"}


def write_cargo_raw_output(
    out_root: Path, out_root_rel: str, *, gate_kind: str,
    stream: str, data: bytes,
) -> dict[str, Any]:
    _gate_stream(gate_kind, stream)
    if not isinstance(data, bytes) or len(data) > MAX_CARGO_RAW_OUTPUT_BYTES:
        raise ValueError("Cargo raw output exceeds the bounded byte contract")
    digest = hashlib.sha256(data).hexdigest()
    relative = checked_relative_path(
        f"verification/raw-output/{gate_kind}/{stream}/{digest}.bin"
    )
    prefix = checked_relative_path(out_root_rel)
    root = out_root.resolve()
    _require_root_suffix(root, PurePosixPath(prefix).parts)
    try:
        write_immutable_artifact(
            root, PurePosixPath(relative), data, MAX_CARGO_RAW_OUTPUT_BYTES,
        )
    except BoundedArtifactIOError as error:
        raise LedgerError("content-addressed Cargo raw output is immutable") from error
    return {
        "path": f"{prefix}/{relative}",
        "sha256": digest,
        "size_bytes": len(data),
    }


def validate_cargo_raw_output_reference(
    value: Any, *, gate_kind: str, stream: str,
    expected_sha256: str,
) -> dict[str, Any]:
    _gate_stream(gate_kind, stream)
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("Cargo raw output reference schema is invalid")
    digest = value.get("sha256")
    size = value.get("size_bytes")
    path = _relative_path(str(value.get("path")), str(digest), gate_kind, stream)
    if (
        digest != expected_sha256 or _SHA256.fullmatch(str(digest)) is None
        or isinstance(size, bool) or not isinstance(size, int)
        or not 0 <= size <= MAX_CARGO_RAW_OUTPUT_BYTES
        or path.name != f"{digest}.bin"
    ):
        raise ValueError("Cargo raw output reference binding is invalid")
    return {"path": path.as_posix(), "sha256": str(digest), "size_bytes": size}


def read_cargo_raw_output(
    ledger_path: Path, value: Mapping[str, Any], *,
    gate_kind: str, stream: str, expected_sha256: str,
) -> bytes:
    reference = validate_cargo_raw_output_reference(
        value, gate_kind=gate_kind, stream=stream,
        expected_sha256=expected_sha256,
    )
    relative = PurePosixPath(reference["path"])
    database = ledger_path.resolve()
    if database.parent.name != "state":
        raise LedgerError("Cargo raw output requires the fixed ledger state root")
    root = database.parent.parent.resolve(strict=True)
    prefix, suffix = _split_reference(relative, gate_kind, stream)
    try:
        _require_root_suffix(root, prefix)
    except ValueError as error:
        raise LedgerError("Cargo raw output evidence root binding drifted") from error
    target = root.joinpath(*suffix)
    try:
        data = read_bounded_artifact(root, target, MAX_CARGO_RAW_OUTPUT_BYTES)
    except BoundedArtifactIOError as error:
        raise LedgerError("Cargo raw output is not safely readable") from error
    if (
        len(data) != reference["size_bytes"]
        or hashlib.sha256(data).hexdigest() != reference["sha256"]
    ):
        raise LedgerError("Cargo raw output content binding changed")
    return data


def verify_cargo_check_raw_outputs(
    ledger_path: Path, check: Mapping[str, Any], *, gate_kind: str,
) -> None:
    try:
        for stream in _STREAMS:
            read_cargo_raw_output(
                ledger_path, check.get(f"{stream}_ref"),
                gate_kind=gate_kind, stream=stream,
                expected_sha256=str(check.get(f"{stream}_sha256")),
            )
    except (TypeError, ValueError) as error:
        raise LedgerError("Cargo raw output reference is invalid") from error


def persist_captured_cargo_outputs(
    execution: Mapping[str, Any], *, out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    result = deepcopy(dict(execution))
    checks = result.get("checks")
    complete = isinstance(checks, list)
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            complete = False
            continue
        command = check.get("command")
        stage = command[1] if isinstance(command, list) and len(command) > 1 else None
        gate_kind = f"cargo-{stage}" if stage in {"check", "test"} else None
        executed = check.get("cargo_executed") is True and check.get("status") in {
            "passed", "failed",
        }
        for stream in _STREAMS:
            captured = check.pop(f"_captured_{stream}", None)
            reference = check.get(f"{stream}_ref")
            digest = str(check.get(f"{stream}_sha256"))
            if not executed:
                check[f"{stream}_ref"] = None
                continue
            try:
                if reference is not None and gate_kind is not None:
                    validate_cargo_raw_output_reference(
                        reference, gate_kind=gate_kind, stream=stream,
                        expected_sha256=digest,
                    )
                    continue
                if not isinstance(captured, bytes) or gate_kind is None:
                    raise ValueError("captured Cargo output is unavailable")
                if hashlib.sha256(captured).hexdigest() != digest:
                    raise ValueError("captured Cargo output hash drifted")
                check[f"{stream}_ref"] = write_cargo_raw_output(
                    out_root, out_root_rel, gate_kind=gate_kind,
                    stream=stream, data=captured,
                )
            except (OSError, TypeError, ValueError, LedgerError):
                check[f"{stream}_ref"] = None
                complete = False
    if not complete and result.get("status") != "blocked":
        result["status"] = "blocked"
        diagnostics = result.get("diagnostics")
        if not isinstance(diagnostics, list):
            diagnostics = []
        result["diagnostics"] = [*diagnostics, {
            "code": "cargo_raw_output_unavailable",
            "stage": "cargo-evidence",
            "message": "Cargo raw output could not be persisted and rebound",
        }]
    return result


def _relative_path(
    value: str, digest: str, gate_kind: str, stream: str,
) -> PurePosixPath:
    try:
        normalized = checked_relative_path(value)
    except ValueError as error:
        raise ValueError("Cargo raw output path is invalid") from error
    path = PurePosixPath(normalized)
    expected = (
        "verification", "raw-output", gate_kind, stream, f"{digest}.bin",
    )
    if len(path.parts) <= len(expected) or tuple(path.parts[-5:]) != expected:
        raise ValueError("Cargo raw output path binding is invalid")
    return path


def _gate_stream(gate_kind: str, stream: str) -> None:
    if gate_kind not in _GATES or stream not in _STREAMS:
        raise ValueError("Cargo raw output gate or stream is invalid")


def _split_reference(
    path: PurePosixPath, gate_kind: str, stream: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    suffix = (
        "verification", "raw-output", gate_kind, stream, path.name,
    )
    if tuple(path.parts[-5:]) != suffix:
        raise LedgerError("Cargo raw output path binding is invalid")
    return tuple(path.parts[:-5]), suffix


def _require_root_suffix(root: Path, prefix: tuple[str, ...]) -> None:
    if not prefix or len(root.parts) < len(prefix):
        raise ValueError("Cargo raw output evidence root is invalid")
    actual = tuple(part.casefold() for part in root.parts[-len(prefix):])
    expected = tuple(part.casefold() for part in prefix)
    if actual != expected:
        raise ValueError("Cargo raw output evidence root binding drifted")


__all__ = [
    "MAX_CARGO_RAW_OUTPUT_BYTES", "persist_captured_cargo_outputs",
    "read_cargo_raw_output",
    "validate_cargo_raw_output_reference", "verify_cargo_check_raw_outputs",
    "write_cargo_raw_output",
]
