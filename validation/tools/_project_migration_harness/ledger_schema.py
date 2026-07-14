from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import count
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

from .ledger_security import SchemaVersionError, assert_no_secrets, safe_json
from .ledger_project_diagnostic_schema import PROJECT_DIAGNOSTIC_SCHEMA
from .ledger_project_repair_schema import PROJECT_REPAIR_SCHEMA
from .ledger_context_frontier_schema import CONTEXT_FRONTIER_SCHEMA
from .schema_integrity import assert_schema_integrity


SCHEMA_VERSION = 8
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAVEPOINTS = count()


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _require_repo_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field} must be a POSIX repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.parts[0].startswith("~") or ":" in path.parts[0]:
        raise ValueError(f"{field} must stay repository-relative")
    return path.as_posix()


def _json(value: Mapping[str, Any] | None) -> str:
    return safe_json(value)


@contextmanager
def atomic(connection: sqlite3.Connection, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
    nested = connection.in_transaction
    savepoint = f"project_ledger_{next(_SAVEPOINTS)}"
    connection.execute(f"SAVEPOINT {savepoint}" if nested else ("BEGIN IMMEDIATE" if immediate else "BEGIN"))
    try:
        yield connection
    except BaseException:
        if nested:
            connection.execute(f"ROLLBACK TO {savepoint}")
            connection.execute(f"RELEASE {savepoint}")
        else:
            connection.rollback()
        raise
    else:
        connection.execute(f"RELEASE {savepoint}") if nested else connection.commit()


_SCHEMA = (
    f"""create table if not exists schema_migrations(version integer primary key
        check(version={SCHEMA_VERSION}), applied_at text not null, schema_sha256 text not null
        check(length(schema_sha256)=64))""",
    """create table if not exists project_runs(run_id text primary key, project_key text not null,
       source_commit text not null, dag_sha256 text not null, initial_status text not null check(initial_status in
       ('active','completed','failed','cancelled')), status text not null check(status in
       ('active','completed','failed','cancelled')), max_concurrency integer not null check(max_concurrency>0),
       max_attempts integer not null check(max_attempts>0), created_at text not null, updated_at text not null,
       state_version integer not null check(state_version>=0), metadata_json text not null)""",
    """create table if not exists migration_units(run_id text not null, unit_id text not null,
       group_id text not null, wave_index integer not null check(wave_index>=0),
       initial_status text not null check(initial_status in
       ('pending','running','candidate-ready','gate-pending','retry-ready','failed','blocked','resume-ready',
        'completed','cancelled','exhausted')), initial_resumable_status text not null check(initial_resumable_status in
       ('ready','in_progress','awaiting_gate','retryable','last_good','terminal','exhausted')),
       status text not null check(status in
       ('pending','running','candidate-ready','gate-pending','retry-ready','failed','blocked','resume-ready',
        'completed','cancelled','exhausted')), resumable_status text not null check(resumable_status in
       ('ready','in_progress','awaiting_gate','retryable','last_good','terminal','exhausted')),
       state_version integer not null check(state_version>=0), content_sha256 text not null,
       last_good_artifact_id text, updated_at text not null,
       primary key(run_id,unit_id), foreign key(run_id) references project_runs(run_id) on delete cascade,
       foreign key(run_id,last_good_artifact_id,unit_id) references artifacts(run_id,artifact_id,unit_id)
       deferrable initially deferred)""",
    """create table if not exists assignments(run_id text not null, unit_id text not null, worker_id text not null
       check(length(worker_id)>0), role text not null check(role in
       ('planner','translator','reviewer','repairer')), out_root text not null,
       max_attempts integer not null check(max_attempts>0), status text not null check(status in
       ('active','disabled','completed')), created_at text not null,
       check(length(out_root)>0 and instr(out_root,'\\')=0 and substr(out_root,1,1) not in ('/','~')
       and instr('/'||out_root||'/','/../')=0 and instr(out_root,':')=0),
       primary key(run_id,unit_id,worker_id), unique(run_id,worker_id), unique(run_id,unit_id,role),
       unique(run_id,out_root), unique(run_id,unit_id,worker_id,role), foreign key(run_id,unit_id)
       references migration_units(run_id,unit_id) on delete cascade)""",
    """create table if not exists attempts(attempt_id text primary key, run_id text not null, unit_id text not null,
       role text not null check(role in ('planner','translator','reviewer','repairer')),
       ordinal integer not null check(ordinal>0), worker_id text not null,
       status text not null check(status in ('running','completed','failed','blocked','cancelled')),
       fencing_token integer not null check(fencing_token>0), input_sha256 text not null, output_sha256 text,
       error_key text, started_at text not null, finished_at text, metadata_json text not null,
       unique(run_id,unit_id,worker_id,role,ordinal), unique(attempt_id,run_id,unit_id),
       unique(attempt_id,run_id,unit_id,worker_id,fencing_token), foreign key(run_id,unit_id,worker_id,role)
       references assignments(run_id,unit_id,worker_id,role))""",
    """create table if not exists artifacts(run_id text not null, artifact_id text not null, unit_id text not null,
       attempt_id text not null, worker_id text not null, fencing_token integer not null, kind text not null,
       repo_rel_path text not null, content_sha256 text not null, status text not null check(status in
       ('written','candidate','diagnostic','reviewed','failed','blocked')), created_at text not null,
       metadata_json text not null, primary key(run_id,artifact_id), unique(run_id,artifact_id,unit_id),
       unique(run_id,repo_rel_path), foreign key(attempt_id,run_id,unit_id,worker_id,fencing_token)
       references attempts(attempt_id,run_id,unit_id,worker_id,fencing_token))""",
    """create table if not exists verifier_records(record_id text primary key, run_id text not null,
       unit_id text not null, candidate_artifact_id text not null, gate_family text not null check(gate_family in
       ('compile','oracle-replay-diff','negative','unsafe-alias','abi-layout','final-verification')),
       gate_epoch integer not null check(gate_epoch>0), kind text not null check(kind in ('verifier','gate')),
       status text not null check(status in ('passed','failed')), verifier_id text not null,
       evidence_path text not null, evidence_sha256 text not null, finished_at text not null,
       metadata_json text not null, unique(run_id,unit_id,candidate_artifact_id,gate_family,gate_epoch),
       foreign key(run_id,candidate_artifact_id,unit_id) references artifacts(run_id,artifact_id,unit_id))""",
    """create table if not exists transitions(transition_id integer primary key autoincrement,
       run_id text not null, unit_id text not null, scope text not null check(scope in ('unit','run')),
       command_kind text not null check(length(command_kind)>0),
       command_id text not null check(length(command_id)>0),
       from_status text not null, to_status text not null,
       from_resumable_status text, to_resumable_status text,
       from_version integer not null check(from_version>=0),
       to_version integer not null check(to_version=from_version+1),
       reason text not null, evidence_sha256 text not null check(length(evidence_sha256)=64),
       attempt_id text, fencing_token integer, clear_last_good_if text,
       set_last_good_artifact_id text, created_at text not null,
       unique(run_id,scope,command_id),
       check((scope='unit' and from_resumable_status is not null and to_resumable_status is not null)
          or (scope='run' and from_resumable_status is null and to_resumable_status is null
              and clear_last_good_if is null and set_last_good_artifact_id is null)),
       foreign key(run_id,unit_id) references migration_units(run_id,unit_id) on delete cascade,
       foreign key(attempt_id,run_id,unit_id) references attempts(attempt_id,run_id,unit_id))""",
    """create table if not exists leases(run_id text not null, unit_id text not null, owner text not null,
       role text not null, status text not null check(status in ('active','released','expired')),
       fencing_token integer not null check(fencing_token>0), expires_at integer not null,
       heartbeat_at integer not null, primary key(run_id,unit_id), foreign key(run_id,unit_id,owner,role)
       references assignments(run_id,unit_id,worker_id,role))""",
    """create table if not exists project_gate_requirements(run_id text not null,
       gate_kind text not null, required integer not null check(required in (0,1)),
       primary key(run_id,gate_kind), foreign key(run_id) references project_runs(run_id)
       on delete cascade)""",
    """create table if not exists candidate_sets(run_id text not null, candidate_set_sha256 text not null,
       member_count integer not null check(member_count>0), manifest_json text not null, created_at text not null,
       primary key(run_id,candidate_set_sha256), foreign key(run_id) references project_runs(run_id)
       on delete cascade)""",
    """create table if not exists candidate_set_members(run_id text not null, candidate_set_sha256 text not null,
       unit_id text not null, artifact_id text not null, content_sha256 text not null,
       primary key(run_id,candidate_set_sha256,unit_id),
       foreign key(run_id,candidate_set_sha256) references candidate_sets(run_id,candidate_set_sha256)
       on delete cascade, foreign key(run_id,artifact_id,unit_id)
       references artifacts(run_id,artifact_id,unit_id))""",
    """create table if not exists project_gate_records(record_id text primary key, run_id text not null,
       gate_kind text not null, gate_epoch integer not null check(gate_epoch>0),
       status text not null check(status in ('passed','failed')), candidate_set_sha256 text not null,
       verifier_id text not null, evidence_path text not null, evidence_sha256 text not null,
       finished_at text not null, metadata_json text not null,
       unique(run_id,candidate_set_sha256,gate_kind,gate_epoch), foreign key(run_id,gate_kind)
       references project_gate_requirements(run_id,gate_kind), foreign key(run_id,candidate_set_sha256)
       references candidate_sets(run_id,candidate_set_sha256))""",
    """create trigger if not exists project_run_default_gates after insert on project_runs begin
       insert into project_gate_requirements(run_id,gate_kind,required) values(new.run_id,'integration',1);
       insert into project_gate_requirements(run_id,gate_kind,required) values(new.run_id,'cargo-check',1);
       insert into project_gate_requirements(run_id,gate_kind,required) values(new.run_id,'cargo-test',1);
       insert into project_gate_requirements(run_id,gate_kind,required) values(new.run_id,'oracle-replay',1);
       insert into project_gate_requirements(run_id,gate_kind,required) values(new.run_id,'negative',1);
       insert into project_gate_requirements(run_id,gate_kind,required) values(new.run_id,'unsafe-alias-abi',1);
       insert into project_gate_requirements(run_id,gate_kind,required) values(new.run_id,'final-verification',1);
       end""",
    """create trigger if not exists assignment_attempt_limit before insert on assignments
       when new.max_attempts > (select max_attempts from project_runs where run_id=new.run_id)
       begin select raise(abort,'assignment max_attempts exceeds run limit'); end""",
    """create trigger if not exists candidate_sets_no_update before update on candidate_sets
       begin select raise(abort,'candidate sets are immutable'); end""",
    """create trigger if not exists candidate_set_members_no_update before update on candidate_set_members
       begin select raise(abort,'candidate set members are immutable'); end""",
    """create trigger if not exists transitions_no_update before update on transitions
       begin select raise(abort,'transition events are immutable'); end""",
    """create trigger if not exists transitions_no_delete before delete on transitions
       begin select raise(abort,'transition events are immutable'); end""",
    """create trigger if not exists project_run_initial_state_no_update
       before update of initial_status on project_runs
       begin select raise(abort,'project run initial state is immutable'); end""",
    """create trigger if not exists migration_unit_initial_state_no_update
       before update of initial_status,initial_resumable_status on migration_units
       begin select raise(abort,'migration unit initial state is immutable'); end""",
    "create unique index if not exists one_running_attempt_per_unit on attempts(run_id,unit_id) where status='running'",
    "create index if not exists attempts_by_assignment on attempts(run_id,unit_id,worker_id,role,ordinal)",
    "create index if not exists transitions_by_unit on transitions(run_id,unit_id,transition_id)",
    "create index if not exists verifier_latest_gate on verifier_records(run_id,unit_id,candidate_artifact_id,gate_family,gate_epoch)",
    "create index if not exists project_gates_latest on project_gate_records(run_id,candidate_set_sha256,gate_kind,gate_epoch)",
) + CONTEXT_FRONTIER_SCHEMA + PROJECT_DIAGNOSTIC_SCHEMA + PROJECT_REPAIR_SCHEMA


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


def migrate_schema(connection: sqlite3.Connection) -> None:
    existing = connection.execute(
        "select 1 from sqlite_master where type='table' and name='schema_migrations'"
    ).fetchone()
    if existing:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(schema_migrations)")]
        if columns != ["version", "applied_at", "schema_sha256"]:
            raise SchemaVersionError("ledger schema metadata layout mismatch")
        rows = connection.execute(
            "select version,schema_sha256 from schema_migrations order by version"
        ).fetchall()
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if len(rows) != 1 or rows[0][0] != SCHEMA_VERSION or user_version != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"ledger schema version mismatch: user_version={user_version}, expected={SCHEMA_VERSION}"
            )
        fingerprint = assert_schema_integrity(connection, _SCHEMA)
        if rows[0][1] != fingerprint:
            raise SchemaVersionError("ledger schema fingerprint metadata mismatch")
        return
    user_tables = connection.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
    ).fetchall()
    if user_tables:
        raise SchemaVersionError("unversioned ledger database is not accepted")
    with atomic(connection):
        for statement in _SCHEMA:
            connection.execute(statement)
        fingerprint = assert_schema_integrity(connection, _SCHEMA)
        connection.execute(
            "insert into schema_migrations(version,applied_at,schema_sha256) values (?,?,?)",
            (SCHEMA_VERSION, _now_text(), fingerprint),
        )
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


__all__ = [
    "SCHEMA_VERSION", "_json", "_now_text", "_require_repo_path", "_require_sha256",
    "assert_no_secrets", "atomic", "connect_database", "migrate_schema",
]
