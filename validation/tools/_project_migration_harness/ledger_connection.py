from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


def connect_database(
    path: str | Path, *, busy_timeout_ms: int = 5_000,
    read_only: bool = False,
) -> sqlite3.Connection:
    if busy_timeout_ms < 1:
        raise ValueError("busy_timeout_ms must be positive")
    database = Path(path)
    if read_only:
        if not database.is_file():
            raise FileNotFoundError(database)
        uri = database.resolve(strict=True).as_uri() + "?mode=ro"
        connection = sqlite3.connect(
            uri, uri=True, isolation_level=None,
            timeout=busy_timeout_ms / 1000, factory=_ClosingConnection,
        )
    else:
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            database, isolation_level=None, timeout=busy_timeout_ms / 1000,
            factory=_ClosingConnection,
        )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    if read_only:
        connection.execute("PRAGMA query_only=ON")
    else:
        connection.execute("PRAGMA journal_mode=WAL")
    return connection


__all__ = ["connect_database"]
