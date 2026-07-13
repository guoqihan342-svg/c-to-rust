from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from validation.tools._ai_candidate_harness_parts.prompt_transport import (
    prompt_file_arguments,
)
from validation.tools._ai_candidate_harness_parts.provider_receipt import (
    write_invocation_receipt,
)
from validation.tools._ai_candidate_harness_parts.provider_response import (
    assistant_text_from_jsonl, extract_single_json_text,
)
from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    MAX_PROVIDER_STDOUT_BYTES, ProviderExecution, classify_provider_failure,
)

from .artifacts import content_sha256, write_bytes_artifact, write_json_artifact
from .gate_evidence import write_content_addressed_json
from .opencode_project_repair_output import provider_response_for_persistence
from .orchestration_facts import read_artifact_reference
from .project_preflight import validate_project_worker_preflight
from .project_receipt_validation import validate_project_invocation_receipt
from .project_repair_patch import normalize_project_repair_response
from .project_repair_prompt import render_project_repair_prompt
from .project_repair_dispatch_permit import (
    assert_project_repair_request_preflight_binding,
)


Runner = Callable[[list[str], int], ProviderExecution]
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
FIXED_COMMAND = "opencode"
FIXED_AGENT = "c2rust-candidate"
FIXED_VARIANT = "max"


