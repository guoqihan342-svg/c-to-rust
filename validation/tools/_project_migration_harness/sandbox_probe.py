from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from .sandbox_contract import SandboxContract, canonical_sha256
from .sandbox_requirements import REQUIRED_CAPABILITIES, SandboxRequirements


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_BACKEND = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z", re.ASCII)
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class SandboxProbeReceipt:
    backend: str
    backend_version: str
    contract_sha256: str
    requirements_sha256: str
    probe_plan_sha256: str
    raw_observation_sha256: str
    capability_results: tuple[tuple[str, bool], ...]
    cleanup_verified: bool

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or _BACKEND.fullmatch(self.backend) is None:
            raise ValueError("sandbox probe backend identity is invalid")
        if (
            not isinstance(self.backend_version, str)
            or _VERSION.fullmatch(self.backend_version) is None
        ):
            raise ValueError("sandbox probe backend version is invalid")
        for value, label in (
            (self.contract_sha256, "contract_sha256"),
            (self.requirements_sha256, "requirements_sha256"),
            (self.probe_plan_sha256, "probe_plan_sha256"),
            (self.raw_observation_sha256, "raw_observation_sha256"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise ValueError(f"sandbox probe {label} is invalid")
        expected_names = tuple(REQUIRED_CAPABILITIES)
        if (
            type(self.capability_results) is not tuple
            or tuple(name for name, _ in self.capability_results) != expected_names
            or any(type(value) is not bool for _, value in self.capability_results)
        ):
            raise ValueError("sandbox probe capability results are invalid")
        if type(self.cleanup_verified) is not bool:
            raise ValueError("sandbox probe cleanup result is invalid")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "contract_sha256": self.contract_sha256,
            "requirements_sha256": self.requirements_sha256,
            "probe_plan_sha256": self.probe_plan_sha256,
            "raw_observation_sha256": self.raw_observation_sha256,
            "capability_results": dict(self.capability_results),
            "cleanup_verified": self.cleanup_verified,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.payload())


def probe_plan_sha256(
    contract: SandboxContract, requirements: SandboxRequirements,
) -> str:
    return canonical_sha256({
        "schema_version": 1,
        "probe_kind": "strict-sandbox-capability-probe-v1",
        "contract_sha256": contract.sha256,
        "requirements_sha256": requirements.sha256,
        "required_capabilities": list(requirements.capabilities),
    })


def make_probe_receipt(
    *, contract: SandboxContract, backend_version: str,
    capability_results: Mapping[str, bool], raw_observation: Mapping[str, Any],
    cleanup_verified: bool,
) -> SandboxProbeReceipt:
    if set(capability_results) != set(REQUIRED_CAPABILITIES):
        raise ValueError("sandbox probe capability results set is invalid")
    ordered = tuple(
        (name, capability_results.get(name)) for name in REQUIRED_CAPABILITIES
    )
    return SandboxProbeReceipt(
        backend=contract.backend,
        backend_version=backend_version,
        contract_sha256=contract.sha256,
        requirements_sha256=contract.requirements.sha256,
        probe_plan_sha256=probe_plan_sha256(
            contract, contract.requirements,
        ),
        raw_observation_sha256=canonical_sha256(dict(raw_observation)),
        capability_results=ordered,
        cleanup_verified=cleanup_verified,
    )


def validate_probe_receipt(
    receipt: SandboxProbeReceipt, contract: SandboxContract,
    requirements: SandboxRequirements,
) -> None:
    if not isinstance(receipt, SandboxProbeReceipt):
        raise ValueError("sandbox probe receipt type is invalid")
    if (
        receipt.backend != contract.backend
        or receipt.contract_sha256 != contract.sha256
        or requirements != contract.requirements
        or receipt.requirements_sha256 != requirements.sha256
        or receipt.probe_plan_sha256 != probe_plan_sha256(contract, requirements)
        or not receipt.cleanup_verified
        or any(value is not True for _, value in receipt.capability_results)
    ):
        raise ValueError("sandbox capability probe did not satisfy the strict plan")


def probe_receipt_from_payload(value: Any) -> SandboxProbeReceipt:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "backend", "backend_version", "contract_sha256",
        "requirements_sha256", "probe_plan_sha256", "raw_observation_sha256",
        "capability_results", "cleanup_verified",
    } or value.get("schema_version") != 1:
        raise ValueError("sandbox probe receipt schema is invalid")
    results = value.get("capability_results")
    if not isinstance(results, Mapping) or set(results) != set(REQUIRED_CAPABILITIES):
        raise ValueError("sandbox probe receipt capability schema is invalid")
    receipt = SandboxProbeReceipt(
        backend=value.get("backend"),
        backend_version=value.get("backend_version"),
        contract_sha256=value.get("contract_sha256"),
        requirements_sha256=value.get("requirements_sha256"),
        probe_plan_sha256=value.get("probe_plan_sha256"),
        raw_observation_sha256=value.get("raw_observation_sha256"),
        capability_results=tuple(
            (name, results.get(name)) for name in REQUIRED_CAPABILITIES
        ),
        cleanup_verified=value.get("cleanup_verified"),
    )
    if receipt.payload() != dict(value):
        raise ValueError("sandbox probe receipt is not canonical")
    return receipt


__all__ = [
    "SandboxProbeReceipt", "make_probe_receipt", "probe_plan_sha256",
    "probe_receipt_from_payload", "validate_probe_receipt",
]
