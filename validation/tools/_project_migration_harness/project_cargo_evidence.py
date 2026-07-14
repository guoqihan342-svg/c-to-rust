from __future__ import annotations

from collections.abc import Mapping
import re
from pathlib import Path
from typing import Any

from .cargo_raw_output_evidence import verify_cargo_check_raw_outputs
from .ledger_security import LedgerError
from .project_cargo_classification_receipt import (
    require_cargo_classification_reference,
    verify_cargo_classification_receipt,
)
from .sandbox_execution_schema import (
    CHECK_EVIDENCE_KEYS,
    SANDBOX_EVIDENCE_KEYS,
    is_sha256,
    validate_sandbox_execution_evidence,
)


LEGACY_CARGO_OBSERVATION_KEYS = frozenset({
    "outcome", "project_input_sha256", "project_state_unchanged",
    "blocker_code", "sandbox", "check",
})
V2_CARGO_OBSERVATION_KEYS = LEGACY_CARGO_OBSERVATION_KEYS | {"schema_version"}
CARGO_OBSERVATION_KEYS = V2_CARGO_OBSERVATION_KEYS | {"classification_receipt"}
CARGO_COMMANDS = {
    "cargo-check": [
        "cargo", "check", "--all-targets", "--all-features", "--offline", "--locked",
        "--message-format=json",
    ],
    "cargo-test": [
        "cargo", "test", "--all-targets", "--all-features", "--offline", "--locked",
        "--message-format=json",
    ],
}
_PORTABLE_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z", re.ASCII)


def project_cargo_observation(
    execution: Any,
    check: Any,
    *,
    gate_kind: str,
    expected_input_sha256: str | None,
) -> dict[str, Any]:
    command = _command(gate_kind)
    unchanged = (
        isinstance(execution, Mapping)
        and execution.get("project_state_unchanged") is True
    )
    if not is_sha256(expected_input_sha256):
        return _blocked_observation(
            None, unchanged, "managed_project_input_unavailable",
        )
    if not isinstance(execution, Mapping) or not isinstance(check, Mapping):
        return _blocked_observation(
            expected_input_sha256, unchanged, _blocker_code(execution),
        )
    sandbox = execution.get("sandbox")
    detached_sandbox = (
        {key: sandbox.get(key) for key in sorted(SANDBOX_EVIDENCE_KEYS)}
        if isinstance(sandbox, Mapping) else None
    )
    detached_check = {
        key: check.get(key) for key in sorted(CHECK_EVIDENCE_KEYS)
    }
    try:
        validate_sandbox_execution_evidence(
            detached_sandbox,
            detached_check,
            expected_command=command,
            expected_input_sha256=expected_input_sha256,
            expected_purpose=gate_kind,
            require_raw_output=True,
        )
    except (TypeError, ValueError):
        return _blocked_observation(
            expected_input_sha256, unchanged,
            "sandbox_execution_evidence_invalid",
        )
    if (
        execution.get("project_input_sha256", execution.get("project_state_before"))
        != expected_input_sha256
        or execution.get("project_state_before") != expected_input_sha256
        or execution.get("project_state_after") != expected_input_sha256
    ):
        unchanged = False
    return {
        "schema_version": 2,
        "outcome": "executed",
        "project_input_sha256": expected_input_sha256,
        "project_state_unchanged": unchanged,
        "blocker_code": None,
        "sandbox": detached_sandbox,
        "check": detached_check,
    }


def derive_project_cargo_status(
    gate_kind: str, observation: Mapping[str, Any],
) -> str:
    fields = frozenset(observation)
    v2 = (
        fields == V2_CARGO_OBSERVATION_KEYS
        and observation.get("schema_version") == 2
    )
    v3 = (
        fields == CARGO_OBSERVATION_KEYS
        and observation.get("schema_version") == 3
    )
    legacy = fields == LEGACY_CARGO_OBSERVATION_KEYS
    if not v2 and not v3 and not legacy:
        raise LedgerError("project Cargo observation schema is invalid")
    if v3:
        try:
            require_cargo_classification_reference(
                observation.get("classification_receipt"),
            )
        except (TypeError, ValueError, LedgerError) as error:
            raise LedgerError(
                "project Cargo classification reference is invalid"
            ) from error
    outcome = observation.get("outcome")
    blocker = observation.get("blocker_code")
    if outcome == "blocked":
        if (
            blocker is None
            or not isinstance(blocker, str)
            or _PORTABLE_CODE.fullmatch(blocker) is None
            or observation.get("sandbox") is not None
            or observation.get("check") is not None
            or (
                observation.get("project_input_sha256") is not None
                and not is_sha256(observation.get("project_input_sha256"))
            )
            or type(observation.get("project_state_unchanged")) is not bool
        ):
            raise LedgerError("project Cargo blocker observation is invalid")
        return "failed"
    if outcome != "executed" or blocker is not None:
        raise LedgerError("project Cargo execution outcome is invalid")
    expected_input = observation.get("project_input_sha256")
    if not is_sha256(expected_input):
        raise LedgerError("project Cargo input binding is invalid")
    try:
        verified = validate_sandbox_execution_evidence(
            observation.get("sandbox"),
            observation.get("check"),
            expected_command=_command(gate_kind),
            expected_input_sha256=expected_input,
            expected_purpose=gate_kind,
            require_raw_output=v2 or v3,
        )
    except (TypeError, ValueError) as error:
        raise LedgerError("project Cargo sandbox evidence is invalid") from error
    if observation.get("project_state_unchanged") is not True:
        return "failed"
    return verified.status


