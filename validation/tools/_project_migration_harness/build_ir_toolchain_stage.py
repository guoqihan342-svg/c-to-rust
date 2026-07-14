from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import write_json_artifact
from .c_toolchain_reopen import collect_c_toolchain_evidence
from .host_tool_binding import competition_profile_binding


def materialize_c_toolchain_stage(
    output: Path,
    artifacts: dict[str, dict[str, Any]],
    requests: Sequence[Mapping[str, Any]],
    *,
    profile: str,
) -> dict[str, Any] | None:
    if profile == "development":
        return None
    if profile != "competition":
        raise ValueError("project_migration_profile_invalid")
    evidence = collect_c_toolchain_evidence(
        requests,
        profile="competition",
        profile_binding=competition_profile_binding(),
    )
    artifacts["c_toolchain_evidence"] = write_json_artifact(
        output, "plan/c-toolchain-evidence.json", evidence,
    )
    return evidence


def blocked_c_toolchain_stage(
    output: Path,
    artifacts: dict[str, dict[str, Any]],
    evidence: Mapping[str, Any],
    *,
    closure: Mapping[str, Any] | None = None,
    closure_verification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blockers = [
        {"kind": str(item)} for item in evidence.get("blockers", [])
        if isinstance(item, str) and item
    ]
    verification = {
        "schema_version": 1,
        "status": "blocked",
        "build_ir_sha256": None,
        "semantic_sha256": None,
        "verified_binding_count": 0,
        "blockers": blockers or [{"kind": "c_toolchain_evidence_blocked"}],
    }
    artifacts["build_ir_verification"] = write_json_artifact(
        output, "plan/build-ir-verification.json", verification,
    )
    return {
        "build_ir": None,
        "closure": dict(closure or {}),
        "closure_verification": dict(closure_verification or {}),
        "closure_ready": False,
        "verification": verification,
    }


__all__ = ["blocked_c_toolchain_stage", "materialize_c_toolchain_stage"]
