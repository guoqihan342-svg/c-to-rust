from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .gate_evidence import require_content_addressed_reference
from .ledger_security import LedgerError
from .project_cargo_evidence import (
    CARGO_OBSERVATION_KEYS, derive_project_cargo_status,
    is_project_cargo_observation_fields,
)


CANDIDATE_REQUIRED_GATES = frozenset({
    "compile",
    "oracle-replay-diff",
    "negative",
    "unsafe-alias",
    "abi-layout",
})
CANDIDATE_GATE_FAMILIES = CANDIDATE_REQUIRED_GATES | {"final-verification"}
PROJECT_GATE_KINDS = frozenset({
    "integration",
    "cargo-check",
    "cargo-test",
    "oracle-replay",
    "negative",
    "unsafe-alias-abi",
    "final-verification",
})

_PORTABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id", "unit_id",
    "candidate_artifact_id", "candidate_sha256", "gate_family", "status",
    "candidate_set_sha256", "source_evidence", "diagnostics",
    "expected_actual_withheld", "semantic_gate",
}
_PROJECT_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id", "gate_kind",
    "status", "candidate_set_sha256", "source_evidence", "diagnostic_codes",
    "expected_actual_withheld", "semantic_gate",
}
_OBSERVATION_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id", "gate_kind",
    "candidate_set_sha256", "observation",
}
_OBSERVATION_FIELDS = {
    "integration": {
        "managed_project_unchanged", "candidate_count", "manifest_sha256",
        "project_sha256", "interface_complete",
    },
    "cargo-check": CARGO_OBSERVATION_KEYS,
    "cargo-test": CARGO_OBSERVATION_KEYS,
    "oracle-replay": {
        "case_count", "mismatch_count", "crash_count", "oracle_sha256",
        "candidate_sha256",
    },
    "negative": {"case_count", "unexpected_accept_count"},
    "unsafe-alias-abi": {"check_count", "violation_count"},
}


def require_portable_id(value: str, field: str) -> str:
    if not isinstance(value, str) or _PORTABLE_ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a portable identifier")
    return value


def candidate_authority(gate_family: str) -> str:
    if gate_family not in CANDIDATE_GATE_FAMILIES:
        raise ValueError("candidate gate family is invalid")
    return f"host.candidate.{gate_family}.v1"


def candidate_kind(gate_family: str) -> str:
    return "gate" if gate_family == "final-verification" else "verifier"


def project_authority(gate_kind: str) -> str:
    if gate_kind not in PROJECT_GATE_KINDS:
        raise ValueError("project gate kind is invalid")
    return f"host.project.{gate_kind}.v1"


