from __future__ import annotations


CONTEXT_FRONTIER_SCHEMA = (
    """create table if not exists context_frontiers(
       run_id text not null, unit_id text not null,
       initial_status text not null check(initial_status in ('pending_retrieval','ready')),
       status text not null check(status in ('pending_retrieval','ready')),
       state_version integer not null check(state_version>=0),
       initial_head_json text not null, initial_head_sha256 text not null check(length(initial_head_sha256)=64),
       head_json text not null, head_sha256 text not null check(length(head_sha256)=64),
       updated_at text not null, primary key(run_id,unit_id),
       foreign key(run_id,unit_id) references migration_units(run_id,unit_id) on delete cascade)""",
    """create table if not exists context_frontier_events(
       event_id integer primary key autoincrement, run_id text not null, unit_id text not null,
       command_kind text not null check(command_kind in ('selection_ready','selection_invalidated')),
       command_id text not null check(length(command_id)>0),
       from_status text not null check(from_status in ('pending_retrieval','ready')),
       to_status text not null check(to_status in ('pending_retrieval','ready')),
       from_version integer not null check(from_version>=0),
       to_version integer not null check(to_version=from_version+1),
       from_head_sha256 text not null check(length(from_head_sha256)=64),
       to_head_json text not null, to_head_sha256 text not null check(length(to_head_sha256)=64),
       evidence_sha256 text not null check(length(evidence_sha256)=64), created_at text not null,
       unique(run_id,command_id), unique(run_id,unit_id,to_version),
       foreign key(run_id,unit_id)
       references context_frontiers(run_id,unit_id) on delete cascade)""",
    """create trigger if not exists context_frontier_events_no_update
       before update on context_frontier_events
       begin select raise(abort,'context frontier events are immutable'); end""",
    """create trigger if not exists context_frontier_events_no_delete
       before delete on context_frontier_events
       begin select raise(abort,'context frontier events are immutable'); end""",
    """create trigger if not exists context_frontier_initial_state_no_update
       before update of initial_status,initial_head_json,initial_head_sha256 on context_frontiers
       begin select raise(abort,'context frontier initial state is immutable'); end""",
    """create index if not exists context_frontier_events_by_unit
       on context_frontier_events(run_id,unit_id,event_id)""",
)


__all__ = ["CONTEXT_FRONTIER_SCHEMA"]
