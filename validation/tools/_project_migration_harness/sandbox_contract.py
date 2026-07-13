from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import subprocess
from collections.abc import Mapping
from typing import Any, Protocol, Sequence

from .sandbox_requirements import (
    SandboxRequirements, SandboxVerificationPlan, requirements_from_payload,
    strict_sandbox_requirements,
)


SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class SandboxContract:
    backend: str
    launcher_sha256: str
    toolchain_sha256: str
    requirements: SandboxRequirements = field(
        default_factory=strict_sandbox_requirements,
    )

    def __post_init__(self) -> None:
        if type(self.requirements) is not SandboxRequirements:
            raise ValueError("sandbox contract requirements type is invalid")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "backend": self.backend,
            "os_family": "linux",
            "launcher_sha256": self.launcher_sha256,
            "toolchain_sha256": self.toolchain_sha256,
            "network": "unshared",
            "project_input": "read-only",
            "runtime_output": "isolated-read-write",
            "home": "isolated-empty",
            "temporary_directory": "isolated-tmpfs",
            "user_namespace": "isolated",
            "process_namespace": "isolated",
            "privileges": "all-capabilities-dropped",
            "requirements": self.requirements.payload(),
            "requirements_sha256": self.requirements.sha256,
            "resource_limits": dict(self.requirements.payload()["resource_limits"]),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.payload())

    @property
    def cpu_seconds(self) -> int:
        return self.requirements.cpu_seconds

    @property
    def address_space_bytes(self) -> int:
        return self.requirements.address_space_bytes

    @property
    def file_size_bytes(self) -> int:
        return self.requirements.file_size_bytes

    @property
    def process_count(self) -> int:
        return self.requirements.process_count

    @property
    def open_files(self) -> int:
        return self.requirements.open_files


@dataclass(frozen=True)
class SandboxRunResult:
    completed: subprocess.CompletedProcess[str]
    contract_sha256: str
    command_sha256: str
    command_started: bool
    launcher_argv_sha256: str
    requirements_sha256: str
    verification_plan_sha256: str
    probe_receipt_sha256: str


class SandboxBackend(Protocol):
    @property
    def contract(self) -> SandboxContract: ...

    def execute(
        self, cargo_binary: Path, cargo_args: Sequence[str], *,
        project_root: Path, runtime_root: Path,
        verification_plan: SandboxVerificationPlan,
        probe_receipt: object,
    ) -> SandboxRunResult: ...


@dataclass(frozen=True)
class SandboxDiscovery:
    backend: SandboxBackend | None
    reason_code: str | None
    probe_receipt: object | None = None


def validate_contract(contract: SandboxContract) -> None:
    if not isinstance(contract, SandboxContract):
        raise ValueError("sandbox contract type is invalid")
    payload = contract.payload()
    try:
        reopened_requirements = requirements_from_payload(payload.get("requirements"))
    except ValueError as error:
        raise ValueError("sandbox contract requirements are invalid") from error
    if (
        contract.backend != "bubblewrap-v1"
        or not isinstance(contract.launcher_sha256, str)
        or SHA256.fullmatch(contract.launcher_sha256) is None
        or not isinstance(contract.toolchain_sha256, str)
        or SHA256.fullmatch(contract.toolchain_sha256) is None
        or payload["network"] != "unshared"
        or payload["project_input"] != "read-only"
        or payload["home"] != "isolated-empty"
        or payload["temporary_directory"] != "isolated-tmpfs"
        or payload["user_namespace"] != "isolated"
        or payload["privileges"] != "all-capabilities-dropped"
        or reopened_requirements != contract.requirements
        or payload.get("requirements_sha256") != contract.requirements.sha256
        or payload.get("resource_limits")
        != contract.requirements.payload()["resource_limits"]
    ):
        raise ValueError("sandbox contract policy is invalid")
    limits = (
        contract.cpu_seconds,
        contract.address_space_bytes,
        contract.file_size_bytes,
        contract.process_count,
        contract.open_files,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in limits):
        raise ValueError("sandbox resource limits are invalid")
    if contract.cpu_seconds > 3_600 or contract.process_count > 512 or contract.open_files > 4_096:
        raise ValueError("sandbox resource limits exceed policy")


def contract_from_payload(value: Any) -> SandboxContract:
    if not isinstance(value, Mapping):
        raise ValueError("sandbox contract payload is invalid")
    requirements = requirements_from_payload(value.get("requirements"))
    contract = SandboxContract(
        backend=value.get("backend"),
        launcher_sha256=value.get("launcher_sha256"),
        toolchain_sha256=value.get("toolchain_sha256"),
        requirements=requirements,
    )
    validate_contract(contract)
    if contract.payload() != dict(value):
        raise ValueError("sandbox contract payload is not canonical")
    return contract


def validate_run_result(
    result: SandboxRunResult, contract: SandboxContract,
    plan: SandboxVerificationPlan, probe_receipt: object,
) -> None:
    from .sandbox_probe import SandboxProbeReceipt, validate_probe_receipt

    if not isinstance(result, SandboxRunResult):
        raise ValueError("sandbox result type is invalid")
    if not isinstance(plan, SandboxVerificationPlan):
        raise ValueError("sandbox verification plan type is invalid")
    if not isinstance(probe_receipt, SandboxProbeReceipt):
        raise ValueError("sandbox probe receipt type is invalid")
    validate_probe_receipt(probe_receipt, contract, plan.requirements)
    expected_command = canonical_sha256(list(plan.command))
    if (
        result.contract_sha256 != contract.sha256
        or result.command_sha256 != expected_command
        or not result.command_started
        or SHA256.fullmatch(result.launcher_argv_sha256) is None
        or plan.requirements != contract.requirements
        or result.requirements_sha256 != contract.requirements.sha256
        or result.verification_plan_sha256 != plan.sha256
        or result.probe_receipt_sha256 != probe_receipt.sha256
    ):
        raise ValueError("sandbox execution binding is invalid")


def canonical_sha256(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "SandboxBackend",
    "SandboxContract",
    "SandboxDiscovery",
    "SandboxRunResult",
    "canonical_sha256",
    "contract_from_payload",
    "validate_contract",
    "validate_run_result",
]
