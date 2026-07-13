from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import canonical_json_bytes
from .build_ir_validation import verify_build_ir_artifact
from .held_out_integrity import confined_path, file_sha256
from .held_out_ledger_support import (
    HeldOutLedgerError,
    require as _require,
)
from .ledger import ProjectLedger
from .ledger_run_contract import load_migration_contract
from .orchestration_facts import read_artifact_reference


def verify_discovery(
    ledger_path: Path, metadata: Mapping[str, Any], repo_root: Path,
    compile_database: Path, compile_database_sha256: str,
) -> str:
    artifacts = metadata.get("artifacts")
    reference = artifacts.get("discovery") if isinstance(artifacts, Mapping) else None
    _require(isinstance(reference, Mapping), "run discovery artifact is missing")
    out_root = ledger_path.parent.parent
    data = read_artifact_reference(out_root, reference)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise HeldOutLedgerError("run discovery artifact is invalid JSON") from error
    _require(
        isinstance(payload, dict) and canonical_json_bytes(payload) == data,
        "run discovery artifact is not canonical",
    )
    compile_fact = payload.get("compile_database")
    relative_compile = compile_database.resolve(strict=True).relative_to(
        repo_root.resolve(strict=True)
    ).as_posix()
    _require(
        payload.get("status") == "ready"
        and isinstance(compile_fact, Mapping)
        and compile_fact.get("path") == relative_compile
        and compile_fact.get("sha256") == compile_database_sha256,
        "run discovery does not match held-out compile input",
    )
    units = payload.get("translation_units")
    _require(isinstance(units, list) and units, "run discovery has no translation units")
    for unit in units:
        source = unit.get("source") if isinstance(unit, Mapping) else None
        _require(isinstance(source, Mapping), "translation-unit source binding is missing")
        path = confined_path(
            repo_root, str(source.get("path", "")), "translation-unit source",
            must_exist=True,
        )
        _require(
            file_sha256(path) == source.get("sha256")
            and path.stat().st_size == source.get("size_bytes"),
            "translation-unit source binding drifted",
        )
    build_ir_ref = artifacts.get("build_ir")
    _require(isinstance(build_ir_ref, Mapping), "canonical BuildIR artifact is missing")
    verified = verify_build_ir_artifact(repo_root, out_root, build_ir_ref)
    _require(
        verified.get("status") == "verified",
        "canonical BuildIR is not currently verified",
    )
    return hashlib.sha256(data).hexdigest()


def completed_members(connection: Any, run_id: str) -> list[dict[str, str]]:
    rows = connection.execute(
        """select u.unit_id,u.status,u.resumable_status,u.last_good_artifact_id,
                  a.content_sha256,a.status as artifact_status,a.repo_rel_path,a.attempt_id
           from migration_units u left join artifacts a
             on a.run_id=u.run_id and a.unit_id=u.unit_id
            and a.artifact_id=u.last_good_artifact_id
           where u.run_id=? order by u.unit_id""",
        (run_id,),
    ).fetchall()
    _require(bool(rows), "completed run has no migration units")
    result = []
    for row in rows:
        _require(
            row["status"] == "completed"
            and row["resumable_status"] == "terminal"
            and row["last_good_artifact_id"]
            and row["artifact_status"] == "candidate"
            and row["content_sha256"],
            "completed unit does not retain a last-good candidate",
        )
        result.append({
            "unit_id": str(row["unit_id"]),
            "artifact_id": str(row["last_good_artifact_id"]),
            "content_sha256": str(row["content_sha256"]),
            "repo_rel_path": str(row["repo_rel_path"]),
            "attempt_id": str(row["attempt_id"]),
        })
    return result


def verify_candidate_set(
    ledger: ProjectLedger, connection: Any, run_id: str,
    members: list[dict[str, str]],
) -> str:
    candidate_members = [
        {key: item[key] for key in ("unit_id", "artifact_id", "content_sha256")}
        for item in members
    ]
    contract, _integration = load_migration_contract(ledger.path, connection, run_id)
    manifest = {
        "schema_version": 2,
        "scope": "project-final",
        "run_context_sha256": contract["context_sha256"],
        "dag_sha256": contract["dag_sha256"],
        "integration_manifest_sha256": contract["integration_manifest"]["sha256"],
        "roots": [item["unit_id"] for item in candidate_members],
        "members": candidate_members,
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    row = connection.execute(
        "select member_count,manifest_json from candidate_sets where run_id=? and candidate_set_sha256=?",
        (run_id, digest),
    ).fetchone()
    _require(
        row is not None
        and int(row["member_count"]) == len(candidate_members)
        and row["manifest_json"] == encoded,
        "completed candidate set is missing or drifted",
    )
    stored = connection.execute(
        """select unit_id,artifact_id,content_sha256 from candidate_set_members
           where run_id=? and candidate_set_sha256=? order by unit_id""",
        (run_id, digest),
    ).fetchall()
    _require(
        [dict(item) for item in stored] == candidate_members,
        "candidate set members drifted",
    )
    return digest


__all__ = ["completed_members", "verify_candidate_set", "verify_discovery"]
