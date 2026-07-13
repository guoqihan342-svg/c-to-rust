from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .held_out_integrity import file_sha256


MAX_LEDGER_BYTES = 512 * 1024 * 1024


class HeldOutLedgerError(ValueError):
    pass


def json_object(value: Any, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise HeldOutLedgerError(f"{label} is invalid JSON") from error
    require(isinstance(payload, dict), f"{label} must be an object")
    return payload


def require_no_sidecars(path: Path) -> None:
    for suffix in ("-journal", "-shm", "-wal"):
        require(not Path(str(path) + suffix).exists(), "ledger has mutable SQLite sidecars")


def file_identity(path: Path) -> tuple[int, int, int, int, str]:
    metadata = path.stat()
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns,
        file_sha256(path, max_bytes=MAX_LEDGER_BYTES),
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HeldOutLedgerError(message)


__all__ = [
    "HeldOutLedgerError", "file_identity", "json_object", "require",
    "require_no_sidecars",
]
