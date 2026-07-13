from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_schema import _json, _now_text, _require_sha256, atomic
from .ledger_security import LedgerError, LeaseConflict, assert_no_semantic_claims
from .ledger_transition_authority import TransitionAuthority, load_unit_state
from .ledger_transition_policy import (
    UnitState, attempt_started_command, lease_recovery_command,
    lease_recovery_run_command,
)


ROLES = {"planner", "translator", "reviewer", "repairer"}


class LeaseLifecycleMixin:
    def acquire_lease(
        self, *, run_id: str, unit_id: str, owner: str, ttl_seconds: int,
        now: int | None = None,
    ) -> int:
        if not owner or ttl_seconds < 1:
            raise ValueError("owner and a positive ttl_seconds are required")
        clock = int(time.time()) if now is None else int(now)
        with self.connect() as connection, atomic(connection):
            assignment = connection.execute(
                """select a.role,r.max_concurrency,r.status as run_status,u.resumable_status
                   from assignments a join project_runs r using(run_id)
                   join migration_units u using(run_id,unit_id)
                   where a.run_id=? and a.unit_id=? and a.worker_id=? and a.status='active'""",
                (run_id, unit_id, owner),
            ).fetchone()
            if (
                not assignment or assignment["run_status"] != "active"
                or assignment["resumable_status"] in {"terminal", "exhausted"}
            ):
                raise LeaseConflict("lease owner is not actively assigned to this runnable unit")
            row = connection.execute(
                "select status,fencing_token,expires_at from leases where run_id=? and unit_id=?",
                (run_id, unit_id),
            ).fetchone()
            if row and row["status"] == "active" and row["expires_at"] > clock:
                raise LeaseConflict(f"unit {unit_id} already has an active lease")
            active = int(connection.execute(
                """select count(*) from leases where run_id=? and status='active'
                   and expires_at>? and unit_id<>?""", (run_id, clock, unit_id),
            ).fetchone()[0])
            if active >= int(assignment["max_concurrency"]):
                raise LeaseConflict(f"run {run_id} reached max_concurrency")
            token = (int(row["fencing_token"]) if row else 0) + 1
            connection.execute(
                """insert into leases(run_id,unit_id,owner,role,status,fencing_token,expires_at,heartbeat_at)
                   values (?,?,?,?,'active',?,?,?) on conflict(run_id,unit_id) do update set
                   owner=excluded.owner,role=excluded.role,status='active',
                   fencing_token=excluded.fencing_token,expires_at=excluded.expires_at,
                   heartbeat_at=excluded.heartbeat_at""",
                (run_id, unit_id, owner, assignment["role"], token,
                 clock + ttl_seconds, clock),
            )
            return token

    def begin_worker_attempt(
        self, *, run_id: str, assignment: Mapping[str, Any], ttl_seconds: int,
        input_sha256: str, metadata: Mapping[str, Any] | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        if ttl_seconds < 30 or ttl_seconds > 86_400:
            raise ValueError("lease ttl must be between 30 and 86400 seconds")
        worker_id = _text(assignment, "worker_id")
        unit_id = _text(assignment, "unit_id")
        group_id = _text(assignment, "group_id")
        role = _text(assignment, "role")
        if group_id != unit_id or role not in ROLES or assignment.get("run_id") != run_id:
            raise ValueError("attempt assignment identity is invalid")
        clock = int(time.time()) if now is None else int(now)
        assert_no_semantic_claims(metadata or {})
        with self.connect() as connection, atomic(connection):
            run = connection.execute(
                "select status,max_concurrency,metadata_json from project_runs where run_id=?",
                (run_id,),
            ).fetchone()
            unit = connection.execute(
                """select group_id,status,resumable_status from migration_units
                   where run_id=? and unit_id=?""", (run_id, unit_id),
            ).fetchone()
            row = connection.execute(
                """select role,out_root,max_attempts,status from assignments
                   where run_id=? and unit_id=? and worker_id=?""",
                (run_id, unit_id, worker_id),
            ).fetchone()
            if (
                not run or run["status"] != "active" or not unit or unit["group_id"] != unit_id
                or unit["resumable_status"] in {"terminal", "exhausted"}
                or not row or row["status"] != "active" or row["role"] != role
                or row["out_root"] != assignment.get("out_root")
                or int(row["max_attempts"]) != int(assignment.get("max_attempts", 0))
            ):
                raise LeaseConflict("assignment is not an active immutable runnable unit")
            _require_assignment_digest(run["metadata_json"], assignment)
            lease = connection.execute(
                "select status,fencing_token,expires_at from leases where run_id=? and unit_id=?",
                (run_id, unit_id),
            ).fetchone()
            if lease and lease["status"] == "active" and int(lease["expires_at"]) > clock:
                raise LeaseConflict(f"unit {unit_id} already has an active lease")
            if connection.execute(
                "select 1 from attempts where run_id=? and unit_id=? and status='running'",
                (run_id, unit_id),
            ).fetchone():
                raise LeaseConflict(f"unit {unit_id} already has a running attempt")
            active = int(connection.execute(
                """select count(*) from leases where run_id=? and status='active'
                   and expires_at>?""", (run_id, clock),
            ).fetchone()[0])
            if active >= int(run["max_concurrency"]):
                raise LeaseConflict(f"run {run_id} reached max_concurrency")
            token = (int(lease["fencing_token"]) if lease else 0) + 1
            connection.execute(
                """insert into leases(run_id,unit_id,owner,role,status,fencing_token,expires_at,heartbeat_at)
                   values (?,?,?,?,'active',?,?,?) on conflict(run_id,unit_id) do update set
                   owner=excluded.owner,role=excluded.role,status='active',
                   fencing_token=excluded.fencing_token,expires_at=excluded.expires_at,
                   heartbeat_at=excluded.heartbeat_at""",
                (run_id, unit_id, worker_id, role, token, clock + ttl_seconds, clock),
            )
            ordinal = int(connection.execute(
                """select count(*) from attempts where run_id=? and unit_id=?
                   and worker_id=? and role=?""", (run_id, unit_id, worker_id, role),
            ).fetchone()[0]) + 1
            if ordinal > int(row["max_attempts"]):
                raise LedgerError(f"attempt limit reached for {run_id}/{unit_id}/{worker_id}")
            attempt_id = f"{run_id}:{unit_id}:{role}:{ordinal}"
            attempt_metadata = {
                **dict(metadata or {}),
                "run_id": run_id,
                "unit_id": unit_id,
                "group_id": group_id,
                "role": role,
                "worker_id": worker_id,
                "assignment_sha256": content_sha256(assignment),
                "lease_ttl_seconds": ttl_seconds,
                "command_started": False,
                "previous_status": unit["status"],
                "previous_resumable_status": unit["resumable_status"],
            }
            expected = UnitState(str(unit["status"]), str(unit["resumable_status"]))
            input_digest = _require_sha256(input_sha256, "input_sha256")
            timestamp = _now_text()
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,worker_id,status,
                   fencing_token,input_sha256,output_sha256,error_key,started_at,finished_at,metadata_json)
                   values (?,?,?,?,?,?,'running',?,?,null,null,?,null,?)""",
                (attempt_id, run_id, unit_id, role, ordinal, worker_id, token,
                 input_digest, timestamp, _json(attempt_metadata)),
            )
            TransitionAuthority(connection).apply(
                attempt_started_command(
                    run_id=run_id, unit_id=unit_id, attempt_id=attempt_id,
                    fencing_token=token, expected=expected, input_sha256=input_digest,
                ),
                created_at=timestamp,
            )
            return {"attempt_id": attempt_id, "fencing_token": token}

    def heartbeat_lease(
        self, *, run_id: str, unit_id: str, owner: str, fencing_token: int, ttl_seconds: int,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        clock = int(time.time())
        with self.connect() as connection, atomic(connection):
            self._require_fence(connection, run_id, unit_id, owner, fencing_token, clock)
            connection.execute(
                "update leases set heartbeat_at=?,expires_at=? where run_id=? and unit_id=?",
                (clock, clock + ttl_seconds, run_id, unit_id),
            )

    def release_lease(
        self, *, run_id: str, unit_id: str, owner: str, fencing_token: int,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            self._require_fence(connection, run_id, unit_id, owner, fencing_token)
            connection.execute(
                "update leases set status='released',heartbeat_at=? where run_id=? and unit_id=?",
                (int(time.time()), run_id, unit_id),
            )

    def recover_expired_attempts(
        self, *, run_id: str, now: int | None = None,
    ) -> list[str]:
        clock = int(time.time()) if now is None else int(now)
        recovered: list[str] = []
        with self.connect() as connection, atomic(connection):
            run = connection.execute(
                "select status from project_runs where run_id=?", (run_id,),
            ).fetchone()
            if not run:
                raise LedgerError("run does not exist")
            if run["status"] != "active":
                return recovered
            rows = connection.execute(
                """select t.*,a.max_attempts,l.status as lease_status,l.expires_at
                   from attempts t join assignments a on a.run_id=t.run_id
                     and a.unit_id=t.unit_id and a.worker_id=t.worker_id and a.role=t.role
                   left join leases l on l.run_id=t.run_id and l.unit_id=t.unit_id
                   where t.run_id=? and t.status='running' and
                     (l.run_id is null or l.status<>'active' or l.expires_at<=?)
                   order by t.started_at,t.attempt_id""", (run_id, clock),
            ).fetchall()
            terminal_rows = []
            for row in rows:
                metadata = _metadata(row["metadata_json"])
                started = metadata.get("command_started") is True
                count = int(connection.execute(
                    """select count(*) from attempts where run_id=? and unit_id=?
                       and worker_id=? and role=?""",
                    (run_id, row["unit_id"], row["worker_id"], row["role"]),
                ).fetchone()[0])
                exhausted = count >= int(row["max_attempts"])
                next_status = "blocked" if started else ("exhausted" if exhausted else "retry-ready")
                resumable = "terminal" if started else ("exhausted" if exhausted else "retryable")
                error_key = "worker_command_result_unknown" if started else "lease_expired"
                unit_id = str(row["unit_id"])
                expected = load_unit_state(connection, run_id, unit_id)
                timestamp = _now_text()
                connection.execute(
                    """update attempts set status=?,error_key=?,finished_at=? where attempt_id=?""",
                    ("blocked" if started else "failed", error_key, timestamp, row["attempt_id"]),
                )
                connection.execute(
                    "update leases set status='expired',heartbeat_at=? where run_id=? and unit_id=?",
                    (clock, run_id, unit_id),
                )
                TransitionAuthority(connection).apply(
                    lease_recovery_command(
                        run_id=run_id, unit_id=unit_id, row=row,
                        attempt_count=count, started=started, expected=expected,
                        target=UnitState(next_status, resumable), reason=error_key,
                    ),
                    created_at=timestamp,
                )
                if started:
                    terminal_rows.append(row)
                recovered.append(str(row["attempt_id"]))
            if terminal_rows:
                TransitionAuthority(connection).apply_run(
                    lease_recovery_run_command(
                        run_id=run_id, rows=terminal_rows, clock=clock,
                    )
                )
        return recovered


def _require_assignment_digest(metadata_json: str, assignment: Mapping[str, Any]) -> None:
    metadata = _metadata(metadata_json)
    binding = metadata.get("runtime_binding")
    records = binding.get("assignments") if isinstance(binding, Mapping) else None
    if not isinstance(records, list):
        raise LedgerError("run has no immutable runtime assignment binding")
    digest = content_sha256(assignment)
    matches = [item for item in records if isinstance(item, Mapping)
               and item.get("worker_id") == assignment.get("worker_id")]
    if len(matches) != 1 or matches[0].get("assignment_sha256") != digest:
        raise LedgerError("assignment does not match the immutable run binding")


def _metadata(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(value) if isinstance(value, str) else None
    except json.JSONDecodeError as error:
        raise LedgerError("ledger metadata is invalid JSON") from error
    if not isinstance(result, dict):
        raise LedgerError("ledger metadata must be an object")
    return result


def _text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"assignment {key} is invalid")
    return result


__all__ = ["LeaseLifecycleMixin"]
