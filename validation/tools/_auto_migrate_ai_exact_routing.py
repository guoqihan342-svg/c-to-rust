from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def next_attempt_dir(root: Path, label: str, candidate_sha: str) -> Path:
    safe_label = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in label
    )
    for ordinal in range(1, 100):
        candidate = root / f"{ordinal:02d}-{safe_label}-{candidate_sha[:12]}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise ValueError("AI exact validation attempt limit exceeded")


def router_candidate(
    candidate_id: str,
    source: str,
    result: Mapping[str, Any],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = {
        "candidate_id": candidate_id,
        "source": source,
        "artifact_sha256": result["candidate_sha256"],
        "gate_results": result["router_gate_results"],
    }
    if metadata is not None:
        candidate.update(metadata)
    return candidate


def manifest_candidate_id(manifest: Mapping[str, Any]) -> str:
    selected_id = manifest.get("selected_candidate_id")
    candidates = manifest.get("candidates")
    if (
        not isinstance(selected_id, str)
        or not selected_id
        or not isinstance(candidates, list)
        or len(candidates) != 1
        or not isinstance(candidates[0], Mapping)
        or candidates[0].get("candidate_id") != selected_id
    ):
        raise ValueError(
            "AI candidate manifest selected_candidate_id must bind its only candidate"
        )
    return selected_id


def manifest_generator_metadata(manifest: Mapping[str, Any]) -> dict[str, Any]:
    generator = manifest.get("generator")
    if not isinstance(generator, Mapping):
        raise ValueError("AI candidate manifest requires generator identity")
    fields = (
        "provider",
        "logical_model",
        "resolved_model",
        "competition_eligible",
        "evaluation_scope",
        "agent",
        "variant",
    )
    metadata = {field: generator.get(field) for field in fields}
    if any(value is None for value in metadata.values()):
        raise ValueError("AI candidate manifest generator identity is incomplete")
    return metadata


def passed_gate_count(result: Mapping[str, Any]) -> int:
    gate_results = result.get("router_gate_results")
    if not isinstance(gate_results, Mapping):
        return 0
    return sum(
        isinstance(gate_result, Mapping) and gate_result.get("status") == "passed"
        for gate_result in gate_results.values()
    )


def sync_duplicate_audit(
    router: Mapping[str, Any],
    *,
    source: str,
    audit: dict[str, Any],
) -> None:
    duplicates = router.get("deduplicated_candidates")
    candidate_set = router.get("candidate_set")
    if not isinstance(duplicates, list) or not isinstance(candidate_set, list):
        return
    duplicate = next(
        (
            item
            for item in duplicates
            if isinstance(item, Mapping) and item.get("source") == source
        ),
        None,
    )
    if duplicate is None:
        return
    duplicate_of = duplicate.get("duplicate_of")
    unique = next(
        (
            item
            for item in candidate_set
            if isinstance(item, Mapping) and item.get("candidate_id") == duplicate_of
        ),
        None,
    )
    audit.update(
        status="duplicate",
        reason="duplicate_exact_artifact_sha256",
        duplicate_of=duplicate_of,
        duplicate_source=unique.get("source") if isinstance(unique, Mapping) else None,
        duplicate_candidate_sha256=duplicate.get("artifact_sha256"),
    )
