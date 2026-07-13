from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .accepted_candidates import accepted_candidate_descriptors
from .artifacts import content_sha256, write_json_artifact
from .integration import integrate_candidates
from .ledger import ProjectLedger


def integrate_verified_project(
    migration_manifest: Mapping[str, Any], *, ledger: ProjectLedger,
    run_id: str, candidate_root: Path, candidate_root_rel: str,
    project_root: Path,
) -> dict[str, Any]:
    descriptors = accepted_candidate_descriptors(
        ledger, run_id=run_id, out_root_rel=candidate_root_rel
    )
    result = integrate_candidates(
        migration_manifest,
        descriptors,
        candidate_root,
        project_root,
    )
    candidate_set_sha256 = ledger.bind_current_candidate_set(run_id=run_id)
    report = {
        **result,
        "run_id": run_id,
        "candidate_set_sha256": candidate_set_sha256,
        "candidate_descriptor_sha256": content_sha256(descriptors),
        "candidate_count": len(descriptors),
        "semantic_gate": False,
        "proof_boundary": "deterministic Cargo reconstruction only; project gates not yet run",
    }
    write_json_artifact(candidate_root, "integration/latest-integration.json", report)
    return report


__all__ = ["integrate_verified_project"]
