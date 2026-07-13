from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from .sandbox_contract import (
    SandboxContract, canonical_sha256, contract_from_payload,
)
from .sandbox_probe import (
    SandboxProbeReceipt, probe_receipt_from_payload, validate_probe_receipt,
)
from .sandbox_requirements import (
    SandboxVerificationPlan, verification_plan_from_payload,
)


SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SANDBOX_EVIDENCE_KEYS = {
    "contract", "contract_sha256", "probe_receipt",
    "probe_receipt_sha256", "cleanup_verified",
}
CHECK_EVIDENCE_KEYS = {
    "command", "status", "cargo_executed", "returncode", "timed_out",
    "stdout_sha256", "stderr_sha256", "sandbox_contract_sha256",
    "sandbox_command_sha256", "sandbox_command_started",
    "sandbox_launcher_argv_sha256", "sandbox_requirements_sha256",
    "sandbox_verification_plan", "sandbox_verification_plan_sha256",
    "sandbox_probe_receipt_sha256",
}


@dataclass(frozen=True, slots=True)
class ValidatedSandboxExecution:
    contract: SandboxContract
    probe_receipt: SandboxProbeReceipt
    verification_plan: SandboxVerificationPlan
    status: str


def validate_sandbox_execution_evidence(
    sandbox: Any,
    check: Any,
    *,
    expected_command: Sequence[str],
    expected_input_sha256: str,
    expected_purpose: str,
) -> ValidatedSandboxExecution:
    if not isinstance(sandbox, Mapping) or set(sandbox) != SANDBOX_EVIDENCE_KEYS:
        raise ValueError("sandbox execution evidence schema is invalid")
    if not isinstance(check, Mapping) or set(check) != CHECK_EVIDENCE_KEYS:
        raise ValueError("sandbox check evidence schema is invalid")
    command = list(expected_command)
    if not command or not all(type(item) is str for item in command):
        raise ValueError("expected sandbox command is invalid")
    contract = _validated_contract(sandbox)
    probe = _validated_probe(sandbox, contract)
    plan = _validated_plan(
        check,
        contract,
        expected_command=command,
        expected_input_sha256=expected_input_sha256,
        expected_purpose=expected_purpose,
    )
    if (
        check.get("command") != command
        or check.get("sandbox_contract_sha256") != contract.sha256
        or check.get("sandbox_command_sha256") != canonical_sha256(command)
        or check.get("sandbox_command_started") is not True
        or check.get("sandbox_requirements_sha256") != contract.requirements.sha256
        or check.get("sandbox_verification_plan_sha256") != plan.sha256
        or check.get("sandbox_probe_receipt_sha256") != probe.sha256
        or sandbox.get("cleanup_verified") is not True
        or check.get("cargo_executed") is not True
        or check.get("timed_out") is not False
        or not all(is_sha256(check.get(key)) for key in (
            "stdout_sha256", "stderr_sha256", "sandbox_command_sha256",
            "sandbox_launcher_argv_sha256",
        ))
    ):
        raise ValueError("sandbox execution bindings are invalid")
    status = _derived_status(check)
    return ValidatedSandboxExecution(contract, probe, plan, status)


def _validated_contract(sandbox: Mapping[str, Any]) -> SandboxContract:
    payload = sandbox.get("contract")
    claimed = sandbox.get("contract_sha256")
    if not isinstance(payload, Mapping) or not is_sha256(claimed):
        raise ValueError("sandbox contract evidence schema is invalid")
    contract = contract_from_payload(payload)
    if contract.sha256 != claimed:
        raise ValueError("sandbox contract evidence drifted")
    return contract


def _validated_probe(
    sandbox: Mapping[str, Any], contract: SandboxContract,
) -> SandboxProbeReceipt:
    receipt = probe_receipt_from_payload(sandbox.get("probe_receipt"))
    validate_probe_receipt(receipt, contract, contract.requirements)
    if receipt.sha256 != sandbox.get("probe_receipt_sha256"):
        raise ValueError("sandbox probe receipt drifted")
    return receipt


def _validated_plan(
    check: Mapping[str, Any], contract: SandboxContract, *,
    expected_command: list[str], expected_input_sha256: str,
    expected_purpose: str,
) -> SandboxVerificationPlan:
    plan = verification_plan_from_payload(
        check.get("sandbox_verification_plan"), contract.requirements,
    )
    if (
        plan.purpose != expected_purpose
        or list(plan.command) != expected_command
        or plan.input_sha256 != expected_input_sha256
    ):
        raise ValueError("sandbox verification plan binding is invalid")
    return plan


def _derived_status(check: Mapping[str, Any]) -> str:
    returncode = check.get("returncode")
    if check.get("status") == "passed" and type(returncode) is int and returncode == 0:
        return "passed"
    if (
        check.get("status") == "failed"
        and type(returncode) is int
        and returncode != 0
    ):
        return "failed"
    raise ValueError("sandbox execution result is environmental or ambiguous")


def is_sha256(value: Any) -> bool:
    return type(value) is str and SHA256.fullmatch(value) is not None


__all__ = [
    "CHECK_EVIDENCE_KEYS", "SANDBOX_EVIDENCE_KEYS",
    "ValidatedSandboxExecution", "is_sha256",
    "validate_sandbox_execution_evidence",
]
