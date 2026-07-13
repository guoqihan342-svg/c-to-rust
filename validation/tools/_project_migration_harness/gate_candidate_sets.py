from __future__ import annotations

import hashlib
import json
from typing import Any

from .ledger_schema import _now_text
from .ledger_security import LedgerError


def bind_current_candidate_set(connection: Any, run_id: str) -> str:
    members = current_candidate_members(connection, run_id)
    manifest_json = json.dumps(members, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    existing = connection.execute(
        """select member_count,manifest_json from candidate_sets
           where run_id=? and candidate_set_sha256=?""",
        (run_id, digest),
    ).fetchone()
    if existing is None:
        connection.execute(
            """insert into candidate_sets(run_id,candidate_set_sha256,member_count,
               manifest_json,created_at) values (?,?,?,?,?)""",
            (run_id, digest, len(members), manifest_json, _now_text()),
        )
        for member in members:
            connection.execute(
                """insert into candidate_set_members(run_id,candidate_set_sha256,unit_id,
                   artifact_id,content_sha256) values (?,?,?,?,?)""",
                (run_id, digest, member["unit_id"], member["artifact_id"], member["content_sha256"]),
            )
    elif int(existing["member_count"]) != len(members) or existing["manifest_json"] != manifest_json:
        raise LedgerError("immutable candidate set manifest does not match its digest")
    _verify_members(connection, run_id, digest, members)
    return digest


def assert_current_candidate_set(connection: Any, run_id: str, expected_sha256: str) -> None:
    actual = bind_current_candidate_set(connection, run_id)
    if actual != expected_sha256:
        raise LedgerError("project gates are not bound to the current last-good candidate set")


def current_candidate_members(connection: Any, run_id: str) -> list[dict[str, str]]:
    units = connection.execute(
        """select u.unit_id,u.resumable_status,u.last_good_artifact_id,
                  a.content_sha256,a.status as artifact_status
           from migration_units u left join artifacts a
             on a.run_id=u.run_id and a.unit_id=u.unit_id
            and a.artifact_id=u.last_good_artifact_id
           where u.run_id=? order by u.unit_id""",
        (run_id,),
    ).fetchall()
    if not units:
        raise LedgerError("project run has no migration units")
    members: list[dict[str, str]] = []
    for row in units:
        if (
            row["resumable_status"] != "last_good"
            or not row["last_good_artifact_id"]
            or row["artifact_status"] != "candidate"
            or not row["content_sha256"]
        ):
            raise LedgerError("candidate set requires last-good for every migration unit")
        members.append({
            "unit_id": str(row["unit_id"]),
            "artifact_id": str(row["last_good_artifact_id"]),
            "content_sha256": str(row["content_sha256"]),
        })
    return members


def _verify_members(
    connection: Any, run_id: str, digest: str, expected: list[dict[str, str]],
) -> None:
    rows = connection.execute(
        """select unit_id,artifact_id,content_sha256 from candidate_set_members
           where run_id=? and candidate_set_sha256=? order by unit_id""",
        (run_id, digest),
    ).fetchall()
    actual = [dict(row) for row in rows]
    if actual != expected:
        raise LedgerError("immutable candidate set members do not match the manifest")


__all__ = [
    "assert_current_candidate_set", "bind_current_candidate_set",
    "current_candidate_members",
]
