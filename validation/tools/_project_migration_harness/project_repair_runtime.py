from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    subprocess_runner_with_environment,
)

from .artifacts import content_sha256, write_json_artifact
from .ledger import ProjectLedger
from .ledger_security import LedgerError
from .opencode_environment import isolated_opencode_environment
from .opencode_project_repair_worker import execute_opencode_project_repair_worker
from .orchestration_facts import read_artifact_reference
from .project_repair_ingest import ingest_project_repair_response
from .project_repair_prompt import render_project_repair_prompt
from .project_repair_paths import require_bound_project_repair_out_root


class _ProjectRepairLaunchAlreadyClaimed(Exception):
    pass


def run_and_ingest_opencode_project_repair(
    request_reference: Mapping[str, Any], preflight_reference: Mapping[str, Any], *,
    ledger: ProjectLedger, harness_root: Path, out_root: Path,
    out_root_rel: str, logical_model: str = "GLM-5.1",
    resolved_model: str = "zai/glm-5.1", opencode_command: str = "opencode",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    require_bound_project_repair_out_root(harness_root, out_root, out_root_rel)
    request = _bound_request(request_reference, ledger, harness_root)
    binding = request["execution_binding"]
    attempt_id = str(binding["attempt_id"])
    fencing_token = int(binding["fencing_token"])
    worker_id = str(request["worker_id"])
    try:
        with isolated_opencode_environment(
            harness_root=harness_root, runtime_roots=request["runtime_roots"],
            attempt_id=attempt_id, fencing_token=fencing_token,
        ) as (environment, working_directory, attestation):
            def runner(argv: list[str], seconds: int):
                claimed = ledger.mark_project_repair_command_started(
                    attempt_id=attempt_id, worker_id=worker_id,
                    expected_version=fencing_token,
                )
                if not claimed:
                    raise _ProjectRepairLaunchAlreadyClaimed
                return subprocess_runner_with_environment(
                    argv, seconds, environment=environment,
                    cwd=working_directory,
                )
            generated = execute_opencode_project_repair_worker(
                request_reference, preflight_reference,
                harness_root=harness_root, attempt_id=attempt_id,
                fencing_token=fencing_token, logical_model=logical_model,
                resolved_model=resolved_model, opencode_command=opencode_command,
                timeout_seconds=timeout_seconds, runner=runner,
                runtime_environment=attestation,
            )
        _record_provider_artifacts(
            ledger, attempt_id=attempt_id, artifacts=generated["artifacts"],
            proof_scope=str(generated["preflight"]["proof_scope"]),
        )
        if generated["status"] != "generated":
            recovered = ledger.recover_project_repair_attempt(
                attempt_id=attempt_id,
                command_id=f"project-repair-provider-recover-{content_sha256(generated)[:24]}",
                expected_version=fencing_token,
                worker_id=worker_id,
                result_known=True,
                evidence_sha256=str(generated["artifacts"]["raw_response"]["sha256"]),
            )
            return {
                **generated, "status": recovered.current.status,
                "attempt_consumed": True,
            }
        ingested = ingest_project_repair_response(
            request, generated["worker_response"], ledger=ledger,
            harness_root=harness_root, out_root=out_root,
            out_root_rel=out_root_rel,
        )
    except _ProjectRepairLaunchAlreadyClaimed:
        return {
            "schema_version": 1, "status": "waiting",
            "stage": "project-repair-launch-already-claimed",
            "run_id": request["run_id"], "repair_id": request["repair_id"],
            "attempt_id": attempt_id, "attempt_consumed": False,
            "model_launched": False, "semantic_gate": False,
        }
    except Exception:
        return _recover_unknown(
            request, ledger=ledger, out_root=out_root,
            out_root_rel=out_root_rel,
        )
    return {
        "schema_version": 1, "status": ingested["status"],
        "run_id": request["run_id"], "repair_id": request["repair_id"],
        "attempt_id": attempt_id,
        "generation": {
            key: value for key, value in generated.items()
            if key != "worker_response"
        },
        "ledger": ingested,
        "semantic_gate": False,
    }


def _bound_request(
    reference: Mapping[str, Any], ledger: ProjectLedger, root: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(read_artifact_reference(root, reference).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("project repair request is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("project repair request must be an object")
    render_project_repair_prompt(value, harness_root=root)
    binding = value.get("execution_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("project repair execution binding is missing")
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


def _record_provider_artifacts(
    ledger: ProjectLedger, *, attempt_id: str,
    artifacts: Mapping[str, Any], proof_scope: str,
) -> None:
    statuses = {
        "prompt": "written", "raw_response": "written",
        "invocation_receipt": "diagnostic", "parsed_response": "written",
        "session_identity": "diagnostic", "execution_report": "diagnostic",
    }
    for kind, reference in artifacts.items():
        if kind not in statuses or not isinstance(reference, Mapping):
            raise ValueError("project repair provider artifact is invalid")
        ledger.record_project_repair_artifact(
            attempt_id=attempt_id,
            artifact_id=f"project-repair-provider-{kind}-{reference['sha256'][:24]}",
            kind=f"provider-{kind}", repo_rel_path=str(reference["path"]),
            content_sha256=str(reference["sha256"]), status=statuses[kind],
            metadata={"proof_scope": proof_scope},
        )


def _recover_unknown(
    request: Mapping[str, Any], *, ledger: ProjectLedger,
    out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    attempt_id = str(request["execution_binding"]["attempt_id"])
    projection = ledger.project_repair_projection(
        run_id=str(request["run_id"]),
        queue_sha256=str(request["project_repair_queue_sha256"]),
        repair_id=str(request["repair_id"]),
    )
    if projection.status != "running" or projection.active_attempt_id != attempt_id:
        return {
            "schema_version": 1, "status": "manual-reconcile",
            "run_id": request["run_id"], "repair_id": request["repair_id"],
            "attempt_id": attempt_id, "current_state": projection.status,
            "semantic_gate": False,
        }
    with ledger.connect() as connection:
        attempt = connection.execute(
            """select worker_id,command_started from project_repair_attempts
               where attempt_id=?""", (attempt_id,),
        ).fetchone()
    if attempt is None or attempt["worker_id"] != request["worker_id"]:
        return {
            "schema_version": 1, "status": "manual-reconcile",
            "run_id": request["run_id"], "repair_id": request["repair_id"],
            "attempt_id": attempt_id, "current_state": projection.status,
            "semantic_gate": False,
        }
    payload = {
        "schema_version": 1, "run_id": request["run_id"],
        "repair_id": request["repair_id"], "attempt_id": attempt_id,
        "error_code": "project_repair_provider_result_unknown",
        "semantic_gate": False,
    }
    reference = write_json_artifact(
        out_root,
        f"project-repair/runtime-failures/{attempt_id}-{content_sha256(payload)}.json",
        payload,
    )
    ledger.record_project_repair_artifact(
        attempt_id=attempt_id,
        artifact_id=f"project-repair-runtime-failure-{reference['sha256'][:24]}",
        kind="provider-runtime-failure",
        repo_rel_path=f"{out_root_rel}/{reference['path']}",
        content_sha256=str(reference["sha256"]), status="failed",
        metadata={"error_code": payload["error_code"]},
    )
    command_started = bool(attempt["command_started"])
    if command_started:
        terminal = ledger.finish_project_repair_attempt(
            attempt_id=attempt_id,
            command_id=f"project-repair-runtime-unknown-{reference['sha256'][:24]}",
            expected_version=projection.version,
            worker_id=str(request["worker_id"]), outcome="unknown",
            evidence_sha256=str(reference["sha256"]),
            error_key=payload["error_code"],
        )
        return {
            **payload, "status": "manual-reconcile",
            "current_state": terminal.current.status,
            "attempt_consumed": True,
            "failure": {**reference, "path": f"{out_root_rel}/{reference['path']}"},
        }
    recovered = ledger.recover_project_repair_attempt(
        attempt_id=attempt_id,
        command_id=f"project-repair-runtime-recover-{reference['sha256'][:24]}",
        expected_version=projection.version,
        worker_id=str(request["worker_id"]),
        evidence_sha256=str(reference["sha256"]),
    )
    return {
        **payload, "status": recovered.current.status,
        "failure": {**reference, "path": f"{out_root_rel}/{reference['path']}"},
    }


__all__ = ["run_and_ingest_opencode_project_repair"]
