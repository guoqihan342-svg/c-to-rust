from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.candidate_compile_evidence import (
    compile_observation_payload,
)
from validation.tools._project_migration_harness.gate_candidate_sets import (
    candidate_set_manifest,
)
from validation.tools._project_migration_harness.ledger_artifact_binding import (
    candidate_source_reference,
)
from validation.tools._project_migration_harness.ledger_run_contract import (
    load_migration_contract,
)
from validation.tools.project_migration_sandbox_test_support import (
    bind_execution_plan,
)


def compile_observation_for_ledger(
    ledger: Any, harness_root: Path, *, run_id: str, unit_id: str,
    candidate_artifact_id: str, candidate_set_sha256: str,
    execution: dict[str, Any],
) -> dict[str, Any]:
    with ledger.connect() as connection:
        candidate = connection.execute(
            """select repo_rel_path,content_sha256 from artifacts
               where run_id=? and unit_id=? and artifact_id=?""",
            (run_id, unit_id, candidate_artifact_id),
        ).fetchone()
        contract, _manifest = load_migration_contract(
            ledger.path, connection, run_id,
        )
        cohort = candidate_set_manifest(
            connection, run_id, candidate_set_sha256,
        )
    source = candidate_source_reference(ledger.path, dict(candidate))
    base = f"target/run/test-quarantine/{candidate_artifact_id}"
    quarantine_payload = {
        "schema_version": 1,
        "candidate_set": {"sha256": candidate_set_sha256, "manifest": cohort},
    }
    quarantine = write_json_artifact(
        harness_root, f"{base}/migration-quarantine.json", quarantine_payload,
    )
    generation_payload = {
        "schema_version": 1,
        "quarantine_manifest": {
            "path": "migration-quarantine.json", "sha256": quarantine["sha256"],
        },
    }
    generation = write_json_artifact(
        harness_root, f"{base}/migration-last-good.json", generation_payload,
    )
    return compile_observation_payload(
        run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=str(candidate["content_sha256"]),
        candidate_set_sha256=candidate_set_sha256,
        candidate_source=source,
        run_contract=contract,
        quarantine={
            "generation_sha256": generation["sha256"],
            "quarantine_manifest": quarantine,
            "generation_manifest": generation,
        },
        execution=bind_execution_plan(execution, generation["sha256"]),
    )


__all__ = ["compile_observation_for_ledger"]
