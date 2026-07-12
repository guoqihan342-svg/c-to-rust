from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


JsonWriter = Callable[[Path, Mapping[str, Any]], None]
Sha256Path = Callable[[Path], str]


def persist_candidate_result(
    result: Mapping[str, Any],
    path: Path,
    *,
    persist_summary: Callable[..., dict[str, Any]],
    sha256_path: Sha256Path,
) -> dict[str, Any]:
    payload = dict(result)
    attempt_dir = Path(str(payload.pop("attempt_dir")))
    persist_summary(payload, path=path, attempt_dir=attempt_dir)
    return {"path": path.name, "sha256": sha256_path(path), "status": payload["status"]}


def mark_ai_not_applied(
    manifest: dict[str, Any],
    evidence_dir: Path,
    slice_id: str,
    *,
    atomic_write_json: JsonWriter,
) -> None:
    candidates = manifest.get("candidates")
    if (
        isinstance(candidates, list)
        and len(candidates) == 1
        and isinstance(candidates[0], dict)
    ):
        candidate = candidates[0]
        candidate["applied"] = False
        candidate.pop("applied_artifact", None)
        candidate.pop("rust_draft_sha256", None)
    manifest.pop("selected_candidate_id", None)
    atomic_write_json(evidence_dir / f"l3-{slice_id}-ai-candidate-manifest.json", manifest)


def persist_exact_validation_summary(
    result: Mapping[str, Any],
    *,
    path: Path,
    attempt_dir: Path,
    atomic_write_json: JsonWriter,
) -> dict[str, Any]:
    payload = dict(result)
    gate_index = dict(payload.get("gate_index", {}))
    gate_index["path"] = attempt_dir.relative_to(path.parent).as_posix() + "/gate-index.json"
    payload["gate_index"] = gate_index
    atomic_write_json(path, payload)
    return payload
