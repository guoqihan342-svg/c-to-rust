from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Protocol, Sequence


SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class SandboxContract:
    backend: str
    launcher_sha256: str
    toolchain_sha256: str
    cpu_seconds: int = 300
    address_space_bytes: int = 4 * 1024 * 1024 * 1024
    file_size_bytes: int = 512 * 1024 * 1024
    process_count: int = 128
    open_files: int = 256

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
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
            "resource_limits": {
                "cpu_seconds": self.cpu_seconds,
                "address_space_bytes": self.address_space_bytes,
                "file_size_bytes": self.file_size_bytes,
                "process_count": self.process_count,
                "open_files": self.open_files,
            },
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.payload())


@dataclass(frozen=True)
class SandboxRunResult:
    completed: subprocess.CompletedProcess[str]
    contract_sha256: str
    command_sha256: str
    command_started: bool
    launcher_argv_sha256: str


class SandboxBackend(Protocol):
    @property
    def contract(self) -> SandboxContract: ...

    def execute(
        self, cargo_binary: Path, cargo_args: Sequence[str], *,
        project_root: Path, runtime_root: Path, timeout_seconds: int,
    ) -> SandboxRunResult: ...


@dataclass(frozen=True)
class SandboxDiscovery:
    backend: SandboxBackend | None
    reason_code: str | None


def validate_contract(contract: SandboxContract) -> None:
    if not isinstance(contract, SandboxContract):
        raise ValueError("sandbox contract type is invalid")
    payload = contract.payload()
    if (
        contract.backend != "bubblewrap-v1"
        or SHA256.fullmatch(contract.launcher_sha256) is None
        or SHA256.fullmatch(contract.toolchain_sha256) is None
        or payload["network"] != "unshared"
        or payload["project_input"] != "read-only"
        or payload["home"] != "isolated-empty"
        or payload["temporary_directory"] != "isolated-tmpfs"
        or payload["user_namespace"] != "isolated"
        or payload["privileges"] != "all-capabilities-dropped"
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


def validate_run_result(
    result: SandboxRunResult, contract: SandboxContract, command: Sequence[str],
) -> None:
    if not isinstance(result, SandboxRunResult):
        raise ValueError("sandbox result type is invalid")
    expected_command = canonical_sha256(list(command))
    if (
        result.contract_sha256 != contract.sha256
        or result.command_sha256 != expected_command
        or not result.command_started
        or SHA256.fullmatch(result.launcher_argv_sha256) is None
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
    "validate_contract",
    "validate_run_result",
]
