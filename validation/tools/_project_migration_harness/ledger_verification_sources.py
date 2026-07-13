from __future__ import annotations

from typing import Any, Mapping

from .artifacts import canonical_json_bytes
from .candidate_compile_evidence import derive_compile_status, verify_compile_bindings
from .candidate_semantic_evidence import derive_semantic_status
from .gate_authority import CANDIDATE_REQUIRED_GATES
from .gate_evidence import (
    read_content_addressed_json,
    require_candidate_raw_reference,
    require_content_addressed_reference,
)
from .ledger_security import LedgerError


def verify_candidate_sources(
    ledger: Any, connection: Any, payload: Mapping[str, Any], *, status: str,
) -> None:
    references = payload.get("source_evidence")
    if not isinstance(references, list):
        raise LedgerError("candidate gate source evidence is invalid")
    if status == "passed" and not references:
        raise LedgerError("candidate pass requires source evidence")
    family = payload.get("gate_family")
    if family != "final-verification" and references and len(references) != 1:
        raise LedgerError("candidate gate requires one host observation")
    for reference in references:
        require_content_addressed_reference(reference)
        if family != "final-verification":
            require_candidate_raw_reference(reference, str(family))
        source = read_content_addressed_json(
            ledger.path, str(reference["path"]), str(reference["sha256"])
        )
        if len(canonical_json_bytes(source)) != int(reference["size_bytes"]):
            raise LedgerError("candidate gate source evidence size changed")
        if family == "compile":
            actual = derive_compile_status(
                source,
                run_id=str(payload.get("run_id")),
                unit_id=str(payload.get("unit_id")),
                candidate_artifact_id=str(payload.get("candidate_artifact_id")),
                candidate_sha256=str(payload.get("candidate_sha256")),
                candidate_set_sha256=str(payload.get("candidate_set_sha256")),
            )
            if actual != status:
                raise LedgerError(
                    "candidate compile verdict does not match host execution"
                )
            verify_compile_bindings(
                source, ledger_path=ledger.path, connection=connection,
            )
        elif family in CANDIDATE_REQUIRED_GATES:
            actual = derive_semantic_status(
                source,
                run_id=str(payload.get("run_id")),
                unit_id=str(payload.get("unit_id")),
                candidate_artifact_id=str(payload.get("candidate_artifact_id")),
                candidate_sha256=str(payload.get("candidate_sha256")),
                candidate_set_sha256=str(payload.get("candidate_set_sha256")),
                gate_family=str(family),
            )
            if actual != status:
                raise LedgerError(
                    "candidate semantic verdict does not match host execution"
                )


__all__ = ["verify_candidate_sources"]
