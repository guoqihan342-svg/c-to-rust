from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .gate_authority import candidate_authority
from .gate_evidence import require_content_addressed_reference
from .ledger_security import LedgerError
from .sandbox_contract import canonical_sha256


SEMANTIC_FAMILIES = frozenset({
    "oracle-replay-diff", "negative", "unsafe-alias", "abi-layout",
})
FIXED_TIMEOUT_SECONDS = 300
MAX_ADAPTER_OUTPUT_BYTES = 1024 * 1024
MAX_OBSERVATION_COUNT = 1_000_000
FIXED_RESOURCE_LIMITS = {
    "cpu_seconds": 300,
    "address_space_bytes": 2 * 1024 * 1024 * 1024,
    "file_size_bytes": MAX_ADAPTER_OUTPUT_BYTES,
    "process_count": 64,
    "open_files": 128,
}
OBSERVATION_FIELDS = {
    "oracle-replay-diff": {
        "case_count", "mismatch_count", "crash_count", "c_oracle_sha256",
        "rust_replay_sha256", "diff_sha256",
    },
    "negative": {
        "case_count", "unexpected_accept_count", "mutation_manifest_sha256",
    },
    "unsafe-alias": {
        "unsafe_site_count", "unproven_alias_count", "unsafe_ledger_sha256",
        "alias_evidence_sha256",
    },
    "abi-layout": {
        "check_count", "mismatch_count", "c_layout_sha256",
        "rust_layout_sha256",
    },
}
CONTEXT_KEYS = {
    "run_id", "group_id", "unit_id", "candidate_artifact_id",
    "candidate_sha256", "candidate_set_sha256", "candidate_source",
    "run_context_sha256", "compile_verdict", "compile_observation",
    "generation_sha256", "toolchain_sha256",
}
PLAN_KEYS = {
    "schema_version", "adapter_id", "protocol", "gate_family", "command",
    "command_sha256", "launcher_argv_sha256", "adapter_source_sha256",
    "launcher_sha256", "timeout_seconds", "resource_limits",
    "max_stdout_bytes", "max_stderr_bytes", "shell",
}
EXECUTION_KEYS = {
    "command_sha256", "launcher_argv_sha256", "command_started",
    "returncode", "timed_out", "stdout_sha256", "stderr_sha256",
    "stdout_size_bytes", "stderr_size_bytes",
}
PAYLOAD_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "adapter_id",
    "gate_family", *CONTEXT_KEYS, "verification_plan",
    "verification_context_sha256", "execution", "observation",
}


def fixed_adapter_plan(gate_family: str) -> dict[str, Any]:
    _family(gate_family)
    launcher = Path(sys.executable).resolve(strict=True)
    adapter = Path(__file__).with_name("candidate_semantic_runners.py").resolve(strict=True)
    command = [
        launcher.name, "-E", "-s", "-B", "-m",
        "validation.tools._project_migration_harness.candidate_semantic_runners",
        "--adapter-worker", gate_family,
    ]
    launcher_argv = [
        str(launcher), *command[1:],
    ]
    plan = {
        "schema_version": 1,
        "adapter_id": f"host.candidate.semantic.{gate_family}.v1",
        "protocol": "candidate-semantic-raw-json-v1",
        "gate_family": gate_family,
        "command": command,
        "command_sha256": canonical_sha256(command),
        "launcher_argv_sha256": canonical_sha256(launcher_argv),
        "adapter_source_sha256": _file_sha256(adapter),
        "launcher_sha256": _file_sha256(launcher),
        "timeout_seconds": FIXED_TIMEOUT_SECONDS,
        "resource_limits": dict(FIXED_RESOURCE_LIMITS),
        "max_stdout_bytes": MAX_ADAPTER_OUTPUT_BYTES,
        "max_stderr_bytes": MAX_ADAPTER_OUTPUT_BYTES,
        "shell": False,
    }
    return plan


def semantic_verification_context(
    context: Mapping[str, Any], plan: Mapping[str, Any],
) -> str:
    if not isinstance(context, Mapping) or set(context) != CONTEXT_KEYS:
        raise LedgerError("candidate semantic verification context is invalid")
    return canonical_sha256({"bindings": dict(context), "plan": dict(plan)})


def semantic_raw_payload(
    *, gate_family: str, context: Mapping[str, Any],
    execution: Mapping[str, Any], observation: Mapping[str, Any],
) -> dict[str, Any]:
    plan = fixed_adapter_plan(gate_family)
    payload = {
        "schema_version": 2,
        "artifact_kind": "host-candidate-semantic-raw-observation",
        "authority_id": candidate_authority(gate_family),
        "adapter_id": plan["adapter_id"],
        "gate_family": gate_family,
        **dict(context),
        "verification_plan": plan,
        "verification_context_sha256": semantic_verification_context(context, plan),
        "execution": dict(execution),
        "observation": dict(observation),
    }
    derive_strict_semantic_status(
        payload,
        run_id=str(context.get("run_id")),
        unit_id=str(context.get("unit_id")),
        candidate_artifact_id=str(context.get("candidate_artifact_id")),
        candidate_sha256=str(context.get("candidate_sha256")),
        candidate_set_sha256=str(context.get("candidate_set_sha256")),
        gate_family=gate_family,
    )
    return payload


