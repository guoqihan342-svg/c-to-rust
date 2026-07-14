from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    subprocess_runner_with_environment,
)

from .artifacts import content_sha256
from .controller_ingest import fail_running_worker_attempt, ingest_worker_result
from .ledger import ProjectLedger
from .opencode_project_worker import execute_opencode_project_worker
from .opencode_environment import isolated_opencode_environment
from .runtime_request_validation import (
    bound_worker_request, cancel_invalid_bound_worker_request,
)
from .runtime_security import heartbeat_runner


def run_and_ingest_opencode_worker(
    request_reference: Mapping[str, Any], preflight_reference: Mapping[str, Any], *,
    ledger: ProjectLedger, harness_root: Path,
    logical_model: str = "GLM-5.1", resolved_model: str = "zai/glm-5.1",
    opencode_command: str = "opencode", timeout_seconds: int = 300,
) -> dict[str, Any]:
    try:
        request, attempt = bound_worker_request(
            request_reference, ledger=ledger, harness_root=harness_root,
        )
    except Exception:
        cancelled = cancel_invalid_bound_worker_request(
            request_reference, ledger=ledger, harness_root=harness_root,
        )
        if cancelled is None:
            raise
        return {
            "schema_version": 1,
            "status": "prelaunch-blocked",
            "run_id": str(cancelled["run_id"]),
            "worker_id": str(cancelled["worker_id"]),
            "attempt_consumed": False,
            "semantic_gate": False,
        }
    run_id = str(attempt["run_id"])
    worker_id = str(attempt["worker_id"])
    attempt_id = str(attempt["attempt_id"])
    token = int(attempt["fencing_token"])
    unit_id = str(attempt["unit_id"])
    ttl = int(attempt["metadata"].get("lease_ttl_seconds", 0))

    def heartbeat() -> None:
        ledger.heartbeat_lease(
            run_id=run_id,
            unit_id=unit_id,
            owner=worker_id,
            fencing_token=token,
            ttl_seconds=ttl,
        )

    try:
        if ttl <= timeout_seconds + 30:
            raise ValueError("lease TTL must exceed worker timeout by at least 30 seconds")
        preflight_path = preflight_reference.get("path")
        preflight_sha256 = preflight_reference.get("sha256")
        if not isinstance(preflight_path, str) or not isinstance(preflight_sha256, str):
            raise ValueError("worker preflight reference is incomplete")
        ledger.bind_attempt_preflight(
            attempt_id=attempt_id,
            owner=worker_id,
            fencing_token=token,
            preflight_path=preflight_path,
            preflight_sha256=preflight_sha256,
        )
        roots = request.get("runtime_roots")
        if not isinstance(roots, Mapping):
            raise ValueError("worker request runtime roots are missing")
        with isolated_opencode_environment(
            harness_root=harness_root,
            runtime_roots=roots,
            attempt_id=attempt_id,
            fencing_token=token,
        ) as (environment, working_directory, environment_attestation):
            def command_runner(argv: list[str], seconds: int) -> Any:
                ledger.authorize_command_launch(
                    attempt_id=attempt_id,
                    owner=worker_id,
                    fencing_token=token,
                )
                return subprocess_runner_with_environment(
                    argv,
                    seconds,
                    environment=environment,
                    cwd=working_directory,
                    on_started=lambda: ledger.mark_command_started(
                        attempt_id=attempt_id,
                        owner=worker_id,
                        fencing_token=token,
                    ),
                )
            wrapped_runner = heartbeat_runner(
                command_runner,
                heartbeat,
                interval_seconds=min(30.0, max(1.0, ttl / 3)),
            )
            generated = execute_opencode_project_worker(
                request_reference,
                preflight_reference,
                harness_root=harness_root,
                attempt_id=attempt_id,
                fencing_token=token,
                logical_model=logical_model,
                resolved_model=resolved_model,
                opencode_command=opencode_command,
                timeout_seconds=timeout_seconds,
                runner=wrapped_runner,
                runtime_environment=environment_attestation,
            )
    except Exception:  # the ledger state, not exception text, decides retry safety.
        current = ledger.bound_attempt(
            attempt_id=attempt_id, owner=worker_id, fencing_token=token
        )
        if current["metadata"].get("command_started") is not True:
            ledger.cancel_prelaunch_attempt(
                attempt_id=attempt_id, owner=worker_id, fencing_token=token
            )
            return {
                "schema_version": 1,
                "status": "prelaunch-blocked",
                "run_id": run_id,
                "worker_id": worker_id,
                "attempt_consumed": False,
                "semantic_gate": False,
            }
        failed = fail_running_worker_attempt(
            ledger=ledger,
            run_id=run_id,
            worker_id=worker_id,
            attempt_id=attempt_id,
            fencing_token=token,
            error_key="worker_command_result_unknown",
            retryable=False,
        )
        return {
            "schema_version": 1,
            "status": "manual-reconcile",
            "run_id": run_id,
            "worker_id": worker_id,
            "ledger": failed,
            "semantic_gate": False,
        }
    if generated["status"] != "generated":
        current = ledger.bound_attempt(
            attempt_id=attempt_id, owner=worker_id, fencing_token=token
        )
        if current["metadata"].get("command_started") is not True:
            ledger.cancel_prelaunch_attempt(
                attempt_id=attempt_id, owner=worker_id, fencing_token=token
            )
            return {
                **generated,
                "status": "prelaunch-blocked",
                "attempt_consumed": False,
            }
        failed = fail_running_worker_attempt(
            ledger=ledger,
            run_id=run_id,
            worker_id=worker_id,
            attempt_id=attempt_id,
            fencing_token=token,
            error_key=str(generated.get("root_cause_key", "provider_failed")),
            retryable=False,
        )
        return {**generated, "status": "manual-reconcile", "ledger": failed}
    current = ledger.bound_attempt(
        attempt_id=attempt_id, owner=worker_id, fencing_token=token,
    )
    if current["metadata"].get("command_started") is not True:
        ledger.cancel_prelaunch_attempt(
            attempt_id=attempt_id, owner=worker_id, fencing_token=token,
        )
        return {
            **generated,
            "status": "prelaunch-blocked",
            "attempt_consumed": False,
        }
    try:
        execution_ref = generated["artifacts"]["execution_report"]
        execution_id = "execution-" + content_sha256({
            "attempt_id": attempt_id,
            "sha256": execution_ref["sha256"],
        })[:32]
        ledger.record_artifact(
            run_id=run_id,
            unit_id=unit_id,
            owner=worker_id,
            fencing_token=token,
            artifact_id=execution_id,
            attempt_id=attempt_id,
            kind="provider-execution",
            repo_rel_path=str(execution_ref["path"]),
            content_sha256=str(execution_ref["sha256"]),
            status="written",
            metadata={
                "execution_report_sha256": execution_ref["sha256"],
                "proof_scope": generated["preflight"]["proof_scope"],
            },
        )
        recorded = ingest_worker_result(
            generated["worker_response"],
            ledger=ledger,
            harness_root=harness_root,
            run_id=run_id,
            worker_id=worker_id,
            attempt_id=attempt_id,
            fencing_token=token,
        )
    except Exception:
        failed = fail_running_worker_attempt(
            ledger=ledger,
            run_id=run_id,
            worker_id=worker_id,
            attempt_id=attempt_id,
            fencing_token=token,
            error_key="provider_evidence_persistence_failed",
            retryable=False,
        )
        return {
            "schema_version": 1,
            "status": "manual-reconcile",
            "run_id": run_id,
            "worker_id": worker_id,
            "ledger": failed,
            "semantic_gate": False,
        }
    return {
        "schema_version": 1,
        "status": recorded["status"],
        "run_id": run_id,
        "worker_id": worker_id,
        "generation": {
            key: value for key, value in generated.items() if key != "worker_response"
        },
        "ledger": recorded,
        "semantic_gate": False,
    }


__all__ = ["run_and_ingest_opencode_worker"]
