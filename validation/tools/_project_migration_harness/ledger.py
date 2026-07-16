from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .ledger_artifacts import ArtifactLedgerMixin
from .ledger_attempt_budget import next_attempt_ordinal
from .ledger_schema import (
    SCHEMA_VERSION, _json, _now_text, _require_repo_path, _require_sha256,
    atomic, connect_database, migrate_schema,
)
from .ledger_lease import LeaseLifecycleMixin
from .ledger_frontier_gate import reject_split_lease_for_context_frontier
from .ledger_context_frontier import (
    ContextFrontierLedgerMixin, insert_context_frontiers,
    prepare_portfolio_frontiers, verify_initial_context_frontiers,
)
from .ledger_project_diagnostics import ProjectDiagnosticLedgerMixin
from .ledger_project_completion import ProjectCompletionLedgerMixin
from .ledger_project_gates import ProjectGateMixin
from .ledger_project_repair import ProjectRepairLedgerMixin
from .ledger_project_repair_artifacts import ProjectRepairArtifactMixin
from .ledger_recovery import LedgerRecoveryMixin
from .ledger_run_metadata import prepare_run_metadata
from .ledger_run_state import require_active_completion
from .ledger_security import (
    LedgerError, LeaseConflict, SchemaVersionError, StaleFence,
    assert_no_semantic_claims,
)
from .ledger_transition_authority import TransitionAuthority, load_unit_projection
from .ledger_transition_commands import attempt_started_command
from .ledger_transition_policy import UnitState
from .ledger_verifier import HostVerifierMixin
from .ledger_views import LedgerViewMixin
from .runtime_binding import RuntimeBindingMixin

