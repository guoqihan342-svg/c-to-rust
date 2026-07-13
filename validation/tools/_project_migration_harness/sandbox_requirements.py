from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any


REQUIRED_CAPABILITIES = (
    "cpu-limit",
    "environment-allowlist",
    "exit-cleanup",
    "file-size-limit",
    "home-isolated-empty",
    "memory-limit",
    "network-isolation",
    "open-files-limit",
    "privileges-dropped",
    "process-count-limit",
    "process-isolation",
    "project-read-only",
    "runtime-output-isolated",
    "temporary-isolated",
    "toolchain-read-only",
    "user-isolation",
    "wall-timeout",
)
ENVIRONMENT_ALLOWLIST = (
    "CARGO_HOME",
    "CARGO_NET_OFFLINE",
    "CARGO_TARGET_DIR",
    "CARGO_TERM_COLOR",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "RUSTC",
    "RUSTDOC",
    "TMPDIR",
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PURPOSE = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z", re.ASCII)
_SHELL_SYNTAX = re.compile(r"(?:&&|\|\||[;|<>`]|\$\(|\r|\n|\x00)")
_SHELLS = frozenset({
    "bash", "cmd", "cmd.exe", "dash", "fish", "ksh", "powershell",
    "powershell.exe", "pwsh", "sh", "zsh",
})


@dataclass(frozen=True, slots=True)
class SandboxRequirements:
    capabilities: tuple[str, ...] = REQUIRED_CAPABILITIES
    environment_allowlist: tuple[str, ...] = ENVIRONMENT_ALLOWLIST
    cpu_seconds: int = 300
    address_space_bytes: int = 4 * 1024 * 1024 * 1024
    file_size_bytes: int = 512 * 1024 * 1024
    process_count: int = 128
    open_files: int = 256

    def __post_init__(self) -> None:
        if type(self.capabilities) is not tuple or self.capabilities != REQUIRED_CAPABILITIES:
            raise ValueError("sandbox capabilities must match the strict fixed set")
        if (
            type(self.environment_allowlist) is not tuple
            or self.environment_allowlist != ENVIRONMENT_ALLOWLIST
        ):
            raise ValueError("sandbox environment allowlist must match the fixed set")
        _bounded_int(self.cpu_seconds, "cpu_seconds", maximum=3_600)
        _bounded_int(
            self.address_space_bytes, "address_space_bytes",
            maximum=64 * 1024 * 1024 * 1024,
        )
        _bounded_int(
            self.file_size_bytes, "file_size_bytes",
            maximum=8 * 1024 * 1024 * 1024,
        )
        _bounded_int(self.process_count, "process_count", maximum=512)
        _bounded_int(self.open_files, "open_files", maximum=4_096)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "capabilities": list(self.capabilities),
            "environment_allowlist": list(self.environment_allowlist),
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
        return _canonical_sha256(self.payload())


@dataclass(frozen=True, slots=True)
class SandboxVerificationPlan:
    purpose: str
    command: tuple[str, ...]
    input_sha256: str
    timeout_seconds: int
    requirements_sha256: str
    requirements: SandboxRequirements

    def __post_init__(self) -> None:
        if type(self.purpose) is not str or _PURPOSE.fullmatch(self.purpose) is None:
            raise ValueError("sandbox verification purpose is invalid")
        _validate_command(self.command)
        _validate_sha256(self.input_sha256, "input_sha256")
        _bounded_int(
            self.timeout_seconds, "timeout_seconds", minimum=30, maximum=3_600,
        )
        _validate_sha256(self.requirements_sha256, "requirements_sha256")
        if type(self.requirements) is not SandboxRequirements:
            raise ValueError("sandbox requirements type is invalid")
        if self.requirements_sha256 != self.requirements.sha256:
            raise ValueError("sandbox requirements hash is inconsistent")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "purpose": self.purpose,
            "command": list(self.command),
            "input_sha256": self.input_sha256,
            "timeout_seconds": self.timeout_seconds,
            "requirements_sha256": self.requirements_sha256,
        }

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.payload())


def strict_sandbox_requirements(
    *,
    cpu_seconds: int = 300,
    address_space_bytes: int = 4 * 1024 * 1024 * 1024,
    file_size_bytes: int = 512 * 1024 * 1024,
    process_count: int = 128,
    open_files: int = 256,
) -> SandboxRequirements:
    return SandboxRequirements(
        cpu_seconds=cpu_seconds,
        address_space_bytes=address_space_bytes,
        file_size_bytes=file_size_bytes,
        process_count=process_count,
        open_files=open_files,
    )


