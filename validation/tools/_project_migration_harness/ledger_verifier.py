from __future__ import annotations

from typing import Any, Mapping

from .gate_authority import (
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
)
from .ledger_candidate_state import (
    CandidateStateMixin,
    latest_candidate_records as _latest_candidate_records,
)
from .ledger_verification_promotion import promote_last_good
from .ledger_verification_records import record_derived_verification
from .ledger_verification_sources import (
    verify_candidate_sources as _verify_candidate_sources,
)


class HostVerifierMixin(CandidateStateMixin):
    def record_candidate_failure(
        self, *, record_id: str, run_id: str, unit_id: str,
        candidate_artifact_id: str, gate_family: str, evidence_path: str,
        evidence_sha256: str, metadata: Mapping[str, Any] | None = None,
    ) -> int:
        return self._record_derived_verification(
            record_id=record_id,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            kind=candidate_kind(gate_family),
            status="failed",
            verifier_id=candidate_authority(gate_family),
            evidence_path=evidence_path,
            evidence_sha256=evidence_sha256,
            gate_family=gate_family,
            metadata=metadata,
        )

    def _record_derived_verification(
        self, *, record_id: str, run_id: str, unit_id: str,
        candidate_artifact_id: str, kind: str, status: str, verifier_id: str,
        evidence_path: str, evidence_sha256: str, gate_family: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        return record_derived_verification(
            self,
            record_id=record_id,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            kind=kind,
            status=status,
            verifier_id=verifier_id,
            evidence_path=evidence_path,
            evidence_sha256=evidence_sha256,
            gate_family=gate_family,
            metadata=metadata,
        )

    def promote_last_good_from_verification(
        self, *, run_id: str, unit_id: str, candidate_artifact_id: str,
        verifier_record_id: str, gate_record_id: str,
    ) -> None:
        promote_last_good(
            self,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            verifier_record_id=verifier_record_id,
            gate_record_id=gate_record_id,
        )


__all__ = [
    "CANDIDATE_REQUIRED_GATES",
    "HostVerifierMixin",
    "_latest_candidate_records",
    "_verify_candidate_sources",
]
