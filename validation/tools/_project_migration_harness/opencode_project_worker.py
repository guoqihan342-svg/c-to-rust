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
    assistant_text_from_jsonl,
    extract_single_json_text,
)
from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    MAX_PROVIDER_STDOUT_BYTES,
    ProviderExecution,
    classify_provider_failure,
)

from .artifacts import content_sha256, write_bytes_artifact, write_json_artifact
from .gate_evidence import write_content_addressed_json
from .orchestration_facts import read_artifact_reference
from .project_preflight import validate_project_worker_preflight
from .project_prompt import render_project_worker_prompt
from .project_receipt_validation import validate_project_invocation_receipt
from .runtime_security import reject_forbidden_tool_events
from .worker_result_contracts import normalize_worker_result


Runner = Callable[[list[str], int], ProviderExecution]
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
FIXED_COMMAND = "opencode"
FIXED_AGENT = "c2rust-candidate"
FIXED_VARIANT = "max"


def execute_opencode_project_worker(
    request_reference: Mapping[str, Any], preflight_reference: Mapping[str, Any], *,
    harness_root: Path, attempt_id: str, fencing_token: int,
    logical_model: str = "GLM-5.1", resolved_model: str = "zai/glm-5.1",
    opencode_command: str = FIXED_COMMAND, agent: str = FIXED_AGENT,
    variant: str = FIXED_VARIANT, timeout_seconds: int = 300,
    runner: Runner | None = None,
    runtime_environment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if opencode_command != FIXED_COMMAND or agent != FIXED_AGENT or variant != FIXED_VARIANT:
        raise ValueError("project workers require fixed opencode/c2rust-candidate/max")
    if (
        MODEL_ID.fullmatch(logical_model) is None
        or MODEL_ID.fullmatch(resolved_model) is None
        or "/" not in resolved_model
    ):
        raise ValueError("OpenCode model identity is invalid")
    if timeout_seconds < 30 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    if (
        not isinstance(runtime_environment, Mapping)
        or runtime_environment.get("status") != "isolated"
        or runtime_environment.get("scope") != "attempt"
        or runtime_environment.get("explicit_environment") is not True
        or runtime_environment.get("global_environment_mutated") is not False
    ):
        raise ValueError("project worker requires an attempt-isolated OpenCode environment")
    request = _request(harness_root, request_reference)
    _validate_execution_identity(request, attempt_id, fencing_token)
    preflight = validate_project_worker_preflight(
        preflight_reference,
        harness_root=harness_root,
        run_id=str(request["run_id"]),
        logical_model=logical_model,
        resolved_model=resolved_model,
        opencode_command=opencode_command,
        agent=agent,
        variant=variant,
    )
    if (
        runtime_environment.get("agent_sha256") != preflight["agent_sha256"]
        or runtime_environment.get("runtime_input_sha256")
        != preflight["runtime_input_sha256"]
    ):
        raise ValueError("OpenCode runtime inputs drifted after preflight")
    prompt = render_project_worker_prompt(request, harness_root=harness_root)
    worker_root = _worker_root(request)
    stem = "attempt-" + content_sha256({
        "attempt_id": attempt_id, "fencing_token": fencing_token,
        "request_sha256": request_reference.get("sha256"),
    })[:24]
    prompt_bytes = prompt.encode("utf-8")
    prompt_digest = hashlib.sha256(prompt_bytes).hexdigest()
    prompt_ref = write_bytes_artifact(
        harness_root,
        f"{worker_root}/prompts/{prompt_digest}.json",
        prompt_bytes,
    )
    prompt_path = _absolute(harness_root, prompt_ref["path"])
    argv = [
        FIXED_COMMAND, "run", "--pure", "--format", "json", "--print-logs",
        "--log-level", "ERROR", "--model", resolved_model,
        "--agent", FIXED_AGENT, "--variant", FIXED_VARIANT,
        *prompt_file_arguments(prompt_path),
    ]
    if runner is None:
        raise ValueError("project worker requires a bound process runner")
    execution = runner(argv, timeout_seconds)
    stdout_bytes = execution.stdout.encode("utf-8")
    if len(stdout_bytes) > MAX_PROVIDER_STDOUT_BYTES:
        raise ValueError("OpenCode project worker response exceeds the bounded size")
    response_digest = hashlib.sha256(stdout_bytes).hexdigest()
    response_rel = f"{worker_root}/responses/{stem}-{response_digest}.jsonl"
    response_path = _absolute(harness_root, response_rel)
    receipt_path = _absolute(
        harness_root,
        f"{worker_root}/receipts/{stem}-{response_digest}.json",
    )
    session_path = _absolute(
        harness_root,
        f"{worker_root}/receipts/{stem}-{response_digest}-session.json",
    )
    response_ref = write_bytes_artifact(harness_root, response_rel, stdout_bytes)
    write_invocation_receipt(
        execution,
        resolved_model=resolved_model,
        agent=FIXED_AGENT,
        variant=FIXED_VARIANT,
        persisted_response=execution.stdout,
        prompt_path=prompt_path,
        response_path=response_path,
        receipt_path=receipt_path,
        session_identity_path=session_path,
    )
    reject_forbidden_tool_events(execution.stdout)
    failure = classify_provider_failure(execution)
    artifacts = {
        "prompt": prompt_ref,
        "raw_response": response_ref,
        "invocation_receipt": _ref(harness_root, receipt_path),
    }
    if failure is not None:
        return {
            "schema_version": 1,
            "status": "blocked",
            "run_id": request["run_id"],
            "worker_id": request["worker_id"],
            "role": request["role"],
            "attempt_id": attempt_id,
            "fencing_token": fencing_token,
            "root_cause_key": str(failure.get("kind", "provider_failed")),
            "provider_invocations": int(execution.process_started),
            "model_launched": execution.process_started,
            "artifacts": artifacts,
            "preflight": preflight,
            "runtime_environment": dict(runtime_environment),
            "semantic_gate": False,
        }
    identity_status = validate_project_invocation_receipt(
        receipt_path,
        prompt_path=prompt_path,
        response_path=response_path,
        resolved_model=resolved_model,
        agent=FIXED_AGENT,
        variant=FIXED_VARIANT,
        require_export=preflight["proof_scope"] == "competition-model-preflight",
    )
    text = extract_single_json_text(assistant_text_from_jsonl(execution.stdout))
    try:
        response = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("OpenCode project worker returned invalid JSON") from error
    if not isinstance(response, dict):
        raise ValueError("OpenCode project worker response must be a JSON object")
    normalize_worker_result(request, response)
    parsed_ref = write_json_artifact(
        harness_root,
        f"{worker_root}/parsed/{stem}-{response_digest}.json",
        response,
    )
    final_artifacts = {
        **artifacts,
        "parsed_response": parsed_ref,
        **(
            {"session_identity": _ref(harness_root, session_path)}
            if identity_status.get("session_identity") is not None
            else {}
        ),
    }
    execution_report = {
        "schema_version": 1,
        "artifact_kind": "project-opencode-execution",
        "status": "generated",
        "run_id": request["run_id"],
        "worker_id": request["worker_id"],
        "role": request["role"],
        "attempt_id": attempt_id,
        "fencing_epoch": fencing_token,
        "request": dict(request_reference),
        "preflight": dict(preflight_reference),
        "model": {
            "logical": logical_model,
            "resolved": resolved_model,
            "agent": FIXED_AGENT,
            "variant": FIXED_VARIANT,
        },
        "runtime_input_sha256": runtime_environment["runtime_input_sha256"],
        "identity": identity_status,
        "artifacts": final_artifacts,
        "semantic_gate": False,
    }
    execution_local = write_content_addressed_json(
        _absolute(harness_root, worker_root),
        "provider-execution",
        execution_report,
    )
    execution_ref = {
        **execution_local,
        "path": f"{worker_root}/{execution_local['path']}",
    }
    final_artifacts["execution_report"] = execution_ref
    return {
        "schema_version": 1,
        "status": "generated",
        "run_id": request["run_id"],
        "worker_id": request["worker_id"],
        "role": request["role"],
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "worker_response": response,
        "artifacts": final_artifacts,
        "provider_invocations": 1,
        "model_launched": True,
        "preflight": preflight,
        "runtime_environment": dict(runtime_environment),
        "identity": identity_status,
        "semantic_gate": False,
    }


def _request(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(read_artifact_reference(root, reference).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("project worker request is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("project worker request must be a JSON object")
    return value


def _validate_execution_identity(
    request: Mapping[str, Any], attempt_id: str, fencing_token: int,
) -> None:
    binding = request.get("execution_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("project worker execution binding is absent")
    payload = {key: value for key, value in binding.items() if key != "binding_sha256"}
    if (
        binding.get("attempt_id") != attempt_id
        or binding.get("fencing_token") != fencing_token
        or content_sha256(payload) != binding.get("binding_sha256")
    ):
        raise ValueError("project worker attempt/fence binding drifted")


def _worker_root(request: Mapping[str, Any]) -> str:
    roots = request.get("runtime_roots")
    value = roots.get("out") if isinstance(roots, Mapping) else None
    if not isinstance(value, str):
        raise ValueError("project worker out root is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("project worker out root is unsafe")
    return path.as_posix()


def _absolute(root: Path, relative: str) -> Path:
    base = root.resolve(strict=True)
    target = (base / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise ValueError("project worker runtime path escapes the harness root") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _ref(root: Path, path: Path) -> dict[str, Any]:
    relative = path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
    data = path.read_bytes()
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


__all__ = ["execute_opencode_project_worker"]