_ROLES = {"planner", "translator", "reviewer", "repairer"}
class ProjectLedger(
    HostVerifierMixin,
    ProjectCompletionLedgerMixin,
    ProjectGateMixin,
    ProjectDiagnosticLedgerMixin,
    ProjectRepairLedgerMixin,
    ProjectRepairArtifactMixin,
    RuntimeBindingMixin,
    ContextFrontierLedgerMixin,
    LeaseLifecycleMixin,
    LedgerRecoveryMixin,
    LedgerViewMixin,
    ArtifactLedgerMixin,
):
    def __init__(
        self, path: str | Path, *, busy_timeout_ms: int = 5_000,
        read_only: bool = False,
    ) -> None:
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms
        self.read_only = read_only
        with self.connect() as connection:
            migrate_schema(connection)

    def connect(self) -> sqlite3.Connection:
        return connect_database(
            self.path, busy_timeout_ms=self.busy_timeout_ms,
            read_only=self.read_only,
        )

    @staticmethod
    def _insert_assignment(
        connection: sqlite3.Connection, run_id: str, item: Mapping[str, Any], now: str,
    ) -> None:
        role = str(item.get("role", ""))
        if role not in _ROLES:
            raise ValueError(f"unsupported worker role: {role}")
        worker_id = str(item.get("worker_id", ""))
        unit_id = str(item.get("unit_id", item.get("group_id", "")))
        if not worker_id or not unit_id:
            raise ValueError("assignment worker_id and unit_id are required")
        connection.execute(
            """insert into assignments(run_id,unit_id,worker_id,role,out_root,max_attempts,status,created_at)
               values (?,?,?,?,?,?,?,?)""",
            (run_id, unit_id, worker_id, role, _require_repo_path(str(item.get("out_root", "")), "out_root"),
             int(item.get("max_attempts", 0)), "active", now),
        )

    def create_run(
        self, *, run_id: str, project_key: str, source_commit: str, dag_sha256: str,
        units: Iterable[Mapping[str, Any]], max_concurrency: int, max_attempts: int,
        metadata: Mapping[str, Any] | None = None,
        assignments: Iterable[Mapping[str, Any]] | None = None,
        portfolio: Mapping[str, Any] | None = None,
    ) -> None:
        if max_concurrency < 1 or max_attempts < 1:
            raise ValueError("run concurrency and attempt limits must be positive")
        rows, assigned = list(units), list(assignments or ())
        frontiers = prepare_portfolio_frontiers(
            portfolio, run_id=run_id,
            unit_ids=[str(item["unit_id"]) for item in rows],
        )
        bound_metadata = prepare_run_metadata(
            self.path, metadata, run_id=run_id, dag_sha256=dag_sha256,
            assignments=assigned, units=rows, portfolio_payload=portfolio,
        )
        now = _now_text()
        with self.connect() as connection, atomic(connection):
            connection.execute(
                """insert into project_runs(run_id,project_key,source_commit,dag_sha256,
                   initial_status,status,max_concurrency,max_attempts,created_at,updated_at,
                   state_version,metadata_json)
                   values (?,?,?,?,'active','active',?,?,?,?,0,?)""",
                (run_id, project_key, source_commit, _require_sha256(dag_sha256, "dag_sha256"),
                 max_concurrency, max_attempts, now, now, _json(bound_metadata)),
            )
            for unit in rows:
                status = str(unit.get("status", "pending"))
                resumable = str(unit.get("resumable_status", "ready"))
                UnitState(status, resumable)
                connection.execute(
                    """insert into migration_units(run_id,unit_id,group_id,wave_index,
                       initial_status,initial_resumable_status,status,resumable_status,state_version,
                       content_sha256,last_good_artifact_id,updated_at)
                       values (?,?,?,?,?,?,?,?,0,?,null,?)""",
                    (run_id, str(unit["unit_id"]), str(unit["group_id"]), int(unit["wave_index"]),
                     status, resumable, status, resumable,
                     _require_sha256(str(unit["content_sha256"]), "content_sha256"), now),
                )
            for item in assigned:
                self._insert_assignment(connection, run_id, item, now)
            insert_context_frontiers(
                connection, run_id=run_id, rows=frontiers, now=now,
            )

    def register_assignments(self, *, run_id: str, assignments: Iterable[Mapping[str, Any]]) -> None:
        now = _now_text()
        with self.connect() as connection, atomic(connection):
            require_active_completion(connection, run_id, action="assignments")
            if connection.execute(
                "select 1 from context_frontiers where run_id=? limit 1", (run_id,),
            ).fetchone():
                raise LedgerError("portfolio-bound assignments are immutable")
            for item in assignments:
                self._insert_assignment(connection, run_id, item, now)

    def create_or_resume_run(self, **kwargs: Any) -> str:
        units = list(kwargs["units"])
        assignments_supplied = "assignments" in kwargs
        assignments = list(kwargs.get("assignments") or ())
        portfolio = kwargs.get("portfolio")
        frontiers_supplied = (
            isinstance(portfolio, Mapping) and "context_frontiers" in portfolio
        )
        expected_frontiers = prepare_portfolio_frontiers(
            portfolio, run_id=str(kwargs["run_id"]),
            unit_ids=[str(item["unit_id"]) for item in units],
        )
        payload = {
            **kwargs, "units": units, "assignments": assignments,
        }
        try:
            self.create_run(**payload)
            return "created"
        except sqlite3.IntegrityError:
            run_id = str(kwargs["run_id"])
            metadata = prepare_run_metadata(
                self.path, kwargs.get("metadata"), run_id=run_id,
                dag_sha256=str(kwargs["dag_sha256"]), assignments=assignments,
                units=units, portfolio_payload=kwargs.get("portfolio"),
            )
            with self.connect() as connection:
                run = connection.execute(
                    """select project_key,source_commit,dag_sha256,max_concurrency,max_attempts,
                              metadata_json
                       from project_runs where run_id=?""", (run_id,),
                ).fetchone()
                actual = connection.execute(
                    """select unit_id,group_id,wave_index,content_sha256 from migration_units
                       where run_id=? order by unit_id""", (run_id,),
                ).fetchall()
                actual_assignments = connection.execute(
                    """select unit_id,worker_id,role,out_root,max_attempts from assignments
                       where run_id=? order by unit_id,worker_id""", (run_id,),
                ).fetchall()
                if frontiers_supplied:
                    verify_initial_context_frontiers(
                        connection, run_id=run_id, expected=expected_frontiers,
                    )
            expected = sorted((str(x["unit_id"]), str(x["group_id"]), int(x["wave_index"]),
                               str(x["content_sha256"])) for x in units)
            expected_assignments = sorted((str(x.get("unit_id", x.get("group_id", ""))),
                                           str(x["worker_id"]), str(x["role"]), str(x["out_root"]),
                                           int(x["max_attempts"])) for x in assignments)
            immutable = (kwargs["project_key"], kwargs["source_commit"], kwargs["dag_sha256"],
                         kwargs["max_concurrency"], kwargs["max_attempts"])
            actual_immutable = tuple(run)[:5] if run is not None else None
            actual_metadata = json.loads(run["metadata_json"]) if run is not None else {}
            expected_binding = metadata.get("runtime_binding")
            expected_contract = metadata.get("migration_contract")
            if (run is None or actual_immutable != immutable or [tuple(row) for row in actual] != expected
                    or (assignments_supplied and [tuple(row) for row in actual_assignments] != expected_assignments)):
                raise LedgerError("run_id already exists with different immutable inputs")
            if expected_binding is not None and actual_metadata.get("runtime_binding") != expected_binding:
                raise LedgerError("run_id already exists with a different runtime binding")
            if expected_contract is not None and actual_metadata.get("migration_contract") != expected_contract:
                raise LedgerError("run_id already exists with a different migration contract")
            return "resumed"

    @staticmethod
    def _require_fence(
        connection: sqlite3.Connection, run_id: str, unit_id: str, owner: str,
        fencing_token: int, now: int | None = None,
    ) -> None:
        clock = int(time.time()) if now is None else int(now)
        row = connection.execute(
            "select owner,status,fencing_token,expires_at from leases where run_id=? and unit_id=?",
            (run_id, unit_id),
        ).fetchone()
        if (not row or row["owner"] != owner or row["status"] != "active"
                or row["fencing_token"] != fencing_token or row["expires_at"] <= clock):
            raise StaleFence(f"stale fencing token for {run_id}/{unit_id}")

    def start_attempt(
        self, *, run_id: str, unit_id: str, role: str, worker_id: str,
        fencing_token: int, input_sha256: str, metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if role not in _ROLES:
            raise ValueError(f"unsupported worker role: {role}")
        assert_no_semantic_claims(metadata or {})
        with self.connect() as connection, atomic(connection):
            require_active_completion(connection, run_id, action="attempt start")
            reject_split_lease_for_context_frontier(
                connection, run_id=run_id, unit_id=unit_id,
            )
            self._require_fence(connection, run_id, unit_id, worker_id, fencing_token)
            assignment = connection.execute(
                """select role,max_attempts from assignments where run_id=? and unit_id=?
                   and worker_id=? and status='active'""", (run_id, unit_id, worker_id),
            ).fetchone()
            if not assignment or assignment["role"] != role:
                raise LedgerError("attempt role does not match the active worker assignment")
            ordinal = next_attempt_ordinal(
                connection, run_id=run_id, unit_id=unit_id,
                worker_id=worker_id, role=role,
                max_attempts=int(assignment["max_attempts"]),
            )
            attempt_id = f"{run_id}:{unit_id}:{role}:{ordinal}"
            expected = load_unit_projection(connection, run_id, unit_id)
            input_digest = _require_sha256(input_sha256, "input_sha256")
            now = _now_text()
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,worker_id,status,fencing_token,
                   input_sha256,output_sha256,error_key,started_at,finished_at,metadata_json)
                   values (?,?,?,?,?,?,'running',?,?,null,null,?,null,?)""",
                (attempt_id, run_id, unit_id, role, ordinal, worker_id, fencing_token,
                 input_digest, now, _json(metadata)),
            )
            TransitionAuthority(connection).apply(
                attempt_started_command(
                    run_id=run_id, unit_id=unit_id, attempt_id=attempt_id,
                    fencing_token=fencing_token, expected=expected,
                    input_sha256=input_digest,
                ),
                created_at=now,
            )
            return attempt_id

    def _running_attempt(
        self, connection: sqlite3.Connection, attempt_id: str, owner: str, fencing_token: int,
    ) -> sqlite3.Row:
        attempt = connection.execute(
            """select run_id,unit_id,role,status,worker_id,fencing_token from attempts
               where attempt_id=?""", (attempt_id,),
        ).fetchone()
        if not attempt or attempt["status"] != "running":
            raise LedgerError(f"attempt is not running: {attempt_id}")
        if attempt["worker_id"] != owner or attempt["fencing_token"] != fencing_token:
            raise StaleFence("attempt identity does not match worker_id/fencing_token")
        self._require_fence(connection, attempt["run_id"], attempt["unit_id"], owner, fencing_token)
        return attempt

__all__ = [
    "LedgerError", "LeaseConflict", "ProjectLedger", "SCHEMA_VERSION",
    "SchemaVersionError", "StaleFence",
]
