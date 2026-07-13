from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .gate_authority import candidate_authority
from .ledger_security import LedgerError
from .sandbox_contract import canonical_sha256


SHA256 = re.compile(r"^[0-9a-f]{64}$")
PAYLOAD_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id", "unit_id",
    "candidate_artifact_id", "candidate_sha256", "candidate_set_sha256",
    "candidate_source", "run_contract", "quarantine",
    "verification_context_sha256", "sandbox", "check",
    "project_state_unchanged",
}
REFERENCE_KEYS = {"path", "sha256", "size_bytes"}
RUN_CONTRACT_KEYS = {"context_sha256", "dag_sha256", "integration_manifest"}
QUARANTINE_KEYS = {
    "generation_sha256", "quarantine_manifest", "generation_manifest",
}
SANDBOX_KEYS = {"contract", "contract_sha256"}
CONTRACT_KEYS = {
    "schema_version", "backend", "os_family", "launcher_sha256",
    "toolchain_sha256", "network", "project_input", "runtime_output", "home",
    "temporary_directory", "user_namespace", "process_namespace", "privileges",
    "resource_limits",
}
RESOURCE_LIMIT_KEYS = {
    "cpu_seconds", "address_space_bytes", "file_size_bytes", "process_count",
    "open_files",
}
CHECK_KEYS = {
    "command", "status", "cargo_executed", "returncode", "timed_out",
    "stdout_sha256", "stderr_sha256", "sandbox_contract_sha256",
    "sandbox_command_sha256", "sandbox_launcher_argv_sha256",
}
FIXED_CARGO_CHECK = [
    "cargo", "check", "--all-targets", "--offline", "--locked",
    "--message-format=json",
]


