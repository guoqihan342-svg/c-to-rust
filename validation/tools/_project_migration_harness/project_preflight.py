from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from validation.tools._ai_candidate_harness_parts.model_identity import (
    resolve_model_identity,
)

from .artifacts import content_sha256
from .ledger_security import assert_no_secrets
from .opencode_environment import ENVIRONMENT_VARIABLES, fixed_isolation_contract
from .orchestration_facts import read_artifact_reference
from .project_agent_contract import verify_project_agent


FIXED_COMMAND = "opencode"
FIXED_AGENT = "c2rust-candidate"
FIXED_VARIANT = "max"
REPORT_KEYS = {
    "schema_version", "report_kind", "run_id", "status", "exit_code",
    "process_returncode", "redaction_count", "opencode_run_launched",
    "provider_invocations", "launch_policy", "model_probe", "agent_contract",
    "isolation_contract", "environment_probe", "marker",
}


def validate_project_worker_preflight(
    reference: Mapping[str, Any], *, harness_root: Path, run_id: str,
    logical_model: str, resolved_model: str, opencode_command: str,
    agent: str, variant: str,
) -> dict[str, str]:
    if opencode_command != FIXED_COMMAND or agent != FIXED_AGENT or variant != FIXED_VARIANT:
        raise ValueError("project worker preflight policy is not fixed")
    identity = resolve_model_identity(resolved_model)
    if logical_model != identity.logical_model:
        raise ValueError("logical model does not match the resolved model identity")
    payload = _json_reference(harness_root, reference, "OpenCode preflight report")
    assert_no_secrets(payload, "project_preflight")
    policy = payload.get("launch_policy")
    probe = payload.get("model_probe")
    if not isinstance(policy, Mapping) or not isinstance(probe, Mapping):
        raise ValueError("OpenCode preflight report sections are missing")
    checks = (
        set(payload) == REPORT_KEYS,
        payload.get("schema_version") == 2,
        payload.get("report_kind") == "project-opencode-preflight",
        payload.get("run_id") == run_id,
        payload.get("status") == "passed",
        payload.get("exit_code") == 0,
        payload.get("process_returncode") == 0,
        payload.get("redaction_count") == 0,
        payload.get("opencode_run_launched") is False,
        payload.get("provider_invocations") == 0,
        policy.get("opencode_command") == FIXED_COMMAND,
        policy.get("opencode_model") == logical_model,
        policy.get("resolved_model_id") == resolved_model,
        policy.get("opencode_agent") == FIXED_AGENT,
        policy.get("opencode_variant") == FIXED_VARIANT,
        set(policy) == {
            "opencode_command", "opencode_model", "resolved_model_id",
            "opencode_agent", "opencode_variant",
        },
        probe.get("status") == "available",
        probe.get("model_listed") is True,
        probe.get("process_returncode") == 0,
        probe.get("argv") == [FIXED_COMMAND, "models"],
        set(probe) == {
            "status", "model_listed", "process_returncode", "argv", "stdout", "stderr",
        },
        payload.get("agent_contract") == verify_project_agent(harness_root),
        payload.get("isolation_contract") == fixed_isolation_contract(),
        isinstance(payload.get("environment_probe"), Mapping),
        payload.get("environment_probe", {}).get("agent_sha256")
        == payload.get("agent_contract", {}).get("sha256"),
    )
    if not all(checks):
        raise ValueError("OpenCode preflight report does not authorize this worker launch")
    _validate_environment_probe(payload.get("environment_probe"))
    _validate_marker(
        payload, harness_root=harness_root, run_id=run_id,
        logical_model=logical_model, resolved_model=resolved_model,
    )
    stdout = _probe_log(probe, "stdout", harness_root)
    _probe_log(probe, "stderr", harness_root)
    if not _contains_exact_model_token(stdout.decode("utf-8"), resolved_model):
        raise ValueError("OpenCode model probe log does not contain the exact resolved model")
    return {
        "status": "passed",
        "logical_model": logical_model,
        "resolved_model": resolved_model,
        "agent": FIXED_AGENT,
        "variant": FIXED_VARIANT,
        "agent_sha256": str(payload["agent_contract"]["sha256"]),
        "runtime_input_sha256": str(payload["environment_probe"]["runtime_input_sha256"]),
        "proof_scope": (
            "competition-model-preflight"
            if identity.competition_eligible
            else "auxiliary-local-validation"
        ),
    }


