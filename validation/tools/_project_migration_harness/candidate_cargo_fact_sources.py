from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .cargo_fact_commands import CARGO_METADATA_COMMAND
from .cargo_raw_output_evidence import (
    read_cargo_raw_output,
    validate_cargo_raw_output_reference,
    verify_cargo_check_raw_outputs,
)
from .project_cargo_evidence import CARGO_COMMANDS
from .sandbox_execution_schema import (
    CHECK_EVIDENCE_KEYS,
    SANDBOX_EVIDENCE_KEYS,
    validate_sandbox_execution_evidence,
)


def captured_candidate_cargo_fact_sources(
    execution: Mapping[str, Any],
) -> dict[str, bytes]:
    return {
        "cargo_metadata": _captured_stdout(
            _metadata_check(execution, require_raw_output=False)
        ),
        "compiler_artifacts": _captured_stdout(_compiler_check(execution)),
    }


def candidate_cargo_fact_source_references(
    execution: Mapping[str, Any], observations: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    checks = candidate_cargo_fact_source_checks(execution, observations)
    return {
        "cargo_metadata": _raw_reference(checks["cargo_metadata"], "cargo-metadata"),
        "compiler_artifacts": _raw_reference(
            checks["compiler_artifacts"], "cargo-check",
        ),
    }


def candidate_cargo_fact_source_checks(
    execution: Mapping[str, Any], observations: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    metadata = _metadata_check(execution, require_raw_output=True)
    cargo = observations.get("cargo-check")
    compiler = cargo.get("check") if isinstance(cargo, Mapping) else None
    sandbox = execution.get("sandbox")
    detached_sandbox = (
        {key: sandbox.get(key) for key in SANDBOX_EVIDENCE_KEYS}
        if isinstance(sandbox, Mapping) else None
    )
    execution_compiler = _compiler_check(execution)
    detached_compiler = {
        key: execution_compiler.get(key) for key in CHECK_EVIDENCE_KEYS
    }
    if (
        not isinstance(cargo, Mapping)
        or not isinstance(compiler, Mapping)
        or compiler.get("command") != CARGO_COMMANDS["cargo-check"]
        or compiler.get("status") != "passed"
        or compiler.get("returncode") != 0
        or compiler.get("cargo_executed") is not True
        or cargo.get("project_input_sha256") != execution.get(
            "project_input_sha256"
        )
        or cargo.get("sandbox") != detached_sandbox
        or dict(compiler) != detached_compiler
    ):
        raise ValueError("candidate_compiler_artifact_source_missing")
    return {"cargo_metadata": metadata, "compiler_artifacts": compiler}


def read_candidate_cargo_fact_sources(
    ledger_path: Path, execution: Mapping[str, Any], observations: Mapping[str, Any],
) -> dict[str, bytes]:
    checks = candidate_cargo_fact_source_checks(execution, observations)
    verify_cargo_check_raw_outputs(
        ledger_path, checks["cargo_metadata"], gate_kind="cargo-metadata",
    )
    verify_cargo_check_raw_outputs(
        ledger_path, checks["compiler_artifacts"], gate_kind="cargo-check",
    )
    return {
        "cargo_metadata": _read_source(
            ledger_path, checks["cargo_metadata"], "cargo-metadata",
        ),
        "compiler_artifacts": _read_source(
            ledger_path, checks["compiler_artifacts"], "cargo-check",
        ),
    }


def _metadata_check(
    execution: Mapping[str, Any], *, require_raw_output: bool,
) -> Mapping[str, Any]:
    probes = execution.get("fact_probes")
    check = probes.get("cargo-metadata") if isinstance(probes, Mapping) else None
    if (
        not isinstance(probes, Mapping) or set(probes) != {"cargo-metadata"}
        or not isinstance(check, Mapping)
        or check.get("command") != list(CARGO_METADATA_COMMAND)
    ):
        raise ValueError("candidate_cargo_metadata_source_missing")
    sandbox = execution.get("sandbox")
    detached_sandbox = (
        {key: sandbox.get(key) for key in SANDBOX_EVIDENCE_KEYS}
        if isinstance(sandbox, Mapping) else None
    )
    detached_check = {key: check.get(key) for key in CHECK_EVIDENCE_KEYS}
    validated = validate_sandbox_execution_evidence(
        detached_sandbox, detached_check,
        expected_command=CARGO_METADATA_COMMAND,
        expected_input_sha256=str(execution.get("project_input_sha256")),
        expected_purpose="cargo-metadata",
        require_raw_output=require_raw_output,
    )
    if validated.status != "passed":
        raise ValueError("candidate_cargo_metadata_source_failed")
    return check


def _compiler_check(execution: Mapping[str, Any]) -> Mapping[str, Any]:
    checks = execution.get("checks")
    if not isinstance(checks, list) or len(checks) != 2 or not all(
        isinstance(item, Mapping) for item in checks
    ):
        raise ValueError("candidate_compiler_artifact_source_missing")
    test_commands = (
        CARGO_COMMANDS["cargo-test"],
        [*CARGO_COMMANDS["cargo-test"], "--jobs", "1"],
    )
    if (
        checks[0].get("command") != CARGO_COMMANDS["cargo-check"]
        or checks[1].get("command") not in test_commands
    ):
        raise ValueError("candidate_compiler_artifact_source_missing")
    return checks[0]


def _captured_stdout(check: Mapping[str, Any]) -> bytes:
    data = check.get("_captured_stdout")
    if (
        check.get("status") != "passed" or check.get("cargo_executed") is not True
        or type(data) is not bytes
        or hashlib.sha256(data).hexdigest() != check.get("stdout_sha256")
    ):
        raise ValueError("candidate_cargo_fact_source_capture_invalid")
    return data


def _raw_reference(check: Mapping[str, Any], gate: str) -> dict[str, Any]:
    return validate_cargo_raw_output_reference(
        check.get("stdout_ref"), gate_kind=gate, stream="stdout",
        expected_sha256=str(check.get("stdout_sha256")),
    )


def _read_source(
    ledger_path: Path, check: Mapping[str, Any], gate: str,
) -> bytes:
    return read_cargo_raw_output(
        ledger_path, check.get("stdout_ref"), gate_kind=gate, stream="stdout",
        expected_sha256=str(check.get("stdout_sha256")),
    )


__all__ = [
    "candidate_cargo_fact_source_checks",
    "candidate_cargo_fact_source_references",
    "captured_candidate_cargo_fact_sources",
    "read_candidate_cargo_fact_sources",
]
