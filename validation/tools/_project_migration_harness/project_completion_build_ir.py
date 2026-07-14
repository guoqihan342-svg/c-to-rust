from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import write_json_artifact
from .build_ir import validate_artifact_reference
from .build_ir_validation import verify_build_ir_artifact


def verify_project_final_build_ir(
    *, migration_manifest: Mapping[str, Any], repo_root: Path | None,
    artifact_root: Path,
) -> dict[str, Any]:
    """Reopen the manifest-bound BuildIR at a project completion boundary."""
    profile = migration_manifest.get("profile")
    if profile not in {None, "development", "competition"}:
        return _result(
            profile, None, "blocked", [{"kind": "migration_manifest_profile_invalid"}],
        )
    build_ir = migration_manifest.get("build_ir")
    if not isinstance(build_ir, Mapping) or build_ir.get("status") != "bound":
        return _result(
            profile, None, "blocked",
            [{"kind": "migration_manifest_build_ir_binding_invalid"}],
        )
    reference = build_ir.get("artifact")
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes",
    }:
        return _result(
            profile, None, "blocked",
            [{"kind": "migration_manifest_build_ir_reference_invalid"}],
        )
    bound_reference = dict(reference)
    try:
        validate_artifact_reference(
            bound_reference, "migration_manifest_build_ir_reference_invalid",
        )
    except (TypeError, ValueError):
        return _result(
            profile, None, "blocked",
            [{"kind": "migration_manifest_build_ir_reference_invalid"}],
        )
    if repo_root is None:
        if profile == "competition":
            return _result(
                profile, bound_reference, "blocked",
                [{"kind": "competition_repo_root_missing"}],
            )
        return _result(
            profile, bound_reference, "compatibility-skipped", [],
            compatibility_reason="non_competition_repo_root_not_provided",
        )
    try:
        resolved_repo_root = Path(repo_root).resolve(strict=True)
        if not resolved_repo_root.is_dir():
            raise NotADirectoryError(str(resolved_repo_root))
    except (OSError, RuntimeError):
        kind = (
            "competition_repo_root_missing"
            if profile == "competition"
            else "repo_root_missing"
        )
        return _result(profile, bound_reference, "blocked", [{"kind": kind}])

    verification = verify_build_ir_artifact(
        resolved_repo_root, artifact_root, bound_reference,
    )
    blockers = verification.get("blockers")
    if not isinstance(blockers, list):
        blockers = [{"kind": "build_ir_verification_result_invalid"}]
    if (
        profile == "competition"
        and verification.get("toolchain_profile") != "competition"
    ):
        blockers = [
            *blockers,
            {"kind": "competition_build_ir_toolchain_profile_invalid"},
        ]
    status = "verified" if verification.get("status") == "verified" and not blockers \
        else "blocked"
    return _result(
        profile, bound_reference, status, blockers,
        build_ir_sha256=verification.get("build_ir_sha256"),
        semantic_sha256=verification.get("semantic_sha256"),
        toolchain_profile=verification.get("toolchain_profile"),
        verified_binding_count=verification.get("verified_binding_count", 0),
    )


def _result(
    profile: Any, reference: Mapping[str, Any] | None, status: str,
    blockers: list[Any], **details: Any,
) -> dict[str, Any]:
    normalized_blockers = [
        dict(item) if isinstance(item, Mapping) else {"kind": str(item)}
        for item in blockers
    ]
    return {
        "schema_version": 1,
        "artifact_kind": "project-final-build-ir-verification",
        "status": status,
        "profile": profile,
        "build_ir_artifact": dict(reference) if reference is not None else None,
        "blockers": normalized_blockers,
        "claim_boundary": {
            "competition_profile": profile == "competition",
            "competition_profile_build_ir_verified": (
                profile == "competition" and status == "verified"
            ),
            "competition_exact": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        **details,
    }


def record_build_ir_checkpoint(
    paths: Mapping[str, Any], phase: str, verification: Mapping[str, Any],
) -> dict[str, Any]:
    return write_json_artifact(
        paths["out_root"],
        f"completion/project-final-build-ir-{phase}.json",
        {**dict(verification), "verification_phase": phase},
    )


def build_ir_allows_completion(verification: Mapping[str, Any]) -> bool:
    return verification.get("status") in {"verified", "compatibility-skipped"}


def build_ir_blocker_kinds(verification: Mapping[str, Any]) -> list[str]:
    blockers = verification.get("blockers")
    if not isinstance(blockers, list):
        return ["build_ir_verification_failed"]
    kinds = [
        str(item.get("kind"))
        for item in blockers
        if isinstance(item, Mapping) and item.get("kind")
    ]
    return kinds or ["build_ir_verification_failed"]


__all__ = [
    "build_ir_allows_completion", "build_ir_blocker_kinds",
    "record_build_ir_checkpoint", "verify_project_final_build_ir",
]
