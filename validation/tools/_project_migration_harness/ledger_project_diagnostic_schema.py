from __future__ import annotations


PROJECT_DIAGNOSTIC_SCHEMA = (
    """create table if not exists project_diagnostic_intakes(
       intake_sha256 text primary key, run_id text not null,
       candidate_set_sha256 text not null, rust_project_ir_sha256 text not null,
       rust_project_interface_sha256 text not null,
       project_input_sha256 text not null, gate_record_id text not null unique,
       gate_kind text not null, gate_epoch integer not null check(gate_epoch>0),
       artifact_path text not null unique, artifact_size_bytes integer not null
       check(artifact_size_bytes>0), diagnostic_count integer not null
       check(diagnostic_count between 1 and 64), created_at text not null,
       foreign key(gate_record_id) references project_gate_records(record_id),
       foreign key(run_id,candidate_set_sha256)
       references candidate_sets(run_id,candidate_set_sha256))""",
    """create trigger if not exists project_diagnostic_intakes_no_update
       before update on project_diagnostic_intakes
       begin select raise(abort,'project diagnostic intakes are immutable'); end""",
    """create trigger if not exists project_diagnostic_intakes_no_delete
       before delete on project_diagnostic_intakes
       begin select raise(abort,'project diagnostic intakes are immutable'); end""",
    """create trigger if not exists project_gate_records_no_update
       before update on project_gate_records
       begin select raise(abort,'project gate records are immutable'); end""",
    """create trigger if not exists project_gate_records_no_delete
       before delete on project_gate_records
       begin select raise(abort,'project gate records are immutable'); end""",
    """create index if not exists project_diagnostic_intakes_latest
       on project_diagnostic_intakes(
       run_id,candidate_set_sha256,rust_project_ir_sha256,
       project_input_sha256,gate_kind,gate_epoch)""",
)


__all__ = ["PROJECT_DIAGNOSTIC_SCHEMA"]
