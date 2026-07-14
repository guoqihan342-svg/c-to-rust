from __future__ import annotations

"""Bounded raw bytes for host-verifier envelopes, without running a verifier."""

import hashlib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import checked_relative_path
from .bounded_artifact_io import (
    BoundedArtifactIOError, read_bounded_artifact, write_immutable_artifact,
)
from .host_verifier_contract import (
    evidence_root_value, gate_kind_value, sha256_value,
)


MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES = 1024 * 1024
HOST_VERIFIER_RAW_STREAMS = ("stdout", "stderr")
_RAW_SUFFIX = ("verification", "host-verifier", "raw")


def write_host_verifier_raw_evidence(
    repository_root: Path, evidence_root: str, *, gate_kind: str,
    stream: str, data: bytes,
) -> dict[str, Any]:
    root = _repository_root(repository_root)
    prefix = evidence_root_value(evidence_root)
    gate_kind_value(gate_kind)
    _stream_value(stream)
    if type(data) is not bytes or len(data) > MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES:
        raise ValueError("host verifier raw evidence exceeds its byte bound")
    digest = hashlib.sha256(data).hexdigest()
    relative = checked_relative_path(
        f"{prefix}/verification/host-verifier/raw/"
        f"{gate_kind}/{stream}/{digest}.bin"
    )
    try:
        write_immutable_artifact(
            root, PurePosixPath(relative), data,
            MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES,
        )
    except BoundedArtifactIOError as error:
        raise ValueError("host verifier raw evidence is not immutable") from error
    return {"path": relative, "sha256": digest, "size_bytes": len(data)}


def validate_host_verifier_raw_evidence_reference(
    value: Any, *, gate_kind: str, stream: str,
    evidence_root: str | None = None,
) -> dict[str, Any]:
    gate_kind_value(gate_kind)
    _stream_value(stream)
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("host verifier raw evidence reference schema is invalid")
    digest = sha256_value(value.get("sha256"), "raw evidence sha256")
    size = value.get("size_bytes")
    if (
        type(size) is not int
        or not 0 <= size <= MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES
    ):
        raise ValueError("host verifier raw evidence size is invalid")
    try:
        normalized = checked_relative_path(value.get("path"))
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError("host verifier raw evidence path is invalid") from error
    path = PurePosixPath(normalized)
    suffix = (*_RAW_SUFFIX, gate_kind, stream, f"{digest}.bin")
    if len(path.parts) < len(suffix) or tuple(path.parts[-len(suffix):]) != suffix:
        raise ValueError("host verifier raw evidence path binding is invalid")
    if evidence_root is not None:
        prefix = PurePosixPath(evidence_root_value(evidence_root))
        if path != prefix.joinpath(*suffix):
            raise ValueError("host verifier raw evidence root binding is stale")
    return {"path": path.as_posix(), "sha256": digest, "size_bytes": size}


def read_host_verifier_raw_evidence(
    repository_root: Path, value: Mapping[str, Any], *, gate_kind: str,
    stream: str, evidence_root: str | None = None,
) -> bytes:
    root = _repository_root(repository_root)
    reference = validate_host_verifier_raw_evidence_reference(
        value, gate_kind=gate_kind, stream=stream,
        evidence_root=evidence_root,
    )
    target = root.joinpath(*PurePosixPath(reference["path"]).parts)
    try:
        data = read_bounded_artifact(
            root, target, MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES,
        )
    except BoundedArtifactIOError as error:
        raise ValueError("host verifier raw evidence is not safely readable") from error
    if (
        len(data) != reference["size_bytes"]
        or hashlib.sha256(data).hexdigest() != reference["sha256"]
    ):
        raise ValueError("host verifier raw evidence content binding drifted")
    return data


def _repository_root(value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except OSError as error:
        raise ValueError("host verifier repository root is unavailable") from error
    if not root.is_dir():
        raise ValueError("host verifier repository root is invalid")
    return root


def _stream_value(value: Any) -> str:
    if type(value) is not str or value not in HOST_VERIFIER_RAW_STREAMS:
        raise ValueError("host verifier raw evidence stream is invalid")
    return value


__all__ = [
    "HOST_VERIFIER_RAW_STREAMS", "MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES",
    "read_host_verifier_raw_evidence",
    "validate_host_verifier_raw_evidence_reference",
    "write_host_verifier_raw_evidence",
]
