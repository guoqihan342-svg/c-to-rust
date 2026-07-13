from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .gate_evidence import read_content_addressed_json
from .ledger_security import LedgerError
from .sandbox_execution_schema import is_sha256


def require_cargo_integration_binding(
    ledger: Any, verified: Sequence[tuple[Any, Mapping[str, Any]]],
) -> None:
    summaries = {
        str(row["gate_kind"]): payload for row, payload in verified
    }
    required = {"integration", "cargo-check", "cargo-test"}
    if not required.issubset(summaries):
        return
    integration = _raw_observation(ledger, summaries["integration"])
    expected_input = integration.get("manifest_sha256")
    if not is_sha256(expected_input):
        raise LedgerError("integration gate has no managed project input binding")
    for gate_kind in ("cargo-check", "cargo-test"):
        observation = _raw_observation(ledger, summaries[gate_kind])
        if (
            observation.get("outcome") != "executed"
            or observation.get("project_input_sha256") != expected_input
        ):
            raise LedgerError(
                "project Cargo gate is not bound to the latest integrated generation"
            )


def _raw_observation(
    ledger: Any, summary: Mapping[str, Any],
) -> Mapping[str, Any]:
    references = summary.get("source_evidence")
    if not isinstance(references, list) or len(references) != 1:
        raise LedgerError("project gate has no unique raw observation")
    reference = references[0]
    if not isinstance(reference, Mapping):
        raise LedgerError("project gate raw observation reference is invalid")
    source = read_content_addressed_json(
        ledger.path, str(reference.get("path")), str(reference.get("sha256")),
    )
    observation = source.get("observation") if isinstance(source, Mapping) else None
    if not isinstance(observation, Mapping):
        raise LedgerError("project gate raw observation payload is invalid")
    return observation


__all__ = ["require_cargo_integration_binding"]
