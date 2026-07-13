from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.accepted_candidates import (
    candidate_set_descriptors,
)
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
from validation.tools._project_migration_harness.project_rust_ir import (
    derive_bound_project_ir, persist_project_ir,
)
from validation.tools._project_migration_harness.quarantine_generation import (
    materialize_rust_project_ir_quarantine_generation,
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
        contract, manifest = load_migration_contract(
            ledger.path, connection, run_id,
        )
        cohort = candidate_set_manifest(
            connection, run_id, candidate_set_sha256,
        )
    source = candidate_source_reference(ledger.path, dict(candidate))
    out_root = ledger.path.parent.parent
    out_root_rel = out_root.relative_to(harness_root).as_posix()
    descriptors = candidate_set_descriptors(
        ledger, run_id=run_id, out_root_rel=out_root_rel,
        candidate_set_sha256=candidate_set_sha256,
    )
    rust_project_ir = derive_bound_project_ir(
        migration_contract=contract, migration_manifest=manifest,
        candidate_descriptors=descriptors, artifact_root=out_root,
    )
    ir_ref = persist_project_ir(out_root, "test-quarantine-ir", rust_project_ir)
    quarantine_root = harness_root / "target/test-quarantine" / candidate_artifact_id
    quarantine_root.parent.mkdir(parents=True, exist_ok=True)
    materialized = materialize_rust_project_ir_quarantine_generation(
        rust_project_ir, descriptors, out_root, quarantine_root,
        candidate_set_sha256, cohort,
    )
    if materialized.get("status") != "materialized":
        raise AssertionError(materialized)
    generation_sha = str(materialized["generation"]["sha256"])
    return compile_observation_payload(
        run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=str(candidate["content_sha256"]),
        candidate_set_sha256=candidate_set_sha256,
        candidate_source=source,
        run_contract=contract,
        quarantine={
            "generation_sha256": generation_sha,
            "quarantine_manifest": _repo_ref(
                harness_root, quarantine_root, materialized["manifest_ref"],
            ),
            "generation_manifest": _repo_ref(
                harness_root, quarantine_root, materialized["generation_manifest_ref"],
            ),
            "rust_project_ir": _repo_ref(harness_root, out_root, ir_ref),
            "rust_project_ir_sha256": rust_project_ir["ir_sha256"],
            "rust_project_interface_sha256": rust_project_ir["interface_sha256"],
            "rust_project_ir_scope": materialized["rust_project_ir_scope"],
            "generator": materialized["generator"],
        },
        execution=bind_execution_plan(execution, generation_sha),
    )


def _repo_ref(
    harness_root: Path, base: Path, value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError("test artifact reference is invalid")
    path = base.joinpath(*Path(str(value["path"])).parts)
    return {
        "path": path.relative_to(harness_root).as_posix(),
        "sha256": value["sha256"], "size_bytes": value["size_bytes"],
    }


__all__ = ["compile_observation_for_ledger"]
