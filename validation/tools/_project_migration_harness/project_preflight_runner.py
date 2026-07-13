from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any

from validation.tools._ai_candidate_harness_parts.model_identity import (
    resolve_model_identity,
)
from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    MAX_PROVIDER_STDERR_BYTES,
    MAX_PROVIDER_STDOUT_BYTES,
    ProviderExecution,
    subprocess_runner_with_environment,
)

from .artifacts import content_sha256, write_bytes_artifact, write_json_artifact
from .ledger_security import contains_secret_text
from .opencode_environment import (
    fixed_isolation_contract,
    isolated_opencode_environment,
    preflight_runtime_roots,
)
from .project_agent_contract import verify_project_agent
from .project_preflight import FIXED_AGENT, FIXED_COMMAND, FIXED_VARIANT


SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def run_project_worker_preflight(
    *, harness_root: Path, out_root_rel: str, run_id: str,
    logical_model: str, resolved_model: str, timeout_seconds: int = 60,
) -> dict[str, Any]:
    if SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ValueError("project preflight run id is invalid")
    if timeout_seconds < 5 or timeout_seconds > 300:
        raise ValueError("project preflight timeout must be between 5 and 300 seconds")
    identity = resolve_model_identity(resolved_model)
    if logical_model != identity.logical_model:
        raise ValueError("logical model does not match the resolved model identity")
    root = harness_root.resolve(strict=True)
    out_root = _out_root(root, out_root_rel)
    agent_contract = verify_project_agent(root)
    runtime_roots = preflight_runtime_roots(out_root_rel)
    probe_id = "preflight-" + content_sha256({
        "run_id": run_id,
        "logical_model": logical_model,
        "resolved_model": resolved_model,
    })[:24]
    with isolated_opencode_environment(
        harness_root=root,
        runtime_roots=runtime_roots,
        attempt_id=probe_id,
        fencing_token=1,
    ) as (environment, working_directory, environment_probe):
        execution = subprocess_runner_with_environment(
            [FIXED_COMMAND, "models"],
            timeout_seconds,
            environment=environment,
            cwd=working_directory,
        )
    stdout, stdout_redacted = _bounded_log(
        execution.stdout, MAX_PROVIDER_STDOUT_BYTES
    )
    stderr, stderr_redacted = _bounded_log(
        execution.stderr, MAX_PROVIDER_STDERR_BYTES
    )
    stdout_ref = _write_log(out_root, "stdout", stdout)
    stderr_ref = _write_log(out_root, "stderr", stderr)
    model_listed = (
        not stdout_redacted
        and execution.returncode == 0
        and _contains_exact_model_token(stdout.decode("utf-8"), resolved_model)
    )
    redaction_count = int(stdout_redacted) + int(stderr_redacted)
    status = "passed" if model_listed and redaction_count == 0 else "blocked"
    binding = {
        "run_id": run_id,
        "logical_model": logical_model,
        "resolved_model": resolved_model,
        "agent_sha256": agent_contract["sha256"],
        "isolation_contract_sha256": content_sha256(fixed_isolation_contract()),
    }
    marker_payload = {
        "schema_version": 2,
        "report_kind": "project-opencode-preflight-marker",
        "run_id": run_id,
        "status": "written",
        "binding": binding,
        "binding_sha256": content_sha256(binding),
    }
    marker_ref = _content_addressed_json(out_root, "markers", marker_payload)
    report = {
        "schema_version": 2,
        "report_kind": "project-opencode-preflight",
        "run_id": run_id,
        "status": status,
        "exit_code": 0 if status == "passed" else 2,
        "process_returncode": execution.returncode,
        "redaction_count": redaction_count,
        "opencode_run_launched": False,
        "provider_invocations": 0,
        "launch_policy": {
            "opencode_command": FIXED_COMMAND,
            "opencode_model": logical_model,
            "resolved_model_id": resolved_model,
            "opencode_agent": FIXED_AGENT,
            "opencode_variant": FIXED_VARIANT,
        },
        "model_probe": {
            "status": "available" if model_listed else "unavailable",
            "model_listed": model_listed,
            "process_returncode": execution.returncode,
            "argv": [FIXED_COMMAND, "models"],
            "stdout": _prefix(stdout_ref, out_root_rel),
            "stderr": _prefix(stderr_ref, out_root_rel),
        },
        "agent_contract": agent_contract,
        "isolation_contract": fixed_isolation_contract(),
        "environment_probe": environment_probe,
        "marker": _prefix(marker_ref, out_root_rel),
    }
    report_ref = _content_addressed_json(out_root, "reports", report)
    return {
        "schema_version": 1,
        "status": status,
        "run_id": run_id,
        "report": _prefix(report_ref, out_root_rel),
        "marker": _prefix(marker_ref, out_root_rel),
        "model_launched": False,
        "provider_invocations": 0,
        "semantic_gate": False,
    }


def _out_root(harness_root: Path, value: str) -> Path:
    runtime_roots = preflight_runtime_roots(value)
    first = runtime_roots["config"].split("/preflight/runtime/", 1)[0]
    target = (harness_root / Path(*first.split("/"))).resolve()
    try:
        target.relative_to(harness_root)
    except ValueError as error:
        raise ValueError("project preflight out root escapes the harness") from error
    target.mkdir(parents=True, exist_ok=True)
    return target


def _bounded_log(value: str, limit: int) -> tuple[bytes, bool]:
    data = value.encode("utf-8")
    if len(data) > limit:
        return b"provider_error=output_too_large\n", True
    if contains_secret_text(value):
        return b"provider_error=redacted_sensitive_output\n", True
    return data, False


def _write_log(out_root: Path, stream: str, data: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    return write_bytes_artifact(
        out_root, f"preflight/logs/models-{stream}-{digest}.log", data
    )


def _content_addressed_json(
    out_root: Path, family: str, payload: dict[str, Any],
) -> dict[str, Any]:
    digest = content_sha256(payload)
    return write_json_artifact(
        out_root, f"preflight/{family}/{digest}.json", payload
    )


def _prefix(reference: dict[str, Any], root: str) -> dict[str, Any]:
    return {**reference, "path": f"{root}/{reference['path']}"}


def _contains_exact_model_token(stdout: str, resolved_model: str) -> bool:
    return any(
        token.strip("`'\"*,").casefold() == resolved_model.casefold()
        for line in stdout.splitlines()
        for token in re.split(r"\s+", line.strip())
    )


__all__ = ["run_project_worker_preflight"]
