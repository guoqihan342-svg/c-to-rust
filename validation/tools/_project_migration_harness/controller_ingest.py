from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import content_sha256, write_bytes_artifact, write_json_artifact
from .ledger import ProjectLedger
from .orchestration_facts import read_artifact_reference
from .worker_result_contracts import normalize_worker_result


def ingest_worker_result(
    response: Mapping[str, Any], *, ledger: ProjectLedger,
    harness_root: Path, run_id: str, worker_id: str,
    attempt_id: str | None = None, fencing_token: int | None = None,
) -> dict[str, Any]:
    attempt = _attempt(
        ledger, run_id=run_id, worker_id=worker_id,
        attempt_id=attempt_id, fencing_token=fencing_token,
    )
    token = int(attempt["fencing_token"])
    trusted_attempt_id = str(attempt["attempt_id"])
    metadata = attempt["metadata"]
    request_ref = {
        "path": metadata.get("request_path"),
        "sha256": metadata.get("request_sha256"),
    }
    try:
        request = json.loads(
            read_artifact_reference(harness_root, request_ref).decode("utf-8")
        )
        if not isinstance(request, dict):
            raise ValueError("worker request artifact must be a JSON object")
        normalized = normalize_worker_result(request, response)
        reference, artifact_id, artifact_metadata = _materialize_result(
            normalized,
            harness_root=harness_root,
            out_root=str(attempt["out_root"]),
            attempt_id=trusted_attempt_id,
        )
        ledger.record_artifact_and_finish(
            run_id=run_id,
            unit_id=str(attempt["unit_id"]),
            owner=worker_id,
            fencing_token=token,
            artifact_id=artifact_id,
            attempt_id=trusted_attempt_id,
            kind=str(normalized["artifact_kind"]),
            repo_rel_path=reference["path"],
            content_sha256=reference["sha256"],
            artifact_status=str(normalized["artifact_status"]),
            next_status=str(normalized["next_status"]),
            metadata=artifact_metadata,
            terminal=bool(normalized.get("terminal")),
            fail_run=bool(normalized.get("fail_run")),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        failed = fail_running_worker_attempt(
            ledger=ledger,
            run_id=run_id,
            worker_id=worker_id,
            attempt_id=trusted_attempt_id,
            fencing_token=token,
            error_key=type(error).__name__.lower(),
        )
        return {
            "schema_version": 1,
            "status": "rejected" if failed["status"] == "retry-ready" else "manual-reconcile",
            "run_id": run_id,
            "worker_id": worker_id,
            "attempt_id": trusted_attempt_id,
            "reason": "worker_result_contract_invalid",
            "semantic_gate": False,
        }
    ledger.release_lease(
        run_id=run_id,
        unit_id=str(attempt["unit_id"]),
        owner=worker_id,
        fencing_token=token,
    )
    return {
        "schema_version": 1,
        "status": "recorded",
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt_id": trusted_attempt_id,
        "artifact_id": artifact_id,
        "artifact": reference,
        "next_status": normalized["next_status"],
        "terminal": bool(normalized.get("terminal")),
        "semantic_gate": False,
    }


def fail_running_worker_attempt(
    *, ledger: ProjectLedger, run_id: str, worker_id: str, error_key: str,
    attempt_id: str | None = None, fencing_token: int | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    attempt = _attempt(
        ledger, run_id=run_id, worker_id=worker_id,
        attempt_id=attempt_id, fencing_token=fencing_token,
    )
    token = int(attempt["fencing_token"])
    command_started = attempt["metadata"].get("command_started") is True
    may_retry = (not command_started) if retryable is None else (retryable and not command_started)
    ledger.finish_attempt(
        attempt_id=str(attempt["attempt_id"]),
        owner=worker_id,
        fencing_token=token,
        status="failed" if may_retry else "blocked",
        next_status="retry-ready" if may_retry else "blocked",
        error_key=error_key,
    )
    ledger.release_lease(
        run_id=run_id,
        unit_id=str(attempt["unit_id"]),
        owner=worker_id,
        fencing_token=token,
    )
    return {
        "schema_version": 1,
        "status": "retry-ready" if may_retry else "manual-reconcile",
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt_id": attempt["attempt_id"],
        "command_started": command_started,
        "semantic_gate": False,
    }


def _attempt(
    ledger: ProjectLedger, *, run_id: str, worker_id: str,
    attempt_id: str | None, fencing_token: int | None,
) -> dict[str, Any]:
    if attempt_id is None or fencing_token is None:
        current = ledger.running_attempt_for_worker(run_id=run_id, worker_id=worker_id)
        attempt_id = str(current["attempt_id"])
        fencing_token = int(current["fencing_token"])
    result = ledger.bound_attempt(
        attempt_id=attempt_id, owner=worker_id, fencing_token=fencing_token,
    )
    if result["run_id"] != run_id or result["worker_id"] != worker_id:
        raise ValueError("running attempt identity does not match ingest request")
    return result


def _materialize_result(
    normalized: Mapping[str, Any], *, harness_root: Path,
    out_root: str, attempt_id: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    root = PurePosixPath(out_root)
    if normalized["artifact_kind"] == "rust-candidate":
        digest = str(normalized["candidate_sha256"])
        attempt_key = content_sha256(attempt_id)[:10]
        relative = (
            root / f"candidate-{digest[:20]}-{attempt_key}.rs"
        ).as_posix()
        reference = write_bytes_artifact(
            harness_root, relative, bytes(normalized["candidate_source"])
        )
        metadata = dict(normalized["candidate_metadata"])
        boundary = metadata.pop("boundary_manifest_payload", None)
        if boundary is not None:
            boundary_ref = write_json_artifact(
                harness_root,
                (root / f"boundary-{digest[:20]}-{attempt_key}.json").as_posix(),
                boundary,
            )
            metadata["boundary_manifest"] = boundary_ref
    else:
        payload = normalized["artifact_payload"]
        identity = content_sha256(payload)
        relative = (root / f"{normalized['artifact_kind']}-{identity[:24]}.json").as_posix()
        reference = write_json_artifact(harness_root, relative, payload)
        metadata = {
            key: normalized[key]
            for key in ("planner_decision", "planner_decision_sha256")
            if key in normalized
        }
    artifact_id = "artifact-" + content_sha256({
        "attempt_id": attempt_id,
        "kind": normalized["artifact_kind"],
        "sha256": reference["sha256"],
    })[:32]
    return reference, artifact_id, metadata


__all__ = ["fail_running_worker_attempt", "ingest_worker_result"]