def _validate_environment_probe(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("OpenCode preflight isolation probe is missing")
    if (
        value.get("schema_version") != 1
        or value.get("status") != "isolated"
        or value.get("scope") != "attempt"
        or value.get("explicit_environment") is not True
        or value.get("global_environment_mutated") is not False
        or value.get("environment_variables") != list(ENVIRONMENT_VARIABLES)
        or value.get("cleanup") != "context-exit"
        or value.get("credential_copy") not in {"bounded-ephemeral", "unavailable"}
        or not isinstance(value.get("config_file_count"), int)
        or isinstance(value.get("config_file_count"), bool)
        or not 0 <= value["config_file_count"] <= 2
        or not isinstance(value.get("agent_sha256"), str)
        or value["agent_sha256"] != value["agent_sha256"].lower()
        or re.fullmatch(r"[0-9a-f]{64}", value["agent_sha256"]) is None
        or not isinstance(value.get("runtime_input_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["runtime_input_sha256"]) is None
        or set(value) != {
            "schema_version", "status", "scope", "attempt_tag",
            "explicit_environment", "global_environment_mutated",
            "credential_copy", "config_file_count", "agent_sha256",
            "runtime_input_sha256", "environment_variables", "cleanup",
        }
    ):
        raise ValueError("OpenCode preflight isolation probe is invalid")


def _validate_marker(
    report: Mapping[str, Any], *, harness_root: Path, run_id: str,
    logical_model: str, resolved_model: str,
) -> None:
    marker = _json_reference(harness_root, report.get("marker"), "OpenCode preflight marker")
    agent = verify_project_agent(harness_root)
    binding = {
        "run_id": run_id,
        "logical_model": logical_model,
        "resolved_model": resolved_model,
        "agent_sha256": agent["sha256"],
        "isolation_contract_sha256": content_sha256(fixed_isolation_contract()),
    }
    if (
        marker.get("schema_version") != 2
        or set(marker) != {
            "schema_version", "report_kind", "run_id", "status",
            "binding", "binding_sha256",
        }
        or marker.get("report_kind") != "project-opencode-preflight-marker"
        or marker.get("run_id") != run_id
        or marker.get("status") != "written"
        or marker.get("binding") != binding
        or marker.get("binding_sha256") != content_sha256(binding)
    ):
        raise ValueError("OpenCode preflight marker is invalid")


def _probe_log(probe: Mapping[str, Any], stream: str, harness_root: Path) -> bytes:
    reference = probe.get(stream)
    if not isinstance(reference, Mapping) or not _reference_keys_valid(reference):
        raise ValueError(f"OpenCode model probe {stream} binding is missing")
    data = read_artifact_reference(harness_root, reference)
    try:
        data.decode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"OpenCode model probe {stream} is not UTF-8") from error
    return data


def _json_reference(
    root: Path, reference: Any, label: str,
) -> dict[str, Any]:
    if not isinstance(reference, Mapping):
        raise ValueError(f"{label} reference is invalid")
    if not _reference_keys_valid(reference):
        raise ValueError(f"{label} reference fields are invalid")
    try:
        payload = json.loads(read_artifact_reference(root, reference).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _contains_exact_model_token(stdout: str, resolved_model: str) -> bool:
    return any(
        token.strip("`'\"*,").casefold() == resolved_model.casefold()
        for line in stdout.splitlines()
        for token in re.split(r"\s+", line.strip())
    )


def _reference_keys_valid(reference: Mapping[str, Any]) -> bool:
    return set(reference) in ({"path", "sha256"}, {"path", "sha256", "size_bytes"})


__all__ = [
    "FIXED_AGENT", "FIXED_COMMAND", "FIXED_VARIANT",
    "validate_project_worker_preflight",
]
