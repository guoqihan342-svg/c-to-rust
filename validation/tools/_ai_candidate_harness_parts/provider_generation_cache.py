from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate_cache import (
    cache_key_payload,
    cache_key_sha256,
    load_candidate_cache,
)
from .context import atomic_write_bytes, atomic_write_json, sha256_bytes, sha256_path
from .provider_manifest import CandidateArtifactPaths, candidate_record, manifest_base
from .provider_response import parse_candidate_response


def load_cached_candidate(
    cache_root: Path,
    context_pack: dict[str, Any],
    paths: CandidateArtifactPaths,
    *,
    target_id: str,
    slice_id: str,
    resolved_model: str,
    agent: str,
    agent_definition_sha256: str,
    variant: str,
    provider_preflight: dict[str, str],
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    cache_payload = cache_key_payload(
        sha256_path(paths.context),
        prompt_sha256=sha256_path(paths.prompt),
        resolved_model=resolved_model,
        agent=agent,
        agent_definition_sha256=agent_definition_sha256,
        variant=variant,
    )
    cache_key = cache_key_sha256(cache_payload)
    cached, cache_reason = load_candidate_cache(
        cache_root,
        cache_payload,
        parse_candidate_response,
    )
    if cached is None:
        return (
            None,
            cache_payload,
            {
                "status": "miss",
                "key_sha256": cache_key,
                "miss_reason": cache_reason,
                "stored": False,
            },
        )

    atomic_write_bytes(paths.cache_entry, cached.entry_bytes)
    atomic_write_bytes(paths.response, cached.response_bytes)
    atomic_write_bytes(paths.candidate, cached.candidate_bytes)
    cache_evidence = {
        "status": "hit",
        "key_sha256": cache_key,
        "entry_sha256": cached.entry_sha256,
        "entry": {
            "path": paths.cache_entry.name,
            "sha256": sha256_path(paths.cache_entry),
        },
        "raw_response_sha256": sha256_bytes(cached.response_bytes),
        "candidate_sha256": sha256_bytes(cached.candidate_bytes),
    }
    base = manifest_base(
        target_id,
        slice_id,
        resolved_model,
        agent,
        variant,
        paths.context,
        paths.prompt,
        paths.response,
        provider_invocations=0,
        provider_preflight=provider_preflight,
        cache_evidence=cache_evidence,
    )
    candidate = candidate_record(
        cached.parsed,
        context_pack=context_pack,
        resolved_model=resolved_model,
        context_path=paths.context,
        prompt_path=paths.prompt,
        candidate_path=paths.candidate,
    )
    manifest = {**base, "status": "generated", "candidates": [candidate]}
    atomic_write_json(paths.manifest, manifest)
    return manifest, cache_payload, cache_evidence


__all__ = ["load_cached_candidate"]