def candidate_verdict_payload(
    *, run_id: str, unit_id: str, candidate_artifact_id: str,
    candidate_sha256: str, gate_family: str, status: str,
    diagnostics: Sequence[Mapping[str, Any]],
    candidate_set_sha256: str | None = None,
    source_evidence: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    if status not in {"passed", "failed"}:
        raise ValueError("candidate verdict status is invalid")
    if _SHA256.fullmatch(candidate_sha256) is None:
        raise ValueError("candidate_sha256 is invalid")
    if len(diagnostics) > 64:
        raise ValueError("candidate verdict diagnostics exceed the bound")
    if candidate_set_sha256 is not None and _SHA256.fullmatch(candidate_set_sha256) is None:
        raise ValueError("candidate_set_sha256 is invalid")
    references = _candidate_references(source_evidence)
    if status == "passed" and (candidate_set_sha256 is None or not references):
        raise ValueError("candidate pass requires a verification candidate set and source evidence")
    return {
        "schema_version": 2,
        "artifact_kind": "candidate-gate-verdict",
        "authority_id": candidate_authority(gate_family),
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_sha256": candidate_sha256,
        "candidate_set_sha256": candidate_set_sha256,
        "gate_family": gate_family,
        "status": status,
        "source_evidence": references,
        "diagnostics": [dict(item) for item in diagnostics],
        "expected_actual_withheld": True,
        "semantic_gate": False,
    }


def validate_candidate_verdict(
    payload: Mapping[str, Any], *, run_id: str, unit_id: str,
    candidate_artifact_id: str, candidate_sha256: str, gate_family: str,
    candidate_set_sha256: str | None, status: str, verifier_id: str, kind: str,
) -> None:
    _require_exact_keys(payload, _CANDIDATE_KEYS, "candidate gate verdict")
    expected = candidate_verdict_payload(
        run_id=run_id,
        unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=candidate_sha256,
        gate_family=gate_family,
        status=status,
        diagnostics=_diagnostics(payload.get("diagnostics")),
        candidate_set_sha256=candidate_set_sha256,
        source_evidence=_candidate_references(payload.get("source_evidence")),
    )
    if dict(payload) != expected:
        raise LedgerError("candidate gate evidence does not match the fixed host schema")
    if verifier_id != candidate_authority(gate_family) or kind != candidate_kind(gate_family):
        raise LedgerError("candidate gate authority or kind is not host-owned")


def project_summary_payload(
    *, run_id: str, gate_kind: str, status: str, candidate_set_sha256: str,
    source_evidence: Sequence[Mapping[str, Any]], diagnostic_codes: Sequence[str] = (),
) -> dict[str, Any]:
    if status not in {"passed", "failed"}:
        raise ValueError("project gate status is invalid")
    if _SHA256.fullmatch(candidate_set_sha256) is None:
        raise ValueError("candidate_set_sha256 is invalid")
    codes = sorted({require_portable_id(code, "diagnostic code") for code in diagnostic_codes})
    return {
        "schema_version": 1,
        "artifact_kind": "project-gate-summary",
        "authority_id": project_authority(gate_kind),
        "run_id": run_id,
        "gate_kind": gate_kind,
        "status": status,
        "candidate_set_sha256": candidate_set_sha256,
        "source_evidence": [dict(item) for item in source_evidence],
        "diagnostic_codes": codes,
        "expected_actual_withheld": True,
        "semantic_gate": False,
    }


def validate_project_summary(
    payload: Mapping[str, Any], *, run_id: str, gate_kind: str, status: str,
    candidate_set_sha256: str, verifier_id: str,
) -> None:
    _require_exact_keys(payload, _PROJECT_KEYS, "project gate summary")
    expected = project_summary_payload(
        run_id=run_id,
        gate_kind=gate_kind,
        status=status,
        candidate_set_sha256=candidate_set_sha256,
        source_evidence=_references(payload.get("source_evidence")),
        diagnostic_codes=_codes(payload.get("diagnostic_codes")),
    )
    if dict(payload) != expected:
        raise LedgerError("project gate evidence does not match the fixed host schema")
    if verifier_id != project_authority(gate_kind):
        raise LedgerError("project gate verifier is not the fixed host authority")


def derive_project_observation(
    payload: Mapping[str, Any], *, run_id: str, gate_kind: str,
    candidate_set_sha256: str,
) -> str:
    if gate_kind == "final-verification":
        raise LedgerError("final verification is derived from current ledger records")
    _require_exact_keys(payload, _OBSERVATION_KEYS, "project gate observation")
    if (
        payload.get("schema_version") != 1
        or payload.get("artifact_kind") != "host-project-gate-observation"
        or payload.get("authority_id") != project_authority(gate_kind)
        or payload.get("run_id") != run_id
        or payload.get("gate_kind") != gate_kind
        or payload.get("candidate_set_sha256") != candidate_set_sha256
    ):
        raise LedgerError("project gate observation is not bound to this host decision")
    observation = payload.get("observation")
    if not isinstance(observation, Mapping):
        raise LedgerError("project gate observation payload is invalid")
    return "passed" if _observation_passed(gate_kind, observation) else "failed"


def _observation_passed(gate_kind: str, value: Mapping[str, Any]) -> bool:
    if gate_kind in {"cargo-check", "cargo-test"}:
        if not is_project_cargo_observation_fields(value):
            raise LedgerError(
                "project gate observation fields are not fixed by the host adapter"
            )
        return derive_project_cargo_status(gate_kind, value) == "passed"
    if set(value) != _OBSERVATION_FIELDS.get(gate_kind):
        raise LedgerError("project gate observation fields are not fixed by the host adapter")
    if gate_kind == "integration":
        return (
            value.get("managed_project_unchanged") is True
            and value.get("interface_complete") is True
            and _positive_int(value.get("candidate_count"))
            and _is_sha(value.get("manifest_sha256"))
            and _is_sha(value.get("project_sha256"))
        )
    if gate_kind == "oracle-replay":
        return (
            _positive_int(value.get("case_count"))
            and value.get("mismatch_count") == 0
            and value.get("crash_count") == 0
            and _is_sha(value.get("oracle_sha256"))
            and _is_sha(value.get("candidate_sha256"))
        )
    if gate_kind == "negative":
        return _positive_int(value.get("case_count")) and value.get("unexpected_accept_count") == 0
    if gate_kind == "unsafe-alias-abi":
        return _positive_int(value.get("check_count")) and value.get("violation_count") == 0
    return False


def _require_exact_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise LedgerError(f"{label} has an invalid schema")


def _diagnostics(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) > 64 or not all(isinstance(item, Mapping) for item in value):
        raise LedgerError("candidate gate diagnostics are invalid")
    return list(value)


def _references(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) > 32 or not all(isinstance(item, Mapping) for item in value):
        raise LedgerError("project gate source evidence is invalid")
    return list(value)


def _candidate_references(value: Any) -> list[dict[str, Any]]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) > 16
    ):
        raise LedgerError("candidate gate source evidence is invalid")
    references = []
    for item in value:
        if not isinstance(item, Mapping):
            raise LedgerError("candidate gate source evidence is invalid")
        require_content_addressed_reference(item)
        references.append(dict(item))
    return references


def _codes(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LedgerError("project gate diagnostic codes are invalid")
    return list(value)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


__all__ = [
    "CANDIDATE_GATE_FAMILIES", "CANDIDATE_REQUIRED_GATES", "PROJECT_GATE_KINDS",
    "candidate_authority", "candidate_kind", "candidate_verdict_payload",
    "derive_project_observation", "project_authority", "project_summary_payload",
    "require_portable_id", "validate_candidate_verdict", "validate_project_summary",
]
