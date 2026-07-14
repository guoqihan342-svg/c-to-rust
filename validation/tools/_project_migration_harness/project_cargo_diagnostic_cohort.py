from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from .project_cargo_diagnostic_intake import CargoDiagnosticPartition


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GATES = ("cargo-check", "cargo-test")


@dataclass(frozen=True, slots=True)
class CargoDiagnosticCohortDecision:
    status: str
    blocker_code: str | None

    @property
    def admits_repairs(self) -> bool:
        return self.status == "admitted"

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "blocker_code": self.blocker_code,
            "scope": "whole-candidate-cohort",
        }


def decide_cargo_diagnostic_cohort(
    *, execution_status: Any,
    checks: Mapping[str, Mapping[str, Any]],
    observations: Mapping[str, Mapping[str, Any]],
    partitions: Mapping[str, CargoDiagnosticPartition],
    candidate_members: Sequence[Mapping[str, Any]],
) -> CargoDiagnosticCohortDecision:
    if execution_status == "blocked":
        return _blocked("cargo-execution-blocked")
    if execution_status not in {"passed", "failed"}:
        return _blocked("cargo-execution-status-invalid")
    check = checks.get("cargo-check")
    test = checks.get("cargo-test")
    if check is None:
        return _blocked("cargo-check-missing")
    check_status = check.get("status")
    if check_status == "passed" and test is None:
        return _blocked("cargo-test-missing")
    if check_status != "passed" and test is not None:
        return _blocked("cargo-gate-order-invalid")
    present = {
        gate: item for gate, item in (("cargo-check", check), ("cargo-test", test))
        if item is not None
    }
    for gate, item in present.items():
        if observations.get(gate, {}).get("outcome") != "executed":
            return _blocked("cargo-observation-blocked")
        status = item.get("status")
        if status not in {"passed", "failed"}:
            return _blocked("cargo-check-status-invalid")
        diagnostics = item.get("diagnostics")
        if not isinstance(diagnostics, list):
            return _blocked("cargo-diagnostic-set-invalid")
        if status == "passed" and diagnostics:
            return _blocked("cargo-pass-has-error-diagnostics")
    failed_gates = [gate for gate, item in present.items() if item["status"] == "failed"]
    derived_status = "failed" if failed_gates else "passed"
    if execution_status != derived_status:
        return _blocked("cargo-execution-status-drift")
    if not failed_gates:
        return CargoDiagnosticCohortDecision("not-applicable", None)
    owner_blocker = _candidate_owner_blocker(candidate_members)
    if owner_blocker is not None:
        return _blocked(owner_blocker)
    for gate in _GATES:
        if gate not in failed_gates:
            continue
        partition = partitions.get(gate)
        if partition is None:
            return _blocked("cargo-partition-missing")
        if partition.admission_blocker is not None:
            return _blocked(partition.admission_blocker)
        if not partition.unit_diagnostics and not partition.project_diagnostics:
            return _blocked("cargo-failure-unclassified")
    return CargoDiagnosticCohortDecision("admitted", None)


def _candidate_owner_blocker(
    members: Sequence[Mapping[str, Any]],
) -> str | None:
    identities: set[tuple[str, str]] = set()
    digests: set[str] = set()
    if not members:
        return "candidate-cohort-empty"
    for member in members:
        unit_id = member.get("unit_id")
        artifact_id = member.get("artifact_id")
        digest = member.get("content_sha256")
        if (
            not isinstance(unit_id, str) or not unit_id
            or not isinstance(artifact_id, str) or not artifact_id
            or not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
        ):
            return "candidate-owner-invalid"
        identity = (unit_id, artifact_id)
        if identity in identities:
            return "candidate-identity-not-unique"
        if digest in digests:
            return "candidate-content-not-unique"
        identities.add(identity)
        digests.add(digest)
    return None


def _blocked(code: str) -> CargoDiagnosticCohortDecision:
    return CargoDiagnosticCohortDecision("blocked", code)


__all__ = ["CargoDiagnosticCohortDecision", "decide_cargo_diagnostic_cohort"]
