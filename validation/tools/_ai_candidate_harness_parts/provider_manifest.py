from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import atomic_write_bytes, atomic_write_json, sha256_path
from .context_scope import prompt_scope_for_context
from .model_identity import resolve_model_identity
from .prompt_transport import prompt_transport_contract


@dataclass(frozen=True)
class CandidateArtifactPaths:
    context: Path
    prompt: Path
    response: Path
    invocation_receipt: Path
    session_identity: Path
    candidate: Path
    cache_entry: Path
    manifest: Path

    @classmethod
    def for_slice(cls, out_dir: Path, slice_id: str) -> CandidateArtifactPaths:
        prefix = f"l3-{slice_id}"
        return cls(
            context=out_dir / f"{prefix}-ai-context-pack.json",
            prompt=out_dir / f"{prefix}-ai-prompt.txt",
            response=out_dir / f"{prefix}-ai-response.jsonl",
            invocation_receipt=out_dir / f"{prefix}-ai-invocation-receipt.json",
            session_identity=out_dir / f"{prefix}-ai-session-export-identity.json",
            candidate=out_dir / f"{prefix}-ai-rust-candidate.rs",
            cache_entry=out_dir / f"{prefix}-ai-cache-entry.json",
            manifest=out_dir / f"{prefix}-ai-candidate-manifest.json",
        )


def candidate_record(
    parsed: dict[str, Any],
    *,
    context_pack: dict[str, Any],
    resolved_model: str,
    context_path: Path,
    prompt_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    identity = resolve_model_identity(resolved_model)
    return {
        "candidate_id": identity.candidate_id,
        "purpose": "rust_draft",
        "kind": "opencode-ai",
        "provider_label": identity.provider_label,
        "model_label": identity.logical_model,
        "resolved_model": resolved_model,
        "competition_eligible": identity.competition_eligible,
        "evaluation_scope": identity.evaluation_scope,
        "prompt_scope": prompt_scope_for_context(context_pack),
        "input_artifact_hashes": {
            "context_pack": sha256_path(context_path),
            "prompt": sha256_path(prompt_path),
        },
        "output_hash": sha256_path(candidate_path),
        "artifact": {"path": candidate_path.name, "sha256": sha256_path(candidate_path)},
        "applied": False,
        "semantic_pass": False,
        "accepted_by_gates": [],
        "rejected_by_gates": [],
        "assumptions": parsed.get("assumptions", []),
    }


def apply_generated_candidate(
    manifest: dict[str, Any],
    *,
    out_dir: Path,
    canonical_draft_path: Path,
) -> dict[str, Any]:
    if manifest.get("status") != "generated":
        return manifest
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("generated AI manifest must contain exactly one candidate")
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise ValueError("generated AI candidate must be an object")
    artifact = candidate.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("generated AI candidate artifact binding is missing")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("generated AI candidate id is missing")
    relative_path = artifact.get("path")
    expected_sha256 = artifact.get("sha256")
    if not isinstance(relative_path, str) or not relative_path or Path(relative_path).is_absolute():
        raise ValueError("generated AI candidate artifact path must be relative")
    candidate_path = (out_dir / relative_path).resolve()
    try:
        candidate_path.relative_to(out_dir.resolve())
    except ValueError as error:
        raise ValueError("generated AI candidate artifact escapes output directory") from error
    if not candidate_path.is_file():
        raise ValueError("generated AI candidate artifact does not exist")
    actual_sha256 = sha256_path(candidate_path)
    if actual_sha256 != expected_sha256 or candidate.get("output_hash") != actual_sha256:
        raise ValueError("generated AI candidate artifact sha256 drifted")
    canonical_draft_path = canonical_draft_path.resolve()
    try:
        canonical_draft_path.relative_to(out_dir.resolve())
    except ValueError as error:
        raise ValueError("canonical Rust draft escapes output directory") from error
    atomic_write_bytes(canonical_draft_path, candidate_path.read_bytes())
    canonical_sha256 = sha256_path(canonical_draft_path)
    candidate["applied"] = True
    candidate["applied_artifact"] = {
        "path": canonical_draft_path.name,
        "sha256": canonical_sha256,
    }
    candidate["rust_draft_sha256"] = canonical_sha256
    manifest["selected_candidate_id"] = candidate_id
    manifest_path = out_dir / f"l3-{manifest['slice_id']}-ai-candidate-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest


def manifest_base(
    target_id: str,
    slice_id: str,
    resolved_model: str,
    agent: str,
    variant: str,
    context_path: Path,
    prompt_path: Path,
    response_path: Path,
    *,
    provider_invocations: int,
    provider_preflight: dict[str, str],
    cache_evidence: dict[str, Any],
) -> dict[str, Any]:
    identity = resolve_model_identity(resolved_model)
    return {
        "schema_version": 9,
        "target_id": target_id,
        "slice_id": slice_id,
        "ai_required_for_default_pipeline": True,
        "provider_invocations": provider_invocations,
        "provider_attempts": [],
        "provider_preflight": provider_preflight,
        "cache": cache_evidence,
        "generator": {
            "tool": "opencode",
            "provider": identity.provider_label,
            "logical_model": identity.logical_model,
            "resolved_model": resolved_model,
            "competition_eligible": identity.competition_eligible,
            "evaluation_scope": identity.evaluation_scope,
            "agent": agent,
            "variant": variant,
            "prompt_transport": prompt_transport_contract(),
        },
        "bindings": {
            "context_pack": {"path": context_path.name, "sha256": sha256_path(context_path)},
            "prompt": {"path": prompt_path.name, "sha256": sha256_path(prompt_path)},
            "raw_response": {"path": response_path.name, "sha256": sha256_path(response_path)},
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "candidate_requires_common_validation": True,
            "competition_eligible": identity.competition_eligible,
        },
        "cache_invalidation_keys": [
            f"context_pack:{sha256_path(context_path)}",
            f"prompt:{sha256_path(prompt_path)}",
            f"raw_response:{sha256_path(response_path)}",
        ],
    }


__all__ = [
    "CandidateArtifactPaths",
    "apply_generated_candidate",
    "candidate_record",
    "manifest_base",
]
