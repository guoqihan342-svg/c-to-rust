from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import content_sha256
from .context_frontier_state import (
    ContextFrontierProjection, FRONTIER_PENDING, FRONTIER_READY,
    validate_context_frontier_head,
)
from .ledger_schema import _json, _now_text, atomic
from .ledger_security import LedgerError


_COMMAND_ID = re.compile(r"^[a-z][a-z0-9_.:-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KINDS = frozenset({"selection_ready", "selection_invalidated"})


@dataclass(frozen=True, slots=True)
class _ContextFrontierCommand:
    command_kind: str
    command_id: str
    run_id: str
    unit_id: str
    expected_status: str
    expected_version: int
    expected_head_sha256: str
    target_head: Mapping[str, Any]
    evidence_sha256: str

    def __post_init__(self) -> None:
        if self.command_kind not in _KINDS:
            raise ValueError("context frontier command kind is invalid")
        if _COMMAND_ID.fullmatch(self.command_id) is None:
            raise ValueError("context frontier command id is invalid")
        if not self.run_id or not self.unit_id:
            raise ValueError("context frontier command identity is invalid")
        if self.expected_status not in {FRONTIER_PENDING, FRONTIER_READY}:
            raise ValueError("context frontier expected status is invalid")
        if (
            isinstance(self.expected_version, bool)
            or not isinstance(self.expected_version, int)
            or self.expected_version < 0
        ):
            raise ValueError("context frontier expected version is invalid")
        if not _sha(self.expected_head_sha256) or not _sha(self.evidence_sha256):
            raise ValueError("context frontier command SHA-256 is invalid")
        validate_context_frontier_head(self.target_head)


@dataclass(frozen=True, slots=True)
class ContextFrontierResult:
    applied: bool
    event_id: int
    previous: ContextFrontierProjection
    current: ContextFrontierProjection


class ContextFrontierAuthority:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def apply(
        self, command: _ContextFrontierCommand, *, created_at: str | None = None,
    ) -> ContextFrontierResult:
        with atomic(self.connection):
            replay = self._find_replay(command)
            if replay is not None:
                assert_context_frontier_projection(
                    self.connection, command.run_id, command.unit_id,
                )
                return replay
            current = assert_context_frontier_projection(
                self.connection, command.run_id, command.unit_id,
            )
            expected = ContextFrontierProjection(
                command.expected_status, command.expected_version,
                current.head, command.expected_head_sha256,
            )
            if current != expected:
                raise LedgerError("context frontier expected state/version/head is stale")
            target = validate_context_frontier_head(command.target_head)
            _require_edge(command.command_kind, current.head, target)
            if command.command_kind == "selection_invalidated" and (
                self.connection.execute(
                    """select 1 from leases where run_id=? and unit_id=?
                       and status='active'""", (command.run_id, command.unit_id),
                ).fetchone()
                or self.connection.execute(
                    """select 1 from attempts where run_id=? and unit_id=?
                       and status='running'""", (command.run_id, command.unit_id),
                ).fetchone()
            ):
                raise LedgerError("active lease or attempt prevents frontier invalidation")
            target_sha = content_sha256(target)
            timestamp = created_at or _now_text()
            cursor = self.connection.execute(
                """insert into context_frontier_events(
                   run_id,unit_id,command_kind,command_id,from_status,to_status,
                   from_version,to_version,from_head_sha256,to_head_json,to_head_sha256,
                   evidence_sha256,created_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    command.run_id, command.unit_id, command.command_kind,
                    command.command_id, current.status, target["status"],
                    current.version, current.version + 1, current.head_sha256,
                    _json(target), target_sha, command.evidence_sha256, timestamp,
                ),
            )
            updated = self.connection.execute(
                """update context_frontiers set status=?,state_version=state_version+1,
                   head_json=?,head_sha256=?,updated_at=? where run_id=? and unit_id=?
                   and status=? and state_version=? and head_sha256=?""",
                (
                    target["status"], _json(target), target_sha, timestamp,
                    command.run_id, command.unit_id, command.expected_status,
                    command.expected_version, command.expected_head_sha256,
                ),
            )
            if updated.rowcount != 1:
                raise LedgerError("context frontier projection lost its CAS binding")
            projected = assert_context_frontier_projection(
                self.connection, command.run_id, command.unit_id,
            )
            return ContextFrontierResult(
                True, int(cursor.lastrowid), current, projected,
            )

    def _find_replay(
        self, command: _ContextFrontierCommand,
    ) -> ContextFrontierResult | None:
        rows = self.connection.execute(
            """select * from context_frontier_events
               where run_id=? and command_id=?""",
            (command.run_id, command.command_id),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise LedgerError("context frontier command id is duplicated")
        row = rows[0]
        target = validate_context_frontier_head(command.target_head)
        binding = (
            row["unit_id"] == command.unit_id
            and row["command_kind"] == command.command_kind
            and row["from_status"] == command.expected_status
            and int(row["from_version"]) == command.expected_version
            and row["from_head_sha256"] == command.expected_head_sha256
            and row["to_head_sha256"] == content_sha256(target)
            and row["evidence_sha256"] == command.evidence_sha256
        )
        if not binding:
            raise LedgerError("context frontier command replay changed its binding")
        previous = ContextFrontierProjection(
            str(row["from_status"]), int(row["from_version"]),
            _head_before_event(self.connection, row), str(row["from_head_sha256"]),
        )
        current = ContextFrontierProjection(
            str(row["to_status"]), int(row["to_version"]), target,
            str(row["to_head_sha256"]),
        )
        return ContextFrontierResult(False, int(row["event_id"]), previous, current)


def load_context_frontier_projection(
    connection: sqlite3.Connection, run_id: str, unit_id: str,
) -> ContextFrontierProjection:
    row = connection.execute(
        """select status,state_version,head_json,head_sha256 from context_frontiers
           where run_id=? and unit_id=?""", (run_id, unit_id),
    ).fetchone()
    if row is None:
        raise LedgerError("context frontier does not exist")
    head = _head(row["head_json"])
    digest = content_sha256(head)
    if row["status"] != head["status"] or row["head_sha256"] != digest:
        raise LedgerError("context frontier projection head drifted")
    return ContextFrontierProjection(
        str(row["status"]), int(row["state_version"]), head, digest,
    )


def assert_context_frontier_projection(
    connection: sqlite3.Connection, run_id: str, unit_id: str,
) -> ContextFrontierProjection:
    row = connection.execute(
        """select * from context_frontiers where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    if row is None:
        raise LedgerError("context frontier does not exist")
    head = _head(row["initial_head_json"])
    if row["initial_status"] != head["status"] or row["initial_head_sha256"] != content_sha256(head):
        raise LedgerError("context frontier initial projection drifted")
    projection = ContextFrontierProjection(head["status"], 0, head, content_sha256(head))
    events = connection.execute(
        """select * from context_frontier_events where run_id=? and unit_id=?
           order by event_id""", (run_id, unit_id),
    ).fetchall()
    for event in events:
        target = _head(event["to_head_json"])
        if (
            event["from_status"] != projection.status
            or int(event["from_version"]) != projection.version
            or event["from_head_sha256"] != projection.head_sha256
            or int(event["to_version"]) != projection.version + 1
            or event["to_status"] != target["status"]
            or event["to_head_sha256"] != content_sha256(target)
        ):
            raise LedgerError("context frontier event chain is discontinuous")
        _require_edge(str(event["command_kind"]), projection.head, target)
        projection = ContextFrontierProjection(
            target["status"], int(event["to_version"]), target,
            content_sha256(target),
        )
    current = load_context_frontier_projection(connection, run_id, unit_id)
    if current != projection:
        raise LedgerError("context frontier projection does not match immutable events")
    return current


def _require_edge(kind: str, current: Mapping[str, Any], target: Mapping[str, Any]) -> None:
    if current["run_id"] != target["run_id"] or current["unit_id"] != target["unit_id"]:
        raise ValueError("context frontier transition changed identity")
    if kind == "selection_ready":
        valid = (
            current["status"] == FRONTIER_PENDING
            and target["status"] == FRONTIER_READY
            and target["mode"] == "host_retrieval"
            and target["query_epoch"] == current["query_epoch"]
            and target["selection_input_sha256"] == current["selection_input_sha256"]
            and target.get("context_overlay") is not None
        )
    else:
        valid = (
            current["status"] == FRONTIER_READY
            and target["status"] == FRONTIER_PENDING
            and target["mode"] == "host_retrieval"
            and target["query_epoch"] == current["query_epoch"] + 1
        )
    if not valid:
        raise ValueError("context frontier transition edge is invalid")


def _head(value: Any) -> dict[str, Any]:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as error:
        raise LedgerError("context frontier head is invalid JSON") from error
    try:
        return validate_context_frontier_head(decoded)
    except ValueError as error:
        raise LedgerError("context frontier head is invalid") from error


def _head_before_event(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    previous = connection.execute(
        """select to_head_json from context_frontier_events
           where run_id=? and unit_id=? and event_id<? order by event_id desc limit 1""",
        (row["run_id"], row["unit_id"], row["event_id"]),
    ).fetchone()
    if previous is not None:
        return _head(previous["to_head_json"])
    initial = connection.execute(
        """select initial_head_json from context_frontiers
           where run_id=? and unit_id=?""", (row["run_id"], row["unit_id"]),
    ).fetchone()
    if initial is None:
        raise LedgerError("context frontier replay lost its initial head")
    return _head(initial["initial_head_json"])


def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


__all__ = [
    "ContextFrontierAuthority", "ContextFrontierResult",
    "assert_context_frontier_projection", "load_context_frontier_projection",
]
