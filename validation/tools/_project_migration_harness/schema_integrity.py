from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from .ledger_security import SchemaVersionError


def assert_schema_integrity(
    connection: sqlite3.Connection, statements: Iterable[str],
) -> str:
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise SchemaVersionError("ledger foreign-key enforcement is disabled")
    expected = sqlite3.connect(":memory:")
    try:
        expected.execute("PRAGMA foreign_keys=ON")
        for statement in statements:
            expected.execute(statement)
        expected_manifest = _manifest(expected)
    finally:
        expected.close()
    actual_manifest = _manifest(connection)
    if actual_manifest != expected_manifest:
        raise SchemaVersionError("ledger DDL, trigger, or index fingerprint mismatch")
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise SchemaVersionError("ledger integrity_check failed")
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise SchemaVersionError("ledger schema contains foreign-key violations")
    encoded = json.dumps(actual_manifest, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _manifest(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    rows = connection.execute(
        """select type,name,tbl_name,coalesce(sql,'') from sqlite_master
           where name not like 'sqlite_%' order by type,name"""
    ).fetchall()
    return [tuple(row) for row in rows]


__all__ = ["assert_schema_integrity"]
