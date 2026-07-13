from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger import LedgerError, ProjectLedger
from .orchestration_facts import read_artifact_reference
from .project_repair_prompt import render_project_repair_prompt


def read_project_repair_request(
    reference: Mapping[str, Any], *, root: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(read_artifact_reference(root, reference).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("project repair request is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("project repair request must be an object")
    render_project_repair_prompt(value, harness_root=root)
    return value


def reopen_active_project_repair_request(
    reference: Mapping[str, Any], preflight_reference: Mapping[str, Any], *,
    ledger: ProjectLedger, root: Path, logical_model: str,
    resolved_model: str,
) -> dict[str, Any]:
    value = read_project_repair_request(reference, root=root)
    binding = value.get("execution_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("project repair execution binding is missing")
    _assert_preflight(value, preflight_reference, logical_model, resolved_model)
    projection = ledger.project_repair_projection(
        run_id=str(value["run_id"]),
        queue_sha256=str(value["project_repair_queue_sha256"]),
        repair_id=str(value["repair_id"]),
    )
    with ledger.connect() as connection:
        attempt = connection.execute(
            "select * from project_repair_attempts where attempt_id=?",
            (binding.get("attempt_id"),),
        ).fetchone()
    if (
        attempt is None or attempt["status"] != "running"
        or attempt["worker_id"] != value.get("worker_id")
        or attempt["input_sha256"] != value.get("effective_input_sha256")
        or projection.status != "running"
        or projection.active_attempt_id != binding.get("attempt_id")
        or projection.version != binding.get("fencing_token")
        or projection.version != binding.get("started_state_version")
    ):
        raise LedgerError("project repair request is not bound to the active attempt")
    latest = ledger.load_latest_project_interface_receipt(
        run_id=str(value["run_id"]),
    )
    coordinator = value.get("coordinator_binding")
    if (
        latest is None or not isinstance(coordinator, Mapping)
        or int(coordinator.get("receipt_epoch", 0)) != int(latest[0])
        or coordinator.get("coordinator_receipt_sha256")
        != latest[1]["coordinator_receipt_sha256"]
        or value["project_repair_queue_sha256"]
        != latest[1]["project_repair_queue"]["project_repair_queue_sha256"]
    ):
        raise LedgerError("project repair request coordinator epoch is stale")
    return value


def terminal_project_repair_runtime_replay(
    reference: Mapping[str, Any], preflight_reference: Mapping[str, Any], *,
    ledger: ProjectLedger, root: Path, logical_model: str,
    resolved_model: str,
) -> dict[str, Any] | None:
    value = read_project_repair_request(reference, root=root)
    _assert_preflight(value, preflight_reference, logical_model, resolved_model)
    binding = value.get("execution_binding")
    if not isinstance(binding, Mapping):
        return None
    attempt_id = binding.get("attempt_id")
    with ledger.connect() as connection:
        attempt = connection.execute(
            "select * from project_repair_attempts where attempt_id=?", (attempt_id,),
        ).fetchone()
        artifact = connection.execute(
            """select repo_rel_path,content_sha256 from project_repair_artifacts
               where attempt_id=? and kind='project-repair-request'""",
            (attempt_id,),
        ).fetchone()
    if attempt is None or attempt["status"] == "running":
        return None
    if (
        artifact is None or artifact["repo_rel_path"] != reference.get("path")
        or artifact["content_sha256"] != reference.get("sha256")
        or attempt["worker_id"] != value.get("worker_id")
        or attempt["input_sha256"] != value.get("effective_input_sha256")
    ):
        raise LedgerError("terminal project repair replay changed its binding")
    projection = ledger.project_repair_projection(
        run_id=str(value["run_id"]),
        queue_sha256=str(value["project_repair_queue_sha256"]),
        repair_id=str(value["repair_id"]),
    )
    return {
        "schema_version": 1, "status": "terminal-replay",
        "run_id": value["run_id"], "repair_id": value["repair_id"],
        "attempt_id": attempt_id, "attempt_status": attempt["status"],
        "item_status": projection.status,
        "attempt_consumed": bool(attempt["command_started"]),
        "provider_invocations": 0, "model_launched": False,
        "semantic_gate": False,
    }


def _assert_preflight(
    request: Mapping[str, Any], reference: Mapping[str, Any],
    logical_model: str, resolved_model: str,
) -> None:
    preflight = request.get("preflight_binding")
    if (
        not isinstance(preflight, Mapping)
        or preflight.get("preflight") != dict(reference)
        or preflight.get("logical_model") != logical_model
        or preflight.get("resolved_model") != resolved_model
    ):
        raise LedgerError("project repair request changed its preflight binding")


__all__ = [
    "read_project_repair_request", "reopen_active_project_repair_request",
    "terminal_project_repair_runtime_replay",
]