def _blocked_observation(
    input_sha256: str | None, unchanged: bool, blocker_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "outcome": "blocked",
        "project_input_sha256": input_sha256,
        "project_state_unchanged": unchanged,
        "blocker_code": (
            blocker_code if _PORTABLE_CODE.fullmatch(blocker_code)
            else "sandbox_execution_blocked"
        ),
        "sandbox": None,
        "check": None,
    }


def blocked_project_cargo_observation(
    project_input_sha256: str | None, *, unchanged: bool, blocker_code: str,
) -> dict[str, Any]:
    return _blocked_observation(
        project_input_sha256, unchanged, blocker_code,
    )


def _blocker_code(execution: Any) -> str:
    if isinstance(execution, Mapping):
        sandbox = execution.get("sandbox")
        reason = sandbox.get("reason_code") if isinstance(sandbox, Mapping) else None
        if isinstance(reason, str) and _PORTABLE_CODE.fullmatch(reason):
            return reason
        diagnostics = execution.get("diagnostics")
        if isinstance(diagnostics, list):
            for item in diagnostics:
                code = item.get("code") if isinstance(item, Mapping) else None
                if isinstance(code, str) and _PORTABLE_CODE.fullmatch(code):
                    return code
    return "cargo_gate_not_executed"


def _command(gate_kind: str) -> list[str]:
    command = CARGO_COMMANDS.get(gate_kind)
    if command is None:
        raise LedgerError("project Cargo gate kind is invalid")
    return list(command)


def is_project_cargo_observation_fields(value: Mapping[str, Any]) -> bool:
    fields = frozenset(value)
    legacy = fields == LEGACY_CARGO_OBSERVATION_KEYS
    v2 = fields == V2_CARGO_OBSERVATION_KEYS \
        and value.get("schema_version") == 2
    v3 = fields == CARGO_OBSERVATION_KEYS \
        and value.get("schema_version") == 3
    return legacy or v2 or v3


def verify_project_cargo_raw_outputs(
    ledger_path: Path, observation: Mapping[str, Any], *, gate_kind: str,
) -> None:
    fields = frozenset(observation)
    v2 = fields == V2_CARGO_OBSERVATION_KEYS \
        and observation.get("schema_version") == 2
    v3 = fields == CARGO_OBSERVATION_KEYS \
        and observation.get("schema_version") == 3
    versioned = v2 or v3
    if not versioned or observation.get("outcome") != "executed":
        return
    check = observation.get("check")
    if not isinstance(check, Mapping):
        raise LedgerError("project Cargo raw output check is missing")
    verify_cargo_check_raw_outputs(ledger_path, check, gate_kind=gate_kind)


def bind_project_cargo_classification(
    observation: Mapping[str, Any], reference: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        frozenset(observation) != V2_CARGO_OBSERVATION_KEYS
        or observation.get("schema_version") != 2
    ):
        raise ValueError("Cargo classification requires a v2 observation")
    require_cargo_classification_reference(reference)
    return {
        **dict(observation), "schema_version": 3,
        "classification_receipt": dict(reference),
    }


def verify_project_cargo_classification(
    ledger_path: Path, observation: Mapping[str, Any], *,
    run_id: str, candidate_set_sha256: str, gate_kind: str,
    rust_project_ir_sha256: str | None = None,
    rust_project_interface_sha256: str | None = None,
) -> dict[str, Any] | None:
    if (
        frozenset(observation) != CARGO_OBSERVATION_KEYS
        or observation.get("schema_version") != 3
    ):
        return None
    project_input = observation.get("project_input_sha256")
    if not is_sha256(project_input):
        raise LedgerError("Cargo classification project input is invalid")
    return verify_cargo_classification_receipt(
        ledger_path, observation.get("classification_receipt"),
        run_id=run_id, candidate_set_sha256=candidate_set_sha256,
        project_input_sha256=str(project_input), observation=observation,
        gate_kind=gate_kind,
        rust_project_ir_sha256=rust_project_ir_sha256,
        rust_project_interface_sha256=rust_project_interface_sha256,
    )


__all__ = [
    "CARGO_COMMANDS", "CARGO_OBSERVATION_KEYS",
    "bind_project_cargo_classification", "blocked_project_cargo_observation",
    "derive_project_cargo_status", "project_cargo_observation",
    "is_project_cargo_observation_fields",
    "verify_project_cargo_raw_outputs",
    "verify_project_cargo_classification",
]
