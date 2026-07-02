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

    publication = require_object(packet.get("publication_manifest"), "publication_manifest")
    publication_archive = require_object(
        publication.get("competition_config_archive"),
        "publication_manifest.competition_config_archive",
    )
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
    if boundary.get("opencode_runtime_enabled") is True:
        proof = require_object(
            boundary.get("opencode_preflight_proof_summary"),
            "opencode_patch_boundary.opencode_preflight_proof_summary",
        )
        require_opencode_preflight_proof_summary_contract(
            proof,
            "opencode_patch_boundary.opencode_preflight_proof_summary",
            repo_root=repo_root,
        )


def require_opencode_preflight_proof_summary_contract(
    proof: dict[str, Any],
    label: str,
    *,
    repo_root: Path,
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
    if proof.get("opencode_model") != judge_validator.COMPETITION_OPENCODE_MODEL:
        raise ValueError(f"{label}.opencode_model must be {judge_validator.COMPETITION_OPENCODE_MODEL}")
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
    if proof.get("proof_class") == "competition-exact":
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
    if launch_policy.get("opencode_model") != proof.get("opencode_model"):
        raise ValueError(f"{label}.opencode_model must match preflight_report.launch_policy.opencode_model")
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

    session_ref = judge_validator.validate_hash_bound_artifact_binding(
        preflight_payload.get("opencode_session_evidence"),
        f"{label}.opencode_session_evidence",
        repo_root=repo_root,
    )
    session_evidence = require_object(
        judge_validator.load_json(judge_validator.repo_path(session_ref["path"], repo_root=repo_root)),
        f"{label}.opencode_session_evidence file",
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
    publication = require_object(packet.get("publication_manifest"), "publication_manifest")
    for field in ("judge_entrypoints_run_report", "readiness_report"):
        if packet.get(field) != bundle.get(field):
            raise ValueError(f"{field} must match judge_milestone_bundle.{field}")
        if field in publication and publication.get(field) != packet.get(field):
            raise ValueError(f"publication_manifest.{field} must match public_release_packet.{field}")

    for field in (
        "publication_manifest",
        "before_after_repair_exhibit",
        "known_gaps",
        "reproduction_commands",
        "quantitative_evaluation",
        "progress_delta_ledger",
    ):
        if packet.get(field) != bundle.get(field):
            raise ValueError(f"{field} must match judge_milestone_bundle.{field}")

    summary = require_object(packet.get("summary"), "summary")
    if summary.get("workflow_metrics") != expected_workflow_metrics_summary(bundle):
        raise ValueError(
            "summary.workflow_metrics must match judge_milestone_bundle.workflow_metrics.rollup.repair_activity"
        )
    if summary.get("progress_delta_ledger") != bundle.get("progress_delta_ledger"):
        raise ValueError("summary.progress_delta_ledger must match judge_milestone_bundle.progress_delta_ledger")

    runtime = bundle.get("opencode_runtime") if isinstance(bundle.get("opencode_runtime"), dict) else {}
    expected_preflight = runtime.get("preflight_proof_summary")
    if isinstance(expected_preflight, dict):
        boundary = require_object(packet.get("opencode_patch_boundary"), "opencode_patch_boundary")
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
