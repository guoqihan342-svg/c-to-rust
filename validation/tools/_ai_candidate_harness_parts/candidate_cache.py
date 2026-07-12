from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Callable
import uuid

from .context_security import canonical_json_bytes, sha256_bytes


CACHE_ENTRY_SCHEMA_VERSION = 1
PROMPT_SCHEMA_VERSION = 1
PARSE_CONTRACT_VERSION = 1
MAX_CACHE_ENTRY_BYTES = 32_000
MAX_CACHED_RESPONSE_BYTES = 2_000_000
MAX_CACHED_CANDIDATE_BYTES = 256_000
MAX_AGENT_DEFINITION_BYTES = 256_000
SHA256_LENGTH = 64


@dataclass(frozen=True)
class CachedCandidate:
    entry_bytes: bytes
    response_bytes: bytes
    candidate_bytes: bytes
    parsed: dict[str, Any]
    entry_sha256: str


def cache_key_payload(
    context_pack_sha256: str,
    *,
    prompt_sha256: str,
    resolved_model: str,
    agent: str,
    agent_definition_sha256: str,
    variant: str,
) -> dict[str, Any]:
    if not _is_sha256(context_pack_sha256):
        raise ValueError("context_pack_sha256 must be lowercase SHA-256")
    if not _is_sha256(prompt_sha256):
        raise ValueError("prompt_sha256 must be lowercase SHA-256")
    if not _is_sha256(agent_definition_sha256):
        raise ValueError("agent_definition_sha256 must be lowercase SHA-256")
    for label, value in (
        ("resolved_model", resolved_model),
        ("agent", agent),
        ("variant", variant),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{label} must be non-empty")
    return {
        "context_pack_sha256": context_pack_sha256,
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "prompt_sha256": prompt_sha256,
        "resolved_model": resolved_model,
        "agent": agent,
        "agent_definition_sha256": agent_definition_sha256,
        "variant": variant,
        "parse_contract_version": PARSE_CONTRACT_VERSION,
    }


def cache_key_sha256(payload: dict[str, Any]) -> str:
    _validate_key_payload(payload)
    return sha256_bytes(canonical_json_bytes(payload))


def agent_definition_sha256(agent: str, repo_root: Path) -> str:
    if not isinstance(agent, str) or not agent or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in agent
    ):
        raise ValueError("agent must be a repository-local identifier")
    root = repo_root.resolve()
    path = root / ".opencode" / "agents" / f"{agent}.md"
    if _is_linklike(path) or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("cache requires a repository-local agent definition")
    return sha256_bytes(_read_bounded(path, MAX_AGENT_DEFINITION_BYTES))


def load_candidate_cache(
    cache_root: Path,
    payload: dict[str, Any],
    parse_response: Callable[[str], dict[str, Any]],
) -> tuple[CachedCandidate | None, str]:
    try:
        key = cache_key_sha256(payload)
        root, entry_dir = _entry_path(cache_root, key)
        if not entry_dir.exists():
            return None, "entry_missing"
        if _is_linklike(root) or _is_linklike(entry_dir) or not entry_dir.is_dir():
            return None, "entry_invalid"
        if not entry_dir.resolve().is_relative_to(root.resolve()):
            return None, "entry_invalid"
        entry_path = entry_dir / "entry.json"
        response_path = entry_dir / "response.jsonl"
        candidate_path = entry_dir / "candidate.rs"
        if any(_is_linklike(path) or not path.is_file() for path in (entry_path, response_path, candidate_path)):
            return None, "entry_invalid"
        entry_bytes = _read_bounded(entry_path, MAX_CACHE_ENTRY_BYTES)
        response_bytes = _read_bounded(response_path, MAX_CACHED_RESPONSE_BYTES)
        candidate_bytes = _read_bounded(candidate_path, MAX_CACHED_CANDIDATE_BYTES)
        entry = json.loads(entry_bytes.decode("utf-8"))
        validate_cache_entry(entry, payload, key, response_bytes, candidate_bytes)
        parsed = parse_response(response_bytes.decode("utf-8"))
        source = parsed.get("candidate", {}).get("source") if isinstance(parsed, dict) else None
        if not isinstance(source, str) or source.encode("utf-8") != candidate_bytes:
            return None, "entry_invalid"
        return (
            CachedCandidate(
                entry_bytes=entry_bytes,
                response_bytes=response_bytes,
                candidate_bytes=candidate_bytes,
                parsed=parsed,
                entry_sha256=sha256_bytes(entry_bytes),
            ),
            "hit",
        )
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None, "entry_invalid"


@contextmanager
def candidate_generation_lock(
    cache_root: Path,
    payload: dict[str, Any],
    *,
    timeout_seconds: float = 300.0,
):
    key = cache_key_sha256(payload)
    root, entry_dir = _entry_path(cache_root, key)
    if root.exists() and (_is_linklike(root) or not root.is_dir()):
        raise OSError("cache root must be a directory without links")
    shard = entry_dir.parent
    shard.mkdir(parents=True, exist_ok=True)
    if (
        _is_linklike(root)
        or not root.is_dir()
        or _is_linklike(shard)
        or not shard.resolve().is_relative_to(root.resolve())
    ):
        raise OSError("cache shard escaped the cache root")
    with _file_lock(
        shard / f".{key}.generate.lock",
        timeout_seconds=timeout_seconds,
    ):
        yield


