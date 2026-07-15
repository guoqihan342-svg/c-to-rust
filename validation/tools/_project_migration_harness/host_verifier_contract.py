from __future__ import annotations

"""Non-authoritative bindings for a future isolated host-verifier process.

The issuer and capability fields are schema bindings, not authentication.  This
layer neither consumes nonces nor submits receipts to TransitionAuthority.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any
import unicodedata

from .artifacts import checked_relative_path
from .gate_evidence import require_content_addressed_reference
from .ledger_security import LedgerError
from .sandbox_environment import (
    canonical_environment_items,
    cargo_guest_environment,
)
from .sandbox_requirements import SandboxVerificationPlan


HOST_VERIFIER_SCHEMA_VERSION = 1
HOST_VERIFIER_ARTIFACT_KIND = "host-verifier-envelope"
HOST_VERIFIER_ISSUER = "host-verifier-process-contract-v1"
HOST_VERIFIER_GATE_KINDS = (
    "project-initialization",
    "project-feature-cfg",
    "project-abi",
)
HOST_VERIFIER_STATUSES = ("failed", "blocked")
HOST_VERIFIER_TERMINATIONS = (
    "exited", "not-started", "signaled", "timed-out",
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PLAN_KEYS = {
    "schema_version", "purpose", "command", "input_sha256",
    "timeout_seconds", "requirements_sha256", "native_link_trace",
    "environment",
}
_SHELL_SYNTAX = re.compile(r"(?:&&|\|\||[;|<>`]|\$\(|\r|\n|\x00)")


@dataclass(frozen=True, slots=True)
class HostVerifierEnvelopeBindings:
    gate_kind: str
    run_capability_sha256: str
    nonce: str
    run_id: str
    cohort_sha256: str
    generation_sha256: str
    rust_project_ir_sha256: str
    rust_project_interface_sha256: str
    verification_plan: SandboxVerificationPlan
    toolchain_sha256: str
    sandbox_receipt: Mapping[str, Any]
    evidence_root: str

    def __post_init__(self) -> None:
        gate_kind_value(self.gate_kind)
        for value, label in (
            (self.run_capability_sha256, "run_capability_sha256"),
            (self.nonce, "nonce"),
            (self.cohort_sha256, "cohort_sha256"),
            (self.generation_sha256, "generation_sha256"),
            (self.rust_project_ir_sha256, "rust_project_ir_sha256"),
            (
                self.rust_project_interface_sha256,
                "rust_project_interface_sha256",
            ),
            (self.toolchain_sha256, "toolchain_sha256"),
        ):
            sha256_value(value, label)
        bounded_text(self.run_id, "run_id")
        if type(self.verification_plan) is not SandboxVerificationPlan:
            raise ValueError("host verifier VerificationPlan type is invalid")
        if (
            self.verification_plan.purpose != self.gate_kind
            or self.verification_plan.input_sha256 != self.generation_sha256
        ):
            raise ValueError("host verifier VerificationPlan binding is stale")
        reference = content_addressed_json_reference(self.sandbox_receipt)
        object.__setattr__(
            self, "sandbox_receipt", MappingProxyType(dict(reference)),
        )
        object.__setattr__(
            self, "evidence_root", evidence_root_value(self.evidence_root),
        )


def gate_kind_value(value: Any) -> str:
    if type(value) is not str or value not in HOST_VERIFIER_GATE_KINDS:
        raise ValueError("host verifier gate kind is invalid")
    return value


def sha256_value(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"host verifier {label} is not a lowercase SHA-256")
    return value


def bounded_text(value: Any, label: str) -> str:
    if (
        type(value) is not str or not value or len(value.encode("utf-8")) > 512
        or value != value.strip()
        or any(unicodedata.category(character) in {"Cc", "Cf"} for character in value)
    ):
        raise ValueError(f"host verifier {label} is invalid")
    return value


def evidence_root_value(value: Any) -> str:
    if type(value) is not str:
        raise ValueError("host verifier evidence root is invalid")
    try:
        normalized = checked_relative_path(value)
    except (IndexError, ValueError) as error:
        raise ValueError("host verifier evidence root is invalid") from error
    if not PurePosixPath(normalized).parts or normalized.endswith("/"):
        raise ValueError("host verifier evidence root is invalid")
    return normalized


def content_addressed_json_reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or type(value.get("size_bytes")) is not int:
        raise ValueError("host verifier JSON reference schema is invalid")
    try:
        require_content_addressed_reference(value)
    except (KeyError, TypeError, ValueError, LedgerError) as error:
        raise ValueError("host verifier JSON reference is invalid") from error
    return {
        "path": str(value["path"]),
        "sha256": str(value["sha256"]),
        "size_bytes": value["size_bytes"],
    }


def verification_plan_payload(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping) or set(value) != _PLAN_KEYS
        or value.get("schema_version") != 2
        or value.get("purpose") not in HOST_VERIFIER_GATE_KINDS
    ):
        raise ValueError("host verifier VerificationPlan schema is invalid")
    command = command_value(value.get("command"))
    sha256_value(value.get("input_sha256"), "VerificationPlan input_sha256")
    sha256_value(
        value.get("requirements_sha256"),
        "VerificationPlan requirements_sha256",
    )
    timeout = value.get("timeout_seconds")
    environment = value.get("environment")
    if type(timeout) is not int or not 30 <= timeout <= 3_600:
        raise ValueError("host verifier VerificationPlan timeout is invalid")
    if (
        value.get("native_link_trace") is not False
        or not isinstance(environment, Mapping)
        or canonical_environment_items(environment)
        != canonical_environment_items(cargo_guest_environment())
    ):
        raise ValueError("host verifier VerificationPlan environment is invalid")
    return {
        "schema_version": 2,
        "purpose": value["purpose"],
        "command": command,
        "input_sha256": value["input_sha256"],
        "timeout_seconds": timeout,
        "requirements_sha256": value["requirements_sha256"],
        "native_link_trace": False,
        "environment": dict(canonical_environment_items(environment)),
    }


def command_value(value: Any) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 64:
        raise ValueError("host verifier argv is invalid")
    total = 0
    result: list[str] = []
    for argument in value:
        if type(argument) is not str or not argument:
            raise ValueError("host verifier argv is invalid")
        encoded = argument.encode("utf-8")
        total += len(encoded)
        if (
            len(encoded) > 4_096 or total > 65_536
            or _SHELL_SYNTAX.search(argument) is not None
            or any(
                unicodedata.category(character) in {"Cc", "Cf"}
                for character in argument
            )
        ):
            raise ValueError("host verifier argv is invalid")
        result.append(argument)
    return result


__all__ = [
    "HOST_VERIFIER_ARTIFACT_KIND", "HOST_VERIFIER_GATE_KINDS",
    "HOST_VERIFIER_ISSUER", "HOST_VERIFIER_SCHEMA_VERSION",
    "HOST_VERIFIER_STATUSES", "HOST_VERIFIER_TERMINATIONS",
    "HostVerifierEnvelopeBindings", "bounded_text", "command_value",
    "content_addressed_json_reference", "evidence_root_value",
    "gate_kind_value", "sha256_value", "verification_plan_payload",
]
