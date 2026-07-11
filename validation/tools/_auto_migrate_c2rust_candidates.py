from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools._ai_candidate_harness_parts.context import (
    canonical_json_bytes,
    sha256_path,
)


def resolve_current_c2rust_baseline_candidate(
    baseline_manifest: Mapping[str, Any] | None,
    *,
    manifest_path: Path | None,
    evidence_dir: Path,
    repo_root: Path,
) -> tuple[Path | None, dict[str, Any]]:
    audit: dict[str, Any] = {
        "source": "c2rust-baseline",
        "status": "rejected",
        "reason": "baseline_manifest_missing",
    }
    if not isinstance(baseline_manifest, Mapping) or manifest_path is None:
        return None, audit

    evidence_root = evidence_dir.resolve()
    resolved_manifest = manifest_path.resolve()
    try:
        resolved_manifest.relative_to(evidence_root)
    except ValueError:
        audit["reason"] = "baseline_manifest_outside_current_run"
        return None, audit
    if not resolved_manifest.is_file() or resolved_manifest.is_symlink():
        audit["reason"] = "baseline_manifest_not_reopenable"
        return None, audit
    try:
        reopened = json.loads(resolved_manifest.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        audit["reason"] = "baseline_manifest_invalid_json"
        return None, audit
    if not isinstance(reopened, dict) or canonical_json_bytes(reopened) != canonical_json_bytes(
        dict(baseline_manifest)
    ):
        audit["reason"] = "baseline_manifest_payload_drift"
        return None, audit

    manifest_status = reopened.get("status")
    audit["manifest_status"] = manifest_status if isinstance(manifest_status, str) else "invalid"
    if manifest_status != "generated":
        audit["reason"] = "baseline_manifest_not_generated"
        return None, audit
    output = reopened.get("output")
    if not isinstance(output, dict) or output.get("status") != "generated":
        audit["reason"] = "baseline_output_not_generated"
        return None, audit
    output_path_value = output.get("path")
    declared_sha = output.get("sha256")
    if not isinstance(output_path_value, str) or not output_path_value:
        audit["reason"] = "baseline_output_path_missing"
        return None, audit
    if not _is_sha256(declared_sha):
        audit["reason"] = "baseline_output_sha256_invalid"
        return None, audit

    output_path = _resolve_current_run_artifact(
        output_path_value,
        evidence_root=evidence_root,
        repo_root=repo_root.resolve(),
    )
    if output_path is None:
        audit["reason"] = "baseline_output_not_reopenable_in_current_run"
        return None, audit
    if judge_validator.sha256_file(output_path) != declared_sha:
        audit["reason"] = "baseline_output_sha256_mismatch"
        return None, audit

    candidate_sha = sha256_path(output_path)
    audit.update(
        status="eligible_for_exact_gates",
        reason="current_run_manifest_and_output_reopened",
        manifest={
            "path": resolved_manifest.relative_to(evidence_root).as_posix(),
            "sha256": sha256_path(resolved_manifest),
        },
        artifact={
            "path": output_path.relative_to(evidence_root).as_posix(),
            "declared_sha256": declared_sha,
            "candidate_sha256": candidate_sha,
        },
    )
    return output_path, audit


def _resolve_current_run_artifact(value: str, *, evidence_root: Path, repo_root: Path) -> Path | None:
    configured = Path(value)
    candidates = [configured] if configured.is_absolute() else [repo_root / configured, evidence_root / configured]
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(evidence_root)
        except ValueError:
            continue
        if resolved.is_file() and not resolved.is_symlink():
            return resolved
    return None


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