def derive_compile_status(
    payload: Mapping[str, Any], *, run_id: str, unit_id: str,
    candidate_artifact_id: str, candidate_sha256: str,
    candidate_set_sha256: str,
) -> str:
    if not isinstance(payload, Mapping) or set(payload) != PAYLOAD_KEYS:
        raise LedgerError("candidate compile observation schema is invalid")
    expected = {
        "schema_version": 1,
        "artifact_kind": "host-candidate-compile-observation",
        "authority_id": candidate_authority("compile"),
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_sha256": candidate_sha256,
        "candidate_set_sha256": candidate_set_sha256,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise LedgerError("candidate compile observation binding is invalid")
    if not all(is_sha(payload.get(key)) for key in (
        "candidate_sha256", "candidate_set_sha256", "verification_context_sha256",
    )):
        raise LedgerError("candidate compile observation hash is invalid")
    sandbox = payload.get("sandbox")
    check = payload.get("check")
    candidate_source = payload.get("candidate_source")
    run_contract = payload.get("run_contract")
    quarantine = payload.get("quarantine")
    if (
        not isinstance(sandbox, Mapping) or set(sandbox) != SANDBOX_KEYS
        or not isinstance(check, Mapping) or set(check) != CHECK_KEYS
        or not reference(candidate_source)
        or not isinstance(run_contract, Mapping) or set(run_contract) != RUN_CONTRACT_KEYS
        or not reference(run_contract.get("integration_manifest"))
        or not isinstance(quarantine, Mapping) or set(quarantine) != QUARANTINE_KEYS
        or not reference(quarantine.get("quarantine_manifest"))
        or not reference(quarantine.get("generation_manifest"))
        or not is_sha(quarantine.get("generation_sha256"))
        or quarantine["generation_manifest"].get("sha256")
        != quarantine.get("generation_sha256")
        or not is_sha(run_contract.get("context_sha256"))
        or not is_sha(run_contract.get("dag_sha256"))
        or payload.get("verification_context_sha256") != verification_context(payload)
    ):
        raise LedgerError("candidate compile execution schema is invalid")
    validated_contract(sandbox)
    if (
        check.get("sandbox_contract_sha256") != sandbox.get("contract_sha256")
        or check.get("command") != FIXED_CARGO_CHECK
        or check.get("sandbox_command_sha256") != canonical_sha256(FIXED_CARGO_CHECK)
        or not all(is_sha(check.get(key)) for key in (
            "stdout_sha256", "stderr_sha256", "sandbox_command_sha256",
            "sandbox_launcher_argv_sha256",
        ))
        or check.get("cargo_executed") is not True
        or check.get("timed_out") is not False
        or payload.get("project_state_unchanged") is not True
    ):
        raise LedgerError("candidate compile execution was not proven in the fixed sandbox")
    returncode = check.get("returncode")
    if check.get("status") == "passed" and returncode == 0:
        return "passed"
    if (
        check.get("status") == "failed"
        and isinstance(returncode, int) and not isinstance(returncode, bool)
        and returncode != 0
    ):
        return "failed"
    raise LedgerError("candidate compile result is environmental or ambiguous")


def validated_contract(sandbox: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = sandbox.get("contract")
    contract_sha256 = sandbox.get("contract_sha256")
    if (
        not isinstance(contract, Mapping)
        or set(contract) != CONTRACT_KEYS
        or not is_sha(contract_sha256)
    ):
        raise LedgerError("candidate compile sandbox contract schema is invalid")
    try:
        calculated = canonical_sha256(dict(contract))
    except (TypeError, ValueError) as error:
        raise LedgerError("candidate compile sandbox contract is not canonical") from error
    limits = contract.get("resource_limits")
    if (
        calculated != contract_sha256
        or contract.get("schema_version") != 1
        or contract.get("backend") != "bubblewrap-v1"
        or contract.get("os_family") != "linux"
        or not is_sha(contract.get("launcher_sha256"))
        or not is_sha(contract.get("toolchain_sha256"))
        or contract.get("network") != "unshared"
        or contract.get("project_input") != "read-only"
        or contract.get("runtime_output") != "isolated-read-write"
        or contract.get("home") != "isolated-empty"
        or contract.get("temporary_directory") != "isolated-tmpfs"
        or contract.get("user_namespace") != "isolated"
        or contract.get("process_namespace") != "isolated"
        or contract.get("privileges") != "all-capabilities-dropped"
        or not isinstance(limits, Mapping)
        or set(limits) != RESOURCE_LIMIT_KEYS
        or not all(positive_int(limits.get(key)) for key in RESOURCE_LIMIT_KEYS)
        or limits.get("cpu_seconds", 0) > 3_600
        or limits.get("process_count", 0) > 512
        or limits.get("open_files", 0) > 4_096
    ):
        raise LedgerError("candidate compile sandbox contract policy is invalid")
    return contract


def cargo_check(execution: Mapping[str, Any]) -> Mapping[str, Any]:
    checks = execution.get("checks")
    if isinstance(checks, (str, bytes)) or not isinstance(checks, Sequence):
        raise LedgerError("candidate compile execution has no unique cargo check")
    matches = [
        item for item in checks
        if isinstance(item, Mapping)
        and isinstance(item.get("command"), list)
        and item["command"] == FIXED_CARGO_CHECK
    ]
    if len(matches) != 1:
        raise LedgerError("candidate compile execution has no unique cargo check")
    return matches[0]


def verification_context(payload: Mapping[str, Any]) -> str:
    check = payload.get("check")
    command = check.get("command") if isinstance(check, Mapping) else None
    return canonical_sha256({
        "candidate_artifact_id": payload.get("candidate_artifact_id"),
        "candidate_sha256": payload.get("candidate_sha256"),
        "candidate_set_sha256": payload.get("candidate_set_sha256"),
        "candidate_source": payload.get("candidate_source"),
        "run_contract": payload.get("run_contract"),
        "quarantine": payload.get("quarantine"),
        "sandbox": payload.get("sandbox"),
        "command": command,
    })


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def reference(value: Any) -> bool:
    return (
        isinstance(value, Mapping) and set(value) == REFERENCE_KEYS
        and isinstance(value.get("path"), str) and bool(value.get("path"))
        and is_sha(value.get("sha256"))
        and positive_int(value.get("size_bytes"))
    )