def requirements_from_payload(value: Any) -> SandboxRequirements:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "capabilities", "environment_allowlist",
        "resource_limits",
    }:
        raise ValueError("sandbox requirements payload schema is invalid")
    limits = value.get("resource_limits")
    if value.get("schema_version") != 1 or not isinstance(limits, Mapping) or set(limits) != {
        "cpu_seconds", "address_space_bytes", "file_size_bytes",
        "process_count", "open_files",
    }:
        raise ValueError("sandbox requirements payload schema is invalid")
    capabilities = value.get("capabilities")
    environment = value.get("environment_allowlist")
    if not isinstance(capabilities, list) or not isinstance(environment, list):
        raise ValueError("sandbox requirements payload schema is invalid")
    return SandboxRequirements(
        capabilities=tuple(capabilities),
        environment_allowlist=tuple(environment),
        cpu_seconds=limits["cpu_seconds"],
        address_space_bytes=limits["address_space_bytes"],
        file_size_bytes=limits["file_size_bytes"],
        process_count=limits["process_count"],
        open_files=limits["open_files"],
    )


def cargo_verification_plan(
    purpose: str,
    command: tuple[str, ...],
    input_sha256: str,
    timeout_seconds: int = 300,
    requirements: SandboxRequirements | None = None,
    requirements_sha256: str | None = None,
) -> SandboxVerificationPlan:
    if (
        type(command) is not tuple
        or not command
        or type(command[0]) is not str
        or command[0].lower() not in {"cargo", "cargo.exe"}
    ):
        raise ValueError("cargo verification command must name Cargo directly")
    selected = strict_sandbox_requirements() if requirements is None else requirements
    if type(selected) is not SandboxRequirements:
        raise ValueError("sandbox requirements type is invalid")
    claimed = selected.sha256 if requirements_sha256 is None else requirements_sha256
    return SandboxVerificationPlan(
        purpose=purpose,
        command=command,
        input_sha256=input_sha256,
        timeout_seconds=timeout_seconds,
        requirements_sha256=claimed,
        requirements=selected,
    )


def verification_plan_from_payload(
    value: Any, requirements: SandboxRequirements,
) -> SandboxVerificationPlan:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "purpose", "command", "input_sha256",
        "timeout_seconds", "requirements_sha256",
    } or value.get("schema_version") != 1:
        raise ValueError("sandbox verification plan schema is invalid")
    command = value.get("command")
    if not isinstance(command, list):
        raise ValueError("sandbox verification command is invalid")
    plan = cargo_verification_plan(
        value.get("purpose"),
        tuple(command),
        value.get("input_sha256"),
        timeout_seconds=value.get("timeout_seconds"),
        requirements=requirements,
        requirements_sha256=value.get("requirements_sha256"),
    )
    if plan.payload() != dict(value):
        raise ValueError("sandbox verification plan is not canonical")
    return plan


def _validate_command(command: Any) -> None:
    if type(command) is not tuple or not command or len(command) > 64:
        raise ValueError("sandbox verification command must be a non-empty tuple")
    total_bytes = 0
    for argument in command:
        if type(argument) is not str or not argument:
            raise ValueError("sandbox verification command arguments must be non-empty strings")
        encoded = argument.encode("utf-8")
        total_bytes += len(encoded)
        if len(encoded) > 4_096 or total_bytes > 65_536:
            raise ValueError("sandbox verification command exceeds its size bound")
        if _SHELL_SYNTAX.search(argument) or any(
            unicodedata.category(character) in {"Cc", "Cf"} for character in argument
        ):
            raise ValueError("sandbox verification command contains shell or control syntax")
    executable = command[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if executable in _SHELLS:
        raise ValueError("sandbox verification command must not invoke a shell")


def _validate_sha256(value: Any, label: str) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")


def _bounded_int(
    value: Any, label: str, *, minimum: int = 1, maximum: int | None = None,
) -> None:
    if type(value) is not int or value < minimum or (
        maximum is not None and value > maximum
    ):
        raise ValueError(f"{label} is outside the sandbox policy range")


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ENVIRONMENT_ALLOWLIST",
    "REQUIRED_CAPABILITIES",
    "SandboxRequirements",
    "SandboxVerificationPlan",
    "cargo_verification_plan",
    "requirements_from_payload",
    "strict_sandbox_requirements",
    "verification_plan_from_payload",
]
