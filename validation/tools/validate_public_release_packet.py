#!/usr/bin/env python3
"""Validate judge-facing public release packet artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from pathlib import PurePosixPath
import sys
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import milestone_release_notes
from validation.tools import validate_judge_entrypoints as judge_validator


DEFAULT_PACKET = Path("target/competition-out-flashdb-judge-entrypoints/summary/public-release-packet.json")
PACKET_SCHEMA = REPO_ROOT / "validation" / "public-release-packet.schema.json"
CORE_ARTIFACT_REFS = (
    "judge_entrypoints_run_report",
    "readiness_report",
    "judge_milestone_bundle",
    "milestone_release_notes",
)
COMPETITION_BUNDLE_MANIFEST_PATH = "config/competition-env/bundle-manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    args = parser.parse_args()

    result = validate_packet(args.packet, repo_root=REPO_ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


def validate_packet(packet_path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    packet_path = resolve_packet_path(packet_path, repo_root=repo_root)
    errors: list[str] = []
    packet: dict[str, Any] = {}
    try:
        packet = judge_validator.load_json(packet_path)
        require_packet_contract(packet, repo_root=repo_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(str(error))
    return {
        "status": "failed" if errors else "passed",
        "packet": {
            "path": judge_validator.repo_relative(packet_path, repo_root),
            "status": "present" if packet_path.is_file() else "missing",
            "sha256": judge_validator.sha256_file(packet_path) if packet_path.is_file() else None,
        },
        "claim_boundary": packet.get("claim_boundary", {}) if isinstance(packet, dict) else {},
        "artifact_refs": checked_artifact_refs(packet, repo_root=repo_root) if not errors else {"checked_count": 0},
        "errors": errors,
    }


def require_packet_contract(packet: dict[str, Any], *, repo_root: Path) -> None:
    require_claim_boundary_contract(packet)
    schema = judge_validator.load_json(PACKET_SCHEMA)
    try:
        jsonschema.validate(packet, schema)
    except jsonschema.ValidationError as error:
        path = judge_validator.jsonschema_error_path(error)
        raise ValueError(
            "public_release_packet must match validation/public-release-packet.schema.json: "
            f"{path}: {error.message}"
        ) from error

    scan = judge_validator.validate_local_absolute_path_policy(packet, label="public_release_packet")
    if scan["host_trace_allowed_count"] != 0:
        raise ValueError(
            "public_release_packet contains forbidden local absolute path at "
            f"{scan['host_trace_allowed_locations']}"
        )

    for name in CORE_ARTIFACT_REFS:
        ref = require_object(packet.get(name), name)
        if ref.get("status") != "present":
            raise ValueError(f"{name}.status must be present")
        judge_validator.validate_ref(ref, repo_root=repo_root)

    require_competition_config_archive_contract(packet, repo_root=repo_root)
    require_opencode_patch_boundary_contract(packet, repo_root=repo_root)
    require_bundle_consistency(packet, repo_root=repo_root)

    if "public_release_packet_is_not_semantic_gate" not in set(packet.get("must_not_claim", [])):
        raise ValueError("must_not_claim must include public_release_packet_is_not_semantic_gate")


def require_claim_boundary_contract(packet: dict[str, Any]) -> None:
    boundary = require_object(packet.get("claim_boundary"), "claim_boundary")
    require_false(boundary.get("semantic_gate"), "claim_boundary.semantic_gate")
    require_false(boundary.get("packet_is_semantic_gate"), "claim_boundary.packet_is_semantic_gate")
    require_false(boundary.get("generated_draft_semantic_pass"), "claim_boundary.generated_draft_semantic_pass")
    require_zero(boundary.get("translation_coverage_numerator"), "claim_boundary.translation_coverage_numerator")

    publication = require_object(packet.get("publication_manifest"), "publication_manifest")
    require_publication_manifest_identity_contract(publication)
    publication_boundary = require_object(
        publication.get("claim_boundary"),
        "publication_manifest.claim_boundary",
    )
    require_false(publication_boundary.get("semantic_gate"), "publication_manifest.claim_boundary.semantic_gate")
    if "publication_manifest_is_semantic_gate" in publication_boundary:
        require_false(
            publication_boundary.get("publication_manifest_is_semantic_gate"),
            "publication_manifest.claim_boundary.publication_manifest_is_semantic_gate",
        )
    require_false(
        publication_boundary.get("generated_draft_semantic_pass"),
        "publication_manifest.claim_boundary.generated_draft_semantic_pass",
    )
    require_zero(
        publication_boundary.get("translation_coverage_numerator"),
        "publication_manifest.claim_boundary.translation_coverage_numerator",
    )

    archive = require_object(packet.get("competition_config_archive"), "competition_config_archive")
    archive_boundary = require_object(archive.get("claim_boundary"), "competition_config_archive.claim_boundary")
    require_false(archive_boundary.get("semantic_gate"), "competition_config_archive.claim_boundary.semantic_gate")
    if "archive_is_semantic_gate" in archive_boundary:
        require_false(
            archive_boundary.get("archive_is_semantic_gate"),
            "competition_config_archive.claim_boundary.archive_is_semantic_gate",
        )


def require_publication_manifest_identity_contract(publication: dict[str, Any]) -> None:
    if publication.get("report_kind") != "publication-manifest":
        raise ValueError("publication_manifest.report_kind must be publication-manifest")
    if publication.get("bundle_version") != 1:
        raise ValueError("publication_manifest.bundle_version must be 1")
    source_commit = require_commit_ref(
        publication.get("source_commit"),
        "publication_manifest.source_commit",
    )
    repo_commit = require_commit_ref(
        publication.get("repo_commit"),
        "publication_manifest.repo_commit",
    )
    if repo_commit != source_commit:
        raise ValueError("publication_manifest.repo_commit must match publication_manifest.source_commit")
    require_target_source_pin_ref(
        publication.get("target_source_pin"),
        "publication_manifest.target_source_pin",
    )


def require_commit_ref(value: Any, label: str) -> str:
    ref = require_object(value, label)
    if ref.get("status") != "present":
        raise ValueError(f"{label}.status must be present")
    commit = ref.get("commit")
    if not is_lower_hex_sha1(commit):
        raise ValueError(f"{label}.commit must be a 40-character lowercase hex commit")
    return str(commit)


def require_target_source_pin_ref(value: Any, label: str) -> None:
    ref = require_object(value, label)
    if ref.get("status") != "passed":
        raise ValueError(f"{label}.status must be passed")
    for field in ("target_id", "repository", "branch"):
        if not isinstance(ref.get(field), str) or not ref[field]:
            raise ValueError(f"{label}.{field} must be a non-empty string")
    if not is_lower_hex_sha1(ref.get("canonical_commit")):
        raise ValueError(f"{label}.canonical_commit must be a 40-character lowercase hex commit")


def is_lower_hex_sha1(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def require_competition_config_archive_contract(packet: dict[str, Any], *, repo_root: Path) -> None:
    archive = require_object(packet.get("competition_config_archive"), "competition_config_archive")
    if archive.get("status") != "present":
        raise ValueError("competition_config_archive.status must be present")
    files = require_object(archive.get("files"), "competition_config_archive.files")
    bundle_file = files.get(COMPETITION_BUNDLE_MANIFEST_PATH)
    if not isinstance(bundle_file, dict):
        raise ValueError(f"competition_config_archive.files must include {COMPETITION_BUNDLE_MANIFEST_PATH}")
    try:
        checked_bundle_file = judge_validator.validate_ref(bundle_file, repo_root=repo_root)
    except ValueError as error:
        raise ValueError(f"competition_config_archive.files.{COMPETITION_BUNDLE_MANIFEST_PATH}: {error}") from error
    require_competition_config_archive_matches_bundle_manifest(
        archive,
        files,
        repo_root=repo_root,
        bundle_manifest_path=str(checked_bundle_file["path"]),
    )
    checked_materialized_manifest = require_materialized_competition_config_archive_manifest(
        archive,
        repo_root=repo_root,
        expected_path=expected_materialized_competition_config_archive_manifest_path(packet),
    )

    publication = require_object(packet.get("publication_manifest"), "publication_manifest")
    publication_archive = require_object(
        publication.get("competition_config_archive"),
        "publication_manifest.competition_config_archive",
    )
    require_publication_archive_summary_projection(publication_archive, archive)
    publication_bundle = require_object(
        publication_archive.get("bundle_manifest"),
        "publication_manifest.competition_config_archive.bundle_manifest",
    )
    if {
        "path": publication_bundle.get("path"),
        "sha256": publication_bundle.get("sha256"),
        "status": publication_bundle.get("status"),
    } != {
        "path": checked_bundle_file["path"],
        "sha256": checked_bundle_file["sha256"],
        "status": checked_bundle_file["status"],
    }:
        raise ValueError(
            "publication_manifest.competition_config_archive.bundle_manifest must match "
            "competition_config_archive.files.config/competition-env/bundle-manifest.json"
        )
    publication_materialized_manifest = require_object(
        publication_archive.get("materialized_manifest"),
        "publication_manifest.competition_config_archive.materialized_manifest",
    )
    if {
        "path": publication_materialized_manifest.get("path"),
        "sha256": publication_materialized_manifest.get("sha256"),
        "status": publication_materialized_manifest.get("status"),
    } != {
        "path": checked_materialized_manifest["path"],
        "sha256": checked_materialized_manifest["sha256"],
        "status": checked_materialized_manifest["status"],
    }:
        raise ValueError(
            "publication_manifest.competition_config_archive.materialized_manifest must match "
            "competition_config_archive.materialized_manifest"
        )
    external_refs = require_object(archive.get("external_refs"), "competition_config_archive.external_refs")
    missing_external_refs = sorted(set(judge_validator.COMPETITION_ENV_EXTERNAL_REF_ROLES) - set(external_refs))
    if missing_external_refs:
        raise ValueError(f"competition_config_archive.external_refs missing required refs: {missing_external_refs}")
    for path_text, expected_role in judge_validator.COMPETITION_ENV_EXTERNAL_REF_ROLES.items():
        ref = require_object(external_refs.get(path_text), f"competition_config_archive.external_refs.{path_text}")
        role = judge_validator.require_string(
            ref.get("role"),
            f"competition_config_archive.external_refs.{path_text}.role",
        )
        if role != expected_role:
            raise ValueError(f"competition_config_archive.external_refs.{path_text}.role must be {expected_role}")
        try:
            judge_validator.validate_ref(ref, repo_root=repo_root)
        except ValueError as error:
            raise ValueError(f"competition_config_archive.external_refs.{path_text}: {error}") from error
    require_publication_archive_external_refs_projection(
        publication_archive,
        external_refs,
    )


def require_publication_archive_external_refs_projection(
    publication_archive: dict[str, Any],
    archive_external_refs: dict[str, Any],
) -> None:
    label = "publication_manifest.competition_config_archive.external_refs"
    publication_external_refs = require_object(publication_archive.get("external_refs"), label)
    if publication_archive.get("external_ref_count") != len(publication_external_refs):
        raise ValueError(
            "publication_manifest.competition_config_archive.external_ref_count must match "
            "publication_manifest.competition_config_archive.external_refs length"
        )
    expected_projection = {
        path_text: {
            "path": path_text,
            "role": judge_validator.require_string(
                ref.get("role"),
                f"competition_config_archive.external_refs.{path_text}.role",
            ),
            "status": ref.get("status"),
            "sha256": ref.get("sha256"),
        }
        for path_text, ref in sorted(archive_external_refs.items())
    }
    if publication_external_refs != expected_projection:
        raise ValueError(
            "publication_manifest.competition_config_archive.external_refs must match "
            "competition_config_archive.external_refs"
        )


def require_publication_archive_summary_projection(
    publication_archive: dict[str, Any],
    archive: dict[str, Any],
) -> None:
    for field in ("status", "root", "report_kind", "file_count"):
        if publication_archive.get(field) != archive.get(field):
            raise ValueError(
                f"publication_manifest.competition_config_archive.{field} must match "
                f"competition_config_archive.{field}"
            )


def require_competition_config_archive_matches_run_report(packet: dict[str, Any], *, repo_root: Path) -> None:
    run_report_ref = require_object(packet.get("judge_entrypoints_run_report"), "judge_entrypoints_run_report")
    try:
        checked_run_report = judge_validator.validate_ref(run_report_ref, repo_root=repo_root)
    except ValueError as error:
        raise ValueError(f"judge_entrypoints_run_report: {error}") from error
    run_report_path = judge_validator.repo_path(str(checked_run_report["path"]), repo_root=repo_root)
    try:
        run_report = judge_validator.load_json(run_report_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"judge_entrypoints_run_report: unable to read JSON payload: {error}") from error
    if packet.get("competition_config_archive") != run_report.get("competition_config_archive"):
        raise ValueError(
            "competition_config_archive must match judge_entrypoints_run_report.competition_config_archive"
        )


def require_materialized_competition_config_archive_manifest(
    archive: dict[str, Any],
    *,
    repo_root: Path,
    expected_path: str,
) -> dict[str, Any]:
    label = "competition_config_archive.materialized_manifest"
    ref = require_object(archive.get("materialized_manifest"), label)
    try:
        checked = judge_validator.validate_ref(ref, repo_root=repo_root)
    except ValueError as error:
        raise ValueError(f"{label}: {error}") from error
    if checked["path"] != expected_path:
        raise ValueError(f"{label}.path must be {expected_path}")
    manifest_path = judge_validator.repo_path(str(checked["path"]), repo_root=repo_root)
    try:
        manifest_payload = judge_validator.load_json(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label}: unable to read JSON payload: {error}") from error
    expected_payload = json.loads(json.dumps(archive))
    expected_payload.pop("materialized_manifest", None)
    if manifest_payload != expected_payload:
        raise ValueError(
            "competition_config_archive.materialized_manifest payload must match "
            "competition_config_archive without materialized_manifest"
        )
    return checked


def expected_materialized_competition_config_archive_manifest_path(packet: dict[str, Any]) -> str:
    run_report_ref = require_object(packet.get("judge_entrypoints_run_report"), "judge_entrypoints_run_report")
    path_text = judge_validator.require_string(
        run_report_ref.get("path"),
        "judge_entrypoints_run_report.path",
    )
    judge_validator.assert_repo_relative_posix(path_text)
    run_report_path = PurePosixPath(path_text)
    if run_report_path.parent.name != "summary":
        raise ValueError("judge_entrypoints_run_report.path must be under a summary directory")
    return (run_report_path.parent / "competition-config-archive" / "manifest.json").as_posix()


def require_competition_config_archive_matches_bundle_manifest(
    archive: dict[str, Any],
    files: dict[str, Any],
    *,
    repo_root: Path,
    bundle_manifest_path: str,
) -> None:
    manifest_path = judge_validator.repo_path(bundle_manifest_path, repo_root=repo_root)
    manifest = judge_validator.load_json(manifest_path)
    judge_validator.validate_competition_env_bundle_contract(
        {
            "environment_profile": require_object(
                manifest.get("canonical_environment_profile"),
                "competition env bundle canonical_environment_profile",
            )
        },
        repo_root=repo_root,
        manifest_path=manifest_path,
    )

    manifest_files = manifest_entries_by_path(manifest.get("files"), "competition env bundle files")
    expected_file_paths = sorted({COMPETITION_BUNDLE_MANIFEST_PATH, *manifest_files})
    actual_file_paths = sorted(files)
    missing_files = sorted(set(expected_file_paths) - set(actual_file_paths))
    if missing_files:
        raise ValueError(f"competition_config_archive.files missing bundle-manifest listed files: {missing_files}")
    unexpected_files = sorted(set(actual_file_paths) - set(expected_file_paths))
    if unexpected_files:
        raise ValueError(f"competition_config_archive.files contains files not listed by bundle-manifest: {unexpected_files}")
    if archive.get("file_count") != len(files):
        raise ValueError("competition_config_archive.file_count must match competition_config_archive.files length")

    bundle_manifest_ref = require_object(
        files.get(COMPETITION_BUNDLE_MANIFEST_PATH),
        f"competition_config_archive.files.{COMPETITION_BUNDLE_MANIFEST_PATH}",
    )
    validate_archive_ref_matches_manifest(
        bundle_manifest_ref,
        expected_path=COMPETITION_BUNDLE_MANIFEST_PATH,
        expected_sha=judge_validator.sha256_file(manifest_path),
        label=f"competition_config_archive.files.{COMPETITION_BUNDLE_MANIFEST_PATH}",
        repo_root=repo_root,
    )
    for path_text, entry in manifest_files.items():
        validate_archive_ref_matches_manifest(
            require_object(files.get(path_text), f"competition_config_archive.files.{path_text}"),
            expected_path=path_text,
            expected_sha=judge_validator.require_string(
                entry.get("sha256"),
                f"competition env bundle {path_text}.sha256",
            ),
            label=f"competition_config_archive.files.{path_text}",
            repo_root=repo_root,
        )

    external_refs = require_object(archive.get("external_refs"), "competition_config_archive.external_refs")
    manifest_external_refs = manifest_entries_by_path(
        manifest.get("external_refs"),
        "competition env bundle external_refs",
    )
    missing_external_refs = sorted(set(manifest_external_refs) - set(external_refs))
    if missing_external_refs:
        raise ValueError(
            "competition_config_archive.external_refs missing required refs from bundle-manifest: "
            f"{missing_external_refs}"
        )
    unexpected_external_refs = sorted(set(external_refs) - set(manifest_external_refs))
    if unexpected_external_refs:
        raise ValueError(
            "competition_config_archive.external_refs contains refs not listed by bundle-manifest: "
            f"{unexpected_external_refs}"
        )
    if archive.get("external_ref_count") != len(external_refs):
        raise ValueError("competition_config_archive.external_ref_count must match competition_config_archive.external_refs length")
    for path_text, entry in manifest_external_refs.items():
        ref = require_object(external_refs.get(path_text), f"competition_config_archive.external_refs.{path_text}")
        role = judge_validator.require_string(ref.get("role"), f"competition_config_archive.external_refs.{path_text}.role")
        expected_role = judge_validator.require_string(entry.get("role"), f"competition env bundle external_ref {path_text}.role")
        if role != expected_role:
            raise ValueError(f"competition_config_archive.external_refs.{path_text}.role must match bundle-manifest")
        validate_archive_ref_matches_manifest(
            ref,
            expected_path=path_text,
            expected_sha=judge_validator.require_string(
                entry.get("sha256"),
                f"competition env bundle external_ref {path_text}.sha256",
            ),
            label=f"competition_config_archive.external_refs.{path_text}",
            repo_root=repo_root,
        )


def manifest_entries_by_path(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    entries: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value):
        entry = require_object(item, f"{label}[{index}]")
        path_text = judge_validator.require_string(entry.get("path"), f"{label}[{index}].path")
        if path_text in entries:
            raise ValueError(f"{label} contains duplicate path: {path_text}")
        entries[path_text] = entry
    return entries


def validate_archive_ref_matches_manifest(
    ref: dict[str, Any],
    *,
    expected_path: str,
    expected_sha: str,
    label: str,
    repo_root: Path,
) -> None:
    checked = judge_validator.validate_ref(ref, repo_root=repo_root)
    if checked["path"] != expected_path:
        raise ValueError(f"{label}.path must match bundle-manifest path")
    if checked["sha256"] != expected_sha:
        raise ValueError(f"{label}.sha256 must match bundle-manifest sha256")


def checked_artifact_refs(packet: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for name in CORE_ARTIFACT_REFS:
        value = packet.get(name)
        if isinstance(value, dict) and isinstance(value.get("path"), str):
            refs[name] = {
                "path": value.get("path"),
                "status": value.get("status", "unknown"),
                "sha256": value.get("sha256"),
            }
    return {"checked_count": len(refs), "refs": refs}


def require_opencode_patch_boundary_contract(packet: dict[str, Any], *, repo_root: Path) -> None:
    boundary = require_object(packet.get("opencode_patch_boundary"), "opencode_patch_boundary")
    require_false(boundary.get("chat_output_is_evidence"), "opencode_patch_boundary.chat_output_is_evidence")
    require_false(boundary.get("semantic_gate"), "opencode_patch_boundary.semantic_gate")
    require_zero(
        boundary.get("translation_coverage_numerator"),
        "opencode_patch_boundary.translation_coverage_numerator",
    )
    require_opencode_safety_transform_attempt_boundary_contract(packet, boundary, repo_root=repo_root)
    proof = require_object(
        boundary.get("opencode_preflight_proof_summary"),
        "opencode_patch_boundary.opencode_preflight_proof_summary",
    )
    if boundary.get("opencode_runtime_enabled") is True or proof.get("status") == "passed":
        require_opencode_preflight_proof_summary_contract(
            proof,
            "opencode_patch_boundary.opencode_preflight_proof_summary",
            repo_root=repo_root,
            allow_competition_exact=competition_host_readiness_allows_exact_preflight(
                require_object(packet.get("competition_host_readiness"), "competition_host_readiness")
            ),
        )


def require_opencode_safety_transform_attempt_boundary_contract(
    packet: dict[str, Any],
    boundary: dict[str, Any],
    *,
    repo_root: Path,
) -> None:
    label = "opencode_patch_boundary.opencode_safety_transform_attempt"
    summary = require_object(boundary.get("opencode_safety_transform_attempt"), label)
    publication = require_object(packet.get("publication_manifest"), "publication_manifest")
    attempt_refs = opencode_safety_transform_attempt_refs(publication)
    status = summary.get("status")
    if status == "absent":
        if attempt_refs:
            raise ValueError(
                f"{label}.status must be present when publication_manifest publishes "
                "opencode_safety_transform_attempt"
            )
        return
    if status not in {"present", "passed"}:
        raise ValueError(f"{label}.status must be present, passed, or absent")
    if len(attempt_refs) != 1:
        raise ValueError(
            "publication_manifest.published_artifact_refs must include exactly one "
            "opencode_safety_transform_attempt when opencode_patch_boundary summary is present"
        )

    published_ref = attempt_refs[0]
    if summary.get("path") != published_ref.get("path"):
        raise ValueError(f"{label}.path must match publication_manifest.published_artifact_refs")
    if summary.get("sha256") != published_ref.get("sha256"):
        raise ValueError(f"{label}.sha256 must match publication_manifest.published_artifact_refs")
    if summary.get("artifact_read_status") != "passed":
        raise ValueError(f"{label}.artifact_read_status must be passed")
    if summary.get("attempt_status") != "accepted":
        raise ValueError(f"{label}.attempt_status must be accepted")

    attempt_result = judge_validator.validate_opencode_safety_transform_attempt_contract(
        published_ref,
        repo_root=repo_root,
    )
    expected = {
        "unit_count": attempt_result["unit_count"],
        "round_count": attempt_result["round_count"],
        "rollback_ref_count": attempt_result["rollback_ref_count"],
        "max_repair_rounds": attempt_result["repair_round_cap"],
    }
    for field, expected_value in expected.items():
        if summary.get(field) != expected_value:
            raise ValueError(f"{label}.{field} must match bound opencode_safety_transform_attempt artifact")

    payload = judge_validator.load_json(judge_validator.repo_path(str(published_ref["path"]), repo_root=repo_root))
    retry_statuses = opencode_attempt_retry_statuses(payload)
    if summary.get("accepted_retry_hint_statuses") != retry_statuses:
        raise ValueError(f"{label}.accepted_retry_hint_statuses must match bound artifact retry hints")
    if summary.get("accepted_retry_hint_status") != summarize_retry_statuses(retry_statuses):
        raise ValueError(f"{label}.accepted_retry_hint_status must match bound artifact retry hints")


def opencode_safety_transform_attempt_refs(publication: dict[str, Any]) -> list[dict[str, Any]]:
    refs = publication.get("published_artifact_refs")
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise ValueError("publication_manifest.published_artifact_refs must be a list")
    return [
        require_object(ref, "publication_manifest.published_artifact_refs[]")
        for ref in refs
        if (
            isinstance(ref, dict)
            and ref.get("artifact_name") == "opencode_safety_transform_attempt"
            and ref.get("status") in {"present", "passed"}
        )
    ]


def require_passed_bundle_published_refs_are_healthy(bundle: dict[str, Any], publication: dict[str, Any]) -> None:
    if bundle.get("status") != "passed":
        return
    refs = publication.get("published_artifact_refs", [])
    if not isinstance(refs, list):
        raise ValueError("publication_manifest.published_artifact_refs must be a list")
    bad_statuses = {"sha256_mismatch", "status_mismatch", "missing_expected_sha256"}
    for ref in refs:
        ref_obj = require_object(ref, "publication_manifest.published_artifact_refs[]")
        status = ref_obj.get("status")
        if status in bad_statuses:
            artifact_name = ref_obj.get("artifact_name", "unknown")
            raise ValueError(
                f"passed bundle cannot publish bad artifact ref status: {artifact_name}:{status}"
            )


def competition_host_readiness_allows_exact_preflight(readiness: dict[str, Any]) -> bool:
    return (
        readiness.get("status") == "ready"
        and readiness.get("competition_exact_host_verified") is True
        and readiness.get("required_agent_tool") == judge_validator.COMPETITION_OPENCODE_COMMAND
        and readiness.get("required_agent") == judge_validator.COMPETITION_OPENCODE_AGENT
        and readiness.get("required_model") == judge_validator.COMPETITION_OPENCODE_MODEL
        and readiness.get("required_variant") == judge_validator.COMPETITION_OPENCODE_VARIANT
        and readiness.get("required_proof_class") == "competition-exact"
    )


def require_publishability_publication_scope_contract(
    publishability: dict[str, Any],
    *,
    competition_host_readiness: dict[str, Any] | None = None,
) -> None:
    status = publishability.get("status")
    scope = publishability.get("scope")
    publication_scope = publishability.get("publication_scope")
    allowed = {"blocked", "partial", "internal_preview_full", "full"}
    if publication_scope not in allowed:
        raise ValueError("publishability.publication_scope must be blocked, partial, internal_preview_full, or full")
    expected_publication_scope = (
        "internal_preview_full"
        if status == "internal_preview" and scope == "full"
        else scope
    )
    if publication_scope != expected_publication_scope:
        raise ValueError("publishability.publication_scope must match external readiness")
    if publishability.get("required_agent_tool") != judge_validator.COMPETITION_OPENCODE_COMMAND:
        raise ValueError("publishability.required_agent_tool must be opencode")
    if publishability.get("required_agent") != judge_validator.COMPETITION_OPENCODE_AGENT:
        raise ValueError("publishability.required_agent must be c2rust-migrator")
    if publishability.get("required_model") != judge_validator.COMPETITION_OPENCODE_MODEL:
        raise ValueError("publishability.required_model must be GLM-5.1")
    readiness = competition_host_readiness if isinstance(competition_host_readiness, dict) else {}
    if readiness.get("required_agent_tool") != judge_validator.COMPETITION_OPENCODE_COMMAND:
        raise ValueError("competition_host_readiness.required_agent_tool must be opencode")
    if readiness.get("required_agent") != judge_validator.COMPETITION_OPENCODE_AGENT:
        raise ValueError("competition_host_readiness.required_agent must be c2rust-migrator")
    if readiness.get("required_model") != judge_validator.COMPETITION_OPENCODE_MODEL:
        raise ValueError("competition_host_readiness.required_model must be GLM-5.1")
    if publication_scope == "full" and publishability.get("external_milestone_claim_ready") is not True:
        raise ValueError("publishability.publication_scope=full requires external_milestone_claim_ready=true")
    if status == "external_release_ready":
        if publishability.get("all_entrypoints_run_publishable") is not True:
            raise ValueError("publishability.all_entrypoints_run_publishable must be true for external_release_ready")
        if publishability.get("competition_exact_publishable") is not True:
            raise ValueError("publishability.competition_exact_publishable must be true for external_release_ready")
        if publishability.get("opencode_glm51_publishable") is not True:
            raise ValueError("publishability.opencode_glm51_publishable must be true for external_release_ready")
        if publishability.get("focused_run") is not False:
            raise ValueError("publishability.focused_run must be false for external_release_ready")
        if readiness.get("status") != "ready":
            raise ValueError("competition_host_readiness.status must be ready for external_release_ready")
        if readiness.get("competition_exact_host_verified") is not True:
            raise ValueError(
                "competition_host_readiness.competition_exact_host_verified must be true for external_release_ready"
            )
    if publishability.get("competition_exact_publishable") is True:
        if readiness.get("all_entrypoints_competition_exact") is not True:
            raise ValueError(
                "publishability.competition_exact_publishable requires "
                "competition_host_readiness.all_entrypoints_competition_exact=true"
            )
        if readiness.get("competition_exact_host_verified") is not True:
            raise ValueError(
                "publishability.competition_exact_publishable requires "
                "competition_host_readiness.competition_exact_host_verified=true"
            )


def require_published_artifact_refs_are_hash_bound(publication: dict[str, Any], *, repo_root: Path) -> None:
    refs = publication.get("published_artifact_refs", [])
    if not isinstance(refs, list):
        raise ValueError("publication_manifest.published_artifact_refs must be a list")
    for ref in refs:
        ref_obj = require_object(ref, "publication_manifest.published_artifact_refs[]")
        if ref_obj.get("status") not in {"present", "passed"}:
            continue
        try:
            judge_validator.validate_ref(ref_obj, repo_root=repo_root)
        except ValueError as error:
            message = str(error)
            if "sha256 mismatch" in message:
                raise ValueError(
                    "publication_manifest.published_artifact_refs[].sha256 mismatch: "
                    f"{message}"
                ) from error
            raise ValueError(f"publication_manifest.published_artifact_refs[] invalid: {message}") from error


def expected_published_artifact_ref_status(publication: dict[str, Any]) -> dict[str, Any]:
    refs = publication.get("published_artifact_refs", [])
    status_counts: dict[str, int] = {}
    abnormal_refs: list[dict[str, str]] = []
    total_count = 0
    for ref in refs if isinstance(refs, list) else []:
        if not isinstance(ref, dict):
            continue
        total_count += 1
        status = str(ref.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "present":
            abnormal_refs.append(
                {
                    "artifact_name": str(ref.get("artifact_name", "unknown")),
                    "path": str(ref.get("path", "unknown")),
                    "status": status,
                }
            )
    return {
        "total_count": total_count,
        "status_counts": dict(sorted(status_counts.items())),
        "abnormal_ref_count": len(abnormal_refs),
        "abnormal_refs": abnormal_refs,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": "Published artifact ref status is a review summary only, not semantic acceptance.",
    }


def opencode_attempt_retry_statuses(payload: dict[str, Any]) -> list[str]:
    hints: list[dict[str, Any]] = []
    top_level = payload.get("accepted_retry_hint")
    if isinstance(top_level, dict):
        hints.append(top_level)
    units = payload.get("safety_transform_units")
    if isinstance(units, list):
        for unit in units:
            if isinstance(unit, dict) and isinstance(unit.get("accepted_retry_hint"), dict):
                hints.append(unit["accepted_retry_hint"])
    return [status for hint in hints if isinstance((status := hint.get("status", "unknown")), str)]


def summarize_retry_statuses(statuses: list[str]) -> str:
    if not statuses:
        return "unknown"
    if len(set(statuses)) == 1:
        return statuses[0]
    return "mixed"


def require_opencode_preflight_proof_summary_contract(
    proof: dict[str, Any],
    label: str,
    *,
    repo_root: Path,
    allow_competition_exact: bool = False,
) -> None:
    if proof.get("status") != "passed":
        raise ValueError(f"{label}.status must be passed")
    if proof.get("required_when_opencode_runtime_enabled") is not True:
        raise ValueError(f"{label}.required_when_opencode_runtime_enabled must be true")
    require_false(proof.get("chat_output_is_evidence"), f"{label}.chat_output_is_evidence")
    require_false(proof.get("semantic_gate"), f"{label}.semantic_gate")
    require_zero(proof.get("translation_coverage_numerator"), f"{label}.translation_coverage_numerator")
    if proof.get("opencode_command") != judge_validator.COMPETITION_OPENCODE_COMMAND:
        raise ValueError(f"{label}.opencode_command must be {judge_validator.COMPETITION_OPENCODE_COMMAND}")
    if proof.get("opencode_agent") != judge_validator.COMPETITION_OPENCODE_AGENT:
        raise ValueError(f"{label}.opencode_agent must be {judge_validator.COMPETITION_OPENCODE_AGENT}")
    if proof.get("opencode_model") != judge_validator.COMPETITION_OPENCODE_MODEL:
        raise ValueError(f"{label}.opencode_model must be {judge_validator.COMPETITION_OPENCODE_MODEL}")
    if proof.get("opencode_variant") != judge_validator.COMPETITION_OPENCODE_VARIANT:
        raise ValueError(f"{label}.opencode_variant must be {judge_validator.COMPETITION_OPENCODE_VARIANT}")
    if proof.get("required_model") != judge_validator.COMPETITION_OPENCODE_MODEL:
        raise ValueError(f"{label}.required_model must be {judge_validator.COMPETITION_OPENCODE_MODEL}")
    if proof.get("model_availability_status") != "available":
        raise ValueError(f"{label}.model_availability_status must be available")
    if proof.get("model_listed") is not True:
        raise ValueError(f"{label}.model_listed must be true")
    if proof.get("process_returncode") != 0:
        raise ValueError(f"{label}.process_returncode must be 0")
    if proof.get("contract_status") != "executed":
        raise ValueError(f"{label}.contract_status must be executed")
    if proof.get("marker_exists") is not True:
        raise ValueError(f"{label}.marker_exists must be true")
    if proof.get("opencode_run_launched") is not True:
        raise ValueError(f"{label}.opencode_run_launched must be true")
    if proof.get("opencode_run_argv_bound") is not True:
        raise ValueError(f"{label}.opencode_run_argv_bound must be true")
    if proof.get("proof_class") == "competition-exact" and not allow_competition_exact:
        raise ValueError(f"{label}.proof_class must not claim competition-exact without host attestation")
    if not judge_validator.opencode_models_argv_matches(
        proof.get("model_probe_argv"),
        expected_command=judge_validator.COMPETITION_OPENCODE_COMMAND,
    ):
        raise ValueError(f"{label}.model_probe_argv must be opencode models")

    preflight_ref = require_object(proof.get("preflight_report"), f"{label}.preflight_report")
    checked_preflight_ref = judge_validator.validate_ref(preflight_ref, repo_root=repo_root)
    logs = require_object(proof.get("model_probe_logs"), f"{label}.model_probe_logs")
    checked_logs: dict[str, dict[str, Any]] = {}
    for stream in ("stdout", "stderr"):
        checked_logs[stream] = judge_validator.validate_ref(
            require_object(logs.get(stream), f"{label}.model_probe_logs.{stream}"),
            repo_root=repo_root,
        )

    preflight_payload = judge_validator.load_json(
        judge_validator.repo_path(str(checked_preflight_ref["path"]), repo_root=repo_root)
    )
    if preflight_payload.get("status") != "passed":
        raise ValueError(f"{label}.preflight_report file status must be passed")
    if preflight_payload.get("marker_exists") is not True:
        raise ValueError(f"{label}.preflight_report file marker_exists must be true")
    if preflight_payload.get("opencode_run_launched") is not True:
        raise ValueError(f"{label}.preflight_report file opencode_run_launched must be true")
    launch_policy = require_object(preflight_payload.get("launch_policy"), f"{label}.preflight_report.launch_policy")
    if launch_policy.get("opencode_agent") != proof.get("opencode_agent"):
        raise ValueError(f"{label}.opencode_agent must match preflight_report.launch_policy.opencode_agent")
    if launch_policy.get("opencode_model") != proof.get("opencode_model"):
        raise ValueError(f"{label}.opencode_model must match preflight_report.launch_policy.opencode_model")
    if launch_policy.get("opencode_variant") != proof.get("opencode_variant"):
        raise ValueError(f"{label}.opencode_variant must match preflight_report.launch_policy.opencode_variant")
    preflight_runtime_env = judge_validator.validate_opencode_runtime_env_contract(
        preflight_payload.get("opencode_runtime_env"),
        f"{label}.preflight_report",
    )
    proof_runtime_env = judge_validator.validate_opencode_runtime_env_contract(
        proof.get("opencode_runtime_env"),
        label,
    )
    if proof_runtime_env != preflight_runtime_env:
        raise ValueError(f"{label}.opencode_runtime_env must match preflight_report.opencode_runtime_env")
    if proof.get("opencode_runtime_env_sha256") != preflight_runtime_env["env_sha256"]:
        raise ValueError(
            f"{label}.opencode_runtime_env_sha256 must match preflight_report.opencode_runtime_env.env_sha256"
        )
    contract = require_object(
        preflight_payload.get("contract_verification"),
        f"{label}.preflight_report.contract_verification",
    )
    if contract.get("status") != proof.get("contract_status"):
        raise ValueError(f"{label}.contract_status must match preflight_report.contract_verification.status")
    require_opencode_preflight_session_contract(
        preflight_payload,
        contract,
        f"{label}.preflight_report",
        repo_root=repo_root,
    )

    availability = require_object(
        preflight_payload.get("opencode_model_availability"),
        f"{label}.preflight_report.opencode_model_availability",
    )
    if availability.get("status") != proof.get("model_availability_status"):
        raise ValueError(f"{label}.model_availability_status must match preflight_report.opencode_model_availability.status")
    if availability.get("required_model") != proof.get("required_model"):
        raise ValueError(f"{label}.required_model must match preflight_report.opencode_model_availability.required_model")
    if availability.get("opencode_command") != proof.get("opencode_command"):
        raise ValueError(f"{label}.opencode_command must match preflight_report.opencode_model_availability.opencode_command")
    if availability.get("model_listed") is not proof.get("model_listed"):
        raise ValueError(f"{label}.model_listed must match preflight_report.opencode_model_availability.model_listed")
    if int(availability.get("process_returncode", -1)) != proof.get("process_returncode"):
        raise ValueError(f"{label}.process_returncode must match preflight_report.opencode_model_availability.process_returncode")
    if availability.get("argv") != proof.get("model_probe_argv"):
        raise ValueError(f"{label}.model_probe_argv must match preflight_report.opencode_model_availability.argv")
    availability_logs = require_object(availability.get("logs"), f"{label}.preflight_report.opencode_model_availability.logs")
    for stream in ("stdout", "stderr"):
        if availability_logs.get(stream) != checked_logs[stream]["path"]:
            raise ValueError(f"{label}.model_probe_logs.{stream}.path must match preflight_report log path")
        expected_hash = availability.get(f"{stream}_sha256")
        if expected_hash != checked_logs[stream]["sha256"]:
            raise ValueError(f"{label}.model_probe_logs.{stream}.sha256 must match preflight_report log sha256")
    judge_validator.validate_opencode_model_probe_log_hashes(availability, label, repo_root=repo_root)


def require_opencode_preflight_session_contract(
    preflight_payload: dict[str, Any],
    contract: dict[str, Any],
    label: str,
    *,
    repo_root: Path,
) -> None:
    if preflight_payload.get("process_returncode") != 0:
        raise ValueError(f"{label} file process_returncode must be 0")
    handoff_ref = judge_validator.validate_hash_bound_artifact_binding(
        preflight_payload.get("handoff_contract"),
        f"{label}.handoff_contract",
        repo_root=repo_root,
    )
    handoff_payload = require_object(
        judge_validator.load_json(judge_validator.repo_path(handoff_ref["path"], repo_root=repo_root)),
        f"{label}.handoff_contract file",
    )
    if handoff_payload.get("runner_kind") != "opencode-preflight":
        raise ValueError(f"{label}.handoff_contract.runner_kind must be opencode-preflight")
    if handoff_payload.get("run_id") != preflight_payload.get("run_id"):
        raise ValueError(f"{label}.handoff_contract.run_id must match preflight_report.run_id")
    preflight_runtime_env = judge_validator.validate_opencode_runtime_env_contract(
        preflight_payload.get("opencode_runtime_env"),
        label,
    )
    handoff_runtime_env = judge_validator.validate_opencode_runtime_env_contract(
        handoff_payload.get("opencode_runtime_env"),
        f"{label}.handoff_contract",
    )
    if handoff_runtime_env != preflight_runtime_env:
        raise ValueError(f"{label}.handoff_contract.opencode_runtime_env must match preflight_report.opencode_runtime_env")
    handoff_policy = judge_validator.validate_opencode_launch_policy_binding(
        handoff_payload.get("launch_policy"),
        handoff_payload.get("launch_policy_sha256"),
        f"{label}.handoff_contract",
    )
    preflight_policy = judge_validator.validate_opencode_launch_policy_binding(
        preflight_payload.get("launch_policy"),
        preflight_payload.get("launch_policy_sha256"),
        f"{label}.launch_policy",
    )
    if handoff_policy != preflight_policy:
        raise ValueError(f"{label}.handoff_contract.launch_policy must match preflight_report.launch_policy")
    worker_command = handoff_payload.get("worker_command")
    if not isinstance(worker_command, list) or not worker_command or not all(
        isinstance(item, str) and item for item in worker_command
    ):
        raise ValueError(f"{label}.handoff_contract.worker_command must be a non-empty string list")
    worker_command_line = judge_validator.require_string(
        handoff_payload.get("worker_command_line"),
        f"{label}.handoff_contract.worker_command_line",
    )
    if worker_command_line != judge_validator.shell_command_line(worker_command):
        raise ValueError(f"{label}.handoff_contract.worker_command_line must match worker_command")
    worker_command_sha256 = handoff_payload.get("worker_command_sha256")
    if worker_command_sha256 != judge_validator.sha256_text(worker_command_line):
        raise ValueError(f"{label}.handoff_contract.worker_command_sha256 must match worker_command_line")
    report_argv = judge_validator.require_string_argv(preflight_payload.get("argv"), f"{label}.argv")
    handoff_argv = judge_validator.require_string_argv(
        handoff_payload.get("opencode_argv"),
        f"{label}.handoff_contract.opencode_argv",
    )
    if report_argv != handoff_argv:
        raise ValueError(f"{label}.argv must match handoff_contract.opencode_argv")
    judge_validator.validate_opencode_run_argv_binding(report_argv, f"{label}.argv", launch_policy=preflight_policy)
    handoff_command_line = judge_validator.require_string(
        handoff_payload.get("opencode_command_line"),
        f"{label}.handoff_contract.opencode_command_line",
    )
    if handoff_command_line != judge_validator.shell_command_line(handoff_argv):
        raise ValueError(f"{label}.handoff_contract.opencode_command_line must match opencode_argv")
    handoff_prompt = judge_validator.require_string(handoff_payload.get("prompt"), f"{label}.handoff_contract.prompt")
    if handoff_prompt != handoff_argv[-1]:
        raise ValueError(f"{label}.handoff_contract.prompt must match opencode_argv prompt")
    marker_path_text = judge_validator.require_string(preflight_payload.get("marker_path"), f"{label}.marker_path")
    expected_marker_path = judge_validator.require_string(
        handoff_payload.get("expected_marker_path"),
        f"{label}.handoff_contract.expected_marker_path",
    )
    if marker_path_text != expected_marker_path:
        raise ValueError(f"{label}.marker_path must match handoff_contract.expected_marker_path")
    marker_path = judge_validator.repo_path(marker_path_text, repo_root=repo_root)
    if not marker_path.is_file():
        raise ValueError(f"{label}.marker_path must exist")
    marker_payload = require_object(
        judge_validator.load_json(marker_path),
        f"{label}.marker file",
    )
    if marker_payload.get("report_kind") != "opencode-preflight-marker":
        raise ValueError(f"{label}.marker.report_kind must be opencode-preflight-marker")
    if marker_payload.get("run_id") != preflight_payload.get("run_id"):
        raise ValueError(f"{label}.marker.run_id must match preflight_report.run_id")
    if marker_payload.get("status") != "written":
        raise ValueError(f"{label}.marker.status must be written")

    session_ref = judge_validator.validate_hash_bound_artifact_binding(
        preflight_payload.get("opencode_session_evidence"),
        f"{label}.opencode_session_evidence",
        repo_root=repo_root,
    )
    session_evidence = require_object(
        judge_validator.load_json(judge_validator.repo_path(session_ref["path"], repo_root=repo_root)),
        f"{label}.opencode_session_evidence file",
    )
    session_runtime_env = judge_validator.validate_opencode_runtime_env_contract(
        session_evidence.get("opencode_runtime_env"),
        f"{label}.opencode_session_evidence",
    )
    if session_runtime_env != preflight_runtime_env:
        raise ValueError(
            f"{label}.opencode_session_evidence.opencode_runtime_env must match preflight_report.opencode_runtime_env"
        )
    judge_validator.validate_opencode_contract_recomputed_from_session(
        embedded_verification=contract,
        session_evidence=session_evidence,
        worker_command=worker_command,
        summary_path=marker_path,
        label=label,
        repo_root=repo_root,
    )


def require_bundle_consistency(packet: dict[str, Any], *, repo_root: Path) -> None:
    bundle_ref = require_object(packet.get("judge_milestone_bundle"), "judge_milestone_bundle")
    bundle_path = judge_validator.repo_path(str(bundle_ref.get("path")), repo_root=repo_root)
    bundle = judge_validator.load_json(bundle_path)
    require_bound_bundle_identity_contract(packet, bundle)
    publication = require_object(packet.get("publication_manifest"), "publication_manifest")
    require_published_artifact_refs_are_hash_bound(publication, repo_root=repo_root)
    require_passed_bundle_published_refs_are_healthy(bundle, publication)
    for field in ("judge_entrypoints_run_report", "readiness_report"):
        if packet.get(field) != bundle.get(field):
            raise ValueError(f"{field} must match judge_milestone_bundle.{field}")
        if field in publication and publication.get(field) != packet.get(field):
            raise ValueError(f"publication_manifest.{field} must match public_release_packet.{field}")
    require_competition_config_archive_matches_run_report(packet, repo_root=repo_root)

    for field in (
        "publication_manifest",
        "publishability",
        "competition_host_readiness",
        "harness_architecture_summary",
        "evidence_cost_retention",
        "before_after_repair_exhibit",
        "known_gaps",
        "reproduction_commands",
        "quantitative_evaluation",
        "progress_delta_ledger",
    ):
        if packet.get(field) != bundle.get(field):
            raise ValueError(f"{field} must match judge_milestone_bundle.{field}")

    require_publishability_publication_scope_contract(
        require_object(packet.get("publishability"), "publishability"),
        competition_host_readiness=require_object(
            packet.get("competition_host_readiness"),
            "competition_host_readiness",
        ),
    )

    summary = require_object(packet.get("summary"), "summary")
    if summary.get("blockers") != bundle.get("blockers", []):
        raise ValueError("summary.blockers must match judge_milestone_bundle.blockers")
    if summary.get("published_artifact_ref_status") != expected_published_artifact_ref_status(publication):
        raise ValueError(
            "summary.published_artifact_ref_status must match "
            "judge_milestone_bundle.publication_manifest.published_artifact_refs"
        )
    if summary.get("workflow_metrics") != expected_workflow_metrics_summary(bundle):
        raise ValueError(
            "summary.workflow_metrics must match judge_milestone_bundle.workflow_metrics.rollup.repair_activity"
        )
    if summary.get("progress_delta_ledger") != bundle.get("progress_delta_ledger"):
        raise ValueError("summary.progress_delta_ledger must match judge_milestone_bundle.progress_delta_ledger")
    expected_proof_class_rollup = bundle.get("proof_class_rollup", bundle.get("proof_classes"))
    if summary.get("proof_class_rollup") != expected_proof_class_rollup:
        raise ValueError("summary.proof_class_rollup must match judge_milestone_bundle.proof_class_rollup")
    require_competition_host_readiness_matches_proof_class_rollup(
        require_object(packet.get("competition_host_readiness"), "competition_host_readiness"),
        require_object(expected_proof_class_rollup, "judge_milestone_bundle.proof_class_rollup"),
    )

    runtime = bundle.get("opencode_runtime") if isinstance(bundle.get("opencode_runtime"), dict) else {}
    boundary = require_object(packet.get("opencode_patch_boundary"), "opencode_patch_boundary")
    expected_runtime_enabled = int(runtime.get("enabled_entrypoint_count", 0) or 0) > 0
    if boundary.get("opencode_runtime_enabled") is not expected_runtime_enabled:
        raise ValueError(
            "opencode_patch_boundary.opencode_runtime_enabled must match "
            "judge_milestone_bundle.opencode_runtime.enabled_entrypoint_count"
        )
    expected_preflight = runtime.get("preflight_proof_summary")
    if isinstance(expected_preflight, dict):
        if boundary.get("opencode_preflight_proof_summary") != expected_preflight:
            raise ValueError(
                "opencode_patch_boundary.opencode_preflight_proof_summary must match "
                "judge_milestone_bundle.opencode_runtime.preflight_proof_summary"
            )

    require_release_notes_match_bundle(packet, bundle, repo_root=repo_root)

    packet_claims = set(packet.get("must_not_claim", []))
    bundle_claims = set(bundle.get("must_not_claim", []))
    missing_claims = sorted(str(claim) for claim in bundle_claims - packet_claims)
    if missing_claims:
        raise ValueError(
            "must_not_claim must include judge_milestone_bundle.must_not_claim entries: "
            f"{missing_claims}"
        )


def require_competition_host_readiness_matches_proof_class_rollup(
    readiness: dict[str, Any],
    proof_class_rollup: dict[str, Any],
) -> None:
    field_pairs = (
        ("actual_highest_proof_class", "highest_proof_class"),
        ("all_entrypoints_competition_exact", "all_entrypoints_competition_exact"),
        ("competition_exact_host_verified", "competition_exact_host_verified"),
    )
    for readiness_field, rollup_field in field_pairs:
        if readiness.get(readiness_field) != proof_class_rollup.get(rollup_field):
            raise ValueError(
                f"competition_host_readiness.{readiness_field} must match "
                f"judge_milestone_bundle.proof_class_rollup.{rollup_field}"
            )
    if readiness.get("status") == "ready":
        if proof_class_rollup.get("all_entrypoints_competition_exact") is not True:
            raise ValueError(
                "competition_host_readiness.status=ready requires "
                "judge_milestone_bundle.proof_class_rollup.all_entrypoints_competition_exact=true"
            )
        if proof_class_rollup.get("competition_exact_host_verified") is not True:
            raise ValueError(
                "competition_host_readiness.status=ready requires "
                "judge_milestone_bundle.proof_class_rollup.competition_exact_host_verified=true"
            )


def require_bound_bundle_identity_contract(packet: dict[str, Any], bundle: dict[str, Any]) -> None:
    if bundle.get("schema_version") != 1:
        raise ValueError("judge_milestone_bundle.schema_version must be 1")
    if bundle.get("report_kind") != "judge-milestone-bundle":
        raise ValueError("judge_milestone_bundle.report_kind must be judge-milestone-bundle")
    status = bundle.get("status")
    if status not in {"passed", "blocked"}:
        raise ValueError("judge_milestone_bundle.status must be passed or blocked")
    blockers = bundle.get("blockers")
    if not isinstance(blockers, list) or not all(isinstance(blocker, str) for blocker in blockers):
        raise ValueError("judge_milestone_bundle.blockers must be a string list")
    if status == "passed" and blockers:
        raise ValueError("judge_milestone_bundle.blockers must be empty when status is passed")
    if status == "blocked" and not blockers:
        raise ValueError("judge_milestone_bundle.blockers must be present when status is blocked")
    if packet.get("status") != status:
        raise ValueError("public_release_packet.status must match judge_milestone_bundle.status")


def expected_workflow_metrics_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    workflow = bundle.get("workflow_metrics") if isinstance(bundle.get("workflow_metrics"), dict) else {}
    rollup = workflow.get("rollup") if isinstance(workflow.get("rollup"), dict) else {}
    repair_activity = rollup.get("repair_activity") if isinstance(rollup.get("repair_activity"), dict) else {}
    return {
        "repair_activity": repair_activity,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Public packet workflow metrics are copied from the bound judge milestone bundle for review only. "
            "They are not a semantic gate and do not increase translation coverage."
        ),
    }


def require_release_notes_match_bundle(packet: dict[str, Any], bundle: dict[str, Any], *, repo_root: Path) -> None:
    notes_ref = require_object(packet.get("milestone_release_notes"), "milestone_release_notes")
    notes_path = judge_validator.repo_path(str(notes_ref.get("path")), repo_root=repo_root)
    actual_notes = normalize_markdown(notes_path.read_text(encoding="utf-8-sig"))
    try:
        expected_notes = normalize_markdown(milestone_release_notes.build_release_notes(bundle))
    except SystemExit as error:
        raise ValueError(f"judge_milestone_bundle release notes contract failed: {error}") from error
    if actual_notes != expected_notes:
        raise ValueError("milestone_release_notes must match judge_milestone_bundle rendered release notes")


def normalize_markdown(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.rstrip("\n") + "\n"


def resolve_packet_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root.resolve())
        return resolved
    path_text = path.as_posix()
    judge_validator.assert_repo_relative_posix(path_text)
    return judge_validator.repo_path(path_text, repo_root=repo_root)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_false(value: Any, label: str) -> None:
    if value is not False:
        raise ValueError(f"{label} must be false")


def require_zero(value: Any, label: str) -> None:
    if value != 0:
        raise ValueError(f"{label} must be 0")


if __name__ == "__main__":
    raise SystemExit(main())