def derive_strict_semantic_status(
    payload: Mapping[str, Any], *, run_id: str, unit_id: str,
    candidate_artifact_id: str, candidate_sha256: str,
    candidate_set_sha256: str, gate_family: str,
) -> str:
    _family(gate_family)
    if not isinstance(payload, Mapping) or set(payload) != PAYLOAD_KEYS:
        raise LedgerError("candidate semantic raw observation schema is invalid")
    expected = {
        "schema_version": 2,
        "artifact_kind": "host-candidate-semantic-raw-observation",
        "authority_id": candidate_authority(gate_family),
        "adapter_id": f"host.candidate.semantic.{gate_family}.v1",
        "gate_family": gate_family,
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_sha256": candidate_sha256,
        "candidate_set_sha256": candidate_set_sha256,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise LedgerError("candidate semantic raw observation binding is invalid")
    _validate_context(payload)
    plan = fixed_adapter_plan(gate_family)
    if payload.get("verification_plan") != plan:
        raise LedgerError("candidate semantic adapter plan drifted")
    context = {key: payload.get(key) for key in CONTEXT_KEYS}
    if payload.get("verification_context_sha256") != semantic_verification_context(context, plan):
        raise LedgerError("candidate semantic verification context drifted")
    _validate_execution(payload.get("execution"), plan)
    observation = payload.get("observation")
    _validate_observation(gate_family, observation)
    encoded = canonical_json_bytes(observation)
    execution = payload["execution"]
    if (
        execution["stdout_sha256"] != hashlib.sha256(encoded).hexdigest()
        or execution["stdout_size_bytes"] != len(encoded)
    ):
        raise LedgerError("candidate semantic observation is not the fixed adapter stdout")
    return "passed" if _observation_passed(gate_family, observation) else "failed"


def parse_adapter_observation(data: bytes, gate_family: str) -> dict[str, Any]:
    _family(gate_family)
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_ADAPTER_OUTPUT_BYTES:
        raise LedgerError("candidate semantic adapter output size is invalid")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("candidate semantic adapter output is not JSON") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise LedgerError("candidate semantic adapter output is not canonical JSON")
    _validate_observation(gate_family, value)
    return value


def is_strict_semantic_payload(value: Mapping[str, Any]) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("schema_version") == 2
        and value.get("artifact_kind") == "host-candidate-semantic-raw-observation"
    )


def _validate_context(value: Mapping[str, Any]) -> None:
    for key in (
        "candidate_sha256", "candidate_set_sha256", "run_context_sha256",
        "generation_sha256", "toolchain_sha256",
    ):
        _sha(value.get(key), key)
    for key in ("run_id", "group_id", "unit_id", "candidate_artifact_id"):
        item = value.get(key)
        if not isinstance(item, str) or not item or len(item) > 256 or any(
            char in item for char in "\r\n\x00"
        ):
            raise LedgerError(f"candidate semantic {key} is invalid")
    source = value.get("candidate_source")
    if not isinstance(source, Mapping) or set(source) != {"path", "sha256", "size_bytes"}:
        raise LedgerError("candidate semantic source reference is invalid")
    try:
        checked_relative_path(str(source.get("path")))
    except ValueError as error:
        raise LedgerError("candidate semantic source path is invalid") from error
    _sha(source.get("sha256"), "candidate source sha256")
    _bounded_int(source.get("size_bytes"), "candidate source size", 64 * 1024 * 1024, 1)
    for key in ("compile_verdict", "compile_observation"):
        reference = value.get(key)
        if not isinstance(reference, Mapping):
            raise LedgerError("candidate semantic compile reference is invalid")
        require_content_addressed_reference(reference)


def _validate_execution(value: Any, plan: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != EXECUTION_KEYS:
        raise LedgerError("candidate semantic execution schema is invalid")
    if (
        value.get("command_sha256") != plan["command_sha256"]
        or value.get("launcher_argv_sha256") != plan["launcher_argv_sha256"]
        or value.get("command_started") is not True
        or value.get("returncode") != 0
        or value.get("timed_out") is not False
    ):
        raise LedgerError("candidate semantic fixed adapter execution is unproven")
    _sha(value.get("stdout_sha256"), "semantic stdout sha256")
    _sha(value.get("stderr_sha256"), "semantic stderr sha256")
    _bounded_int(value.get("stdout_size_bytes"), "semantic stdout size", MAX_ADAPTER_OUTPUT_BYTES, 1)
    _bounded_int(value.get("stderr_size_bytes"), "semantic stderr size", MAX_ADAPTER_OUTPUT_BYTES)


def _validate_observation(gate_family: str, value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != OBSERVATION_FIELDS[gate_family]:
        raise LedgerError("candidate semantic family observation schema is invalid")
    count_fields = {
        "oracle-replay-diff": ("case_count", "mismatch_count", "crash_count"),
        "negative": ("case_count", "unexpected_accept_count"),
        "unsafe-alias": ("unsafe_site_count", "unproven_alias_count"),
        "abi-layout": ("check_count", "mismatch_count"),
    }[gate_family]
    for key in count_fields:
        _bounded_int(value.get(key), key, MAX_OBSERVATION_COUNT)
    for key in OBSERVATION_FIELDS[gate_family] - set(count_fields):
        _sha(value.get(key), key)


def _observation_passed(gate_family: str, value: Mapping[str, Any]) -> bool:
    if gate_family == "oracle-replay-diff":
        return value["case_count"] > 0 and value["mismatch_count"] == value["crash_count"] == 0
    if gate_family == "negative":
        return value["case_count"] > 0 and value["unexpected_accept_count"] == 0
    if gate_family == "unsafe-alias":
        return value["unproven_alias_count"] == 0
    return value["check_count"] > 0 and value["mismatch_count"] == 0


def _family(value: str) -> None:
    if value not in SEMANTIC_FAMILIES:
        raise LedgerError("candidate semantic gate family is invalid")


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise LedgerError(f"{label} is not a SHA-256")


def _bounded_int(value: Any, label: str, maximum: int, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise LedgerError(f"{label} is invalid")


def _file_sha256(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise LedgerError("candidate semantic adapter executable is invalid")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