def execute_opencode_project_repair_worker(
    request_reference: Mapping[str, Any], preflight_reference: Mapping[str, Any], *,
    harness_root: Path, attempt_id: str, fencing_token: int,
    logical_model: str = "GLM-5.1", resolved_model: str = "zai/glm-5.1",
    opencode_command: str = FIXED_COMMAND, agent: str = FIXED_AGENT,
    variant: str = FIXED_VARIANT, timeout_seconds: int = 300,
    runner: Runner | None = None,
    runtime_environment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_launch_policy(
        logical_model, resolved_model, opencode_command, agent, variant,
        timeout_seconds, runtime_environment,
    )
    request = _request(harness_root, request_reference)
    _validate_execution_identity(request, attempt_id, fencing_token)
    assert_project_repair_request_preflight_binding(
        request, preflight_reference, logical_model, resolved_model,
    )
    preflight = validate_project_worker_preflight(
        preflight_reference, harness_root=harness_root,
        run_id=str(request["run_id"]), logical_model=logical_model,
        resolved_model=resolved_model, opencode_command=opencode_command,
        agent=agent, variant=variant,
    )
    if (
        runtime_environment.get("agent_sha256") != preflight["agent_sha256"]
        or runtime_environment.get("runtime_input_sha256")
        != preflight["runtime_input_sha256"]
    ):
        raise ValueError("project repair runtime inputs drifted after preflight")
    prompt = render_project_repair_prompt(request, harness_root=harness_root)
    worker_root = _worker_root(request)
    stem = "attempt-" + content_sha256({
        "attempt_id": attempt_id, "fencing_token": fencing_token,
        "request_sha256": request_reference.get("sha256"),
    })[:24]
    prompt_bytes = prompt.encode("utf-8")
    prompt_digest = hashlib.sha256(prompt_bytes).hexdigest()
    prompt_ref = write_bytes_artifact(
        harness_root, f"{worker_root}/prompts/{prompt_digest}.json", prompt_bytes,
    )
    prompt_path = _absolute(harness_root, prompt_ref["path"])
    argv = [
        FIXED_COMMAND, "run", "--pure", "--format", "json", "--print-logs",
        "--log-level", "ERROR", "--model", resolved_model,
        "--agent", FIXED_AGENT, "--variant", FIXED_VARIANT,
        *prompt_file_arguments(prompt_path),
    ]
    if runner is None:
        raise ValueError("project repair worker requires a bound process runner")
    execution = runner(argv, timeout_seconds)
    stdout_bytes = execution.stdout.encode("utf-8")
    response_digest = hashlib.sha256(stdout_bytes).hexdigest()
    persisted_response, unsafe_output = provider_response_for_persistence(
        execution.stdout, max_bytes=MAX_PROVIDER_STDOUT_BYTES,
    )
    persisted_bytes = persisted_response.encode("utf-8")
    response_rel = f"{worker_root}/responses/{stem}-{response_digest}.jsonl"
    response_path = _absolute(harness_root, response_rel)
    receipt_path = _absolute(
        harness_root, f"{worker_root}/receipts/{stem}-{response_digest}.json",
    )
    session_path = _absolute(
        harness_root,
        f"{worker_root}/receipts/{stem}-{response_digest}-session.json",
    )
    response_ref = write_bytes_artifact(harness_root, response_rel, persisted_bytes)
    artifacts = {"prompt": prompt_ref, "raw_response": response_ref}
    try:
        write_invocation_receipt(
            execution, resolved_model=resolved_model, agent=FIXED_AGENT,
            variant=FIXED_VARIANT, persisted_response=persisted_response,
            prompt_path=prompt_path, response_path=response_path,
            receipt_path=receipt_path, session_identity_path=session_path,
        )
    except (OSError, TypeError, ValueError):
        return _blocked(
            request, attempt_id, fencing_token,
            "provider_receipt_persistence_failed", execution, artifacts,
            preflight, runtime_environment,
        )
    artifacts["invocation_receipt"] = _ref(harness_root, receipt_path)
    if unsafe_output is not None:
        return _blocked(
            request, attempt_id, fencing_token, unsafe_output, execution,
            artifacts, preflight, runtime_environment,
        )
    failure = classify_provider_failure(execution)
    if failure is not None:
        return _blocked(
            request, attempt_id, fencing_token,
            str(failure.get("kind", "provider_failed")), execution,
            artifacts, preflight, runtime_environment,
        )
    try:
        identity = validate_project_invocation_receipt(
            receipt_path, prompt_path=prompt_path, response_path=response_path,
            resolved_model=resolved_model, agent=FIXED_AGENT, variant=FIXED_VARIANT,
            require_export=preflight["proof_scope"] == "competition-model-preflight",
        )
        response = _response(execution.stdout)
        normalize_project_repair_response(request, response)
    except (OSError, TypeError, ValueError):
        return _blocked(
            request, attempt_id, fencing_token,
            "provider_response_contract_failed", execution, artifacts,
            preflight, runtime_environment,
        )
    parsed_ref = write_json_artifact(
        harness_root, f"{worker_root}/parsed/{stem}-{response_digest}.json", response,
    )
    final_artifacts = {
        **artifacts, "parsed_response": parsed_ref,
        **(
            {"session_identity": _ref(harness_root, session_path)}
            if identity.get("session_identity") is not None else {}
        ),
    }
    report = {
        "schema_version": 1,
        "artifact_kind": "project-repair-opencode-execution",
        "status": "generated", "run_id": request["run_id"],
        "worker_id": request["worker_id"], "role": request["role"],
        "attempt_id": attempt_id, "fencing_epoch": fencing_token,
        "request": dict(request_reference), "preflight": dict(preflight_reference),
        "model": {
            "logical": logical_model, "resolved": resolved_model,
            "agent": FIXED_AGENT, "variant": FIXED_VARIANT,
        },
        "runtime_input_sha256": runtime_environment["runtime_input_sha256"],
        "identity": identity, "artifacts": final_artifacts,
        "semantic_gate": False,
    }
    local = write_content_addressed_json(
        _absolute(harness_root, worker_root), "provider-execution", report,
    )
    final_artifacts["execution_report"] = {
        **local, "path": f"{worker_root}/{local['path']}",
    }
    return {
        "schema_version": 1, "status": "generated",
        "run_id": request["run_id"], "worker_id": request["worker_id"],
        "role": request["role"], "attempt_id": attempt_id,
        "fencing_token": fencing_token, "worker_response": response,
        "artifacts": final_artifacts, "provider_invocations": 1,
        "model_launched": True, "preflight": preflight,
        "runtime_environment": dict(runtime_environment),
        "identity": identity, "semantic_gate": False,
    }


def _blocked(
    request: Mapping[str, Any], attempt_id: str, fencing_token: int,
    root_cause: str, execution: ProviderExecution,
    artifacts: Mapping[str, Any], preflight: Mapping[str, Any],
    runtime_environment: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": "blocked",
        "run_id": request["run_id"], "worker_id": request["worker_id"],
        "role": request["role"], "attempt_id": attempt_id,
        "fencing_token": fencing_token, "root_cause_key": root_cause,
        "provider_invocations": int(execution.process_started),
        "model_launched": execution.process_started,
        "artifacts": dict(artifacts), "preflight": dict(preflight),
        "runtime_environment": dict(runtime_environment),
        "semantic_gate": False,
    }


def _validate_launch_policy(
    logical: str, resolved: str, command: str, agent: str, variant: str,
    timeout: int, environment: Mapping[str, Any] | None,
) -> None:
    if command != FIXED_COMMAND or agent != FIXED_AGENT or variant != FIXED_VARIANT:
        raise ValueError("project repair workers require fixed OpenCode policy")
    if MODEL_ID.fullmatch(logical) is None or MODEL_ID.fullmatch(resolved) is None or "/" not in resolved:
        raise ValueError("OpenCode model identity is invalid")
    if not 30 <= timeout <= 3_600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    if (
        not isinstance(environment, Mapping)
        or environment.get("status") != "isolated"
        or environment.get("scope") != "attempt"
        or environment.get("explicit_environment") is not True
        or environment.get("global_environment_mutated") is not False
    ):
        raise ValueError("project repair worker requires an isolated environment")


def _request(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(read_artifact_reference(root, reference).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("project repair request is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("project repair request must be a JSON object")
    return value


def _response(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(extract_single_json_text(assistant_text_from_jsonl(stdout)))
    except json.JSONDecodeError as error:
        raise ValueError("OpenCode project repair worker returned invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("OpenCode project repair response must be a JSON object")
    return value


def _validate_execution_identity(
    request: Mapping[str, Any], attempt_id: str, fencing_token: int,
) -> None:
    binding = request.get("execution_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("project repair execution binding is absent")
    payload = {key: value for key, value in binding.items() if key != "binding_sha256"}
    if (
        binding.get("attempt_id") != attempt_id
        or binding.get("fencing_token") != fencing_token
        or content_sha256(payload) != binding.get("binding_sha256")
    ):
        raise ValueError("project repair attempt/fence binding drifted")


def _worker_root(request: Mapping[str, Any]) -> str:
    roots = request.get("runtime_roots")
    value = roots.get("out") if isinstance(roots, Mapping) else None
    if not isinstance(value, str):
        raise ValueError("project repair worker out root is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("project repair worker out root is unsafe")
    return path.as_posix()


def _absolute(root: Path, relative: str) -> Path:
    base = root.resolve(strict=True)
    target = (base / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise ValueError("project repair runtime path escapes harness root") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _ref(root: Path, path: Path) -> dict[str, Any]:
    relative = path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
    data = path.read_bytes()
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


__all__ = ["execute_opencode_project_repair_worker"]
