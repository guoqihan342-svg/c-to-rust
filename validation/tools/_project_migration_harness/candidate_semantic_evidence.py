from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .candidate_semantic_context import (
    current_semantic_context,
    current_semantic_context_bound,
)
from .candidate_semantic_schema import (
    CONTEXT_KEYS,
    derive_strict_semantic_status,
    is_strict_semantic_payload,
)
from .gate_authority import (
    candidate_authority,
    validate_candidate_verdict,
)
from .gate_candidate_sets import candidate_set_manifest
from .gate_evidence import (
    read_content_addressed_json,
    require_candidate_raw_reference,
)
from .ledger_security import LedgerError


SHA256 = re.compile(r"^[0-9a-f]{64}$")
FAMILIES = {
    "oracle-replay-diff": {
        "case_count", "mismatch_count", "crash_count", "c_oracle_sha256",
        "rust_replay_sha256", "diff_sha256", "execution_context_sha256",
    },
    "negative": {
        "case_count", "unexpected_accept_count", "mutation_manifest_sha256",
        "execution_context_sha256",
    },
    "unsafe-alias": {
        "unsafe_site_count", "unproven_alias_count", "unsafe_ledger_sha256",
        "alias_evidence_sha256", "execution_context_sha256",
    },
    "abi-layout": {
        "check_count", "mismatch_count", "c_layout_sha256",
        "rust_layout_sha256", "execution_context_sha256",
    },
}
PAYLOAD_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id", "unit_id",
    "candidate_artifact_id", "candidate_sha256", "candidate_set_sha256",
    "gate_family", "observation",
}


def semantic_observation_payload(
    *, run_id: str, unit_id: str, candidate_artifact_id: str,
    candidate_sha256: str, candidate_set_sha256: str, gate_family: str,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "artifact_kind": "host-candidate-semantic-observation",
        "authority_id": candidate_authority(gate_family),
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_sha256": candidate_sha256,
        "candidate_set_sha256": candidate_set_sha256,
        "gate_family": gate_family,
        "observation": dict(observation),
    }
    derive_semantic_status(
        payload, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=candidate_sha256,
        candidate_set_sha256=candidate_set_sha256,
        gate_family=gate_family,
    )
    return payload


def derive_semantic_status(
    payload: Mapping[str, Any], *, run_id: str, unit_id: str,
    candidate_artifact_id: str, candidate_sha256: str,
    candidate_set_sha256: str, gate_family: str,
) -> str:
    if is_strict_semantic_payload(payload):
        return derive_strict_semantic_status(
            payload,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            candidate_sha256=candidate_sha256,
            candidate_set_sha256=candidate_set_sha256,
            gate_family=gate_family,
        )
    if gate_family not in FAMILIES or not isinstance(payload, Mapping):
        raise LedgerError("candidate semantic observation family is invalid")
    expected = {
        "schema_version": 1,
        "artifact_kind": "host-candidate-semantic-observation",
        "authority_id": candidate_authority(gate_family),
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_sha256": candidate_sha256,
        "candidate_set_sha256": candidate_set_sha256,
        "gate_family": gate_family,
    }
    if set(payload) != PAYLOAD_KEYS or any(payload.get(key) != value for key, value in expected.items()):
        raise LedgerError("candidate semantic observation binding is invalid")
    if not _sha(candidate_sha256) or not _sha(candidate_set_sha256):
        raise LedgerError("candidate semantic observation hash binding is invalid")
    observation = payload.get("observation")
    if not isinstance(observation, Mapping) or set(observation) != FAMILIES[gate_family]:
        raise LedgerError("candidate semantic observation schema is invalid")
    if gate_family == "oracle-replay-diff":
        passed = (
            _positive(observation.get("case_count"))
            and observation.get("mismatch_count") == 0
            and observation.get("crash_count") == 0
            and _hashes(observation, {
                "c_oracle_sha256", "rust_replay_sha256", "diff_sha256",
                "execution_context_sha256",
            })
        )
    elif gate_family == "negative":
        passed = (
            _positive(observation.get("case_count"))
            and observation.get("unexpected_accept_count") == 0
            and _hashes(observation, {
                "mutation_manifest_sha256", "execution_context_sha256",
            })
        )
    elif gate_family == "unsafe-alias":
        passed = (
            _nonnegative(observation.get("unsafe_site_count"))
            and observation.get("unproven_alias_count") == 0
            and _hashes(observation, {
                "unsafe_ledger_sha256", "alias_evidence_sha256",
                "execution_context_sha256",
            })
        )
    else:
        passed = (
            _positive(observation.get("check_count"))
            and observation.get("mismatch_count") == 0
            and _hashes(observation, {
                "c_layout_sha256", "rust_layout_sha256",
                "execution_context_sha256",
            })
        )
    return "passed" if passed else "failed"


def revalidate_candidate_semantic_verdict(
    ledger: Any, verdict: Mapping[str, Any], *, connection: Any | None = None,
) -> bool:
    family = str(verdict.get("gate_family"))
    if family not in FAMILIES:
        return False
    sources = verdict.get("source_evidence")
    if not isinstance(sources, list) or len(sources) != 1:
        raise LedgerError("candidate semantic verdict requires one raw observation")
    reference = sources[0]
    if not isinstance(reference, Mapping):
        raise LedgerError("candidate semantic raw observation reference is invalid")
    require_candidate_raw_reference(reference, family)
    raw = read_content_addressed_json(
        ledger.path, str(reference["path"]), str(reference["sha256"]),
    )
    if not is_strict_semantic_payload(raw):
        return False
    status = derive_semantic_status(
        raw, run_id=str(raw["run_id"]), unit_id=str(raw["unit_id"]),
        candidate_artifact_id=str(raw["candidate_artifact_id"]),
        candidate_sha256=str(raw["candidate_sha256"]),
        candidate_set_sha256=str(raw["candidate_set_sha256"]),
        gate_family=family,
    )
    validate_candidate_verdict(
        verdict,
        run_id=str(raw["run_id"]), unit_id=str(raw["unit_id"]),
        candidate_artifact_id=str(raw["candidate_artifact_id"]),
        candidate_sha256=str(raw["candidate_sha256"]), gate_family=family,
        candidate_set_sha256=str(raw["candidate_set_sha256"]),
        status=status, verifier_id=candidate_authority(family), kind="verifier",
    )
    if connection is None:
        with ledger.connect() as owned_connection:
            current = _bound_current_context(ledger, owned_connection, raw)
    else:
        current = _bound_current_context(ledger, connection, raw)
    if any(raw.get(key) != current[key] for key in CONTEXT_KEYS):
        raise LedgerError("candidate semantic verification context is stale")
    return True


def _bound_current_context(
    ledger: Any, connection: Any, raw: Mapping[str, Any],
) -> dict[str, Any]:
    run_id = str(raw["run_id"])
    candidate_set = str(raw["candidate_set_sha256"])
    manifest = candidate_set_manifest(connection, run_id, candidate_set)
    current, _root = current_semantic_context_bound(
        ledger, connection, run_id, str(raw["unit_id"]),
        str(raw["candidate_artifact_id"]), candidate_set,
        str(manifest["scope"]),
    )
    return current


def _hashes(value: Mapping[str, Any], keys: set[str]) -> bool:
    return all(_sha(value.get(key)) for key in keys)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _positive(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


__all__ = [
    "current_semantic_context", "derive_semantic_status",
    "revalidate_candidate_semantic_verdict", "semantic_observation_payload",
]