def store_candidate_cache(
    cache_root: Path,
    payload: dict[str, Any],
    response_bytes: bytes,
    candidate_bytes: bytes,
    parse_response: Callable[[str], dict[str, Any]],
) -> bool:
    temporary: Path | None = None
    try:
        if len(response_bytes) > MAX_CACHED_RESPONSE_BYTES or len(candidate_bytes) > MAX_CACHED_CANDIDATE_BYTES:
            return False
        parsed = parse_response(response_bytes.decode("utf-8"))
        source = parsed.get("candidate", {}).get("source") if isinstance(parsed, dict) else None
        if not isinstance(source, str) or source.encode("utf-8") != candidate_bytes:
            return False
        key = cache_key_sha256(payload)
        root, entry_dir = _entry_path(cache_root, key)
        if root.exists() and (_is_linklike(root) or not root.is_dir()):
            return False
        shard = entry_dir.parent
        shard.mkdir(parents=True, exist_ok=True)
        if (
            _is_linklike(root)
            or not root.is_dir()
            or _is_linklike(shard)
            or not shard.resolve().is_relative_to(root.resolve())
        ):
            return False
        with _cache_key_lock(shard, key):
            if entry_dir.exists():
                existing, _reason = load_candidate_cache(cache_root, payload, parse_response)
                if existing is not None:
                    return False
                quarantine = shard / f".{key}.invalid.{os.getpid()}.{uuid.uuid4().hex}"
                try:
                    os.rename(entry_dir, quarantine)
                except OSError:
                    return False
                _remove_private_directory(quarantine, marker=".invalid.")
            temporary = Path(tempfile.mkdtemp(prefix=f".{key}.tmp.", dir=shard))
            response_ref = {"sha256": sha256_bytes(response_bytes), "size_bytes": len(response_bytes)}
            candidate_ref = {"sha256": sha256_bytes(candidate_bytes), "size_bytes": len(candidate_bytes)}
            entry = {
                "schema_version": CACHE_ENTRY_SCHEMA_VERSION,
                "key_sha256": key,
                "key": payload,
                "raw_response": response_ref,
                "candidate": candidate_ref,
            }
            (temporary / "response.jsonl").write_bytes(response_bytes)
            (temporary / "candidate.rs").write_bytes(candidate_bytes)
            (temporary / "entry.json").write_bytes(canonical_json_bytes(entry))
            try:
                os.rename(temporary, entry_dir)
                temporary = None
                return True
            except OSError:
                return False
    except (OSError, UnicodeError, ValueError, TypeError):
        return False
    finally:
        if temporary is not None:
            _remove_private_temporary(temporary)


def _entry_path(cache_root: Path, key: str) -> tuple[Path, Path]:
    root = cache_root.expanduser()
    return root, root / key[:2] / key


def _read_bounded(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError("cache artifact is not a bounded regular file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("cache artifact exceeds size limit")
    return data


def validate_cache_entry(
    entry: Any,
    payload: dict[str, Any],
    key: str,
    response_bytes: bytes,
    candidate_bytes: bytes,
) -> None:
    if not isinstance(entry, dict) or set(entry) != {
        "schema_version",
        "key_sha256",
        "key",
        "raw_response",
        "candidate",
    }:
        raise ValueError("cache entry shape is invalid")
    if entry.get("schema_version") != CACHE_ENTRY_SCHEMA_VERSION:
        raise ValueError("cache entry schema is invalid")
    if entry.get("key_sha256") != key or entry.get("key") != payload:
        raise ValueError("cache key drifted")
    _validate_artifact_ref(entry.get("raw_response"), response_bytes)
    _validate_artifact_ref(entry.get("candidate"), candidate_bytes)


def _validate_artifact_ref(ref: Any, data: bytes) -> None:
    if not isinstance(ref, dict) or set(ref) != {"sha256", "size_bytes"}:
        raise ValueError("cache artifact ref is invalid")
    if ref.get("sha256") != sha256_bytes(data) or ref.get("size_bytes") != len(data):
        raise ValueError("cache artifact drifted")


def _validate_key_payload(payload: Any) -> None:
    expected = {
        "context_pack_sha256",
        "prompt_schema_version",
        "prompt_sha256",
        "resolved_model",
        "agent",
        "agent_definition_sha256",
        "variant",
        "parse_contract_version",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("cache key payload shape is invalid")
    if not _is_sha256(payload.get("context_pack_sha256")):
        raise ValueError("cache key context hash is invalid")
    if not _is_sha256(payload.get("prompt_sha256")):
        raise ValueError("cache key prompt hash is invalid")
    if not _is_sha256(payload.get("agent_definition_sha256")):
        raise ValueError("cache key agent definition hash is invalid")
    if payload.get("prompt_schema_version") != PROMPT_SCHEMA_VERSION:
        raise ValueError("cache prompt schema version drifted")
    if payload.get("parse_contract_version") != PARSE_CONTRACT_VERSION:
        raise ValueError("cache parse contract version drifted")
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in ("resolved_model", "agent", "variant")):
        raise ValueError("cache execution policy is invalid")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _remove_private_temporary(path: Path) -> None:
    _remove_private_directory(path, marker=".tmp.")


def _remove_private_directory(path: Path, *, marker: str) -> None:
    try:
        if _is_linklike(path) or not path.name.startswith(".") or marker not in path.name:
            return
        shutil.rmtree(path)
    except OSError:
        return


@contextmanager
def _cache_key_lock(shard: Path, key: str):
    with _file_lock(shard / f".{key}.lock", timeout_seconds=30.0):
        yield


@contextmanager
def _file_lock(lock_path: Path, *, timeout_seconds: float):
    if _is_linklike(lock_path):
        raise OSError("cache lock path must not be a symlink")
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("timed out waiting for candidate cache lock") from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as error:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("timed out waiting for candidate cache lock") from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "CachedCandidate",
    "agent_definition_sha256",
    "cache_key_payload",
    "cache_key_sha256",
    "candidate_generation_lock",
    "load_candidate_cache",
    "store_candidate_cache",
    "validate_cache_entry",
]
