#!/usr/bin/env python3
"""Run judge-facing harness entrypoints and persist a readiness report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import validate_judge_entrypoints as validator
from validation.tools import judge_milestone_bundle
from validation.tools import milestone_release_notes
from validation.tools import validate_public_release_packet

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]

DEFAULT_REPORT = Path("target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json")
COMPETITION_CONFIG_ROOT = Path("config/competition-env")
ENTRYPOINT_TIMEOUT_EXIT_CODE = 124
DEFAULT_ENTRYPOINT_TIMEOUT_SECONDS = 600 * 60
PORTABLE_PYTHON_COMMAND = "python3"
PYTHON_COMMAND_OVERRIDE_ENV = "C2RUST_HARNESS_PYTHON"
_RESOLVED_PYTHON_COMMAND: list[str] | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=validator.DEFAULT_CONFIG)
    parser.add_argument(
        "--entrypoint-id",
        action="append",
        default=[],
        help="Entrypoint id to run. Omit to run every entrypoint in config order.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the plan without executing commands or requiring local artifacts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_ENTRYPOINT_TIMEOUT_SECONDS,
        help="Maximum seconds allowed for each judge entrypoint command.",
    )
    args = parser.parse_args()

    report = run_judge_entrypoints(
        config_path=args.config,
        entrypoint_ids=args.entrypoint_id,
        out_path=args.out,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout_seconds,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"passed", "planned"} else 1


def run_judge_entrypoints(
    *,
    config_path: Path,
    entrypoint_ids: list[str],
    out_path: Path,
    dry_run: bool = False,
    timeout_seconds: int = DEFAULT_ENTRYPOINT_TIMEOUT_SECONDS,
    repo_root: Path = REPO_ROOT,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    out_path = resolve_output_path(out_path, repo_root=repo_root)
    log_dir = out_path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    config_archive = build_competition_config_archive(repo_root=repo_root)

    try:
        config_path = resolve_input_path(config_path, repo_root=repo_root)
        config = validator.load_json(config_path)
        config_ref = artifact_ref(config_path, repo_root=repo_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return write_run_report(
            out_path=out_path,
            status="failed",
            dry_run=dry_run,
            config_ref=invalid_config_ref(config_path, error),
            configured_entrypoint_count=0,
            config_archive=config_archive,
            command_results=[],
            preflight_validation={"status": "failed", "errors": [str(error)]},
            validation={"status": "skipped", "reason": "preflight_failed"},
            readiness_ref=None,
        )

    preflight_validation = validator.validate_config(config_path, require_local_artifacts=False, repo_root=repo_root)
    if preflight_validation.get("status") != "passed":
        return write_run_report(
            out_path=out_path,
            status="failed",
            dry_run=dry_run,
            config_ref=config_ref,
            configured_entrypoint_count=configured_entrypoint_count(config),
            config_archive=config_archive,
            command_results=[],
            preflight_validation=preflight_validation,
            validation={"status": "skipped", "reason": "preflight_failed"},
            readiness_ref=None,
        )

    try:
        selected = select_entrypoints(config, entrypoint_ids)
    except SystemExit as error:
        return write_run_report(
            out_path=out_path,
            status="failed",
            dry_run=dry_run,
            config_ref=config_ref,
            configured_entrypoint_count=configured_entrypoint_count(config),
            config_archive=config_archive,
            command_results=[],
            preflight_validation=preflight_validation,
            validation={"status": "skipped", "reason": "entrypoint_selection_failed", "errors": [str(error)]},
            readiness_ref=None,
        )

    command_results: list[dict[str, Any]] = []
    for entry in selected:
        command_results.append(
            run_entrypoint_command(
                entry,
                dry_run=dry_run,
                log_dir=log_dir,
                repo_root=repo_root,
                timeout_seconds=timeout_seconds,
                command_runner=command_runner,
            )
        )

    if dry_run:
        validation = {"status": "skipped", "reason": "dry_run", "preflight_status": preflight_validation.get("status")}
    elif all(result["exit_code"] == 0 for result in command_results):
        validation_config_path = post_run_validation_config_path(
            config_path,
            config,
            selected,
            entrypoint_ids=entrypoint_ids,
            out_path=out_path,
        )
        validation = validator.validate_config(validation_config_path, require_local_artifacts=True, repo_root=repo_root)
    else:
        validation = {"status": "skipped", "reason": "failed_command"}

    readiness_path = out_path.parent / "judge-entrypoints-readiness.json"
    readiness_ref: dict[str, Any] | None = None
    if not dry_run and validation.get("status") == "passed":
        validator.write_readiness_report(validation, readiness_path, repo_root=repo_root)
        readiness_ref = artifact_ref(readiness_path, repo_root=repo_root)

    status = (
        "passed"
        if command_results
        and all(result["exit_code"] == 0 for result in command_results)
        and validation.get("status") == "passed"
        else "failed"
    )
    if dry_run:
        status = "planned"

    report = write_run_report(
        out_path=out_path,
        status=status,
        dry_run=dry_run,
        config_ref=config_ref,
        configured_entrypoint_count=configured_entrypoint_count(config),
        config_archive=config_archive,
        command_results=command_results,
        preflight_validation=preflight_validation,
        validation=validation,
        readiness_ref=readiness_ref,
    )
    if not dry_run and status == "passed":
        attach_milestone_bundle(report, out_path=out_path, repo_root=repo_root)
    return report


def post_run_validation_config_path(
    config_path: Path,
    config: dict[str, Any],
    selected: list[dict[str, Any]],
    *,
    entrypoint_ids: list[str],
    out_path: Path,
) -> Path:
    if not entrypoint_ids:
        return config_path
    payload = json.loads(json.dumps(config))
    selected_ids = [str(entry.get("id")) for entry in selected]
    selected_id_set = set(selected_ids)
    payload["entrypoints"] = [
        entry for entry in payload.get("entrypoints", []) if isinstance(entry, dict) and entry.get("id") in selected_id_set
    ]
    contract = payload.get("test_contract")
    if isinstance(contract, dict) and isinstance(contract.get("required_entrypoint_ids"), list):
        contract["required_entrypoint_ids"] = selected_ids
    path = out_path.parent / "selected-entrypoints-validation-config.json"
    atomic_write_json(path, payload)
    return path


def write_run_report(
    *,
    out_path: Path,
    status: str,
    dry_run: bool,
    config_ref: dict[str, Any],
    configured_entrypoint_count: int,
    config_archive: dict[str, Any],
    command_results: list[dict[str, Any]],
    preflight_validation: dict[str, Any],
    validation: dict[str, Any],
    readiness_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "report_kind": "judge-entrypoints-run-report",
        "status": status,
        "dry_run": dry_run,
        "config": config_ref,
        "competition_config_archive": config_archive,
        "entrypoint_count": len(command_results),
        "entrypoints": command_results,
        "preflight_validation": preflight_validation,
        "validation": validation,
        "readiness_report": readiness_ref,
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_claim_source": "validator-owned-artifacts",
            "boundary": (
                "This runner executes judge entrypoint commands and then invokes the existing validator. "
                "It is orchestration evidence only; semantic acceptance remains owned by summaries, "
                "workflow metrics, oracle evidence, and validators."
            ),
        },
    }
    report["summary"] = build_judge_run_summary(
        status=status,
        dry_run=dry_run,
        configured_entrypoint_count=configured_entrypoint_count,
        config_archive=config_archive,
        command_results=command_results,
        validation=validation,
        readiness_ref=readiness_ref,
        claim_boundary=report["claim_boundary"],
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_path, report)
    return report


def attach_milestone_bundle(report: dict[str, Any], *, out_path: Path, repo_root: Path) -> None:
    bundle_path = out_path.parent / "judge-milestone-bundle.json"
    release_notes_path = out_path.parent / "milestone-release-notes.md"
    public_packet_path = out_path.parent / "public-release-packet.json"
    report["milestone_bundle"] = {
        "path": validator.repo_relative(bundle_path, repo_root),
        "status": "present",
        "hash_boundary": "bundle_hashes_this_run_report",
    }
    report["milestone_release_notes"] = {
        "path": validator.repo_relative(release_notes_path, repo_root),
        "status": "derived_after_bundle",
        "hash_boundary": "release_notes_hashes_the_bundle",
    }
    report["public_release_packet"] = {
        "path": validator.repo_relative(public_packet_path, repo_root),
        "status": "derived_after_release_notes",
        "hash_boundary": "packet_hashes_run_report_bundle_and_release_notes",
    }
    atomic_write_json(out_path, report)
    bundle = judge_milestone_bundle.build_judge_milestone_bundle(
        run_report_path=out_path,
        out_path=bundle_path,
        repo_root=repo_root,
    )
    atomic_write_text(release_notes_path, milestone_release_notes.build_release_notes(bundle))
    write_public_release_packet(
        report=report,
        bundle=bundle,
        run_report_path=out_path,
        bundle_path=bundle_path,
        release_notes_path=release_notes_path,
        public_packet_path=public_packet_path,
        repo_root=repo_root,
    )
    packet_validation = validate_public_release_packet.validate_packet(public_packet_path, repo_root=repo_root)
    if packet_validation.get("status") != "passed":
        errors = packet_validation.get("errors", [])
        raise SystemExit(f"public release packet validation failed: {errors}")


def write_public_release_packet(
    *,
    report: dict[str, Any],
    bundle: dict[str, Any],
    run_report_path: Path,
    bundle_path: Path,
    release_notes_path: Path,
    public_packet_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    publication = bundle.get("publication_manifest") if isinstance(bundle.get("publication_manifest"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    packet = {
        "schema_version": 1,
        "report_kind": "public-release-packet",
        "status": bundle.get("status", report.get("status", "unknown")),
        "summary": {
            "entrypoint_count": report.get("entrypoint_count", 0),
            "publication_scope": publication.get("publication_scope", "unknown"),
            "readiness": summary.get("readiness", {}),
            "proof_class_rollup": bundle.get("proof_class_rollup", bundle.get("proof_classes", {})),
            "workflow_metrics": public_packet_workflow_metrics_summary(bundle),
            "progress_delta_ledger": bundle.get("progress_delta_ledger", {}),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "packet_is_semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "boundary": (
                "This packet indexes the public release artifacts. It hashes existing validator-owned "
                "artifacts and does not create semantic acceptance or translator-generated coverage."
            ),
        },
        "judge_entrypoints_run_report": artifact_ref(run_report_path, repo_root=repo_root),
        "readiness_report": artifact_ref_from_report_ref(report.get("readiness_report"), repo_root=repo_root),
        "judge_milestone_bundle": artifact_ref(bundle_path, repo_root=repo_root),
        "milestone_release_notes": artifact_ref(release_notes_path, repo_root=repo_root),
        "competition_config_archive": report.get("competition_config_archive", {}),
        "publication_manifest": publication,
        "before_after_repair_exhibit": bundle.get("before_after_repair_exhibit", {}),
        "opencode_patch_boundary": public_packet_opencode_patch_boundary(bundle, repo_root=repo_root),
        "quantitative_evaluation": bundle.get("quantitative_evaluation", {}),
        "progress_delta_ledger": bundle.get("progress_delta_ledger", {}),
        "known_gaps": bundle.get("known_gaps", []),
        "must_not_claim": public_packet_must_not_claim(bundle.get("must_not_claim", [])),
        "reproduction_commands": bundle.get("reproduction_commands", {}),
    }
    atomic_write_json(public_packet_path, packet)
    return packet


def public_packet_opencode_patch_boundary(bundle: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    before_after = bundle.get("before_after_repair_exhibit") if isinstance(bundle.get("before_after_repair_exhibit"), dict) else {}
    patch_sources: set[str] = set()
    opencode_session_bound_count = 0
    for source in before_after.get("sources", []) if isinstance(before_after.get("sources"), list) else []:
        if not isinstance(source, dict):
            continue
        for unit in source.get("before_after_units", []) if isinstance(source.get("before_after_units"), list) else []:
            if not isinstance(unit, dict):
                continue
            patch_origin = unit.get("patch_origin") if isinstance(unit.get("patch_origin"), dict) else {}
            if isinstance(patch_origin.get("source"), str):
                patch_sources.add(patch_origin["source"])
            if patch_origin.get("opencode_session_bound") is True:
                opencode_session_bound_count += 1

    publication = bundle.get("publication_manifest") if isinstance(bundle.get("publication_manifest"), dict) else {}
    attempt_ref = next(
        (
            ref
            for ref in publication.get("published_artifact_refs", [])
            if isinstance(ref, dict) and ref.get("artifact_name") == "opencode_safety_transform_attempt"
        ),
        None,
    )
    attempt_summary = public_packet_opencode_attempt_summary(attempt_ref, repo_root=repo_root)
    runtime = bundle.get("opencode_runtime") if isinstance(bundle.get("opencode_runtime"), dict) else {}
    opencode_runtime_enabled = int(runtime.get("enabled_entrypoint_count", 0) or 0) > 0
    return {
        "report_kind": "opencode-patch-boundary",
        "opencode_runtime_enabled": opencode_runtime_enabled,
        "before_after_patch_sources": sorted(patch_sources),
        "before_after_opencode_session_bound_count": opencode_session_bound_count,
        "opencode_safety_transform_attempt": attempt_summary,
        "opencode_preflight_proof_summary": public_packet_opencode_preflight_proof_summary(
            runtime,
            opencode_runtime_enabled=opencode_runtime_enabled,
        ),
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "OpenCode runtime and safety-transform attempt artifacts audit command-contract execution and "
            "candidate patch attempts. They do not make chat output semantic evidence; before/after patch "
            "origin remains the bound on-disk patch_origin evidence."
        ),
    }


def public_packet_opencode_preflight_proof_summary(
    runtime: dict[str, Any],
    *,
    opencode_runtime_enabled: bool,
) -> dict[str, Any]:
    summary = runtime.get("preflight_proof_summary")
    if isinstance(summary, dict):
        return json.loads(json.dumps(summary))
    return {
        "status": "absent",
        "required_when_opencode_runtime_enabled": opencode_runtime_enabled,
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "OpenCode preflight proof is absent; runtime output is not semantic evidence "
            "and does not increase translator coverage."
        ),
    }


def public_packet_opencode_attempt_summary(value: object, *, repo_root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "absent"}
    result: dict[str, Any] = {
        "path": value.get("path"),
        "sha256": value.get("sha256"),
        "status": value.get("status", "unknown"),
    }
    if value.get("status") != "present" or not isinstance(value.get("path"), str):
        return result
    try:
        payload = validator.load_json(resolve_input_path(Path(value["path"]), repo_root=repo_root))
    except (OSError, ValueError, json.JSONDecodeError):
        result["artifact_read_status"] = "failed"
        return result
    result["artifact_read_status"] = "passed"
    retry_hints = public_packet_opencode_retry_hints(payload)
    retry_statuses = [
        str(hint.get("status", "unknown")) for hint in retry_hints if isinstance(hint.get("status", "unknown"), str)
    ]
    if not retry_statuses:
        retry_status = "unknown"
    elif len(set(retry_statuses)) == 1:
        retry_status = retry_statuses[0]
    else:
        retry_status = "mixed"
    attempt_contract = payload.get("attempt_contract") if isinstance(payload.get("attempt_contract"), dict) else {}
    units = payload.get("safety_transform_units") if isinstance(payload.get("safety_transform_units"), list) else []
    result.update(
        {
            "attempt_status": payload.get("status", "unknown"),
            "accepted_retry_hint_status": retry_status,
            "accepted_retry_hint_statuses": retry_statuses,
            "rollback_ref_count": public_packet_opencode_rollback_ref_count(payload, retry_hints),
            "round_count": public_packet_opencode_round_count(payload, units),
            "max_repair_rounds": int(attempt_contract.get("max_repair_rounds", 0) or 0),
            "unit_count": len([unit for unit in units if isinstance(unit, dict)]),
        }
    )
    return result


def public_packet_opencode_retry_hints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    top_level = payload.get("accepted_retry_hint")
    if isinstance(top_level, dict):
        hints.append(top_level)
    units = payload.get("safety_transform_units")
    if isinstance(units, list):
        for unit in units:
            if not isinstance(unit, dict):
                continue
            retry_hint = unit.get("accepted_retry_hint")
            if isinstance(retry_hint, dict):
                hints.append(retry_hint)
    return hints


def public_packet_opencode_rollback_ref_count(payload: dict[str, Any], retry_hints: list[dict[str, Any]]) -> int:
    if isinstance(payload.get("rollback_ref_count"), int):
        return int(payload["rollback_ref_count"])
    count = 0
    for retry_hint in retry_hints:
        rollback_evidence = retry_hint.get("rollback_evidence")
        if isinstance(rollback_evidence, list):
            count += len(rollback_evidence)
    return count


def public_packet_opencode_round_count(payload: dict[str, Any], units: list[object]) -> int:
    if isinstance(payload.get("round_count"), int):
        return int(payload["round_count"])
    count = 0
    for unit in units:
        if not isinstance(unit, dict):
            continue
        rounds = unit.get("rounds")
        if isinstance(rounds, list):
            count += len(rounds)
    return count


def public_packet_workflow_metrics_summary(bundle: dict[str, Any]) -> dict[str, Any]:
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


def public_packet_must_not_claim(value: object) -> list[str]:
    claims = [str(item) for item in value] if isinstance(value, list) else []
    if "public_release_packet_is_not_semantic_gate" not in claims:
        claims.append("public_release_packet_is_not_semantic_gate")
    return claims


def artifact_ref_from_report_ref(value: object, *, repo_root: Path) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("path"), str):
        try:
            return artifact_ref(resolve_input_path(Path(value["path"]), repo_root=repo_root), repo_root=repo_root)
        except (OSError, ValueError):
            return {"path": value["path"], "status": "invalid"}
    return {"path": "unknown", "status": "absent"}


def select_entrypoints(config: dict[str, Any], entrypoint_ids: list[str]) -> list[dict[str, Any]]:
    raw_entrypoints = config.get("entrypoints")
    if not isinstance(raw_entrypoints, list) or not raw_entrypoints:
        raise SystemExit("judge config entrypoints must be a non-empty list")
    entrypoints = [entry for entry in raw_entrypoints if isinstance(entry, dict)]
    if not entrypoint_ids:
        return entrypoints
    by_id = {str(entry.get("id")): entry for entry in entrypoints}
    missing = [entrypoint_id for entrypoint_id in entrypoint_ids if entrypoint_id not in by_id]
    if missing:
        raise SystemExit(f"unknown judge entrypoint id(s): {', '.join(missing)}")
    return [by_id[entrypoint_id] for entrypoint_id in entrypoint_ids]


def configured_entrypoint_count(config: dict[str, Any]) -> int:
    entrypoints = config.get("entrypoints")
    return len([entry for entry in entrypoints if isinstance(entry, dict)]) if isinstance(entrypoints, list) else 0


def build_judge_run_summary(
    *,
    status: str,
    dry_run: bool,
    configured_entrypoint_count: int,
    config_archive: dict[str, Any],
    command_results: list[dict[str, Any]],
    validation: dict[str, Any],
    readiness_ref: dict[str, Any] | None,
    claim_boundary: dict[str, Any],
) -> dict[str, Any]:
    executed_count = len(command_results)
    all_entrypoints_executed = (
        not dry_run
        and status == "passed"
        and configured_entrypoint_count > 0
        and executed_count == configured_entrypoint_count
    )
    validation_status = str(validation.get("status", "unknown")) if isinstance(validation, dict) else "unknown"
    entrypoint_summaries = [
        {
            "id": result.get("id"),
            "purpose": result.get("purpose"),
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "proof_class": result.get("proof_class", "unknown"),
            "run_id": result.get("run_id", "unknown"),
            "judge_focus": result.get("judge_focus", []),
            "key_artifacts": result.get("key_artifacts", {}),
        }
        for result in command_results
    ]
    return {
        "report_kind": "judge-entrypoints-summary",
        "headline": (
            f"Judge entrypoints {status}: {executed_count}/{configured_entrypoint_count} "
            f"{'executed' if not dry_run else 'planned'}; semantic_gate=false"
        ),
        "readiness": {
            "status": status,
            "dry_run": dry_run,
            "all_entrypoints_executed": all_entrypoints_executed,
            "executed_count": executed_count,
            "configured_count": configured_entrypoint_count,
            "validation_status": validation_status,
            "readiness_report": readiness_ref,
        },
        "competition_config_archive": {
            "status": config_archive.get("status"),
            "root": config_archive.get("root"),
            "file_count": config_archive.get("file_count", 0),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_claim_source": claim_boundary.get("semantic_claim_source", "validator-owned-artifacts"),
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
        "entrypoints": entrypoint_summaries,
    }


def build_competition_config_archive(*, repo_root: Path) -> dict[str, Any]:
    root = validator.repo_path(COMPETITION_CONFIG_ROOT.as_posix(), repo_root=repo_root)
    files: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return {
            "report_kind": "competition-config-archive",
            "status": "missing",
            "root": COMPETITION_CONFIG_ROOT.as_posix(),
            "file_count": 0,
            "files": files,
            "claim_boundary": {
                "semantic_gate": False,
                "archive_is_semantic_gate": False,
            },
        }

    for path in sorted(candidate_config_files(root)):
        rel = validator.repo_relative(path, repo_root)
        files[rel] = {
            "path": rel,
            "status": "present",
            "sha256": validator.sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return {
        "report_kind": "competition-config-archive",
        "status": "present",
        "root": COMPETITION_CONFIG_ROOT.as_posix(),
        "file_count": len(files),
        "files": files,
        "claim_boundary": {
            "semantic_gate": False,
            "archive_is_semantic_gate": False,
            "boundary": "This archive binds repo-local competition configuration files for reproduction only.",
        },
    }


def candidate_config_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]


def run_entrypoint_command(
    entry: dict[str, Any],
    *,
    dry_run: bool,
    log_dir: Path,
    repo_root: Path,
    timeout_seconds: int,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    entry_id = str(entry.get("id", "unknown"))
    command = str(entry.get("command", ""))
    if not command:
        raise SystemExit(f"judge entrypoint missing command: {entry_id}")
    argv = shlex.split(command)
    effective_argv = argv if dry_run else resolve_local_entrypoint_argv(argv)
    stdout_path = log_dir / f"{safe_file_component(entry_id)}.stdout.log"
    stderr_path = log_dir / f"{safe_file_component(entry_id)}.stderr.log"
    result = {
        "id": entry_id,
        "purpose": entry.get("purpose"),
        "priority": entry.get("priority"),
        "proof_class": entry.get("proof_class", "unknown"),
        "run_id": entry.get("run_id", "unknown"),
        "judge_focus": list(entry.get("judge_focus", [])) if isinstance(entry.get("judge_focus"), list) else [],
        "key_artifacts": dict(entry.get("expected_artifacts", {})) if isinstance(entry.get("expected_artifacts"), dict) else {},
        "command": command,
        "argv": argv,
        "effective_argv": effective_argv,
        "timeout_seconds": timeout_seconds,
        "timeout_policy": {
            "scope": "entrypoint_command",
            "timeout_seconds": timeout_seconds,
            "timeout_exit_code": ENTRYPOINT_TIMEOUT_EXIT_CODE,
        },
        "exit_code": None if dry_run else 1,
        "logs": {
            "stdout": artifact_ref(stdout_path, repo_root=repo_root),
            "stderr": artifact_ref(stderr_path, repo_root=repo_root),
        },
    }
    if dry_run:
        result["status"] = "planned"
        return result

    try:
        completed = command_runner(effective_argv, cwd=repo_root, text=True, capture_output=True, timeout=timeout_seconds)
    except Exception as error:
        stdout_text = stream_text(getattr(error, "stdout", ""))
        stderr_text = stream_text(getattr(error, "stderr", ""))
        stderr_text += f"{type(error).__name__}: {error}\n"
        atomic_write_text(stdout_path, stdout_text)
        atomic_write_text(stderr_path, stderr_text)
        result["exit_code"] = command_exception_exit_code(error)
        result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        if isinstance(error, subprocess.TimeoutExpired):
            result["root_cause_key"] = "process_timeout"
        result["logs"] = {
            "stdout": artifact_ref(stdout_path, repo_root=repo_root),
            "stderr": artifact_ref(stderr_path, repo_root=repo_root),
        }
        return result

    atomic_write_text(stdout_path, completed.stdout or "")
    atomic_write_text(stderr_path, completed.stderr or "")
    result["exit_code"] = int(completed.returncode)
    result["status"] = "passed" if completed.returncode == 0 else "failed"
    result["logs"] = {
        "stdout": artifact_ref(stdout_path, repo_root=repo_root),
        "stderr": artifact_ref(stderr_path, repo_root=repo_root),
    }
    return result


def resolve_local_entrypoint_argv(argv: list[str]) -> list[str]:
    if len(argv) >= 2 and argv[0] == PORTABLE_PYTHON_COMMAND and argv[1] == "-B":
        return [*portable_python_command_argv(), *argv[1:]]
    return list(argv)


def portable_python_command_argv() -> list[str]:
    global _RESOLVED_PYTHON_COMMAND
    override = os.environ.get(PYTHON_COMMAND_OVERRIDE_ENV)
    if override:
        return shlex.split(override, posix=os.name != "nt")
    if _RESOLVED_PYTHON_COMMAND is not None:
        return list(_RESOLVED_PYTHON_COMMAND)
    candidates: list[list[str]] = [[PORTABLE_PYTHON_COMMAND], ["python"]]
    if os.name == "nt":
        candidates.append(["py", "-3"])
    for candidate in candidates:
        if python_command_is_runnable(candidate):
            _RESOLVED_PYTHON_COMMAND = candidate
            return list(candidate)
    _RESOLVED_PYTHON_COMMAND = [PORTABLE_PYTHON_COMMAND]
    return list(_RESOLVED_PYTHON_COMMAND)


def python_command_is_runnable(candidate: list[str]) -> bool:
    try:
        completed = subprocess.run(
            [*candidate, "-B", "-c", "import sys"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return int(completed.returncode) == 0


def resolve_input_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root.resolve())
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def resolve_output_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root.resolve())
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def artifact_ref(path: Path, *, repo_root: Path) -> dict[str, Any]:
    ref = {
        "path": validator.repo_relative(path, repo_root),
        "status": "present" if path.is_file() else "missing",
    }
    if path.is_file():
        ref["sha256"] = validator.sha256_file(path)
    return ref


def invalid_config_ref(path: Path, error: BaseException) -> dict[str, Any]:
    return {"path": path.name if path.is_absolute() else path.as_posix(), "status": "invalid", "error": str(error)}


def stream_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            fd = None
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def command_exception_exit_code(error: Exception) -> int:
    if isinstance(error, subprocess.TimeoutExpired):
        return ENTRYPOINT_TIMEOUT_EXIT_CODE
    if isinstance(error, OSError):
        return 127
    return 1


def safe_file_component(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip())
    return safe or "entrypoint"


if __name__ == "__main__":
    raise SystemExit(main())
