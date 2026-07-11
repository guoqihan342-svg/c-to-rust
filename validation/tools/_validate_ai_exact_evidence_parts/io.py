from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


MAX_JSON_BYTES = 1_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class EvidenceError(ValueError):
    def __init__(self, code: str, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def fail(code: str, message: str, *, path: str | None = None) -> None:
    raise EvidenceError(code, message[:400], path=path)


def require_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value) or value in {".", ".."}:
        fail("invalid_identifier", f"{label} is not a safe evidence identifier", path=label)
    return value


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        fail("invalid_sha256", f"{label} must be a lowercase SHA-256", path=label)
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_accepted_proof(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() == "accepted_evidence_binding":
                fail(
                    "accepted_evidence_forbidden",
                    "accepted_evidence_binding cannot prove AI exact validation",
                    path=f"{label}.{key}",
                )
            reject_accepted_proof(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_accepted_proof(child, f"{label}[{index}]")


class EvidenceStore:
    def __init__(self, evidence_dir: Path) -> None:
        if evidence_dir.is_symlink() or not evidence_dir.is_dir():
            fail("evidence_dir_missing", "evidence directory is missing or is a symlink")
        self.root = evidence_dir.resolve(strict=True)
        self.checked_artifacts = 0

    def resolve(self, value: Any, label: str, *, parent: Path | None = None) -> Path:
        if not isinstance(value, str) or not value or "\x00" in value:
            fail("invalid_path", f"{label}.path must be a non-empty string", path=label)
        raw = Path(value)
        base = parent or self.root
        candidate = raw if raw.is_absolute() else base / raw
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            fail("artifact_missing", f"{label}.path is missing", path=label)
            raise AssertionError from error
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as error:
            fail("path_escape", f"{label}.path escapes evidence directory", path=label)
            raise AssertionError from error
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                fail("symlink_forbidden", f"{label}.path traverses a symlink", path=label)
        if not resolved.is_file():
            fail("artifact_missing", f"{label}.path is not a regular file", path=label)
        return resolved

    def read_json(self, path: Path, label: str) -> dict[str, Any]:
        size = path.stat().st_size
        if size <= 0 or size > MAX_JSON_BYTES:
            fail("invalid_json_size", f"{label} JSON must be non-empty and bounded", path=label)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            fail("invalid_json", f"{label} is not valid UTF-8 JSON", path=label)
            raise AssertionError from error
        if not isinstance(payload, dict):
            fail("invalid_document", f"{label} must be a JSON object", path=label)
        self.checked_artifacts += 1
        return payload

    def read_bound_json(
        self,
        ref: Any,
        label: str,
        *,
        parent: Path | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        if not isinstance(ref, dict):
            fail("invalid_reference", f"{label} reference must be an object", path=label)
        expected = require_sha(ref.get("sha256"), f"{label}.sha256")
        path = self.resolve(ref.get("path"), label, parent=parent)
        actual = sha256_file(path)
        if actual != expected:
            fail("hash_drift", f"{label} SHA-256 drift", path=label)
        return path, self.read_json(path, label)
