from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger import LedgerError, ProjectLedger
from .orchestration_facts import read_artifact_reference
from .project_preflight import (
    FIXED_AGENT, FIXED_COMMAND, FIXED_VARIANT,
    validate_project_worker_preflight,
)
from .project_repair_ingest import ingest_project_repair_response
from .project_repair_recorded_result import RECORDED_RESULT_ARTIFACT_STATUSES
from .project_repair_request_reopener import (
    reopen_active_project_repair_request,
)


def ingest_recorded_project_repair_result(
    request_reference: Mapping[str, Any], response_reference: Mapping[str, Any], *,
    ledger: ProjectLedger, harness_root: Path, out_root: Path,
    out_root_rel: str,
) -> dict[str, Any]:
    request = _request_with_bound_preflight(
        request_reference, ledger=ledger, harness_root=harness_root,
    )
    attempt_id = str(request["execution_binding"]["attempt_id"])
    _assert_recorded_artifacts(
        ledger, attempt_id=attempt_id, request_reference=request_reference,
        response_reference=response_reference, harness_root=harness_root,
    )
    try:
        response = json.loads(
            read_artifact_reference(harness_root, response_reference).decode("utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("recorded project repair response is unreadable") from error
    if not isinstance(response, dict):
        raise LedgerError("recorded project repair response is not an object")
    try:
        ingested = ingest_project_repair_response(
            request, response, ledger=ledger, harness_root=harness_root,
            out_root=out_root, out_root_rel=out_root_rel,
        )
    except Exception:
        projection = ledger.project_repair_projection(
            run_id=str(request["run_id"]),
            queue_sha256=str(request["project_repair_queue_sha256"]),
            repair_id=str(request["repair_id"]),
        )
        if projection.status != "running":
            raise
        return {
            "schema_version": 1, "status": "ingest-required",
            "stage": "project-repair-provider-result-recorded",
            "run_id": request["run_id"], "repair_id": request["repair_id"],
            "attempt_id": attempt_id, "provider_invocations": 0,
            "model_launched": False, "semantic_gate": False,
        }
    return {
        "schema_version": 1, "status": ingested["status"],
        "stage": "project-repair-recorded-result-ingested",
        "run_id": request["run_id"], "repair_id": request["repair_id"],
        "attempt_id": attempt_id, "ledger": ingested,
        "provider_invocations": 0, "model_launched": False,
        "semantic_gate": False,
    }


def _request_with_bound_preflight(
    reference: Mapping[str, Any], *, ledger: ProjectLedger, harness_root: Path,
) -> dict[str, Any]:
    try:
        raw = json.loads(read_artifact_reference(harness_root, reference).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("recorded project repair request is unreadable") from error
    if not isinstance(raw, dict):
        raise LedgerError("recorded project repair request is not an object")
    binding = raw.get("preflight_binding")
    preflight_ref = binding.get("preflight") if isinstance(binding, Mapping) else None
    logical = binding.get("logical_model") if isinstance(binding, Mapping) else None
    resolved = binding.get("resolved_model") if isinstance(binding, Mapping) else None
    if not isinstance(preflight_ref, Mapping):
        raise LedgerError("recorded project repair preflight binding is missing")
    validate_project_worker_preflight(
        preflight_ref, harness_root=harness_root, run_id=str(raw.get("run_id")),
        logical_model=str(logical), resolved_model=str(resolved),
        opencode_command=FIXED_COMMAND, agent=FIXED_AGENT, variant=FIXED_VARIANT,
    )
    return reopen_active_project_repair_request(
        reference, preflight_ref, ledger=ledger, root=harness_root,
        logical_model=str(logical), resolved_model=str(resolved),
    )


def _assert_recorded_artifacts(
    ledger: ProjectLedger, *, attempt_id: str,
    request_reference: Mapping[str, Any], response_reference: Mapping[str, Any],
    harness_root: Path,
) -> None:
    with ledger.connect() as connection:
        rows = connection.execute(
            """select kind,repo_rel_path,content_sha256
               from project_repair_artifacts where attempt_id=? and kind in
               ('project-repair-request','provider-prompt',
               'provider-raw_response','provider-invocation_receipt',
               'provider-parsed_response','provider-execution_report')""",
            (attempt_id,),
        ).fetchall()
    by_kind = {str(row["kind"]): row for row in rows}
    required = set(RECORDED_RESULT_ARTIFACT_STATUSES)
    if set(by_kind) != required or len(rows) != len(required):
        raise LedgerError("recorded project repair result evidence is incomplete")
    expected = {
        "project-repair-request": request_reference,
        "provider-parsed_response": response_reference,
    }
    for kind, reference in expected.items():
        row = by_kind[kind]
        if (
            row["repo_rel_path"] != reference.get("path")
            or row["content_sha256"] != reference.get("sha256")
        ):
            raise LedgerError("recorded project repair result binding drifted")
    try:
        for row in by_kind.values():
            read_artifact_reference(harness_root, {
                "path": row["repo_rel_path"],
                "sha256": row["content_sha256"],
            })
    except (OSError, ValueError) as error:
        raise LedgerError(
            "recorded project repair result artifact drifted"
        ) from error


__all__ = ["ingest_recorded_project_repair_result"]
