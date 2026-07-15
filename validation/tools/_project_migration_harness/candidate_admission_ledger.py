from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .candidate_admission import (
    SEMANTIC_ELIGIBLE_SCOPE,
    candidate_admission_from_manifest,
    candidate_admission_metadata,
)
from .ledger_run_contract import load_migration_contract
from .ledger_security import LedgerError


def require_semantic_candidate_admission(
    ledger: Any, connection: Any, run_id: str, candidate: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        raw = json.loads(str(candidate.get("artifact_metadata_json")))
        actual = candidate_admission_metadata(raw, required=True)
    except (TypeError, json.JSONDecodeError, ValueError) as error:
        raise LedgerError("candidate admission metadata is invalid") from error
    _contract, manifest = load_migration_contract(
        ledger.path, connection, run_id,
    )
    try:
        expected = candidate_admission_from_manifest(manifest)
    except ValueError as error:
        raise LedgerError("candidate admission manifest binding is invalid") from error
    if actual != expected:
        raise LedgerError("candidate admission binding drifted")
    if actual["admission_scope"] != SEMANTIC_ELIGIBLE_SCOPE:
        raise LedgerError("candidate-only artifact has no semantic or promotion authority")
    return actual


__all__ = ["require_semantic_candidate_admission"]
