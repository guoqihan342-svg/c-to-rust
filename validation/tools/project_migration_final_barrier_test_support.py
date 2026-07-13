from __future__ import annotations

from typing import Any

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.gate_authority import (
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    candidate_verdict_payload,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)


def record_project_final_candidate_bundle(case: Any) -> str:
    candidate_set = case.ledger.bind_verification_candidate_set(
        run_id="run", scope="project-final",
    )
    references = []
    ordered = ["compile", *sorted(CANDIDATE_REQUIRED_GATES - {"compile"})]
    for family in ordered:
        payload = candidate_verdict_payload(
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=case.candidate_id,
            candidate_sha256=case.candidate_sha,
            gate_family=family,
            status="passed",
            diagnostics=[],
            candidate_set_sha256=candidate_set,
            source_evidence=case.candidate_sources(
                family, "passed", candidate_set, "project-final",
            ),
        )
        reference = write_content_addressed_json(
            case.out_root, f"candidate/project-final/{family}", payload,
        )
        full_path = f"target/run/{reference['path']}"
        case.ledger._record_derived_verification(
            record_id=f"project-final-{family}",
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=case.candidate_id,
            kind=candidate_kind(family),
            status="passed",
            verifier_id=candidate_authority(family),
            evidence_path=full_path,
            evidence_sha256=str(reference["sha256"]),
            gate_family=family,
            metadata={"candidate_set_sha256": candidate_set},
        )
        references.append({
            "path": full_path,
            "sha256": str(reference["sha256"]),
            "size_bytes": len(canonical_json_bytes(payload)),
        })
    final = candidate_verdict_payload(
        run_id="run",
        unit_id="unit",
        candidate_artifact_id=case.candidate_id,
        candidate_sha256=case.candidate_sha,
        gate_family="final-verification",
        status="passed",
        diagnostics=[],
        candidate_set_sha256=candidate_set,
        source_evidence=references,
    )
    reference = write_content_addressed_json(
        case.out_root, "candidate/project-final/final-verification", final,
    )
    case.ledger._record_derived_verification(
        record_id="project-final-final-verification",
        run_id="run",
        unit_id="unit",
        candidate_artifact_id=case.candidate_id,
        kind=candidate_kind("final-verification"),
        status="passed",
        verifier_id=candidate_authority("final-verification"),
        evidence_path=f"target/run/{reference['path']}",
        evidence_sha256=str(reference["sha256"]),
        gate_family="final-verification",
        metadata={"candidate_set_sha256": candidate_set},
    )
    return candidate_set


__all__ = ["record_project_final_candidate_bundle"]
