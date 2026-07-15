from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .native_link_context import build_native_link_context
from .native_link_model import (
    NATIVE_LINK_RESPONSE_KIND,
    build_native_link_candidate,
)
from .orchestration_facts import read_artifact_reference
from .rust_project_ir_validation import validate_rust_project_ir


def recover_project_native_link_state(
    rust_project_ir: Mapping[str, Any],
    migration_manifest: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    """Rebuild native-link model inputs from immutable project bindings."""
    validate_rust_project_ir(rust_project_ir)
    profile = migration_manifest.get("profile")
    build = migration_manifest.get("build_ir")
    reference = build.get("artifact") if isinstance(build, Mapping) else None
    if (
        profile not in {"competition", "development"}
        or not isinstance(reference, Mapping)
        or dict(reference) not in rust_project_ir["bindings"]["build_ir"]
    ):
        raise ValueError("project_native_link_build_binding_invalid")
    raw = read_artifact_reference(Path(artifact_root), reference)
    try:
        build_ir = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("project_native_link_build_ir_invalid") from error
    if not isinstance(build_ir, dict) or canonical_json_bytes(build_ir) != raw:
        raise ValueError("project_native_link_build_ir_invalid")
    context = build_native_link_context(
        build_ir, reference, profile=str(profile),
    )
    if canonical_json_bytes(context["requirements"]) != canonical_json_bytes(
        rust_project_ir["native_link_requirements"]
    ):
        raise ValueError("project_native_link_requirements_drifted")
    plans = rust_project_ir["native_link_plans"]
    if not context["requirements"]:
        return _result("not-required", context, None)
    if not plans:
        return _result("candidate-missing", context, None)
    response = {
        "schema_version": 1,
        "artifact_kind": NATIVE_LINK_RESPONSE_KIND,
        "context_sha256": context["context_sha256"],
        "proposals": [{
            key: item[key] for key in (
                "requirement_id", "strategy", "rustc_link_name",
                "rustc_link_kind",
            )
        } for item in plans],
    }
    candidate = build_native_link_candidate(context, response)
    candidate_hashes = {item["candidate_sha256"] for item in plans}
    if candidate_hashes != {candidate["candidate_sha256"]}:
        raise ValueError("project_native_link_candidate_binding_drifted")
    return _result("candidate-ready", context, candidate)


def _result(
    status: str, context: Mapping[str, Any], candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "context": dict(context),
        "candidate": None if candidate is None else dict(candidate),
        "requirement_count": int(context["requirement_count"]),
        "semantic_gate": False,
        "resolution_gate": False,
    }


__all__ = ["recover_project_native_link_state"]
