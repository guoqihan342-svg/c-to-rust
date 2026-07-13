from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.ledger_run_contract import (
    derive_migration_contract,
)
from validation.tools.project_migration_rust_project_test_support import (
    valid_build_ir,
)


def migration_run_metadata(
    out_root: Path, database: Path, *, run_id: str, dag_sha256: str,
    units: Sequence[Mapping[str, Any]], dependencies: Mapping[str, list[str]],
) -> dict[str, Any]:
    order = [
        str(item["unit_id"]) for item in sorted(
            units, key=lambda item: (int(item["wave_index"]), str(item["unit_id"])),
        )
    ]
    build = write_json_artifact(out_root, "plan/build-ir.json", valid_build_ir())
    build_verification = write_json_artifact(
        out_root, "plan/build-ir-verification.json",
        {"schema_version": 1, "status": "passed"},
    )
    worker_admission = write_json_artifact(
        out_root, "plan/build-ir-worker-admission.json",
        {"schema_version": 1, "status": "admitted"},
    )
    manifest = {
        "schema_version": 1,
        "dag": {unit_id: list(dependencies[unit_id]) for unit_id in sorted(dependencies)},
        "dag_order": order,
        "unsafe_policy": {
            "allow_unsafe": True, "max_total": None, "max_per_group": None,
        },
        "build_ir": {
            "status": "bound", "artifact": build,
            "verification": build_verification,
            "worker_admission": worker_admission,
        },
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    artifacts = {
        "integration_manifest": write_json_artifact(
            out_root, "plan/integration-manifest.json", manifest,
        ),
    }
    contract, _payload = derive_migration_contract(
        database, artifacts, run_id=run_id, dag_sha256=dag_sha256, units=units,
    )
    return {"artifacts": artifacts, "migration_contract": contract}


__all__ = ["migration_run_metadata"]
