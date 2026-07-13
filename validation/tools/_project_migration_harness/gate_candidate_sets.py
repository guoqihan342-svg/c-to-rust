from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .gate_candidate_closure import (
    current_candidate_members,
    verification_candidate_members,
)
from .ledger_run_contract import load_migration_contract
from .ledger_schema import _now_text, _require_sha256
from .ledger_security import LedgerError


MANIFEST_KEYS = {
    "schema_version", "scope", "run_context_sha256", "dag_sha256",
    "integration_manifest_sha256", "roots", "members",
}
SCOPES = {"wave-provisional", "project-final"}


def bind_current_candidate_set(
    connection: Any, run_id: str, *, database_path: Path,
) -> str:
    contract, _manifest = load_migration_contract(database_path, connection, run_id)
    members = current_candidate_members(connection, run_id)
    return bind_candidate_set(
        connection, run_id, members, scope="project-final",
        roots=[item["unit_id"] for item in members], contract=contract,
    )


def bind_verification_candidate_set(
    connection: Any, run_id: str, *, database_path: Path,
    scope: str = "wave-provisional",
) -> str:
    contract, _manifest = load_migration_contract(database_path, connection, run_id)
    members, roots = verification_candidate_members(
        connection, run_id, contract, scope=scope,
    )
    return bind_candidate_set(
        connection, run_id, members, scope=scope, roots=roots, contract=contract,
    )


def bind_candidate_set(
    connection: Any, run_id: str, members: list[dict[str, str]], *,
    scope: str, roots: list[str], contract: dict[str, Any],
) -> str:
    members = _validated_members(connection, run_id, members)
    if scope not in SCOPES:
        raise LedgerError("candidate set scope or roots are invalid")
    roots = _validated_roots(roots)
    context = contract.get("context_sha256")
    dag = contract.get("dag_sha256")
    integration = contract.get("integration_manifest")
    integration_sha = integration.get("sha256") if isinstance(integration, dict) else None
    for value, label in (
        (context, "run_context_sha256"), (dag, "dag_sha256"),
        (integration_sha, "integration_manifest_sha256"),
    ):
        _require_sha256(str(value), label)
    manifest = {
        "schema_version": 2,
        "scope": scope,
        "run_context_sha256": context,
        "dag_sha256": dag,
        "integration_manifest_sha256": integration_sha,
        "roots": roots,
        "members": members,
    }
    manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
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
                (run_id, digest, member["unit_id"], member["artifact_id"],
                 member["content_sha256"]),
            )
    elif int(existing["member_count"]) != len(members) or existing["manifest_json"] != manifest_json:
        raise LedgerError("immutable candidate set manifest does not match its digest")
    _verify_members(connection, run_id, digest, members)
    return digest


def assert_current_candidate_set(
    connection: Any, run_id: str, expected_sha256: str, *, database_path: Path,
) -> None:
    actual = bind_current_candidate_set(connection, run_id, database_path=database_path)
    if actual != expected_sha256:
        raise LedgerError("project gates are not bound to the current last-good candidate set")


def assert_verification_candidate_set(
    connection: Any, run_id: str, expected_sha256: str, *, database_path: Path,
) -> None:
    expected = candidate_set_manifest(connection, run_id, expected_sha256)
    actual = bind_verification_candidate_set(
        connection, run_id, database_path=database_path, scope=str(expected["scope"]),
    )
    if actual != expected_sha256:
        raise LedgerError("candidate gates are not bound to the current verification candidate set")


def candidate_set_manifest(
    connection: Any, run_id: str, candidate_set_sha256: str,
) -> dict[str, Any]:
    digest = _require_sha256(candidate_set_sha256, "candidate_set_sha256")
    row = connection.execute(
        "select manifest_json from candidate_sets where run_id=? and candidate_set_sha256=?",
        (run_id, digest),
    ).fetchone()
    if row is None:
        raise LedgerError("candidate set is not bound to this run")
    try:
        manifest = json.loads(str(row["manifest_json"]))
    except json.JSONDecodeError as error:
        raise LedgerError("candidate set manifest is invalid") from error
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    if (
        not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS
        or manifest.get("schema_version") != 2 or manifest.get("scope") not in SCOPES
        or hashlib.sha256(encoded.encode("utf-8")).hexdigest() != digest
    ):
        raise LedgerError("candidate set manifest is invalid")
    roots = _validated_roots(manifest.get("roots"))
    members = _validated_members(connection, run_id, manifest.get("members"))
    _verify_members(connection, run_id, digest, members)
    return {**manifest, "roots": roots, "members": members}


def candidate_set_members(
    connection: Any, run_id: str, candidate_set_sha256: str,
) -> list[dict[str, str]]:
    return candidate_set_manifest(connection, run_id, candidate_set_sha256)["members"]


def _validated_members(
    connection: Any, run_id: str, values: Any,
) -> list[dict[str, str]]:
    if not isinstance(values, list) or not values:
        raise LedgerError("candidate set requires at least one member")
    members = []
    seen = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != {
            "unit_id", "artifact_id", "content_sha256",
        }:
            raise LedgerError("candidate set member schema is invalid")
        unit_id, artifact_id = str(value["unit_id"]), str(value["artifact_id"])
        digest = _require_sha256(str(value["content_sha256"]), "content_sha256")
        if not unit_id or not artifact_id or unit_id in seen:
            raise LedgerError("candidate set members must have unique units")
        row = connection.execute(
            """select kind,status,content_sha256 from artifacts
               where run_id=? and unit_id=? and artifact_id=?""",
            (run_id, unit_id, artifact_id),
        ).fetchone()
        if (
            row is None or row["kind"] != "rust-candidate"
            or row["status"] != "candidate" or row["content_sha256"] != digest
        ):
            raise LedgerError("candidate set member does not match a Rust candidate artifact")
        seen.add(unit_id)
        members.append({
            "unit_id": unit_id,
            "artifact_id": artifact_id,
            "content_sha256": digest,
        })
    return sorted(members, key=lambda item: item["unit_id"])


def _validated_roots(values: Any) -> list[str]:
    if (
        not isinstance(values, list) or not values
        or not all(isinstance(item, str) and item for item in values)
        or len(values) != len(set(values))
    ):
        raise LedgerError("candidate set roots are invalid")
    roots = sorted(values)
    if roots != values:
        raise LedgerError("candidate set roots must be sorted")
    return roots


def _verify_members(
    connection: Any, run_id: str, digest: str, expected: list[dict[str, str]],
) -> None:
    rows = connection.execute(
        """select unit_id,artifact_id,content_sha256 from candidate_set_members
           where run_id=? and candidate_set_sha256=? order by unit_id""",
        (run_id, digest),
    ).fetchall()
    if [dict(row) for row in rows] != expected:
        raise LedgerError("immutable candidate set members do not match the manifest")


__all__ = [
    "assert_current_candidate_set", "assert_verification_candidate_set",
    "bind_candidate_set", "bind_current_candidate_set",
    "bind_verification_candidate_set", "candidate_set_manifest",
    "candidate_set_members", "current_candidate_members",
    "verification_candidate_members",
]
