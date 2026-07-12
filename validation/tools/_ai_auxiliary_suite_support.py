from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from contextlib import contextmanager


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode(
            "utf-8"
        ),
    )


def repo_path(root: Path, value: Path) -> Path:
    resolved = value.resolve() if value.is_absolute() else (root / value).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"path escapes repository: {value}") from error
    return resolved


def reserve_output_root(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise ValueError("out_root must be absent or empty to prevent stale evidence reuse")
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".ai-auxiliary-run-reservation"
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError("out_root is already reserved by another suite run") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"ai-auxiliary-run-reservation-v1\n")
        stream.flush()
        os.fsync(stream.fileno())


def artifact_ref(path: Path, *, root: Path) -> dict[str, str]:
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "sha256": sha256_path(path),
    }


def load_object(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def failed_unit(item: dict[str, Any], index: int, reason: str) -> dict[str, Any]:
    return {
        "index": index,
        "item_id": item.get("id"),
        "project_id": item.get("project_id"),
        "construct_family": item.get("construct_family"),
        "target_id": None,
        "slice_id": item.get("slice_id"),
        "status": "contract_failed",
        "returncode": 1,
        "duration_ms": 0,
        "provider_invocations": 0,
        "repair_rounds": 0,
        "auxiliary_exact_pass": False,
        "reason": reason,
        "artifacts": {},
        "_candidate_manifest_path": None,
    }


def required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def safe_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a bounded path-safe identifier")
    return value


def validate_unit_identities(items: list[Any]) -> None:
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"suite.items[{index}] must be an object")
        project_id = safe_identifier(item.get("project_id"), f"suite.items[{index}].project_id")
        slice_id = safe_identifier(item.get("slice_id"), f"suite.items[{index}].slice_id")
        safe_identifier(item.get("id"), f"suite.items[{index}].id")
        identity = (project_id, slice_id)
        if identity in seen:
            raise ValueError("suite project_id/slice_id pairs must be unique")
        seen.add(identity)


@contextmanager
def isolated_opencode_environment(unit_label: str):
    if not isinstance(unit_label, str) or re.fullmatch(r"[A-Za-z0-9_.-]+", unit_label) is None:
        raise ValueError("unit_label must contain only path-safe characters")
    label_hash = hashlib.sha256(unit_label.encode("utf-8")).hexdigest()[:12]
    safe_label = f"{unit_label[:48]}-{label_hash}"
    with tempfile.TemporaryDirectory(prefix=f"opencode-{safe_label}-") as temporary:
        root = Path(temporary)
        data_home = root / "data"
        config_home = root / "config"
        cache_home = root / "cache"
        state_home = root / "state"
        tmp_home = root / "tmp"
        for path in (data_home, config_home, cache_home, state_home, tmp_home):
            path.mkdir(parents=True, exist_ok=True)

        source_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        source_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        copied_credentials = copy_regular_file(
            source_data / "opencode" / "auth.json",
            data_home / "opencode" / "auth.json",
        )
        for name in ("opencode.json", "opencode.jsonc"):
            copy_regular_file(source_config / "opencode" / name, config_home / "opencode" / name)

        environment = os.environ.copy()
        environment.update(
            {
                "XDG_DATA_HOME": str(data_home),
                "XDG_CONFIG_HOME": str(config_home),
                "XDG_CACHE_HOME": str(cache_home),
                "XDG_STATE_HOME": str(state_home),
                "TMPDIR": str(tmp_home),
                "TEMP": str(tmp_home),
                "TMP": str(tmp_home),
            }
        )
        yield environment, {
            "status": "isolated",
            "config": "bounded_copy",
            "data_cache_state_tmp": "per_unit_temporary",
            "credentials_available": copied_credentials,
        }


def copy_regular_file(source: Path, destination: Path) -> bool:
    try:
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 1_048_576:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o600)
        return True
    except OSError:
        return False


__all__ = [
    "artifact_ref",
    "atomic_write_bytes",
    "atomic_write_json",
    "failed_unit",
    "load_object",
    "repo_path",
    "reserve_output_root",
    "required_string",
    "safe_identifier",
    "sha256_path",
    "isolated_opencode_environment",
    "validate_unit_identities",
]
