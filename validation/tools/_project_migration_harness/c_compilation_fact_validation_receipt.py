from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .build_ir import is_sha256
from .c_compilation_fact_raw import (
    MAX_C_COMPILER_STDERR_BYTES, MAX_C_COMPILER_STDOUT_BYTES,
)


_FIELDS = {
    "schema_version", "artifact_kind", "unit_id", "source_sha256",
    "expanded_argv_sha256", "toolchain_id", "toolchain_binding_sha256",
    "compile_context_sha256", "plan_sha256", "sandbox_probe_sha256",
    "status", "reason_code", "command_started", "returncode",
    "timed_out", "output_limit_exceeded", "diagnostics_sha256",
    "diagnostic_bytes", "raw_outputs", "semantic_gate",
    "translation_coverage_numerator", "receipt_sha256",
}
_RAW_FIELDS = {
    "schema_version", "unit_id", "unit_id_sha256", "plan_sha256",
    "stdout_sha256", "stdout_ref", "stderr_sha256", "stderr_ref",
}
_REFERENCE_FIELDS = {"path", "sha256", "size_bytes"}
_REASON = re.compile(r"[A-Za-z0-9_.-]{1,160}\Z", re.ASCII)
_UNIT = re.compile(r"[^\r\n\x00]{1,4096}\Z")
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def validate_compilation_receipt(
    value: Any, toolchains: Mapping[str, Mapping[str, Any]], probe_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ValueError("c_compilation_fact_receipt_fields_invalid")
    receipt = dict(value)
    core = {key: receipt[key] for key in _FIELDS - {"receipt_sha256"}}
    binding = toolchains.get(str(receipt.get("toolchain_id")))
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != "c-compilation-syntax-receipt"
        or receipt.get("status") not in {"syntax_passed", "blocked"}
        or receipt.get("receipt_sha256") != content_sha256(core)
        or receipt.get("semantic_gate") is not False
        or receipt.get("translation_coverage_numerator") != 0
        or not isinstance(receipt.get("unit_id"), str)
        or _UNIT.fullmatch(receipt["unit_id"]) is None
        or any(not is_sha256(receipt.get(key)) for key in (
            "source_sha256", "expanded_argv_sha256", "compile_context_sha256",
            "plan_sha256", "sandbox_probe_sha256", "diagnostics_sha256",
        ))
        or binding is None
        or receipt.get("toolchain_binding_sha256")
        != binding.get("binding_sha256")
        or receipt.get("sandbox_probe_sha256") != probe_sha256
        or type(receipt.get("command_started")) is not bool
        or type(receipt.get("timed_out")) is not bool
        or type(receipt.get("output_limit_exceeded")) is not bool
        or not _returncode(receipt.get("returncode"))
    ):
        raise ValueError("c_compilation_fact_receipt_invalid")
    raw = _validate_raw_outputs(receipt)
    _validate_execution(receipt, raw is not None)
    return receipt


def valid_reason_code(value: Any) -> bool:
    return isinstance(value, str) and _REASON.fullmatch(value) is not None


def _validate_raw_outputs(receipt: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = receipt.get("raw_outputs")
    if raw is None:
        if (
            receipt.get("diagnostics_sha256") != _EMPTY_SHA256
            or receipt.get("diagnostic_bytes") != 0
        ):
            raise ValueError("c_compilation_fact_raw_output_invalid")
        return None
    if not isinstance(raw, Mapping) or set(raw) != _RAW_FIELDS:
        raise ValueError("c_compilation_fact_raw_output_invalid")
    unit_id = str(receipt["unit_id"])
    unit_sha256 = hashlib.sha256(unit_id.encode("utf-8")).hexdigest()
    if (
        raw.get("schema_version") != 1
        or raw.get("unit_id") != unit_id
        or raw.get("unit_id_sha256") != unit_sha256
        or raw.get("plan_sha256") != receipt["plan_sha256"]
    ):
        raise ValueError("c_compilation_fact_raw_output_invalid")
    checked = {}
    for stream, limit in (
        ("stdout", MAX_C_COMPILER_STDOUT_BYTES),
        ("stderr", MAX_C_COMPILER_STDERR_BYTES),
    ):
        checked[stream] = _validate_reference(
            raw.get(f"{stream}_ref"), stream=stream, limit=limit,
            digest=raw.get(f"{stream}_sha256"),
            plan_sha256=receipt["plan_sha256"], unit_sha256=unit_sha256,
        )
    if (
        receipt.get("diagnostics_sha256") != checked["stderr"]["sha256"]
        or receipt.get("diagnostic_bytes") != checked["stderr"]["size_bytes"]
    ):
        raise ValueError("c_compilation_fact_diagnostics_binding_invalid")
    return dict(raw)


def _validate_reference(
    value: Any, *, stream: str, limit: int, digest: Any,
    plan_sha256: str, unit_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REFERENCE_FIELDS:
        raise ValueError("c_compilation_fact_raw_reference_invalid")
    size = value.get("size_bytes")
    if (
        not is_sha256(digest) or value.get("sha256") != digest
        or type(size) is not int or not 0 <= size <= limit
    ):
        raise ValueError("c_compilation_fact_raw_reference_invalid")
    expected = (
        "verification/raw-output/c-compilation/"
        f"{plan_sha256}/{unit_sha256}/{stream}/{digest}.bin"
    )
    try:
        path = checked_relative_path(value.get("path"))
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError("c_compilation_fact_raw_reference_invalid") from error
    if PurePosixPath(path).as_posix() != expected:
        raise ValueError("c_compilation_fact_raw_reference_invalid")
    return {"path": path, "sha256": digest, "size_bytes": size}


def _validate_execution(receipt: Mapping[str, Any], has_raw: bool) -> None:
    passed = receipt["status"] == "syntax_passed"
    reason = receipt.get("reason_code")
    started = receipt["command_started"]
    returncode = receipt["returncode"]
    timed_out = receipt["timed_out"]
    output_limit = receipt["output_limit_exceeded"]
    if passed:
        valid = (
            reason is None and started and returncode == 0
            and not timed_out and not output_limit and has_raw
        )
    elif not valid_reason_code(reason):
        valid = False
    elif not started:
        valid = returncode is None and not timed_out and not output_limit and (
            not has_raw or reason == "compiler_process_not_started"
        )
    elif timed_out:
        valid = has_raw and reason == "compiler_execution_timeout"
    elif output_limit:
        valid = has_raw and reason == "compiler_output_limit_exceeded"
    elif returncode != 0:
        valid = has_raw and returncode is not None and reason == "compiler_nonzero_exit"
    else:
        valid = has_raw and reason in {
            "compiler_runtime_cleanup_failed", "compiler_toolchain_drifted",
        }
    if not valid:
        raise ValueError("c_compilation_fact_receipt_execution_invalid")


def _returncode(value: Any) -> bool:
    return value is None or type(value) is int and -(2**31) <= value < 2**31


__all__ = ["valid_reason_code", "validate_compilation_receipt"]
