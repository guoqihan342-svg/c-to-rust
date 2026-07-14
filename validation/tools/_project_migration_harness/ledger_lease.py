from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_attempt_budget import consumed_attempt_count, next_attempt_ordinal
from .ledger_schema import _json, _now_text, _require_sha256, atomic
from .ledger_security import LedgerError, LeaseConflict, assert_no_semantic_claims
from .ledger_frontier_gate import (
    reject_split_lease_for_context_frontier, require_ready_context_frontier,
)
from .ledger_lease_contract import (
    metadata as _metadata, require_assignment_digest as _require_assignment_digest,
    require_launch_claim, text as _text,
)
from .ledger_transition_authority import (
    TransitionAuthority, load_run_projection, load_unit_projection,
)
from .ledger_transition_commands import (
    attempt_started_command, lease_recovery_command,
    lease_recovery_run_command,
)
from .ledger_transition_policy import UnitState


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
            reject_split_lease_for_context_frontier(
                connection, run_id=run_id, unit_id=unit_id,
            )
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
        context_frontier: Mapping[str, Any] | None = None,
        launch_claim: Mapping[str, Any] | None = None,
        schedule_sha256: str | None = None,
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
                """select group_id,status,resumable_status,state_version from migration_units
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
            frontier = require_ready_context_frontier(
                connection, run_id=run_id, unit_id=unit_id,
                expected=context_frontier,
            )
            bound_claim = require_launch_claim(
                run_id=run_id, assignment=assignment, unit=dict(unit),
                frontier=frontier, claim=launch_claim,
                schedule_sha256=schedule_sha256,
            )
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
            ordinal = next_attempt_ordinal(
                connection, run_id=run_id, unit_id=unit_id,
                worker_id=worker_id, role=role,
                max_attempts=int(row["max_attempts"]),
            )
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
            if bound_claim is not None:
                attempt_metadata["launch_claim"] = {
                    key: value for key, value in bound_claim.items()
                    if key != "schedule_sha256"
                }
                attempt_metadata["schedule_sha256"] = bound_claim["schedule_sha256"]
            expected = load_unit_projection(connection, run_id, unit_id)
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
                count = consumed_attempt_count(
                    connection, run_id=run_id, unit_id=str(row["unit_id"]),
                    worker_id=str(row["worker_id"]), role=str(row["role"]),
                )
                exhausted = count >= int(row["max_attempts"])
                next_status = "blocked" if started else ("exhausted" if exhausted else "retry-ready")
                resumable = "terminal" if started else ("exhausted" if exhausted else "retryable")
                error_key = "worker_command_result_unknown" if started else "lease_expired"
                unit_id = str(row["unit_id"])
                expected = load_unit_projection(connection, run_id, unit_id)
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
                        target=UnitState(next_status, resumable),
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
                        expected=load_run_projection(connection, run_id),
                    )
                )
        return recovered


__all__ = ["LeaseLifecycleMixin"]
