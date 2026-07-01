#!/usr/bin/env python3
"""Validate judge-facing public release packet artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import validate_judge_entrypoints as judge_validator


DEFAULT_PACKET = Path("target/competition-out-flashdb-judge-entrypoints/summary/public-release-packet.json")
PACKET_SCHEMA = REPO_ROOT / "validation" / "public-release-packet.schema.json"
CORE_ARTIFACT_REFS = (
    "judge_entrypoints_run_report",
    "readiness_report",
    "judge_milestone_bundle",
    "milestone_release_notes",
)


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

    if "public_release_packet_is_not_semantic_gate" not in set(packet.get("must_not_claim", [])):
        raise ValueError("must_not_claim must include public_release_packet_is_not_semantic_gate")


def require_claim_boundary_contract(packet: dict[str, Any]) -> None:
    boundary = require_object(packet.get("claim_boundary"), "claim_boundary")
    require_false(boundary.get("semantic_gate"), "claim_boundary.semantic_gate")
    require_false(boundary.get("packet_is_semantic_gate"), "claim_boundary.packet_is_semantic_gate")
    require_false(boundary.get("generated_draft_semantic_pass"), "claim_boundary.generated_draft_semantic_pass")
    require_zero(boundary.get("translation_coverage_numerator"), "claim_boundary.translation_coverage_numerator")

    publication = require_object(packet.get("publication_manifest"), "publication_manifest")
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
