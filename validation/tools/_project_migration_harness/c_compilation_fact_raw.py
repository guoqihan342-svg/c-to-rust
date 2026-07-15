from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import checked_relative_path
from .bounded_artifact_io import (
    BoundedArtifactIOError,
    write_immutable_artifact,
)
from .ledger_security import LedgerError


MAX_C_COMPILER_STDOUT_BYTES = 64 * 1024
MAX_C_COMPILER_STDERR_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def write_c_compilation_raw_outputs(
    out_root: Path,
    *,
    unit_id: str,
    plan_sha256: str,
    stdout: bytes,
    stderr: bytes,
) -> dict[str, Any]:
    if (
        not isinstance(unit_id, str)
        or not unit_id
        or len(unit_id.encode("utf-8")) > 4096
        or _SHA256.fullmatch(plan_sha256) is None
    ):
        raise ValueError("c_compilation_raw_identity_invalid")
    if (
        type(stdout) is not bytes
        or type(stderr) is not bytes
        or len(stdout) > MAX_C_COMPILER_STDOUT_BYTES
        or len(stderr) > MAX_C_COMPILER_STDERR_BYTES
    ):
        raise ValueError("c_compilation_raw_output_limit_exceeded")
    unit_sha256 = hashlib.sha256(unit_id.encode("utf-8")).hexdigest()
    result: dict[str, Any] = {
        "schema_version": 1,
        "unit_id": unit_id,
        "unit_id_sha256": unit_sha256,
        "plan_sha256": plan_sha256,
    }
    for stream, data in (("stdout", stdout), ("stderr", stderr)):
        digest = hashlib.sha256(data).hexdigest()
        relative = checked_relative_path(
            "verification/raw-output/c-compilation/"
            f"{plan_sha256}/{unit_sha256}/{stream}/{digest}.bin"
        )
        try:
            write_immutable_artifact(
                Path(out_root).resolve(),
                PurePosixPath(relative),
                data,
                _stream_limit(stream),
            )
        except BoundedArtifactIOError as error:
            raise LedgerError(
                "content-addressed C compiler raw output is immutable"
            ) from error
        result[f"{stream}_sha256"] = digest
        result[f"{stream}_ref"] = {
            "path": relative,
            "sha256": digest,
            "size_bytes": len(data),
        }
    return result


def _stream_limit(stream: str) -> int:
    if stream == "stdout":
        return MAX_C_COMPILER_STDOUT_BYTES
    if stream == "stderr":
        return MAX_C_COMPILER_STDERR_BYTES
    raise ValueError("c_compilation_raw_stream_invalid")


__all__ = [
    "MAX_C_COMPILER_STDERR_BYTES",
    "MAX_C_COMPILER_STDOUT_BYTES",
    "write_c_compilation_raw_outputs",
]
