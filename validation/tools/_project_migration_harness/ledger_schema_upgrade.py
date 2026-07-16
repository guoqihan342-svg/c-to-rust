from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .ledger_security import SchemaVersionError
from .schema_integrity import assert_schema_integrity


def upgrade_v8_to_v9(
    connection: Any, *, legacy_schema: Iterable[str],
    current_schema: Iterable[str], upgrade_statements: Iterable[str],
    metadata_statement: str, now: str,
) -> None:
    row = connection.execute(
        "select schema_sha256 from schema_migrations where version=8",
    ).fetchone()
    legacy_fingerprint = assert_schema_integrity(connection, legacy_schema)
    if row is None or row[0] != legacy_fingerprint:
        raise SchemaVersionError("legacy ledger schema fingerprint metadata mismatch")
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in upgrade_statements:
            connection.execute(statement)
        connection.execute(
            "update project_runs set completion_status=status",
        )
        connection.execute("drop table schema_migrations")
        connection.execute(metadata_statement)
        fingerprint = assert_schema_integrity(connection, current_schema)
        connection.execute(
            """insert into schema_migrations(version,applied_at,schema_sha256)
               values (9,?,?)""",
            (now, fingerprint),
        )
        connection.execute("PRAGMA user_version=9")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


__all__ = ["upgrade_v8_to_v9"]
