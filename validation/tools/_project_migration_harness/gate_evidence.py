from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .ledger_security import LedgerError


MAX_GATE_EVIDENCE_BYTES = 2 * 1024 * 1024
_SCOPE = re.compile(r"^[a-z0-9][a-z0-9/-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def write_content_addressed_json(
    out_root: Path, scope: str, payload: Mapping[str, Any],
) -> dict[str, Any]:
    if _SCOPE.fullmatch(scope) is None or ".." in PurePosixPath(scope).parts:
        raise ValueError("gate evidence scope is invalid")
    data = canonical_json_bytes(payload)
    if len(data) > MAX_GATE_EVIDENCE_BYTES:
        raise ValueError("gate evidence exceeds the size bound")
    digest = hashlib.sha256(data).hexdigest()
    relative = checked_relative_path(f"verification/{scope}/{digest}.json")
    root = out_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = target.parent.resolve()
    try:
        resolved_parent.relative_to(root)
    except ValueError as error:
        raise ValueError("gate evidence target escapes out_root") from error
    try:
        with target.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        _verify_bytes(target, data)
    return {"path": relative, "sha256": digest, "size_bytes": len(data)}


def read_content_addressed_json(
    ledger_path: Path, evidence_path: str, evidence_sha256: str,
) -> dict[str, Any]:
    path = _relative_evidence_path(evidence_path, evidence_sha256)
    matches: list[Path] = []
    seen: set[Path] = set()
    database = ledger_path.resolve()
    for root in (database.parent, *database.parents):
        resolved_root = root.resolve()
        if resolved_root in seen:
            continue
        seen.add(resolved_root)
        candidate = resolved_root.joinpath(*path.parts)
        if not candidate.is_file():
            continue
        _reject_links(resolved_root, path)
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(resolved_root)
        except ValueError as error:
            raise LedgerError("gate evidence escapes its repository root") from error
        matches.append(resolved)
    unique = list(dict.fromkeys(matches))
    if len(unique) != 1:
        raise LedgerError("gate evidence root is missing or ambiguous")
    data = unique[0].read_bytes()
    if len(data) > MAX_GATE_EVIDENCE_BYTES:
        raise LedgerError("gate evidence exceeds the size bound")
    if hashlib.sha256(data).hexdigest() != evidence_sha256:
        raise LedgerError("gate evidence content hash changed")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("gate evidence is not canonical JSON") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        raise LedgerError("gate evidence is not canonical JSON")
    return payload


def require_content_addressed_reference(reference: Mapping[str, Any]) -> None:
    if set(reference) != {"path", "sha256", "size_bytes"}:
        raise LedgerError("gate evidence reference schema is invalid")
    path = _relative_evidence_path(str(reference["path"]), str(reference["sha256"]))
    if not isinstance(reference["size_bytes"], int) or not 0 < reference["size_bytes"] <= MAX_GATE_EVIDENCE_BYTES:
        raise LedgerError("gate evidence reference size is invalid")
    if "verification" not in path.parts:
        raise LedgerError("gate evidence must live under a verification root")


def require_host_raw_reference(reference: Mapping[str, Any], gate_kind: str) -> None:
    require_content_addressed_reference(reference)
    parts = PurePosixPath(str(reference["path"])).parts
    expected = ("verification", "raw", gate_kind)
    if not any(tuple(parts[index:index + 3]) == expected for index in range(len(parts) - 2)):
        raise LedgerError("project observation is outside its host-owned raw evidence root")


def _relative_evidence_path(value: str, digest: str) -> PurePosixPath:
    if _SHA256.fullmatch(digest) is None:
        raise LedgerError("gate evidence SHA-256 is invalid")
    try:
        normalized = checked_relative_path(value)
    except ValueError as error:
        raise LedgerError("gate evidence path is invalid") from error
    path = PurePosixPath(normalized)
    if path.name != f"{digest}.json" or "verification" not in path.parts:
        raise LedgerError("gate evidence path is not content addressed")
    return path


def _reject_links(root: Path, relative: PurePosixPath) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise LedgerError("gate evidence path contains a symbolic link")


def _verify_bytes(path: Path, expected: bytes) -> None:
    if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
        raise LedgerError("content-addressed gate evidence is immutable")


__all__ = [
    "MAX_GATE_EVIDENCE_BYTES", "read_content_addressed_json",
    "require_content_addressed_reference", "require_host_raw_reference",
    "write_content_addressed_json",
]
