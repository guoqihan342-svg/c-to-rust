from __future__ import annotations

import json
from typing import Any

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, write_json_artifact,
)
from validation.tools._project_migration_harness.project_completion_receipt import (
    completion_receipt_payload, write_durable_completion_receipt,
)


def write_completion_receipt(
    case: Any, candidate_set_sha256: str, *,
    project_final_record_id: str | None = None,
) -> dict[str, Any]:
    with case.ledger.connect() as connection:
        final = connection.execute(
            """select record_id,evidence_path,evidence_sha256 from project_gate_records
               where run_id='run' and gate_kind='final-verification'
               order by gate_epoch desc limit 1""",
        ).fetchone()
        oracle = connection.execute(
            """select record_id from project_gate_records
               where run_id='run' and gate_kind='oracle-replay'
               order by gate_epoch desc limit 1""",
        ).fetchone()
    if final is None or oracle is None:
        raise AssertionError("completion receipt fixture requires project gates")
    final_path = case.harness.joinpath(*str(final["evidence_path"]).split("/"))
    final_payload = final_path.read_bytes()
    final_reference = {
        "path": str(final["evidence_path"]),
        "sha256": str(final["evidence_sha256"]),
        "size_bytes": len(final_payload),
    }
    if canonical_json_bytes(json.loads(final_payload.decode("utf-8"))) != final_payload:
        raise AssertionError("completion final evidence fixture is not canonical")
    builds = {}
    for key, phase in (
        ("before_candidate_execution", "before-candidate-execution"),
        ("before_project_final", "before-project-final"),
    ):
        builds[key] = write_json_artifact(
            case.out_root,
            f"completion/project-final-build-ir-{phase}.json",
            {
                "schema_version": 1,
                "artifact_kind": "project-final-build-ir-verification",
                "status": "verified",
                "verification_phase": phase,
            },
        )
    project_test_evidence = {
        "schema_version": 1,
        "artifact_kind": "project-test-semantic-evidence-binding",
        "status": "verified",
        "inventory": {"path": "plan/tests.json", "sha256": "1" * 64, "size_bytes": 1},
        "mapping": {"path": "completion/mapping.json", "sha256": "2" * 64, "size_bytes": 1},
        "oracle": {"path": "verification/project-test/oracle/" + "3" * 64 + ".json", "sha256": "3" * 64, "size_bytes": 1},
        "summary": {
            "case_count": 1, "mismatch_count": 0, "crash_count": 0,
            "summary_sha256": "4" * 64,
        },
        "project_gate_record_id": str(oracle["record_id"]),
        "semantic_gate": False,
    }
    payload = completion_receipt_payload(
        run_id="run", candidate_set_sha256=candidate_set_sha256,
        project_final={
            "record_id": project_final_record_id or str(final["record_id"]),
            "evidence": final_reference,
        },
        project_test_evidence=project_test_evidence,
        initial_build_ir_ref=builds["before_candidate_execution"],
        final_build_ir_ref=builds["before_project_final"],
    )
    return write_durable_completion_receipt(case.out_root, payload)


__all__ = ["write_completion_receipt"]
