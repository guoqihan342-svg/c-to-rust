from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .held_out_candidate_verification import verify_candidate as _verify_candidate
from .held_out_integrity import IntegrityError, repository_tree_sha256
from .held_out_ledger_support import (
    HeldOutLedgerError,
    file_identity as _file_identity,
    json_object as _json_object,
    require as _require,
    require_no_sidecars as _require_no_sidecars,
)
from .held_out_run_verification import (
    completed_members as _completed_members,
    verify_candidate_set as _verify_candidate_set,
    verify_discovery as _verify_discovery,
)
from .ledger import ProjectLedger
from .ledger_project_gates import _require_latest_project_passes


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
                "select * from project_runs where run_id=?", (run_id,),
            ).fetchone()
            _require(
                run is not None and run["status"] == "completed",
                "run is not completed",
            )
            _require(
                str(run["source_commit"]).lower() == source_commit,
                "run source commit drifted",
            )
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
            candidate_set = _verify_candidate_set(
                ledger, connection, run_id, members,
            )
            provider_candidates = sum(
                _verify_candidate(
                    ledger, connection, harness_root, run_id, member, candidate_set,
                )
                for member in members
            )
            _require(
                provider_candidates > 0,
                "held-out run has no AI provider candidate",
            )
            project_records = _require_latest_project_passes(
                ledger, connection, run_id, candidate_set, include_final=True,
            )
            _require(
                len({str(row["verifier_id"]) for row, _ in project_records}) >= 2,
                "project completion lacks independent host authorities",
            )
            running = connection.execute(
                "select count(*) from attempts where run_id=? and status='running'",
                (run_id,),
            ).fetchone()[0]
            _require(
                int(running) == 0,
                "completed run still has running attempts",
            )
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


__all__ = ["HeldOutLedgerError", "verify_completed_project"]
