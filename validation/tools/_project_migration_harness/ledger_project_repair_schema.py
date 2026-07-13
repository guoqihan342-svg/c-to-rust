from __future__ import annotations


PROJECT_REPAIR_SCHEMA = (
    """create table if not exists project_interface_receipts(
       run_id text not null, receipt_epoch integer not null check(receipt_epoch>0),
       coordinator_receipt_sha256 text not null,
       project_repair_queue_sha256 text not null, rust_project_ir_sha256 text not null,
       rust_project_interface_sha256 text not null,
       status text not null check(status in ('candidate-ready','repair-required')),
       diagnostic_count integer not null check(diagnostic_count>=0),
       queue_item_count integer not null check(queue_item_count>=0),
       receipt_json text not null, queue_json text not null, created_at text not null,
       primary key(run_id,coordinator_receipt_sha256),
       unique(run_id,receipt_epoch),
       unique(run_id,project_repair_queue_sha256),
       foreign key(run_id) references project_runs(run_id) on delete cascade)""",
    """create table if not exists project_repair_items(
       run_id text not null, project_repair_queue_sha256 text not null,
       repair_id text not null, diagnostic_code text not null,
       diagnostic_sha256 text not null, max_attempts integer not null check(max_attempts>0),
       item_json text not null, initial_status text not null check(initial_status='queued'),
       status text not null check(status in
       ('queued','running','candidate-ready','retry-ready','resolved','failed','exhausted','cancelled')),
       state_version integer not null check(state_version>=0),
       attempt_count integer not null check(attempt_count>=0 and attempt_count<=max_attempts),
       active_attempt_id text, candidate_ir_sha256 text, updated_at text not null,
       primary key(run_id,project_repair_queue_sha256,repair_id),
       unique(run_id,project_repair_queue_sha256,diagnostic_sha256),
       foreign key(run_id,project_repair_queue_sha256)
       references project_interface_receipts(run_id,project_repair_queue_sha256)
       on delete cascade,
       foreign key(active_attempt_id,run_id,project_repair_queue_sha256,repair_id)
       references project_repair_attempts(
       attempt_id,run_id,project_repair_queue_sha256,repair_id)
       deferrable initially deferred)""",
    """create table if not exists project_repair_attempts(
       attempt_id text primary key, run_id text not null,
       project_repair_queue_sha256 text not null, repair_id text not null,
       ordinal integer not null check(ordinal>0), worker_id text not null check(length(worker_id)>0),
       status text not null check(status in ('running','completed','failed','cancelled','recovered')),
       input_sha256 text not null, output_ir_sha256 text, error_key text,
       lease_ttl_seconds integer not null check(lease_ttl_seconds between 30 and 3600),
       lease_expires_at integer not null check(lease_expires_at>=0),
       command_started integer not null default 0 check(command_started in (0,1)),
       command_started_at text,
       started_at text not null, finished_at text, metadata_json text not null,
       unique(run_id,project_repair_queue_sha256,repair_id,ordinal),
       unique(attempt_id,run_id,project_repair_queue_sha256,repair_id),
       foreign key(run_id,project_repair_queue_sha256,repair_id)
       references project_repair_items(run_id,project_repair_queue_sha256,repair_id)
       on delete cascade)""",
    """create table if not exists project_repair_events(
       event_id integer primary key autoincrement, run_id text not null,
       project_repair_queue_sha256 text not null, repair_id text not null,
       command_kind text not null check(length(command_kind)>0),
       command_id text not null check(length(command_id)>0),
       from_status text not null, to_status text not null,
       from_version integer not null check(from_version>=0),
       to_version integer not null check(to_version=from_version+1),
       from_attempt_count integer not null check(from_attempt_count>=0),
       to_attempt_count integer not null check(to_attempt_count>=from_attempt_count),
       from_active_attempt_id text, to_active_attempt_id text,
       from_candidate_ir_sha256 text, to_candidate_ir_sha256 text,
       evidence_sha256 text not null check(length(evidence_sha256)=64),
       attempt_id text, reason text not null, created_at text not null,
       unique(run_id,command_id),
       foreign key(run_id,project_repair_queue_sha256,repair_id)
       references project_repair_items(run_id,project_repair_queue_sha256,repair_id)
       on delete cascade,
       foreign key(attempt_id,run_id,project_repair_queue_sha256,repair_id)
       references project_repair_attempts(
       attempt_id,run_id,project_repair_queue_sha256,repair_id))""",
    """create table if not exists project_repair_artifacts(
       run_id text not null, artifact_id text not null,
       project_repair_queue_sha256 text not null, repair_id text not null,
       attempt_id text not null, kind text not null check(length(kind)>0),
       repo_rel_path text not null, content_sha256 text not null check(length(content_sha256)=64),
       status text not null check(status in ('written','candidate','diagnostic','failed')),
       created_at text not null, metadata_json text not null,
       primary key(run_id,attempt_id,artifact_id),
       unique(run_id,attempt_id,repo_rel_path),
       foreign key(attempt_id,run_id,project_repair_queue_sha256,repair_id)
       references project_repair_attempts(
       attempt_id,run_id,project_repair_queue_sha256,repair_id)
       on delete cascade)""",
    """create trigger if not exists project_interface_receipts_no_update
       before update on project_interface_receipts
       begin select raise(abort,'project interface receipts are immutable'); end""",
    """create trigger if not exists project_interface_receipts_no_delete
       before delete on project_interface_receipts
       begin select raise(abort,'project interface receipts are immutable'); end""",
    """create trigger if not exists project_repair_events_no_update
       before update on project_repair_events
       begin select raise(abort,'project repair events are immutable'); end""",
    """create trigger if not exists project_repair_events_no_delete
       before delete on project_repair_events
       begin select raise(abort,'project repair events are immutable'); end""",
    """create trigger if not exists project_repair_artifacts_no_update
       before update on project_repair_artifacts
       begin select raise(abort,'project repair artifacts are immutable'); end""",
    """create trigger if not exists project_repair_artifacts_no_delete
       before delete on project_repair_artifacts
       begin select raise(abort,'project repair artifacts are immutable'); end""",
    """create trigger if not exists project_repair_item_identity_no_update
       before update of initial_status,diagnostic_code,diagnostic_sha256,max_attempts,item_json
       on project_repair_items
       begin select raise(abort,'project repair item identity is immutable'); end""",
    """create trigger if not exists project_repair_attempt_identity_no_update
       before update of run_id,project_repair_queue_sha256,repair_id,ordinal,worker_id,
       input_sha256,lease_ttl_seconds,lease_expires_at,started_at,metadata_json
       on project_repair_attempts
       begin select raise(abort,'project repair attempt identity is immutable'); end""",
    """create trigger if not exists project_repair_attempt_command_start_once
       before update of command_started,command_started_at on project_repair_attempts
       when not (
         old.command_started=0 and new.command_started=1
         and old.command_started_at is null and new.command_started_at is not null
         and old.status='running' and new.status='running'
       )
       begin select raise(abort,'project repair command start is monotonic'); end""",
    """create unique index if not exists one_running_project_repair_attempt
       on project_repair_attempts(run_id)
       where status='running'""",
    """create index if not exists project_repair_events_by_item
       on project_repair_events(
       run_id,project_repair_queue_sha256,repair_id,event_id)""",
)


__all__ = ["PROJECT_REPAIR_SCHEMA"]
