from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .artifacts import write_json_artifact
from .ledger import LedgerError, ProjectLedger
from .project_completion_state import completion_result


def finalize_verified_project(
    *, paths: Mapping[str, Path | str], ledger: ProjectLedger, run_id: str,
    candidate_set_sha256: str, project_semantics: Mapping[str, Any],
    initial_build_ir_ref: Mapping[str, Any], final_build_ir_ref: Mapping[str, Any],
    evidence_reopener: Callable[..., dict[str, Any]],
    project_final_recorder: Callable[..., dict[str, Any]],
    project_completer: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    out_root = paths["out_root"]
    out_root_rel = paths["out_root_rel"]
    if not isinstance(out_root, Path) or not isinstance(out_root_rel, str):
        raise ValueError("project_completion_paths_invalid")
    try:
        evidence = evidence_reopener(
            ledger=ledger, artifact_root=out_root, out_root_rel=out_root_rel,
            run_id=run_id, candidate_set_sha256=candidate_set_sha256,
            verification=project_semantics,
        )
    except (LedgerError, OSError, TypeError, ValueError) as error:
        return completion_result(
            paths, run_id, "blocked", "project-final-oracle-evidence-revalidation",
            [str(error)[:96] or "project_test_semantic_evidence_drifted"],
            candidate_set_sha256, project_semantics=project_semantics,
        )
    try:
        project_final = project_final_recorder(
            ledger=ledger, out_root=out_root, out_root_rel=out_root_rel,
            run_id=run_id,
        )
        completed = project_completer(
            ledger=ledger, run_id=run_id,
            candidate_set_sha256=candidate_set_sha256,
        )
    except LedgerError as error:
        return completion_result(
            paths, run_id, "blocked", "project-final-semantic-project-gates",
            [str(error)], candidate_set_sha256,
        )
    receipt = {
        "schema_version": 1, "artifact_kind": "project-completion-receipt",
        "status": "completed", "run_id": run_id,
        "candidate_set_sha256": candidate_set_sha256,
        "project_final_record_id": project_final["record_id"],
        "project_final_evidence": project_final["evidence"],
        "build_ir_verifications": {
            "before_candidate_execution": dict(initial_build_ir_ref),
            "before_project_final": dict(final_build_ir_ref),
        },
        "project_test_evidence": evidence, "semantic_gate": True,
    }
    reference = write_json_artifact(
        out_root, "completion/completion-receipt.json", receipt,
    )
    return {**completed, "completion_receipt": reference}


__all__ = ["finalize_verified_project"]
