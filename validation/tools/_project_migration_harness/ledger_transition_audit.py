from __future__ import annotations

import sqlite3


def command_rows(
    connection: sqlite3.Connection, *, run_id: str, command_id: str,
    scope: str,
) -> list[sqlite3.Row]:
    if scope not in {"unit", "run"}:
        raise ValueError("transition command scope is invalid")
    return connection.execute(
        """select * from transitions where run_id=? and scope=? and command_id=?
           order by transition_id""",
        (run_id, scope, command_id),
    ).fetchall()


def unit_event_rows(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """select * from transitions where run_id=? and unit_id=? and scope='unit'
           order by transition_id""",
        (run_id, unit_id),
    ).fetchall()


def run_event_rows(
    connection: sqlite3.Connection, *, run_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """select * from transitions where run_id=? and scope='run'
           order by transition_id""",
        (run_id,),
    ).fetchall()


__all__ = ["command_rows", "run_event_rows", "unit_event_rows"]
