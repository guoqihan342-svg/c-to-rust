from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .artifacts import checked_relative_path
from .bounded_artifact_io import (
    BoundedArtifactIOError,
    read_bounded_artifact,
    write_immutable_artifact,
)
from .ledger_security import LedgerError
from .rust_source_pre_cfg_process import MAX_RUST_PARSER_STDERR_BYTES
from .rust_source_pre_cfg_schema import MAX_RUST_WITNESS_OUTPUT_BYTES


_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_STREAMS = ("stdout", "stderr")
_PAIR_KEYS = {
    "schema_version", "source_sha256", "parser_binary_sha256",
    "stdout_ref", "stderr_ref",
}


def write_rust_source_pre_cfg_raw_outputs(
    out_root: Path, *, source_sha256: str, parser_binary_sha256: str,
    stdout: bytes, stderr: bytes,
) -> dict[str, Any]:
    source = _sha(source_sha256)
    parser = _sha(parser_binary_sha256)
    root = Path(out_root).resolve(strict=True)
    result: dict[str, Any] = {
        "schema_version": 1,
        "source_sha256": source,
        "parser_binary_sha256": parser,
    }
    for stream, data in (("stdout", stdout), ("stderr", stderr)):
        result[f"{stream}_ref"] = _write(
            root, source, parser, stream, data,
        )
    return result


def validate_rust_source_pre_cfg_raw_outputs(
    value: Any, *, source_sha256: str, parser_binary_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PAIR_KEYS:
        raise ValueError("rust_source_pre_cfg_raw_pair_schema_invalid")
    source = _sha(source_sha256)
    parser = _sha(parser_binary_sha256)
    if (
        value.get("schema_version") != 1
        or value.get("source_sha256") != source
        or value.get("parser_binary_sha256") != parser
    ):
        raise ValueError("rust_source_pre_cfg_raw_pair_binding_invalid")
    result = {
        "schema_version": 1,
        "source_sha256": source,
        "parser_binary_sha256": parser,
    }
    for stream in _STREAMS:
        result[f"{stream}_ref"] = _reference(
            value.get(f"{stream}_ref"), source, parser, stream,
        )
    return result


def read_rust_source_pre_cfg_raw_outputs(
    ledger_path: Path, value: Mapping[str, Any], *,
    source_sha256: str, parser_binary_sha256: str,
) -> dict[str, bytes]:
    references = validate_rust_source_pre_cfg_raw_outputs(
        value, source_sha256=source_sha256,
        parser_binary_sha256=parser_binary_sha256,
    )
    database = Path(ledger_path).resolve(strict=True)
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise LedgerError("Rust source raw output requires the fixed ledger path")
    root = database.parent.parent.resolve(strict=True)
    result = {}
    for stream in _STREAMS:
        reference = references[f"{stream}_ref"]
        relative = PurePosixPath(reference["path"])
        target = root.joinpath(*relative.parts)
        try:
            data = read_bounded_artifact(root, target, _limit(stream))
        except BoundedArtifactIOError as error:
            raise LedgerError("Rust source raw output is not safely readable") from error
        if (
            len(data) != reference["size_bytes"]
            or hashlib.sha256(data).hexdigest() != reference["sha256"]
        ):
            raise LedgerError("Rust source raw output content binding changed")
        result[stream] = data
    return result


def _write(
    root: Path, source: str, parser: str, stream: str, data: bytes,
) -> dict[str, Any]:
    if type(data) is not bytes or len(data) > _limit(stream):
        raise ValueError("rust_source_pre_cfg_raw_output_limit_exceeded")
    digest = hashlib.sha256(data).hexdigest()
    relative = checked_relative_path(
        "verification/raw-output/rust-source-pre-cfg/"
        f"{source}/{parser}/{stream}/{digest}.bin"
    )
    try:
        write_immutable_artifact(
            root, PurePosixPath(relative), data, _limit(stream),
        )
    except BoundedArtifactIOError as error:
        raise LedgerError("Rust source raw output is not immutable") from error
    return {"path": relative, "sha256": digest, "size_bytes": len(data)}


def _reference(
    value: Any, source: str, parser: str, stream: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("rust_source_pre_cfg_raw_reference_schema_invalid")
    digest = _sha(value.get("sha256"))
    size = value.get("size_bytes")
    if type(size) is not int or not 0 <= size <= _limit(stream):
        raise ValueError("rust_source_pre_cfg_raw_reference_size_invalid")
    try:
        path = PurePosixPath(checked_relative_path(value.get("path")))
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError("rust_source_pre_cfg_raw_reference_path_invalid") from error
    expected = (
        "verification", "raw-output", "rust-source-pre-cfg", source, parser,
        stream, f"{digest}.bin",
    )
    if tuple(path.parts) != expected:
        raise ValueError("rust_source_pre_cfg_raw_reference_path_invalid")
    return {"path": path.as_posix(), "sha256": digest, "size_bytes": size}


def _limit(stream: str) -> int:
    if stream == "stdout":
        return MAX_RUST_WITNESS_OUTPUT_BYTES
    if stream == "stderr":
        return MAX_RUST_PARSER_STDERR_BYTES
    raise ValueError("rust_source_pre_cfg_raw_stream_invalid")


def _sha(value: Any) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError("rust_source_pre_cfg_raw_sha256_invalid")
    return value


__all__ = [
    "read_rust_source_pre_cfg_raw_outputs",
    "validate_rust_source_pre_cfg_raw_outputs",
    "write_rust_source_pre_cfg_raw_outputs",
]
