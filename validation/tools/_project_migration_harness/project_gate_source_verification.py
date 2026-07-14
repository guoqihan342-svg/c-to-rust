from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_authority import derive_project_observation
from .gate_evidence import (
    read_content_addressed_json, require_content_addressed_reference,
    require_host_raw_reference,
)
from .ledger_security import LedgerError
from .project_cargo_evidence import (
    verify_project_cargo_classification, verify_project_cargo_raw_outputs,
)


def verify_project_sources(
    ledger: Any, payload: Mapping[str, Any], *, run_id: str, gate_kind: str,
    candidate_set_sha256: str, status: str,
) -> None:
    references = payload["source_evidence"]
    if gate_kind != "final-verification" and len(references) != 1:
        raise LedgerError("non-final project gates require one host raw observation")
    for reference in references:
        require_content_addressed_reference(reference)
        if gate_kind != "final-verification":
            require_host_raw_reference(reference, gate_kind)
        source = read_content_addressed_json(
            ledger.path, str(reference["path"]), str(reference["sha256"]),
        )
        if len(canonical_json_bytes(source)) != int(reference["size_bytes"]):
            raise LedgerError("project gate source evidence size changed")
        if gate_kind == "final-verification":
            continue
        observation = source.get("observation")
        if isinstance(observation, Mapping) and gate_kind in {
            "cargo-check", "cargo-test",
        }:
            verify_project_cargo_raw_outputs(
                ledger.path, observation, gate_kind=gate_kind,
            )
            verify_project_cargo_classification(
                ledger.path, observation, run_id=run_id,
                candidate_set_sha256=candidate_set_sha256,
                gate_kind=gate_kind,
            )
        if derive_project_observation(
            source, run_id=run_id, gate_kind=gate_kind,
            candidate_set_sha256=candidate_set_sha256,
        ) != status:
            raise LedgerError(
                "project gate status does not match its host observation"
            )


__all__ = ["verify_project_sources"]
