from __future__ import annotations

from typing import Any

from .candidate_pool_selection import load_candidate_pool
from .ledger_security import LedgerError


def current_candidate_members(connection: Any, run_id: str) -> list[dict[str, str]]:
    units = connection.execute(
        """select u.unit_id,u.resumable_status,u.last_good_artifact_id,
                  a.content_sha256,a.status as artifact_status,a.kind as artifact_kind
           from migration_units u left join artifacts a
             on a.run_id=u.run_id and a.unit_id=u.unit_id
            and a.artifact_id=u.last_good_artifact_id
           where u.run_id=? order by u.unit_id""",
        (run_id,),
    ).fetchall()
    if not units:
        raise LedgerError("project run has no migration units")
    members = []
    for row in units:
        if (
            row["resumable_status"] != "last_good" or not row["last_good_artifact_id"]
            or row["artifact_status"] != "candidate"
            or row["artifact_kind"] != "rust-candidate" or not row["content_sha256"]
        ):
            raise LedgerError("candidate set requires last-good for every migration unit")
        members.append(_member(row["unit_id"], row["last_good_artifact_id"], row["content_sha256"]))
    return members


def verification_candidate_members(
    connection: Any, run_id: str, contract: dict[str, Any], *, scope: str,
) -> tuple[list[dict[str, str]], list[str]]:
    if scope == "project-final":
        members = current_candidate_members(connection, run_id)
        return members, [item["unit_id"] for item in members]
    if scope != "wave-provisional":
        raise LedgerError("verification candidate set scope is invalid")
    units = connection.execute(
        """select unit_id,status,resumable_status,last_good_artifact_id
           from migration_units where run_id=? order by unit_id""",
        (run_id,),
    ).fetchall()
    states = {str(row["unit_id"]): row for row in units}
    roots = sorted(
        unit_id for unit_id, row in states.items()
        if row["status"] in {"candidate-ready", "gate-pending"}
    )
    if not roots:
        raise LedgerError("verification candidate set requires an active candidate")
    dependencies = _dependency_map(contract, states)
    root_set = set(roots)
    ancestors = {
        root: _transitive_dependencies(root, dependencies) for root in roots
    }
    if any((root_set - {root}) & values for root, values in ancestors.items()):
        raise LedgerError("active verification roots must be dependency-independent")
    closure = root_set | set().union(*ancestors.values())
    members = []
    for unit_id in sorted(closure):
        if unit_id in roots:
            members.append(_selected_candidate(connection, run_id, unit_id))
            continue
        state = states[unit_id]
        if state["resumable_status"] != "last_good" or not state["last_good_artifact_id"]:
            raise LedgerError("verification candidate dependency has no last-good artifact")
        artifact = connection.execute(
            """select content_sha256 from artifacts where run_id=? and unit_id=?
               and artifact_id=? and kind='rust-candidate' and status='candidate'""",
            (run_id, unit_id, state["last_good_artifact_id"]),
        ).fetchone()
        if artifact is None:
            raise LedgerError("verification candidate dependency artifact is unavailable")
        members.append(_member(unit_id, state["last_good_artifact_id"], artifact["content_sha256"]))
    return members, roots


def _dependency_map(
    contract: dict[str, Any], states: dict[str, Any],
) -> dict[str, list[str]]:
    edges = contract.get("dependency_edges")
    if not isinstance(edges, list):
        raise LedgerError("run dependency edges are missing")
    result = {}
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"unit_id", "dependencies"}:
            raise LedgerError("run dependency edge is invalid")
        unit_id = edge.get("unit_id")
        values = edge.get("dependencies")
        if unit_id not in states or not isinstance(values, list) or any(item not in states for item in values):
            raise LedgerError("run dependency edge does not match migration units")
        result[str(unit_id)] = list(values)
    if set(result) != set(states):
        raise LedgerError("run dependency graph is incomplete")
    return result


def _selected_candidate(connection: Any, run_id: str, unit_id: str) -> dict[str, str]:
    selected = load_candidate_pool(connection, run_id, unit_id)["selected_candidate"]
    if selected is None:
        raise LedgerError("active verification unit has no selected completed candidate")
    return _member(unit_id, selected["artifact_id"], selected["content_sha256"])


def _transitive_dependencies(
    root: str, dependencies: dict[str, list[str]],
) -> set[str]:
    result: set[str] = set()
    pending = list(dependencies[root])
    while pending:
        unit_id = pending.pop()
        if unit_id in result:
            continue
        result.add(unit_id)
        pending.extend(dependencies[unit_id])
    return result


def _member(unit_id: Any, artifact_id: Any, digest: Any) -> dict[str, str]:
    return {
        "unit_id": str(unit_id), "artifact_id": str(artifact_id),
        "content_sha256": str(digest),
    }


__all__ = ["current_candidate_members", "verification_candidate_members"]
