from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .artifacts import canonical_json_bytes
from .execution_evidence import validate_provider_execution_evidence
from .gate_authority import (
    CANDIDATE_GATE_FAMILIES,
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    validate_candidate_verdict,
)
from .gate_evidence import read_content_addressed_json
from .generated_closure import verify_generated_build_closure
from .held_out_integrity import (
    IntegrityError,
    confined_path,
    file_sha256,
    repository_tree_sha256,
)
from .held_out_ledger_support import (
    HeldOutLedgerError,
    file_identity as _file_identity,
    json_object as _json_object,
    require as _require,
    require_no_sidecars as _require_no_sidecars,
)
from .ledger import ProjectLedger
from .ledger_project_gates import _require_latest_project_passes
from .ledger_verifier import _latest_candidate_records
from .orchestration_facts import read_artifact_reference


def verify_completed_project(
    *, ledger_path: Path, harness_root: Path, run_id: str,
    plan_sha256: str, repo_root: Path, source_commit: str,
    repository_tree_sha256_expected: str, compile_database: Path,
    compile_database_sha256: str,
) -> dict[str, Any]:
    ledger_file = Path(ledger_path).resolve(strict=True)
    _require_no_sidecars(ledger_file)
    before = _file_identity(ledger_file)
    try:
        ledger = ProjectLedger(ledger_file, read_only=True)
        with ledger.connect() as connection:
            run = connection.execute(
                "select * from project_runs where run_id=?", (run_id,)
            ).fetchone()
            _require(run is not None and run["status"] == "completed", "run is not completed")
            _require(str(run["source_commit"]).lower() == source_commit, "run source commit drifted")
            metadata = _json_object(run["metadata_json"], "run metadata")
            binding = metadata.get("runtime_binding")
            _require(
                isinstance(binding, Mapping)
                and binding.get("plan_sha256") == plan_sha256
                and binding.get("run_id") == run_id,
                "run is not bound to the held-out plan",
            )
            discovery_sha = _verify_discovery(
                ledger_file, metadata, repo_root, compile_database,
                compile_database_sha256,
            )
            members = _completed_members(connection, run_id)
            candidate_set = _verify_candidate_set(connection, run_id, members)
            provider_candidates = sum(
                _verify_candidate(
                    ledger, connection, harness_root, run_id, member
                )
                for member in members
            )
            _require(provider_candidates > 0, "held-out run has no AI provider candidate")
            project_records = _require_latest_project_passes(
                ledger, connection, run_id, candidate_set, include_final=True
            )
            _require(
                len({str(row["verifier_id"]) for row, _ in project_records}) >= 2,
                "project completion lacks independent host authorities",
            )
            running = connection.execute(
                "select count(*) from attempts where run_id=? and status='running'", (run_id,)
            ).fetchone()[0]
            _require(int(running) == 0, "completed run still has running attempts")
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        raise HeldOutLedgerError(str(error)) from error
    _require_no_sidecars(ledger_file)
    _require(before == _file_identity(ledger_file), "ledger changed during verification")
    _require(
        repository_tree_sha256(repo_root) == repository_tree_sha256_expected,
        "repository tree drifted during semantic verification",
    )
    return {
        "status": "accepted",
        "run_id": run_id,
        "candidate_set_sha256": candidate_set,
        "candidate_count": len(members),
        "provider_candidate_count": provider_candidates,
        "project_gate_count": len(project_records),
        "discovery_sha256": discovery_sha,
        "ledger_sha256": _file_identity(ledger_file)[-1],
        "translation_coverage_numerator": 1,
        "semantic_gate": True,
    }


def _verify_discovery(
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
    closure = payload.get("generated_build_closure")
    _require(isinstance(closure, dict), "generated build closure is missing")
    verified = verify_generated_build_closure(repo_root, closure)
    _require(
        closure.get("status") == "ready" and verified.get("status") == "verified",
        "generated build closure is not currently verified",
    )
    return hashlib.sha256(data).hexdigest()


def _completed_members(connection: Any, run_id: str) -> list[dict[str, str]]:
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


def _verify_candidate_set(
    connection: Any, run_id: str, members: list[dict[str, str]],
) -> str:
    manifest = [
        {key: item[key] for key in ("unit_id", "artifact_id", "content_sha256")}
        for item in members
    ]
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    row = connection.execute(
        "select member_count,manifest_json from candidate_sets where run_id=? and candidate_set_sha256=?",
        (run_id, digest),
    ).fetchone()
    _require(
        row is not None and int(row["member_count"]) == len(manifest)
        and row["manifest_json"] == encoded,
        "completed candidate set is missing or drifted",
    )
    stored = connection.execute(
        """select unit_id,artifact_id,content_sha256 from candidate_set_members
           where run_id=? and candidate_set_sha256=? order by unit_id""",
        (run_id, digest),
    ).fetchall()
    _require([dict(item) for item in stored] == manifest, "candidate set members drifted")
    return digest


def _verify_candidate(
    ledger: ProjectLedger, connection: Any, harness_root: Path,
    run_id: str, member: Mapping[str, str],
) -> int:
    read_artifact_reference(harness_root, {
        "path": member["repo_rel_path"], "sha256": member["content_sha256"],
    })
    records = _latest_candidate_records(
        connection, run_id, member["unit_id"], member["artifact_id"]
    )
    by_family = {str(row["gate_family"]): row for row in records}
    _require(set(by_family) == CANDIDATE_GATE_FAMILIES, "candidate gate bundle is incomplete")
    for family, row in by_family.items():
        _require(
            row["status"] == "passed"
            and row["kind"] == candidate_kind(family)
            and row["verifier_id"] == candidate_authority(family),
            "candidate gate is not a host-owned pass",
        )
        payload = read_content_addressed_json(
            ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"])
        )
        validate_candidate_verdict(
            payload, run_id=run_id, unit_id=member["unit_id"],
            candidate_artifact_id=member["artifact_id"],
            candidate_sha256=member["content_sha256"], gate_family=family,
            status="passed", verifier_id=str(row["verifier_id"]),
            kind=str(row["kind"]),
        )
    final = by_family["final-verification"]
    _require(
        int(final["ledger_rowid"]) > max(
            int(by_family[family]["ledger_rowid"])
            for family in CANDIDATE_REQUIRED_GATES
        ),
        "candidate final gate predates a prerequisite",
    )
    attempt = connection.execute(
        "select worker_id,fencing_token,role,metadata_json from attempts where attempt_id=?",
        (member["attempt_id"],),
    ).fetchone()
    _require(attempt is not None, "candidate attempt is missing")
    attempt_metadata = _json_object(attempt["metadata_json"], "attempt metadata")
    executions = connection.execute(
        """select * from artifacts where run_id=? and unit_id=? and attempt_id=?
           and kind='provider-execution' and status='written' order by rowid""",
        (run_id, member["unit_id"], member["attempt_id"]),
    ).fetchall()
    if attempt_metadata.get("command_started") is True or executions:
        _require(len(executions) == 1, "candidate provider execution is missing or ambiguous")
        validate_provider_execution_evidence(
            ledger.path, dict(executions[0]), run_id=run_id,
            unit_id=member["unit_id"], attempt_id=member["attempt_id"],
            worker_id=str(attempt["worker_id"]),
            fencing_token=int(attempt["fencing_token"]), role=str(attempt["role"]),
        )
        return 1
    return 0


__all__ = ["HeldOutLedgerError", "verify_completed_project"]
