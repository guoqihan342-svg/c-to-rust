from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Iterable


SENSITIVE_KEY_PARTS = ("api_key", "apikey", "credential", "password", "secret", "token")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|credential|password|secret|token)\b"
    r"(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;\]\}\"']+)"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+\-/]+=*")
KNOWN_KEY_PATTERN = re.compile(r"\b[0-9a-fA-F]{32}\.[A-Za-z0-9_-]{12,}\b")
HOST_PATH_PATTERN = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+|"
    r"/(?:mnt/[a-z]|home|root|users|tmp|var/tmp|private/tmp)/)[^\s\"']+"
)
GENERIC_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(^|[\s\"'=:(])(/(?![/*])(?:[^/\s\"'<>]+/)*[^/\s\"'<>,;:)]+)",
    re.MULTILINE,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def compact_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(payload))


def sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_text(value: str, known_roots: Iterable[str] = ()) -> str:
    sanitized = value
    roots = sorted(
        {root for root in known_roots if root and is_absolute_any_platform(root)},
        key=len,
        reverse=True,
    )
    for root in roots:
        variants = {root, root.replace("\\", "/"), root.replace("/", "\\")}
        for variant in sorted(variants, key=len, reverse=True):
            sanitized = re.sub(re.escape(variant), "<source-root>", sanitized, flags=re.IGNORECASE)
    sanitized = SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        sanitized,
    )
    sanitized = BEARER_PATTERN.sub("Bearer <redacted>", sanitized)
    sanitized = KNOWN_KEY_PATTERN.sub("<redacted-key>", sanitized)
    return HOST_PATH_PATTERN.sub("<host-path>", sanitized)


def redact_metadata_text(value: str, known_roots: Iterable[str] = ()) -> str:
    sanitized = redact_text(value, known_roots)
    return GENERIC_ABSOLUTE_PATH_PATTERN.sub(lambda match: f"{match.group(1)}<host-path>", sanitized)


def sanitize_value(value: Any, known_roots: Iterable[str] = ()) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_value(item, known_roots)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [sanitize_value(item, known_roots) for item in value]
    if not isinstance(value, str):
        return value
    return redact_metadata_text(value, known_roots)


def resolve_under(root: Path, value: str | Path, *, base: Path | None = None) -> Path:
    root = root.resolve()
    raw = str(value)
    if is_absolute_any_platform(raw) and not Path(raw).is_absolute():
        raise ValueError("path uses a foreign absolute path")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (base or root) / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("path escapes source root") from error
    return resolved


def is_absolute_any_platform(value: str) -> bool:
    return Path(value).is_absolute() or PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def logical_path(root: Path, path: Path) -> str:
    relative = path.resolve().relative_to(root.resolve())
    return "<source-root>" if not relative.parts else f"<source-root>/{relative.as_posix()}"


def bounded_value(value: Any, *, max_bytes: int) -> tuple[Any, bool]:
    sanitized = value
    if len(compact_json_bytes(sanitized)) <= max_bytes:
        return sanitized, False
    compacted = compact_value(sanitized)
    if len(compact_json_bytes(compacted)) <= max_bytes:
        return compacted, True
    return {"status": "omitted_too_large", "sha256": sha256_bytes(compact_json_bytes(sanitized))}, True


def compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return "<depth-limit>"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda pair: str(pair[0]))
        result = {
            str(key): compact_value(item, depth=depth + 1)
            for key, item in items[:32]
        }
        if len(items) > 32:
            result["_omitted_keys"] = len(items) - 32
        return result
    if isinstance(value, list):
        result = [compact_value(item, depth=depth + 1) for item in value[:24]]
        if len(value) > 24:
            result.append({"_omitted_items": len(value) - 24})
        return result
    if isinstance(value, str) and len(value) > 512:
        return value[:512] + "<truncated>"
    return value
