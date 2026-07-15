from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .generated_closure import verify_generated_build_closure
from .orchestration_facts import read_artifact_reference


def verify_manifest_generated_closure(
    manifest: Mapping[str, Any], *, repo_root: Path, artifact_root: Path,
) -> dict[str, Any]:
    binding = manifest.get("generated_build_closure")
    if not isinstance(binding, Mapping) or binding.get("status") != "bound":
        return _result("blocked", [{"kind": "generated_build_closure_not_bound"}])
    closure_ref = binding.get("closure")
    verification_ref = binding.get("verification")
    try:
        closure = _read_json(artifact_root, closure_ref)
        stored = _read_json(artifact_root, verification_ref)
        actual = verify_generated_build_closure(repo_root, closure)
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return _result(
            "blocked", [{"kind": "generated_build_closure_reopen_failed"}],
        )
    if stored != actual:
        return _result(
            "blocked", [{"kind": "generated_build_closure_verification_drift"}],
            closure=closure_ref, verification=verification_ref,
        )
    blockers = actual.get("blockers")
    if actual.get("status") != "verified" or not isinstance(blockers, list) or blockers:
        normalized = blockers if isinstance(blockers, list) and blockers else [
            {"kind": "generated_build_closure_incomplete"},
        ]
        return _result(
            "blocked", normalized,
            closure=closure_ref, verification=verification_ref,
        )
    return _result(
        "verified", [], closure=closure_ref, verification=verification_ref,
        verified_binding_count=actual.get("verified_binding_count", 0),
    )


def _read_json(root: Path, reference: Any) -> dict[str, Any]:
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("generated closure reference is invalid")
    raw = read_artifact_reference(root, reference)
    if reference.get("size_bytes") != len(raw):
        raise ValueError("generated closure reference size drifted")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise ValueError("generated closure artifact is not canonical")
    return value


def _result(
    status: str, blockers: list[Any], **details: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "blockers": [
            dict(item) if isinstance(item, Mapping) else {"kind": str(item)}
            for item in blockers
        ],
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        **details,
    }


__all__ = ["verify_manifest_generated_closure"]
