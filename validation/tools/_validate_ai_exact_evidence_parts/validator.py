from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import EvidenceStore, fail, require_id, sha256_file
from .router import validate_router


def validate_evidence(
    *,
    target_id: str,
    slice_id: str,
    evidence_root: Path,
    require_semantic_pass: bool = False,
) -> dict[str, Any]:
    target_id = require_id(target_id, "target_id")
    slice_id = require_id(slice_id, "slice_id")
    root = Path(evidence_root)
    if root.is_symlink() or not root.is_dir():
        fail("evidence_root_missing", "evidence_root must be an existing non-symlink directory")
    evidence_dir = root / target_id / "auto-translation" / slice_id
    store = EvidenceStore(evidence_dir)
    prefix = f"l3-{slice_id}"

    manifest_path = store.resolve(
        f"{prefix}-auto-translation-manifest.json",
        "auto_manifest",
    )
    manifest = store.read_json(manifest_path, "auto_manifest")
    for key, expected in (("target_id", target_id), ("slice_id", slice_id)):
        if manifest.get(key) != expected:
            fail("manifest_identity_drift", f"auto manifest {key} drift", path="auto_manifest")
    exact_ref = manifest.get("ai_exact_validation")
    router_path, router = store.read_bound_json(exact_ref, "auto_manifest.ai_exact_validation")
    expected_router = store.resolve(f"{prefix}-ai-router.json", "ai_router")
    if router_path != expected_router:
        fail("router_path_drift", "manifest AI exact ref does not name the canonical router", path="auto_manifest")

    result = validate_router(store, router)
    semantic_pass = result["semantic_pass"]
    expected_status = "passed" if semantic_pass else "failed"
    if exact_ref.get("status") != expected_status or exact_ref.get("semantic_pass") is not semantic_pass:
        fail("manifest_exact_status_drift", "manifest AI exact status differs from router", path="auto_manifest")

    canonical = store.resolve(f"{prefix}-rust-draft.rs", "canonical_draft")
    store.checked_artifacts += 1
    canonical_sha = sha256_file(canonical)
    if router.get("canonical_draft_sha256") != canonical_sha:
        fail("canonical_router_drift", "router canonical draft SHA-256 drift", path="router")
    selected_sha = result["selected_candidate_sha256"]
    if selected_sha is not None and canonical_sha != selected_sha:
        fail("canonical_selected_drift", "canonical draft differs from selected candidate", path="router")
    if require_semantic_pass and not semantic_pass:
        fail("semantic_pass_required", "AI exact semantic pass is required", path="router")

    return {
        "schema_version": 1,
        "status": "passed",
        "target_id": target_id,
        "slice_id": slice_id,
        "semantic_pass": semantic_pass,
        "selected_candidate_id": result["selected_candidate_id"],
        "selected_candidate_sha256": selected_sha,
        "canonical_draft_sha256": canonical_sha,
        "candidate_count": result["candidate_count"],
        "router_metrics": result["metrics"],
        "checked_artifacts": store.checked_artifacts,
        "errors": [],
    }
