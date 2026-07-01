#!/usr/bin/env python3
"""Validate judge-facing harness entrypoint indexes."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sqlite3
import sys
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import validate_competition_run_summary

from validation.tools import milestone_release_report

DEFAULT_CONFIG = REPO_ROOT / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
COMPETITION_ENV_ROOT = "config/competition-env"
COMPETITION_ENV_BUNDLE_MANIFEST = Path("config") / "competition-env" / "bundle-manifest.json"
ROUTE_GOVERNANCE_METRICS_SCHEMA = REPO_ROOT / "validation" / "route-governance-metrics.schema.json"
LOCAL_ABSOLUTE_PATH = re.compile(
    r"(?:^|[^A-Za-z0-9_])(?:"
    r"[A-Za-z]:[\\/]|"
    r"/mnt/[A-Za-z]/|"
    r"/home/|/Users/|/tmp/|/var/|"
    r"\\\\wsl\$\\|"
    r"//wsl\$/|"
    r"\\\\wsl\.localhost\\|"
    r"//wsl\.localhost/"
    r")"
)
REQUIRED_HARNESS_FEATURES = (
    "h1_evaluate_one_click",
    "h2_multi_worker_fanout",
    "h3_precise_repair_self_heal",
    "h4_before_after_exhibit",
    "h5_context_management",
    "h6_judge_reports",
)
REQUIRED_AGENT_ROLES = ("planner", "worker", "repairer", "verifier", "reporter")
REQUIRED_CONTEXT_STAGES = ("plan", "translate", "verify", "repair")
REQUIRED_JUDGE_GRAPH_NODES = ("load_plan", "fanout_workers", "worker", "repair_retry", "merge", "report")
REQUIRED_COMPETITION_SMOKE_STEPS = (
    "environment-check",
    "vendored-clang-verification",
    "core-auto-evidence-validator",
    "evidence-governance",
    "translator-coverage-matrix",
    "milestone-release-report",
    "lightweight-unittest",
)
EXPECTED_ARTIFACT_REF_ALIASES = {
    "competition_summary": "competition_run_summary",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional repo-relative or local output path for a judge entrypoints readiness report.",
    )
    parser.add_argument(
        "--require-local-artifacts",
        action="store_true",
        help="Fail when expected target artifacts listed by the entrypoint index are not present locally.",
    )
    args = parser.parse_args()

    result = validate_config(
        args.config,
        require_local_artifacts=args.require_local_artifacts,
        repo_root=REPO_ROOT,
    )
    if args.out is not None:
        write_readiness_report(result, args.out, repo_root=REPO_ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


def write_readiness_report(result: dict[str, Any], out_path: Path, *, repo_root: Path) -> dict[str, Any]:
    if out_path.is_absolute():
        resolved = out_path.resolve()
        resolved.relative_to(repo_root.resolve())
        path = resolved
        path_text = repo_relative(path, repo_root)
    else:
        path_text = out_path.as_posix()
        assert_repo_relative_posix(path_text)
        path = repo_path(path_text, repo_root=repo_root)
    report = {
        "schema_version": 1,
        "report_kind": "judge-entrypoints-readiness",
        "status": result.get("status"),
        "semantic_gate": False,
        "evidence_boundary": (
            "This readiness report persists judge entrypoint validation results. "
            "Semantic acceptance remains owned by competition summaries, workflow metrics, and validators."
        ),
        "readiness_report_path": path_text,
        "claim_boundary": result.get("claim_boundary", {}),
        "entrypoint_count": result.get("entrypoint_count", 0),
        "proof_class_contract": result.get("proof_class_contract", {}),
        "source_pin_contract": result.get("source_pin_contract", {}),
        "competition_env_bundle_contract": result.get("competition_env_bundle_contract", {}),
        "test_contract": result.get("test_contract", {}),
        "validation": result,
    }
    report["summary"] = build_readiness_summary(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_readiness_summary(result: dict[str, Any]) -> dict[str, Any]:
    entrypoints = result.get("entrypoints") if isinstance(result.get("entrypoints"), list) else []
    configured_count = int(result.get("entrypoint_count", len(entrypoints)) or 0)
    status = str(result.get("status", "unknown"))
    claim_boundary = result.get("claim_boundary") if isinstance(result.get("claim_boundary"), dict) else {}
    entrypoint_summaries = []
    for entry in entrypoints:
        if not isinstance(entry, dict):
            continue
        entrypoint_summaries.append(
            {
                "id": entry.get("id"),
                "purpose": entry.get("purpose"),
                "status": entry.get("status"),
                "proof_class": entry.get("proof_class", "unknown"),
                "run_id": entry.get("run_id", "unknown"),
                "judge_focus": entry.get("judge_focus", []),
            }
        )
    return {
        "report_kind": "judge-entrypoints-summary",
        "headline": f"{configured_count} judge entrypoints ready; status={status}; semantic_gate=false",
        "readiness": {
            "status": status,
            "configured_count": configured_count,
            "validation_status": status,
        },
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_claim_source": claim_boundary.get("semantic_claim_source", "accepted_evidence_binding"),
            "generated_draft_semantic_pass": claim_boundary.get("generated_draft_semantic_pass", False),
            "translation_coverage_numerator": claim_boundary.get("translation_coverage_numerator", 0),
        },
        "entrypoints": entrypoint_summaries,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def repo_path(path_text: str, *, repo_root: Path) -> Path:
    assert_repo_relative_posix(path_text)
    return repo_root / Path(*PurePosixPath(path_text).parts)


def assert_repo_relative_posix(path_text: str) -> None:
    if not isinstance(path_text, str) or not path_text:
        raise ValueError("path must be a non-empty string")
    path = PurePosixPath(path_text)
    if "\\" in path_text or path.is_absolute() or path_text.startswith("~"):
        raise ValueError(f"path must be repo-relative POSIX: {path_text}")
    if len(path_text) >= 2 and path_text[1] == ":":
        raise ValueError(f"path must not use a drive prefix: {path_text}")
    if ".." in path.parts:
        raise ValueError(f"path must not contain parent traversal: {path_text}")


def assert_no_local_absolute_path(text: str) -> None:
    if not isinstance(text, str):
        raise ValueError("command/text must be a string")
    if LOCAL_ABSOLUTE_PATH.search(text):
        raise ValueError(f"text contains local absolute path: {text}")


def json_path(parts: tuple[str, ...]) -> str:
    return "$" + "".join(f".{part}" for part in parts)


def is_allowed_host_trace_path(parts: tuple[str, ...]) -> bool:
    if any(part == "argv" and index > 0 and parts[index - 1] == "merge_execution" for index, part in enumerate(parts)):
        return True
    return (
        len(parts) >= 4
        and parts[-1] == "value"
        and parts[-3] == "diagnostic_host_metadata"
        and parts[-4] == "portability"
    )


def validate_local_absolute_path_policy(payload: Any, *, label: str) -> dict[str, Any]:
    allowed: list[str] = []
    forbidden: list[str] = []

    def visit(value: Any, parts: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, (*parts, str(key)))
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*parts, str(index)))
            return
        if isinstance(value, str) and LOCAL_ABSOLUTE_PATH.search(value):
            location = json_path(parts)
            if is_allowed_host_trace_path(parts):
                allowed.append(location)
            else:
                forbidden.append(location)

    visit(payload, ())
    if forbidden:
        raise ValueError(f"{label} contains forbidden local absolute path at {forbidden}")
    return {
        "status": "passed",
        "host_trace_allowed_count": len(allowed),
        "host_trace_allowed_locations": allowed,
    }


def validate_ref(ref: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    path_text = ref.get("path")
    expected_sha = ref.get("sha256")
    if not isinstance(path_text, str) or not isinstance(expected_sha, str):
        raise ValueError("artifact ref must include path and sha256 strings")
    path = repo_path(path_text, repo_root=repo_root)
    if not path.is_file():
        raise ValueError(f"artifact ref path does not exist: {path_text}")
    actual_sha = sha256_file(path)
    if expected_sha != actual_sha:
        raise ValueError(f"artifact ref sha256 mismatch for {path_text}: {expected_sha} != {actual_sha}")
    return {"path": path_text, "sha256": actual_sha, "status": "present"}


def validate_competition_env_bundle_contract(
    config: dict[str, Any],
    *,
    repo_root: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path or COMPETITION_ENV_BUNDLE_MANIFEST
    manifest_path = manifest_path if manifest_path.is_absolute() else repo_root / manifest_path
    if not manifest_path.is_file():
        raise ValueError("competition env bundle manifest is missing")
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("competition env bundle schema_version must be 1")
    if manifest.get("report_kind") != "competition-env-bundle":
        raise ValueError("competition env bundle report_kind must be competition-env-bundle")
    if manifest.get("bundle_root") != COMPETITION_ENV_ROOT:
        raise ValueError(f"competition env bundle bundle_root must be {COMPETITION_ENV_ROOT}")
    boundary = require_object(manifest.get("claim_boundary"), "competition env bundle claim_boundary")
    if boundary.get("semantic_gate") is not False:
        raise ValueError("competition env bundle claim_boundary.semantic_gate must be false")
    if boundary.get("archive_is_semantic_gate") is not False:
        raise ValueError("competition env bundle claim_boundary.archive_is_semantic_gate must be false")

    environment_profile = require_object(config.get("environment_profile"), "environment_profile")
    canonical_profile = require_object(
        manifest.get("canonical_environment_profile"),
        "competition env bundle canonical_environment_profile",
    )
    for field in ("path", "profile_id", "sha256"):
        if canonical_profile.get(field) != environment_profile.get(field):
            raise ValueError(f"competition env bundle canonical_environment_profile.{field} must match environment_profile")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("competition env bundle files must be a non-empty list")
    result_files: dict[str, dict[str, Any]] = {}
    roles: dict[str, str] = {}
    for file_entry in files:
        entry = require_object(file_entry, "competition env bundle files[]")
        path_text = require_string(entry.get("path"), "competition env bundle files[].path")
        role = require_string(entry.get("role"), f"competition env bundle {path_text}.role")
        expected_sha = require_string(entry.get("sha256"), f"competition env bundle {path_text}.sha256")
        assert_repo_relative_posix(path_text)
        if not path_text.startswith(f"{COMPETITION_ENV_ROOT}/"):
            raise ValueError(f"competition env bundle file must stay under {COMPETITION_ENV_ROOT}: {path_text}")
        if path_text in result_files:
            raise ValueError(f"competition env bundle duplicate file: {path_text}")
        path = repo_path(path_text, repo_root=repo_root)
        if not path.is_file():
            raise ValueError(f"competition env bundle file is missing: {path_text}")
        actual_sha = sha256_file(path)
        if expected_sha != actual_sha:
            raise ValueError(f"competition env bundle file sha256 mismatch for {path_text}: {expected_sha} != {actual_sha}")
        result_files[path_text] = {
            "path": path_text,
            "role": role,
            "sha256": actual_sha,
            "status": "present",
        }
        roles[path_text] = role

    required_paths = {
        "config/competition-env/environment.json",
        "config/competition-env/env.sh",
        "config/competition-env/toolchain-check.sh",
        "config/competition-env/smoke.sh",
        "config/competition-env/apt/sources.list",
        "config/competition-env/pip/pip.conf",
        "config/competition-env/npm/.npmrc",
        "config/competition-env/cargo/config.toml",
        "config/competition-env/rust/rust-toolchain.toml",
        "config/competition-env/judge-entrypoints/flashdb-harness.json",
        "config/competition-env/review-checklists/flashdb-harness-internal-review.json",
        "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
    }
    missing_required = sorted(required_paths - set(result_files))
    if missing_required:
        raise ValueError(f"competition env bundle missing required files: {missing_required}")

    return {
        "status": "passed",
        "report_kind": "competition-env-bundle",
        "manifest": {
            "path": repo_relative(manifest_path, repo_root),
            "sha256": sha256_file(manifest_path),
        },
        "bundle_root": COMPETITION_ENV_ROOT,
        "canonical_environment_profile": {
            "path": str(canonical_profile.get("path")),
            "profile_id": str(canonical_profile.get("profile_id")),
            "sha256": str(canonical_profile.get("sha256")),
        },
        "semantic_gate": False,
        "file_count": len(result_files),
        "files": sorted(result_files),
        "roles": roles,
    }


def validate_entrypoint_review_checklist_ref(entry: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    review_ref = entry.get("review_checklist")
    if review_ref is None:
        return {
            "ref": {"status": "skipped", "reason": "review_checklist not declared"},
            "contract": {"status": "skipped", "reason": "review_checklist not declared"},
        }
    if not isinstance(review_ref, dict):
        raise ValueError(f"{entry.get('id')}.review_checklist must be an object")
    validated_ref = validate_ref(review_ref, repo_root=repo_root)
    review_path = repo_path(validated_ref["path"], repo_root=repo_root)
    payload = load_json(review_path)
    try:
        review_contract = milestone_release_report.validate_review_checklist_payload(
            payload,
            review_path=review_path,
        )
    except SystemExit as error:
        raise ValueError(f"{entry.get('id')}.review_checklist invalid: {error}") from error
    if review_ref.get("report_kind") and review_ref.get("report_kind") != payload.get("report_kind"):
        raise ValueError(f"{entry.get('id')}.review_checklist report_kind must match payload")
    boundary = require_object(
        review_contract.get("claim_boundary"),
        f"{entry.get('id')}.review_checklist.claim_boundary",
    )
    if boundary.get("semantic_gate") is not False:
        raise ValueError(f"{entry.get('id')}.review_checklist claim_boundary.semantic_gate must be false")
    if boundary.get("review_is_semantic_acceptance") is not False:
        raise ValueError(
            f"{entry.get('id')}.review_checklist claim_boundary.review_is_semantic_acceptance must be false"
        )
    return {
        "ref": {
            **validated_ref,
            "report_kind": str(payload.get("report_kind")),
            "review_id": str(review_contract.get("review_id", "")),
            "reviewer": review_contract.get("reviewer", {}),
            "review_status": str(review_contract.get("status", "unknown")),
        },
        "contract": {
            "status": "passed",
            "semantic_gate": False,
            "review_is_semantic_acceptance": False,
            "required_items": sorted(review_contract.get("required_items", [])),
            "item_statuses": review_contract.get("item_statuses", {}),
        },
    }


def validate_expected_artifacts(
    artifacts: dict[str, Any],
    *,
    require_local_artifacts: bool,
    repo_root: Path,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if not isinstance(artifacts, dict):
        raise ValueError("expected_artifacts must be an object")
    for name, path_text in sorted(artifacts.items()):
        if not isinstance(path_text, str):
            raise ValueError(f"expected artifact path must be a string: {name}")
        try:
            assert_repo_relative_posix(path_text)
        except ValueError as error:
            raise ValueError(f"expected_artifacts.{name}: {error}") from error
        path = repo_path(path_text, repo_root=repo_root)
        artifact = {"path": path_text, "status": "present" if path.is_file() else "missing"}
        if path.is_file():
            artifact["sha256"] = sha256_file(path)
        elif require_local_artifacts:
            raise ValueError(f"expected artifact is missing: {path_text}")
        result[str(name)] = artifact
    return result


def is_competition_smoke_entrypoint(entry: dict[str, Any]) -> bool:
    return entry.get("entrypoint_type") == "competition_environment_smoke"


def parsed_command_flags(command: str) -> dict[str, str]:
    flags: dict[str, str] = {}
    parts = shlex.split(command, posix=True)
    index = 0
    while index < len(parts):
        part = parts[index]
        if part.startswith("--") and index + 1 < len(parts) and not parts[index + 1].startswith("--"):
            flags[part] = parts[index + 1]
            index += 2
            continue
        index += 1
    return flags


def require_command_flag(flags: dict[str, str], flag: str, label: str) -> str:
    value = flags.get(flag)
    if not value:
        raise ValueError(f"{label} command must include {flag}")
    return value


def validate_competition_smoke_entrypoint_contract(entry: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(entry.get("id"))
    command = require_string(entry.get("command"), f"{entry_id}.command")
    argv = shlex.split(command, posix=True)
    if "validation/tools/run_competition_smoke.py" not in argv:
        raise ValueError(f"{entry_id} command must run validation/tools/run_competition_smoke.py")
    flags = parsed_command_flags(command)
    proof_class = require_command_flag(flags, "--proof-class", f"{entry_id}.command")
    run_id = require_command_flag(flags, "--run-id", f"{entry_id}.command")
    out_root = require_command_flag(flags, "--out-root", f"{entry_id}.command")
    if proof_class != entry.get("proof_class"):
        raise ValueError(f"{entry_id} command --proof-class must match entrypoint proof_class")
    if run_id != entry.get("run_id"):
        raise ValueError(f"{entry_id} command --run-id must match entrypoint run_id")
    if proof_class == "competition-exact" and "--confirm-competition-exact" not in argv:
        raise ValueError(f"{entry_id} competition-exact smoke requires --confirm-competition-exact")
    contract = require_object(entry.get("smoke_contract"), f"{entry_id}.smoke_contract")
    if contract.get("semantic_gate") is not False:
        raise ValueError(f"{entry_id}.smoke_contract.semantic_gate must be false")
    if contract.get("generated_draft_semantic_pass") is not False:
        raise ValueError(f"{entry_id}.smoke_contract.generated_draft_semantic_pass must be false")
    if contract.get("translation_coverage_numerator") != 0:
        raise ValueError(f"{entry_id}.smoke_contract.translation_coverage_numerator must be 0")
    if contract.get("semantic_acceptance_boundary") != "does_not_translate_new_slices":
        raise ValueError(f"{entry_id}.smoke_contract.semantic_acceptance_boundary must be does_not_translate_new_slices")
    expected_artifact_paths = validate_expected_artifacts_under_out_root(entry, out_root=out_root)
    return {
        "status": "passed",
        "proof_class": proof_class,
        "run_id": run_id,
        "reproduction_out_root": out_root,
        "expected_artifact_count": len(expected_artifact_paths),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
    }


def validate_competition_smoke_summary_contract(
    payload: dict[str, Any],
    *,
    expected_artifacts: dict[str, Any],
    environment_profile: dict[str, Any] | None = None,
    entrypoint_proof_class: str | None = None,
    entrypoint_run_id: str | None = None,
    repo_root: Path = REPO_ROOT,
    verify_command_log_sha: bool = False,
) -> dict[str, Any]:
    if payload.get("report_kind") != "competition-smoke-summary":
        raise ValueError("competition_smoke_summary report_kind must be competition-smoke-summary")
    proof_class = require_string(payload.get("proof_class"), "competition_smoke_summary.proof_class")
    if entrypoint_proof_class is not None and proof_class != entrypoint_proof_class:
        raise ValueError("competition_smoke_summary proof_class must match entrypoint proof_class")
    if entrypoint_run_id is not None and payload.get("run_id") != entrypoint_run_id:
        raise ValueError("competition_smoke_summary run_id must match entrypoint run_id")
    validate_competition_smoke_profile_binding(payload, environment_profile=environment_profile)
    boundary = require_object(payload.get("claim_boundary"), "competition_smoke_summary claim_boundary")
    if boundary.get("semantic_gate") is not False:
        raise ValueError("competition_smoke_summary claim_boundary.semantic_gate must be false")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("competition_smoke_summary claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("competition_smoke_summary claim_boundary.translation_coverage_numerator must be 0")
    if "slices" in payload:
        raise ValueError("competition_smoke_summary must not claim translated slices")
    smoke_entrypoint = require_object(payload.get("smoke_entrypoint"), "competition_smoke_summary smoke_entrypoint")
    if smoke_entrypoint.get("semantic_acceptance_boundary") != "does_not_translate_new_slices":
        raise ValueError("competition_smoke_summary smoke_entrypoint.semantic_acceptance_boundary must be does_not_translate_new_slices")
    validate_competition_smoke_timeout_policy(payload)
    final_gate = require_object(payload.get("final_gate"), "competition_smoke_summary final_gate")
    if final_gate.get("status") != "passed":
        raise ValueError("competition_smoke_summary final_gate.status must be passed")
    validate_competition_smoke_proof_class_environment(payload)
    validate_competition_exact_smoke_summary(payload)
    validate_competition_smoke_step_contract(payload)
    validate_competition_smoke_artifact_roots(payload)

    assert_expected_smoke_path(
        payload.get("vendored_clang_verification"),
        "path",
        expected_artifacts,
        "vendored_clang_verification",
        "competition_smoke_summary.vendored_clang_verification.path",
    )
    reports = require_object(payload.get("reports"), "competition_smoke_summary reports")
    assert_expected_smoke_path(
        reports.get("evidence_governance"),
        "path",
        expected_artifacts,
        "evidence_governance_report",
        "competition_smoke_summary.reports.evidence_governance.path",
    )
    assert_expected_smoke_path(
        reports.get("translator_coverage_matrix"),
        "path",
        expected_artifacts,
        "translator_coverage_matrix",
        "competition_smoke_summary.reports.translator_coverage_matrix.path",
    )
    assert_expected_smoke_path(
        payload.get("milestone_release_report"),
        "path",
        expected_artifacts,
        "milestone_release_report",
        "competition_smoke_summary.milestone_release_report.path",
    )
    milestone = require_object(payload.get("milestone_release_report"), "competition_smoke_summary milestone_release_report")
    if milestone.get("semantic_acceptance_claim") is not False:
        raise ValueError("competition_smoke_summary milestone_release_report.semantic_acceptance_claim must be false")
    command_log = require_object(payload.get("command_log"), "competition_smoke_summary.command_log")
    assert_expected_smoke_path(
        command_log,
        "path",
        expected_artifacts,
        "command_log",
        "competition_smoke_summary.command_log.path",
    )
    command_log_sha = validate_sha256_hex(
        command_log.get("sha256"),
        "competition_smoke_summary.command_log.sha256",
    )
    command_log_path = repo_path(
        require_string(expected_artifacts.get("command_log"), "expected_artifacts.command_log"),
        repo_root=repo_root,
    )
    if verify_command_log_sha and command_log_path.is_file():
        actual_sha = sha256_file(command_log_path)
        if actual_sha != command_log_sha:
            raise ValueError("competition_smoke_summary.command_log.sha256 must match command_log artifact")
    for step in payload.get("steps", []):
        step_name = require_string(step.get("step"), "competition_smoke_summary.steps[].step")
        if step.get("log_path") != command_log["path"]:
            raise ValueError(f"competition_smoke_summary step {step_name}.log_path must match command_log.path")
    return {
        "status": "passed",
        "proof_class": proof_class,
        "profile_sha256": payload.get("profile_sha256"),
        "command_log_sha256": command_log_sha,
        "final_gate": final_gate.get("status"),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
    }


def validate_competition_smoke_artifact_roots(payload: dict[str, Any]) -> dict[str, Any]:
    roots = payload.get("artifact_roots", [])
    if roots is None:
        roots = []
    if not isinstance(roots, list):
        raise ValueError("competition_smoke_summary artifact_roots must be a list")
    for index, root in enumerate(roots):
        assert_repo_relative_posix(require_string(root, f"competition_smoke_summary artifact_roots[{index}]"))
    return {"status": "passed", "root_count": len(roots)}


def validate_competition_smoke_command_log_contract(command_log_path: Path) -> dict[str, Any]:
    if not command_log_path.is_file():
        raise ValueError("competition_smoke_command_log path must exist")
    checked_entries = 0
    with command_log_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"competition_smoke_command_log line {line_number} must be valid JSON") from error
            if not isinstance(entry, dict):
                raise ValueError(f"competition_smoke_command_log line {line_number} must be an object")
            command = entry.get("command")
            if not isinstance(command, list) or not command:
                raise ValueError(f"competition_smoke_command_log line {line_number} command must be a non-empty list")
            for index, argument in enumerate(command):
                if not isinstance(argument, str):
                    raise ValueError(
                        f"competition_smoke_command_log line {line_number} command[{index}] must be a string"
                    )
                if LOCAL_ABSOLUTE_PATH.search(argument):
                    raise ValueError(
                        "competition_smoke_command_log command contains forbidden local absolute path"
                    )
            checked_entries += 1
    if checked_entries == 0:
        raise ValueError("competition_smoke_command_log must contain at least one entry")
    return {"status": "passed", "entry_count": checked_entries}


def validate_vendored_clang_verification_contract(
    payload: dict[str, Any],
    *,
    smoke_summary: dict[str, Any] | None = None,
    environment_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise ValueError("vendored_clang_verification schema_version must be 1")
    if payload.get("artifact_kind") != "vendored-clang-verification":
        raise ValueError("vendored_clang_verification artifact_kind must be vendored-clang-verification")
    proof_class = require_string(payload.get("proof_class"), "vendored_clang_verification.proof_class")
    status = require_string(payload.get("status"), "vendored_clang_verification.status")
    final_gate = require_object(payload.get("final_gate"), "vendored_clang_verification.final_gate")
    clang = require_object(payload.get("clang"), "vendored_clang_verification.clang")
    clang_path = clang.get("path")
    if clang_path is not None:
        try:
            assert_repo_relative_posix(require_string(clang_path, "vendored_clang_verification.clang.path"))
        except ValueError as error:
            raise ValueError("vendored_clang_verification clang.path must be repo-relative POSIX") from error
    clang_lane_verified = payload.get("clang_lane_verified")
    if not isinstance(clang_lane_verified, bool):
        raise ValueError("vendored_clang_verification.clang_lane_verified must be boolean")

    if environment_profile is not None:
        expected_profile_id = require_string(environment_profile.get("profile_id"), "environment_profile.profile_id")
        expected_sha256 = require_string(environment_profile.get("sha256"), "environment_profile.sha256")
        if payload.get("profile_id") != expected_profile_id:
            raise ValueError("vendored_clang_verification profile_id must match environment_profile.profile_id")
        if payload.get("profile_sha256") != expected_sha256:
            raise ValueError("vendored_clang_verification profile_sha256 must match environment_profile.sha256")

    if smoke_summary is not None:
        smoke_proof_class = require_string(smoke_summary.get("proof_class"), "competition_smoke_summary.proof_class")
        if proof_class != smoke_proof_class:
            raise ValueError("vendored_clang_verification proof_class must match competition_smoke_summary.proof_class")
        smoke_profile_match = require_object(
            smoke_summary.get("competition_profile_match"),
            "competition_smoke_summary.competition_profile_match",
        )
        smoke_clang_verified = smoke_profile_match.get("clang_lane_verified")
        if not isinstance(smoke_clang_verified, bool):
            raise ValueError("competition_smoke_summary.competition_profile_match.clang_lane_verified must be boolean")
        if clang_lane_verified != smoke_clang_verified:
            raise ValueError("vendored_clang_verification clang_lane_verified must match competition_smoke_summary")
        top_level_clang_verified = smoke_summary.get("clang_lane_verified")
        if top_level_clang_verified is not None and top_level_clang_verified != clang_lane_verified:
            raise ValueError("vendored_clang_verification clang_lane_verified must match competition_smoke_summary")

    if status == "missing":
        if payload.get("reason") != "missing_clang_path":
            raise ValueError("vendored_clang_verification missing status requires reason=missing_clang_path")
        if clang.get("source") != "missing":
            raise ValueError("vendored_clang_verification missing status requires clang.source=missing")
        if clang_lane_verified is not False:
            raise ValueError("vendored_clang_verification missing status requires clang_lane_verified=false")
        if proof_class == "competition-exact":
            if payload.get("clang_required") is not True:
                raise ValueError("vendored_clang_verification competition-exact missing status requires clang_required=true")
            if final_gate.get("status") != "failed":
                raise ValueError("vendored_clang_verification competition-exact missing status must fail final_gate")
        elif final_gate.get("status") != "passed":
            raise ValueError("vendored_clang_verification non-exact missing status must keep final_gate passed")
    elif status == "passed":
        if clang_lane_verified is not True:
            raise ValueError("vendored_clang_verification passed status requires clang_lane_verified=true")
        if clang_path is None:
            raise ValueError("vendored_clang_verification passed status requires clang.path")
        if final_gate.get("status") != "passed":
            raise ValueError("vendored_clang_verification passed status requires final_gate.status=passed")
    elif status == "failed":
        if final_gate.get("status") != "failed":
            raise ValueError("vendored_clang_verification failed status requires final_gate.status=failed")
    else:
        raise ValueError("vendored_clang_verification.status must be passed, missing, or failed")

    return {
        "status": "passed",
        "proof_class": proof_class,
        "clang_lane_verified": clang_lane_verified,
        "verification_status": status,
        "final_gate": final_gate.get("status"),
    }


def validate_competition_smoke_timeout_policy(payload: dict[str, Any]) -> None:
    timeout_policy = payload.get("timeout_policy")
    if not isinstance(timeout_policy, dict):
        raise ValueError("competition_smoke_summary timeout_policy must be an object")
    timeout_seconds = timeout_policy.get("per_step_timeout_seconds")
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise ValueError("competition_smoke_summary timeout_policy.per_step_timeout_seconds must be a positive integer")
    if timeout_policy.get("timeout_exit_code") != 124:
        raise ValueError("competition_smoke_summary timeout_policy.timeout_exit_code must be 124")
    if timeout_policy.get("timeout_is_final_gate_failure") is not True:
        raise ValueError("competition_smoke_summary timeout_policy.timeout_is_final_gate_failure must be true")


def validate_competition_smoke_proof_class_environment(payload: dict[str, Any]) -> None:
    proof_class = require_string(payload.get("proof_class"), "competition_smoke_summary.proof_class")
    environment = require_object(
        payload.get("execution_environment"),
        "competition_smoke_summary.execution_environment",
    )
    if proof_class == "ci-approximation" and environment.get("detected_ci") is not True:
        raise ValueError(
            "competition_smoke_summary proof_class=ci-approximation requires "
            "execution_environment.detected_ci=true"
        )
    if proof_class == "wsl-local-simulation" and environment.get("detected_wsl") is not True:
        raise ValueError(
            "competition_smoke_summary proof_class=wsl-local-simulation requires "
            "execution_environment.detected_wsl=true"
        )


def validate_competition_smoke_step_contract(payload: dict[str, Any]) -> dict[str, Any]:
    proof_class = require_string(payload.get("proof_class"), "competition_smoke_summary.proof_class")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("competition_smoke_summary steps must be a non-empty list")
    observed_steps: dict[str, dict[str, Any]] = {}
    for step_value in steps:
        step = require_object(step_value, "competition_smoke_summary.steps[]")
        name = require_string(step.get("step"), "competition_smoke_summary.steps[].step")
        if name in observed_steps:
            raise ValueError(f"competition_smoke_summary steps duplicate gate: {name}")
        status = require_string(step.get("status"), f"competition_smoke_summary step {name}.status")
        if step.get("timed_out") is True:
            raise ValueError(f"competition_smoke_summary step {name} timed_out cannot be in a passed summary")
        if not isinstance(step.get("returncode"), int):
            raise ValueError(f"competition_smoke_summary step {name}.returncode must be an integer")
        assert_repo_relative_posix(require_string(step.get("log_path"), f"competition_smoke_summary step {name}.log_path"))
        if status == "degraded":
            if name != "environment-check" or proof_class == "competition-exact":
                raise ValueError(f"competition_smoke_summary step {name} cannot be degraded for proof_class={proof_class}")
            if step.get("proof_class_effect") != "exactness_blocker":
                raise ValueError("competition_smoke_summary environment-check degradation must record exactness_blocker")
        elif status != "passed":
            raise ValueError(f"competition_smoke_summary step {name}.status must be passed")
        observed_steps[name] = step
    missing = [step for step in REQUIRED_COMPETITION_SMOKE_STEPS if step not in observed_steps]
    if missing:
        raise ValueError(f"competition_smoke_summary steps missing required gates: {missing}")
    return {
        "status": "passed",
        "required_steps": list(REQUIRED_COMPETITION_SMOKE_STEPS),
    }


def validate_competition_smoke_profile_binding(
    payload: dict[str, Any],
    *,
    environment_profile: dict[str, Any] | None,
) -> None:
    if environment_profile is None:
        return
    expected_sha256 = require_string(environment_profile.get("sha256"), "environment_profile.sha256")
    expected_profile_id = require_string(environment_profile.get("profile_id"), "environment_profile.profile_id")
    observed_profile_id = require_string(payload.get("profile_id"), "competition_smoke_summary.profile_id")
    if observed_profile_id != expected_profile_id:
        raise ValueError("competition_smoke_summary profile_id must match environment_profile.profile_id")
    observed_sha256 = require_string(payload.get("profile_sha256"), "competition_smoke_summary.profile_sha256")
    if observed_sha256 != expected_sha256:
        raise ValueError("competition_smoke_summary profile_sha256 must match environment_profile.sha256")

    match = require_object(
        payload.get("competition_profile_match"),
        "competition_smoke_summary.competition_profile_match",
    )
    match_profile_id = require_string(
        match.get("profile_id"),
        "competition_smoke_summary.competition_profile_match.profile_id",
    )
    if match_profile_id != expected_profile_id:
        raise ValueError(
            "competition_smoke_summary competition_profile_match.profile_id "
            "must match environment_profile.profile_id"
        )
    match_sha256 = require_string(
        match.get("profile_sha256_actual"),
        "competition_smoke_summary.competition_profile_match.profile_sha256_actual",
    )
    if match_sha256 != expected_sha256:
        raise ValueError(
            "competition_smoke_summary competition_profile_match.profile_sha256_actual "
            "must match environment_profile.sha256"
        )


def validate_competition_summary_entrypoint_contract(
    payload: dict[str, Any],
    *,
    expected_artifacts: dict[str, Any],
    summary_path: Path | None = None,
    environment_profile: dict[str, Any] | None = None,
    entrypoint_proof_class: str | None = None,
    entrypoint_run_id: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise ValueError("competition_summary.schema_version must be 1")

    proof_class = require_string(payload.get("proof_class"), "competition_summary.proof_class")
    if entrypoint_proof_class is not None and proof_class != entrypoint_proof_class:
        raise ValueError("competition_summary proof_class must match entrypoint proof_class")
    run_id = require_string(payload.get("run_id"), "competition_summary.run_id")
    if entrypoint_run_id is not None and run_id != entrypoint_run_id:
        raise ValueError("competition_summary run_id must match entrypoint run_id")

    profile_id = require_string(payload.get("profile_id"), "competition_summary.profile_id")
    profile_sha256 = validate_sha256_hex(payload.get("profile_sha256"), "competition_summary.profile_sha256")
    if environment_profile is not None:
        expected_profile_id = require_string(environment_profile.get("profile_id"), "environment_profile.profile_id")
        if profile_id != expected_profile_id:
            raise ValueError("competition_summary profile_id must match environment_profile.profile_id")
        expected_sha256 = validate_sha256_hex(environment_profile.get("sha256"), "environment_profile.sha256")
        if profile_sha256 != expected_sha256:
            raise ValueError("competition_summary profile_sha256 must match environment_profile.sha256")

    result: dict[str, Any] = {
        "status": "passed",
        "profile_id": profile_id,
        "profile_sha256": profile_sha256,
        "proof_class": proof_class,
        "run_id": run_id,
    }

    final_gate = payload.get("final_gate")
    if final_gate is not None:
        final_gate_payload = require_object(final_gate, "competition_summary.final_gate")
        final_gate_status = require_string(
            final_gate_payload.get("status"),
            "competition_summary.final_gate.status",
        )
        if final_gate_status not in {"passed", "failed"}:
            raise ValueError("competition_summary final_gate.status must be passed or failed")
        result["final_gate_status"] = final_gate_status

    workflow_metrics = payload.get("workflow_metrics")
    if isinstance(workflow_metrics, dict):
        binding = validate_artifact_binding_shape(
            workflow_metrics,
            "competition_summary.workflow_metrics",
            repo_root=repo_root,
        )
        expected_workflow_path = expected_artifacts.get("workflow_metrics")
        if expected_workflow_path is not None and binding["path"] != expected_workflow_path:
            raise ValueError("competition_summary workflow_metrics.path must match expected_artifacts.workflow_metrics")
        result["workflow_metrics"] = binding

    if summary_path is not None:
        try:
            deep_validation = validate_competition_run_summary.validate_summary(
                summary_path,
                repo_root=repo_root or REPO_ROOT,
            )
        except SystemExit as error:
            raise ValueError(f"competition_summary deep validation failed: {error}") from error
        result["deep_validation"] = deep_validation

    return result


def validate_competition_exact_smoke_summary(payload: dict[str, Any]) -> None:
    if payload.get("proof_class") != "competition-exact":
        return

    def fail(detail: str) -> None:
        raise ValueError(
            "competition_smoke_summary proof_class=competition-exact requires exact host evidence: "
            f"{detail}"
        )

    environment = require_object(
        payload.get("execution_environment"),
        "competition_smoke_summary.execution_environment",
    )
    if environment.get("detected_ci") is True:
        fail("execution_environment.detected_ci must be false")
    if environment.get("detected_wsl") is True:
        fail("execution_environment.detected_wsl must be false")
    environment_kind = str(environment.get("kind", ""))
    if str(environment.get("system", "")).lower() == "windows" or environment_kind in {"windows-local", "local"}:
        fail("execution_environment must not be local Windows")
    if environment.get("competition_exact_host_attested") is not True:
        fail("execution_environment.competition_exact_host_attested must be true")

    profile_match = require_object(
        payload.get("competition_profile_match"),
        "competition_smoke_summary.competition_profile_match",
    )
    for field in (
        "os_name_match",
        "kernel_match",
        "python_version_match",
        "clang_lane_verified",
        "cargo_mirror_config_present",
    ):
        if profile_match.get(field) is not True:
            fail(f"competition_profile_match.{field} must be true")

    deviations = payload.get("environment_deviations", [])
    if not isinstance(deviations, list):
        raise ValueError("competition_smoke_summary.environment_deviations must be a list")
    for deviation in deviations:
        if isinstance(deviation, dict) and deviation.get("severity") == "proof-class-limiting":
            fail("environment_deviations must not include proof-class-limiting entries")


def assert_expected_smoke_path(
    container: Any,
    field: str,
    expected_artifacts: dict[str, Any],
    expected_name: str,
    label: str,
) -> None:
    payload = require_object(container, label.rsplit(".", 1)[0])
    observed = require_string(payload.get(field), label)
    expected = require_string(expected_artifacts.get(expected_name), f"expected_artifacts.{expected_name}")
    assert_repo_relative_posix(observed)
    assert_repo_relative_posix(expected)
    if observed != expected:
        raise ValueError(f"{label} must match expected_artifacts.{expected_name}")


def validate_claim_boundary(config: dict[str, Any]) -> dict[str, Any]:
    boundary = config.get("claim_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("claim_boundary must be an object")
    if boundary.get("semantic_claim_source") != "accepted_evidence_binding":
        raise ValueError("claim_boundary.semantic_claim_source must be accepted_evidence_binding")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("claim_boundary.translation_coverage_numerator must be 0")
    return {
        "semantic_claim_source": boundary["semantic_claim_source"],
        "generated_draft_semantic_pass": boundary["generated_draft_semantic_pass"],
        "translation_coverage_numerator": boundary["translation_coverage_numerator"],
    }


def validate_proof_class_contract(config: dict[str, Any], entrypoints: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = config.get("allowed_proof_classes")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(item, str) for item in allowed):
        raise ValueError("allowed_proof_classes must be a non-empty string list")
    default = config.get("proof_class_default")
    if default not in allowed:
        raise ValueError("proof_class_default must be listed in allowed_proof_classes")
    entrypoint_classes: dict[str, str] = {}
    for entry in entrypoints:
        proof_class = entry.get("proof_class")
        if proof_class not in allowed:
            raise ValueError(f"entrypoint proof_class must be allowed: {entry.get('id')}")
        entrypoint_classes[str(entry.get("id"))] = str(proof_class)
    return {
        "proof_class_default": default,
        "allowed_proof_classes": list(allowed),
        "entrypoints": entrypoint_classes,
        "status": "passed",
    }


def validate_source_pin_contract(config: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    target_id = require_string(config.get("target_id"), "target_id")
    source_pin = require_object(config.get("source_pin"), "source_pin")
    environment_ref = require_object(config.get("environment_profile"), "environment_profile")
    environment = load_json(repo_path(require_string(environment_ref.get("path"), "environment_profile.path"), repo_root=repo_root))
    profile_pin = require_object(
        require_object(environment.get("source_pins"), "environment.source_pins").get(target_id),
        f"environment.source_pins.{target_id}",
    )
    for field in ("repository", "branch", "commit", "checkout_command"):
        if source_pin.get(field) != profile_pin.get(field):
            raise ValueError(f"source_pin.{field} must match environment source pin")
    if source_pin.get("target_id") != target_id:
        raise ValueError("source_pin.target_id must match target_id")
    assert_no_local_absolute_path(require_string(source_pin.get("checkout_command"), "source_pin.checkout_command"))

    policy = require_object(config.get("source_pin_policy"), "source_pin_policy")
    canonical_commit = require_string(policy.get("canonical_commit"), "source_pin_policy.canonical_commit")
    if canonical_commit != source_pin.get("commit"):
        raise ValueError("source_pin_policy.canonical_commit must match source_pin.commit")
    if policy.get("new_extraction_requires_canonical_commit") is not True:
        raise ValueError("source_pin_policy.new_extraction_requires_canonical_commit must be true")
    allowed_historical = policy.get("allowed_historical_evidence_commits", [])
    if not isinstance(allowed_historical, list):
        raise ValueError("source_pin_policy.allowed_historical_evidence_commits must be a list")
    allowed_commits = {canonical_commit}
    historical_commits: list[str] = []
    for index, item in enumerate(allowed_historical):
        item_payload = require_object(item, f"source_pin_policy.allowed_historical_evidence_commits[{index}]")
        commit = require_string(item_payload.get("commit"), f"source_pin_policy.allowed_historical_evidence_commits[{index}].commit")
        reason = require_string(item_payload.get("reason"), f"source_pin_policy.allowed_historical_evidence_commits[{index}].reason")
        scope = item_payload.get("scope")
        if not isinstance(scope, list) or not scope or not all(isinstance(value, str) and value for value in scope):
            raise ValueError(f"source_pin_policy.allowed_historical_evidence_commits[{index}].scope must be a non-empty string list")
        if commit == canonical_commit:
            raise ValueError("source_pin_policy.allowed_historical_evidence_commits must not repeat canonical commit")
        if not reason:
            raise ValueError(f"source_pin_policy.allowed_historical_evidence_commits[{index}].reason must be non-empty")
        allowed_commits.add(commit)
        historical_commits.append(commit)
    return {
        "target_id": target_id,
        "repository": source_pin["repository"],
        "branch": source_pin["branch"],
        "canonical_commit": canonical_commit,
        "allowed_commits": sorted(allowed_commits),
        "allowed_historical_evidence_commits": historical_commits,
        "status": "passed",
    }


def validate_entrypoint_profile_contract(
    entry: dict[str, Any],
    *,
    config: dict[str, Any],
    source_pin_contract: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    profile_ref = require_object(entry.get("profile"), f"{entry.get('id')}.profile")
    profile_path = require_string(profile_ref.get("path"), f"{entry.get('id')}.profile.path")
    profile = load_json(repo_path(profile_path, repo_root=repo_root))
    if profile_ref.get("profile_id") != profile.get("profile_id"):
        raise ValueError(f"{entry.get('id')} profile_id must match profile payload")
    if entry.get("proof_class") != profile.get("proof_class"):
        raise ValueError(f"{entry.get('id')} proof_class must match profile proof_class")
    if profile.get("target_id") != config.get("target_id"):
        raise ValueError(f"{entry.get('id')} profile target_id must match judge target_id")
    command = require_string(entry.get("command"), f"{entry.get('id')}.command")
    run_id = require_string(entry.get("run_id"), f"{entry.get('id')}.run_id")
    if f"--profile {profile_path}" not in command:
        raise ValueError(f"{entry.get('id')} command must reference its profile path")
    if f"--run-id {run_id}" not in command:
        raise ValueError(f"{entry.get('id')} command must reference its run_id")
    if "--out-root " not in command:
        raise ValueError(f"{entry.get('id')} command must include --out-root")

    source_repository = profile.get("source_repository")
    if source_repository is not None and source_repository != source_pin_contract["repository"]:
        raise ValueError(f"{entry.get('id')} profile source_repository must match source pin")
    source_branch = profile.get("source_branch")
    if source_branch is not None and source_branch != source_pin_contract["branch"]:
        raise ValueError(f"{entry.get('id')} profile source_branch must match source pin")
    allowed_commits = set(source_pin_contract["allowed_commits"])
    observed_commits: set[str] = set()
    for field in ("source_commit", "require_source_commit"):
        value = profile.get(field)
        if isinstance(value, str):
            observed_commits.add(value)
    workers = profile.get("workers")
    if isinstance(workers, list):
        for index, worker in enumerate(workers):
            worker_payload = require_object(worker, f"{entry.get('id')}.profile.workers[{index}]")
            if worker_payload.get("target_id") not in (None, config.get("target_id")):
                raise ValueError(f"{entry.get('id')} worker target_id must match judge target_id")
            for field in ("source_repository", "source_branch"):
                value = worker_payload.get(field)
                expected = source_pin_contract["repository"] if field == "source_repository" else source_pin_contract["branch"]
                if value is not None and value != expected:
                    raise ValueError(f"{entry.get('id')} worker {field} must match source pin")
            for field in ("source_commit", "require_source_commit"):
                value = worker_payload.get(field)
                if isinstance(value, str):
                    observed_commits.add(value)
    disallowed = sorted(commit for commit in observed_commits if commit not in allowed_commits)
    if disallowed:
        raise ValueError(f"{entry.get('id')} profile uses commits outside source_pin_policy: {disallowed}")
    result = {
        "profile_id": profile.get("profile_id"),
        "proof_class": profile.get("proof_class"),
        "observed_commits": sorted(observed_commits),
        "status": "passed",
    }
    if profile.get("mode") == "opencode":
        result["opencode_launch_policy"] = validate_opencode_profile_launch_policy(profile, entry_id=str(entry.get("id")))
    return result


def validate_opencode_profile_launch_policy(profile: dict[str, Any], *, entry_id: str) -> dict[str, Any]:
    command = require_string(profile.get("opencode_command"), f"{entry_id} opencode profile opencode_command")
    variant = require_string(profile.get("opencode_variant"), f"{entry_id} opencode profile opencode_variant")
    model = profile.get("opencode_model")
    if model is not None and not isinstance(model, str):
        raise ValueError(f"{entry_id} opencode profile opencode_model must be a string or null")
    agent = profile.get("opencode_agent")
    if agent is not None and not isinstance(agent, str):
        raise ValueError(f"{entry_id} opencode profile opencode_agent must be a string or null")
    skip_permissions = profile.get("opencode_skip_permissions")
    if not isinstance(skip_permissions, bool):
        raise ValueError(f"{entry_id} opencode profile opencode_skip_permissions must be a boolean")
    return {
        "opencode_command": command,
        "opencode_model": model,
        "opencode_agent": agent,
        "opencode_variant": variant,
        "opencode_skip_permissions": skip_permissions,
    }


def manifest_profile_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    for field in ("profile", "competition_profile"):
        value = manifest.get(field)
        if isinstance(value, dict):
            return value
    raise ValueError("tracked manifest must include profile or competition_profile")


def expected_manifest_reproduction_command_key(entry: dict[str, Any]) -> str:
    command = require_string(entry.get("command"), f"{entry.get('id')}.command")
    if "validation.tools.judge_demo" in command:
        return "judge_demo_command"
    if "validation.tools.opencode_agent_harness evaluate" in command:
        return "evaluate_profile_command"
    if "validation.tools.opencode_agent_harness run-batch-profile" in command:
        return "run_batch_profile_command"
    raise ValueError(f"{entry.get('id')} command is not a supported judge entrypoint command")


def manifest_source_commits(manifest: dict[str, Any]) -> list[str]:
    commits: set[str] = set()
    source = manifest.get("source")
    if isinstance(source, dict):
        for field in ("source_commit", "require_source_commit"):
            value = source.get(field)
            if isinstance(value, str):
                commits.add(value)
    workers = manifest.get("workers")
    if isinstance(workers, list):
        for worker in workers:
            if not isinstance(worker, dict):
                continue
            for field in ("source_commit", "require_source_commit"):
                value = worker.get(field)
                if isinstance(value, str):
                    commits.add(value)
    return sorted(commits)


def validate_expected_artifacts_under_out_root(entry: dict[str, Any], *, out_root: str) -> list[str]:
    assert_repo_relative_posix(out_root)
    out_root_prefix = out_root.rstrip("/") + "/"
    artifacts = require_object(entry.get("expected_artifacts"), f"{entry.get('id')}.expected_artifacts")
    artifact_paths: list[str] = []
    for name, value in sorted(artifacts.items()):
        path_text = require_string(value, f"{entry.get('id')}.expected_artifacts.{name}")
        assert_repo_relative_posix(path_text)
        if not path_text.startswith(out_root_prefix):
            raise ValueError(f"{entry.get('id')} expected_artifacts.{name} must be under reproduction --out-root")
        artifact_paths.append(path_text)
    return artifact_paths


def validate_tracked_manifest_contract(
    entry: dict[str, Any],
    *,
    config: dict[str, Any],
    claim_boundary: dict[str, Any],
    source_pin_contract: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    manifest_ref = require_object(entry.get("tracked_manifest"), f"{entry.get('id')}.tracked_manifest")
    manifest_path = require_string(manifest_ref.get("path"), f"{entry.get('id')}.tracked_manifest.path")
    manifest = load_json(repo_path(manifest_path, repo_root=repo_root))
    if manifest.get("status") != "passed":
        raise ValueError(f"{entry.get('id')} tracked manifest status must be passed")
    if manifest.get("target_id") != config.get("target_id"):
        raise ValueError(f"{entry.get('id')} tracked manifest target_id must match judge target_id")
    if manifest.get("proof_class") != entry.get("proof_class"):
        raise ValueError(f"{entry.get('id')} tracked manifest proof_class must match entrypoint")

    environment_ref = require_object(config.get("environment_profile"), "environment_profile")
    environment = require_object(manifest.get("environment_profile"), f"{entry.get('id')} tracked manifest environment_profile")
    for field in ("path", "sha256"):
        if environment.get(field) != environment_ref.get(field):
            raise ValueError(f"{entry.get('id')} tracked manifest environment_profile.{field} must match judge config")

    manifest_boundary = require_object(manifest.get("claim_boundary"), f"{entry.get('id')} tracked manifest claim_boundary")
    for field in ("semantic_claim_source", "generated_draft_semantic_pass", "translation_coverage_numerator"):
        if manifest_boundary.get(field) != claim_boundary.get(field):
            raise ValueError(f"{entry.get('id')} tracked manifest claim_boundary.{field} must match judge config")

    if source_pin_contract:
        allowed_commits = set(source_pin_contract["allowed_commits"])
        disallowed = sorted(commit for commit in manifest_source_commits(manifest) if commit not in allowed_commits)
        if disallowed:
            raise ValueError(f"{entry.get('id')} tracked manifest uses commits outside source_pin_policy: {disallowed}")

    profile_ref = require_object(entry.get("profile"), f"{entry.get('id')}.profile")
    profile = manifest_profile_payload(manifest)
    if profile.get("path") != profile_ref.get("path"):
        raise ValueError(f"{entry.get('id')} tracked manifest profile path must match entrypoint profile")
    if profile.get("sha256") != profile_ref.get("sha256"):
        raise ValueError(f"{entry.get('id')} tracked manifest profile sha256 must match entrypoint profile")

    reproduction = require_object(manifest.get("reproduction"), f"{entry.get('id')} tracked manifest reproduction")
    command_key = expected_manifest_reproduction_command_key(entry)
    manifest_command = require_string(reproduction.get(command_key), f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    if manifest_command != entry.get("command"):
        raise ValueError(f"{entry.get('id')} tracked manifest reproduction command must match entrypoint command")
    flags = parsed_command_flags(manifest_command)
    profile_path = require_command_flag(flags, "--profile", f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    run_id = require_command_flag(flags, "--run-id", f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    out_root = require_command_flag(flags, "--out-root", f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    if profile_path != profile_ref.get("path"):
        raise ValueError(f"{entry.get('id')} tracked manifest reproduction --profile must match entrypoint profile")
    if run_id != entry.get("run_id"):
        raise ValueError(f"{entry.get('id')} tracked manifest reproduction --run-id must match entrypoint run_id")
    expected_artifact_paths = validate_expected_artifacts_under_out_root(entry, out_root=out_root)
    validate_local_absolute_path_policy(reproduction, label=f"{entry.get('id')} tracked manifest reproduction")
    return {
        "path": manifest_path,
        "manifest_kind": manifest.get("manifest_kind"),
        "reproduction_command_key": command_key,
        "reproduction_out_root": out_root,
        "expected_artifact_count": len(expected_artifact_paths),
        "source_commits": manifest_source_commits(manifest),
        "status": "passed",
    }


def entrypoint_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    judge_focus = entry.get("judge_focus", [])
    return {
        "id": entry.get("id"),
        "purpose": entry.get("purpose"),
        "priority": entry.get("priority"),
        "proof_class": entry.get("proof_class", "unknown"),
        "run_id": entry.get("run_id", "unknown"),
        "judge_focus": list(judge_focus) if isinstance(judge_focus, list) else [],
    }


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def validate_test_contract(
    config: dict[str, Any],
    *,
    entrypoints: list[dict[str, Any]],
    claim_boundary: dict[str, Any],
) -> dict[str, Any]:
    contract = require_object(config.get("test_contract"), "test_contract")
    features = require_object(config.get("harness_features_demonstrated"), "harness_features_demonstrated")
    required_features = contract.get("required_harness_features", list(REQUIRED_HARNESS_FEATURES))
    if not isinstance(required_features, list) or not required_features:
        raise ValueError("test_contract.required_harness_features must be a non-empty list")
    missing_features = [feature for feature in required_features if features.get(feature) is not True]
    if missing_features:
        raise ValueError(f"harness_features_demonstrated missing true features: {missing_features}")

    entrypoint_ids = [require_string(entry.get("id"), "entrypoint.id") for entry in entrypoints]
    if len(set(entrypoint_ids)) != len(entrypoint_ids):
        raise ValueError(f"entrypoint ids must be unique: {entrypoint_ids}")
    required_entrypoint_ids = contract.get("required_entrypoint_ids")
    if not isinstance(required_entrypoint_ids, list) or not required_entrypoint_ids:
        raise ValueError("test_contract.required_entrypoint_ids must be a non-empty list")
    if set(required_entrypoint_ids) != set(entrypoint_ids):
        raise ValueError(
            "test_contract.required_entrypoint_ids must match entrypoints: "
            f"{required_entrypoint_ids} != {entrypoint_ids}"
        )

    required_artifacts = contract.get("required_expected_artifacts", [])
    if not isinstance(required_artifacts, list):
        raise ValueError("test_contract.required_expected_artifacts must be a list")
    for entry in entrypoints:
        if is_competition_smoke_entrypoint(entry):
            continue
        artifacts = require_object(entry.get("expected_artifacts"), f"{entry.get('id')}.expected_artifacts")
        missing = [name for name in required_artifacts if name not in artifacts]
        if missing:
            raise ValueError(f"{entry.get('id')} missing required expected artifacts: {missing}")

    if contract.get("semantic_claim_source") != claim_boundary.get("semantic_claim_source"):
        raise ValueError("test_contract.semantic_claim_source must match claim_boundary")
    if contract.get("generated_draft_semantic_pass") is not claim_boundary.get("generated_draft_semantic_pass"):
        raise ValueError("test_contract.generated_draft_semantic_pass must match claim_boundary")
    if contract.get("translation_coverage_numerator") != claim_boundary.get("translation_coverage_numerator"):
        raise ValueError("test_contract.translation_coverage_numerator must match claim_boundary")

    repair_round_cap = contract.get("repair_round_cap", 5)
    if repair_round_cap != 5:
        raise ValueError("test_contract.repair_round_cap must be 5")
    required_roles = contract.get("required_agent_roles", list(REQUIRED_AGENT_ROLES))
    if set(required_roles) != set(REQUIRED_AGENT_ROLES):
        raise ValueError(f"test_contract.required_agent_roles must be {list(REQUIRED_AGENT_ROLES)}")
    required_context_stages = contract.get("required_context_pipeline_stages", list(REQUIRED_CONTEXT_STAGES))
    if list(required_context_stages) != list(REQUIRED_CONTEXT_STAGES):
        raise ValueError(f"test_contract.required_context_pipeline_stages must be {list(REQUIRED_CONTEXT_STAGES)}")

    context_contract = require_object(contract.get("context_pack_contract"), "test_contract.context_pack_contract")
    if context_contract.get("chat_output_is_evidence") is not False:
        raise ValueError("test_contract.context_pack_contract.chat_output_is_evidence must be false")
    if context_contract.get("semantic_gate") is not False:
        raise ValueError("test_contract.context_pack_contract.semantic_gate must be false")
    if context_contract.get("evidence_policy") != "on-disk-artifacts-only":
        raise ValueError("test_contract.context_pack_contract.evidence_policy must be on-disk-artifacts-only")
    if context_contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("test_contract.context_pack_contract.checkpoint_backend must be sqlite")
    if context_contract.get("worker_state_source") != "agent-index.agents_by_worker_id":
        raise ValueError("test_contract.context_pack_contract.worker_state_source must be agent-index.agents_by_worker_id")

    agent_contract = require_object(contract.get("agent_index_contract"), "test_contract.agent_index_contract")
    if agent_contract.get("chat_output_is_evidence") is not False:
        raise ValueError("test_contract.agent_index_contract.chat_output_is_evidence must be false")
    if agent_contract.get("semantic_gate") is not False:
        raise ValueError("test_contract.agent_index_contract.semantic_gate must be false")
    if agent_contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("test_contract.agent_index_contract.checkpoint_backend must be sqlite")
    if agent_contract.get("worker_isolation") != "per-worker out_root":
        raise ValueError("test_contract.agent_index_contract.worker_isolation must be per-worker out_root")

    return {
        "required_entrypoint_ids": entrypoint_ids,
        "required_harness_features": list(required_features),
        "required_expected_artifacts": list(required_artifacts),
        "required_context_pipeline_stages": list(required_context_stages),
        "required_agent_roles": list(required_roles),
        "repair_round_cap": repair_round_cap,
        "status": "passed",
    }


def validate_context_management_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
    expected_artifacts: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    if payload.get("report_kind") != "context-pack":
        raise ValueError(f"context_pack report_kind must be context-pack: {path_text}")
    contract = require_object(payload.get("context_management_contract"), "context_management_contract")
    if contract.get("contract_kind") != "context-management":
        raise ValueError("context_management_contract.contract_kind must be context-management")
    if contract.get("schema_version") != 1:
        raise ValueError("context_management_contract.schema_version must be 1")
    if contract.get("chat_output_is_evidence") is not False:
        raise ValueError("context_management_contract.chat_output_is_evidence must be false")
    if contract.get("semantic_gate") is not False:
        raise ValueError("context_management_contract.semantic_gate must be false")
    if contract.get("evidence_policy") != "on-disk-artifacts-only":
        raise ValueError("context_management_contract.evidence_policy must be on-disk-artifacts-only")

    context_pack_path = require_string(contract.get("context_pack"), "context_management_contract.context_pack")
    agent_index_path = require_string(contract.get("agent_index"), "context_management_contract.agent_index")
    assert_repo_relative_posix(context_pack_path)
    assert_repo_relative_posix(agent_index_path)
    if expected_artifacts.get("context_pack") and context_pack_path != expected_artifacts["context_pack"]:
        raise ValueError("context_management_contract.context_pack must match expected_artifacts.context_pack")
    if expected_artifacts.get("agent_index") and agent_index_path != expected_artifacts["agent_index"]:
        raise ValueError("context_management_contract.agent_index must match expected_artifacts.agent_index")

    primary_report = contract.get("primary_report")
    if isinstance(primary_report, str):
        assert_repo_relative_posix(primary_report)
    resume_protocol = require_object(contract.get("resume_protocol"), "context_management_contract.resume_protocol")
    if resume_protocol.get("checkpoint_backend") != "sqlite":
        raise ValueError("context_management_contract.resume_protocol.checkpoint_backend must be sqlite")
    ledger_path = resume_protocol.get("ledger_path")
    if isinstance(ledger_path, str):
        assert_repo_relative_posix(ledger_path)
    if resume_protocol.get("worker_state_source") != "agent-index.agents_by_worker_id":
        raise ValueError("context_management_contract.resume_protocol.worker_state_source must be agent-index.agents_by_worker_id")

    pipeline = payload.get("context_management_contract", {}).get("pipeline")
    if not isinstance(pipeline, list) or not pipeline:
        raise ValueError("context_management_contract.pipeline must be a non-empty list")
    stages = {item.get("stage") for item in pipeline if isinstance(item, dict)}
    missing_stages = [stage for stage in REQUIRED_CONTEXT_STAGES if stage not in stages]
    if missing_stages:
        raise ValueError(f"context_management_contract.pipeline missing stages: {missing_stages}")
    repair_stage = next(item for item in pipeline if isinstance(item, dict) and item.get("stage") == "repair")
    if repair_stage.get("max_rounds") != 5:
        raise ValueError("context_management_contract repair max_rounds must be 5")
    worker_stage = next(item for item in pipeline if isinstance(item, dict) and item.get("stage") == "translate")
    if worker_stage.get("fanout") is not True:
        raise ValueError("context_management_contract translate stage must be fanout")

    return {
        "path": path_text,
        "status": "passed",
        "pipeline_stages": list(REQUIRED_CONTEXT_STAGES),
        "repair_round_cap": 5,
    }


def validate_agent_coordination_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
) -> dict[str, Any]:
    if payload.get("report_kind") != "agent-index":
        raise ValueError(f"agent_index report_kind must be agent-index: {path_text}")
    contract = require_object(payload.get("agent_coordination_contract"), "agent_coordination_contract")
    if contract.get("contract_kind") != "agent-coordination":
        raise ValueError("agent_coordination_contract.contract_kind must be agent-coordination")
    if contract.get("schema_version") != 1:
        raise ValueError("agent_coordination_contract.schema_version must be 1")
    if contract.get("chat_output_is_evidence") is not False:
        raise ValueError("agent_coordination_contract.chat_output_is_evidence must be false")
    if contract.get("semantic_gate") is not False:
        raise ValueError("agent_coordination_contract.semantic_gate must be false")
    if contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("agent_coordination_contract.checkpoint_backend must be sqlite")

    roles = require_object(contract.get("roles"), "agent_coordination_contract.roles")
    missing_roles = [role for role in REQUIRED_AGENT_ROLES if role not in roles]
    if missing_roles:
        raise ValueError(f"agent_coordination_contract.roles missing roles: {missing_roles}")
    repairer = require_object(roles.get("repairer"), "agent_coordination_contract.roles.repairer")
    if repairer.get("round_cap") != 5:
        raise ValueError("agent_coordination_contract.roles.repairer.round_cap must be 5")
    worker = require_object(roles.get("worker"), "agent_coordination_contract.roles.worker")
    if worker.get("isolation") != "per-worker out_root":
        raise ValueError("agent_coordination_contract.roles.worker.isolation must be per-worker out_root")

    agents_by_worker_id = require_object(payload.get("agents_by_worker_id"), "agents_by_worker_id")
    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("agent_index.agents must be a non-empty list")
    if contract.get("worker_count") != len(agents_by_worker_id):
        raise ValueError("agent_coordination_contract.worker_count must match agents_by_worker_id")
    for worker_id, agent in sorted(agents_by_worker_id.items()):
        agent_payload = require_object(agent, f"agents_by_worker_id.{worker_id}")
        if agent_payload.get("worker_id") != worker_id:
            raise ValueError(f"agents_by_worker_id key must match worker_id: {worker_id}")
        for field in ("assignment_path", "request_path", "summary_path", "report_path", "isolated_out_root"):
            assert_repo_relative_posix(require_string(agent_payload.get(field), f"{worker_id}.{field}"))
    local_path_scan = validate_local_absolute_path_policy(payload, label=f"agent_index {path_text}")

    return {
        "path": path_text,
        "status": "passed",
        "roles": list(REQUIRED_AGENT_ROLES),
        "worker_count": len(agents_by_worker_id),
        "repair_round_cap": 5,
        "local_absolute_path_scan": local_path_scan,
    }


def validate_sha256_hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a sha256 hex string")
    return value


def validate_artifact_binding_shape(
    value: Any,
    label: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, str]:
    binding = require_object(value, label)
    path_text = require_string(binding.get("path"), f"{label}.path")
    assert_repo_relative_posix(path_text)
    sha256 = validate_sha256_hex(binding.get("sha256"), f"{label}.sha256")
    if repo_root is not None:
        validate_ref({"path": path_text, "sha256": sha256}, repo_root=repo_root)
    return {"path": path_text, "sha256": sha256}


def validate_route_governance_metrics_report_contract(ref: dict[str, str], *, repo_root: Path) -> dict[str, Any]:
    path_text = ref["path"]
    path = repo_path(path_text, repo_root=repo_root)
    payload = load_json(path)
    schema = load_json(ROUTE_GOVERNANCE_METRICS_SCHEMA)
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as error:
        path = jsonschema_error_path(error)
        raise ValueError(
            "route_governance_metrics_report must match validation/route-governance-metrics.schema.json: "
            f"{path}: {error.message}"
        ) from error
    metrics = require_object(payload.get("metrics"), "route_governance_metrics_report.metrics")
    retention = require_object(payload.get("retention_policy"), "route_governance_metrics_report.retention_policy")
    return {
        "status": "passed",
        "path": path_text,
        "translation_coverage_numerator": metrics.get("translation_coverage_numerator"),
        "accepted_evidence_semantic_pass_count": metrics.get("accepted_evidence_semantic_pass_count"),
        "tracked_route_decision_artifacts": metrics.get("tracked_route_decision_artifacts"),
        "tracked_slice_gate_contexts": metrics.get("tracked_slice_gate_contexts"),
        "retention_policy": {
            "report_kind": retention.get("report_kind"),
            "target_artifacts_committed": retention.get("target_artifacts", {}).get("committed")
            if isinstance(retention.get("target_artifacts"), dict)
            else None,
        },
    }


def jsonschema_error_path(error: jsonschema.ValidationError) -> str:
    parts = ["$"]
    for item in error.absolute_path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}")
    return "".join(parts)


def validate_opencode_launch_policy_binding(value: Any, sha_value: Any, label: str) -> dict[str, Any]:
    policy = require_object(value, f"{label}.launch_policy")
    command = require_string(policy.get("opencode_command"), f"{label}.launch_policy.opencode_command")
    variant = require_string(policy.get("opencode_variant"), f"{label}.launch_policy.opencode_variant")
    model = policy.get("opencode_model")
    if model is not None and not isinstance(model, str):
        raise ValueError(f"{label}.launch_policy.opencode_model must be a string or null")
    agent = policy.get("opencode_agent")
    if agent is not None and not isinstance(agent, str):
        raise ValueError(f"{label}.launch_policy.opencode_agent must be a string or null")
    if not isinstance(policy.get("opencode_skip_permissions"), bool):
        raise ValueError(f"{label}.launch_policy.opencode_skip_permissions must be a boolean")
    normalized = {
        "opencode_command": command,
        "opencode_model": model,
        "opencode_agent": agent,
        "opencode_variant": variant,
        "opencode_skip_permissions": policy["opencode_skip_permissions"],
    }
    expected_sha = sha256_text(json.dumps(normalized, sort_keys=True))
    actual_sha = validate_sha256_hex(sha_value, f"{label}.launch_policy_sha256")
    if actual_sha != expected_sha:
        raise ValueError(f"{label}.launch_policy_sha256 must match launch_policy")
    return normalized


def compare_opencode_launch_policy(
    actual: dict[str, Any],
    expected: dict[str, Any],
    label: str,
    *,
    expected_label: str = "opencode_agent_runtime.opencode_preflight_report",
) -> None:
    if actual != expected:
        raise ValueError(f"{label}.launch_policy must match {expected_label}")


def validate_opencode_preflight_binding(
    value: Any,
    label: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    binding = require_object(value, label)
    result = validate_artifact_binding_shape(binding, label, repo_root=repo_root)
    if binding.get("status") != "passed":
        raise ValueError(f"{label}.status must be passed")
    if binding.get("contract_status") != "executed":
        raise ValueError(f"{label}.contract_status must be executed")
    launch_policy = validate_opencode_launch_policy_binding(
        binding.get("launch_policy"),
        binding.get("launch_policy_sha256"),
        label,
    )
    result.update(
        {
            "status": "passed",
            "contract_status": "executed",
            "launch_policy": launch_policy,
            "launch_policy_sha256": sha256_text(json.dumps(launch_policy, sort_keys=True)),
        }
    )
    if "run_id" in binding:
        result["run_id"] = require_string(binding.get("run_id"), f"{label}.run_id")
    if repo_root is not None:
        preflight_payload = load_json(repo_path(result["path"], repo_root=repo_root))
        if preflight_payload.get("status") != "passed":
            raise ValueError(f"{label} file status must be passed")
        if preflight_payload.get("marker_exists") is not True:
            raise ValueError(f"{label} file marker_exists must be true")
        if "run_id" in preflight_payload:
            file_run_id = require_string(preflight_payload.get("run_id"), f"{label} file.run_id")
            if "run_id" in result and file_run_id != result["run_id"]:
                raise ValueError(f"{label} file.run_id must match binding run_id")
            result["run_id"] = file_run_id
        payload_policy = validate_opencode_launch_policy_binding(
            preflight_payload.get("launch_policy"),
            preflight_payload.get("launch_policy_sha256"),
            f"{label} file",
        )
        if payload_policy != launch_policy:
            raise ValueError(f"{label} file launch_policy must match binding")
        verification = require_object(preflight_payload.get("contract_verification"), f"{label}.contract_verification")
        if verification.get("status") != "executed":
            raise ValueError(f"{label}.contract_verification.status must be executed")
        for field in ("first_shell_command_matches_worker_command", "worker_command_seen", "summary_exists"):
            if verification.get(field) is not True:
                raise ValueError(f"{label}.contract_verification.{field} must be true")
        if verification.get("tools_before_first_shell") != []:
            raise ValueError(f"{label}.contract_verification.tools_before_first_shell must be []")
    return result


def validate_opencode_worker_runtime(
    value: Any,
    *,
    index: int,
    expected_preflight: dict[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    label = f"opencode_agent_runtime.workers[{index}]"
    worker = require_object(value, label)
    worker_id = require_string(worker.get("worker_id"), f"{label}.worker_id")
    if worker.get("chat_output_is_evidence") is not False:
        raise ValueError(f"{label}.chat_output_is_evidence must be false")
    if worker.get("semantic_gate") is not False:
        raise ValueError(f"{label}.semantic_gate must be false")
    if worker.get("contract_verification_status") != "executed":
        raise ValueError(f"{label}.contract_verification_status must be executed")

    bindings = {
        "summary": validate_artifact_binding_shape(worker.get("summary"), f"{label}.summary", repo_root=repo_root),
        "worker_report": validate_artifact_binding_shape(
            worker.get("worker_report"),
            f"{label}.worker_report",
            repo_root=repo_root,
        ),
        "handoff_contract": validate_artifact_binding_shape(
            worker.get("handoff_contract"),
            f"{label}.handoff_contract",
            repo_root=repo_root,
        ),
        "opencode_session_evidence": validate_artifact_binding_shape(
            worker.get("opencode_session_evidence"),
            f"{label}.opencode_session_evidence",
            repo_root=repo_root,
        ),
    }
    logs = require_object(worker.get("logs"), f"{label}.logs")
    bindings["logs_stdout"] = validate_artifact_binding_shape(logs.get("stdout"), f"{label}.logs.stdout", repo_root=repo_root)
    bindings["logs_stderr"] = validate_artifact_binding_shape(logs.get("stderr"), f"{label}.logs.stderr", repo_root=repo_root)
    worker_preflight = validate_opencode_preflight_binding(
        worker.get("opencode_preflight_report"),
        f"{label}.opencode_preflight_report",
        repo_root=repo_root,
    )
    if worker_preflight["path"] != expected_preflight["path"] or worker_preflight["sha256"] != expected_preflight["sha256"]:
        raise ValueError(f"{label}.opencode_preflight_report must match opencode_agent_runtime.opencode_preflight_report")
    compare_opencode_launch_policy(worker_preflight["launch_policy"], expected_preflight["launch_policy"], f"{label}.opencode_preflight_report")
    if worker_preflight.get("run_id") != expected_preflight.get("run_id"):
        raise ValueError(f"{label}.opencode_preflight_report.run_id must match opencode_agent_runtime.opencode_preflight_report")

    verification = require_object(worker.get("opencode_contract_verification"), f"{label}.opencode_contract_verification")
    if verification.get("status") != "executed":
        raise ValueError(f"{label}.opencode_contract_verification.status must be executed")
    for field in ("first_shell_command_matches_worker_command", "worker_command_seen", "summary_exists"):
        if verification.get(field) is not True:
            raise ValueError(f"{label}.opencode_contract_verification.{field} must be true")
    if verification.get("tools_before_first_shell") != []:
        raise ValueError(f"{label}.opencode_contract_verification.tools_before_first_shell must be []")
    command_count = verification.get("executed_shell_command_count")
    if not isinstance(command_count, int) or command_count < 1:
        raise ValueError(f"{label}.opencode_contract_verification.executed_shell_command_count must be >= 1")
    executed_commands = verification.get("executed_shell_commands")
    if not isinstance(executed_commands, list) or not executed_commands or not all(isinstance(item, str) for item in executed_commands):
        raise ValueError(f"{label}.opencode_contract_verification.executed_shell_commands must be a non-empty string list")
    for command in executed_commands:
        assert_no_local_absolute_path(command)

    return {
        "worker_id": worker_id,
        "status": "passed",
        "contract_verification_status": "executed",
        "bindings": bindings,
    }


def validate_opencode_agent_runtime_contract(
    value: Any,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    runtime = require_object(value, "opencode_agent_runtime")
    if runtime.get("runtime") != "opencode":
        raise ValueError("opencode_agent_runtime.runtime must be opencode")
    if runtime.get("chat_output_is_evidence") is not False:
        raise ValueError("opencode_agent_runtime.chat_output_is_evidence must be false")
    if runtime.get("semantic_gate") is not False:
        raise ValueError("opencode_agent_runtime.semantic_gate must be false")
    workers = runtime.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("opencode_agent_runtime.workers must be a non-empty list")
    worker_count = runtime.get("worker_count")
    if not isinstance(worker_count, int) or worker_count != len(workers):
        raise ValueError("opencode_agent_runtime.worker_count must match workers length")
    preflight = validate_opencode_preflight_binding(
        runtime.get("opencode_preflight_report"),
        "opencode_agent_runtime.opencode_preflight_report",
        repo_root=repo_root,
    )
    if runtime.get("all_contracts_executed") is not True:
        raise ValueError("opencode_agent_runtime.all_contracts_executed must be true")
    if runtime.get("failed_or_missing_contract_workers") != []:
        raise ValueError("opencode_agent_runtime.failed_or_missing_contract_workers must be []")
    counts = require_object(runtime.get("contract_status_counts"), "opencode_agent_runtime.contract_status_counts")
    if counts != {"executed": worker_count}:
        raise ValueError("opencode_agent_runtime.contract_status_counts must equal {'executed': worker_count}")

    worker_results = [
        validate_opencode_worker_runtime(worker, index=index, expected_preflight=preflight, repo_root=repo_root)
        for index, worker in enumerate(workers)
    ]
    worker_ids = [worker["worker_id"] for worker in worker_results]
    if len(set(worker_ids)) != len(worker_ids):
        raise ValueError("opencode_agent_runtime.workers worker_id values must be unique")
    return {
        "status": "passed",
        "runtime": "opencode",
        "worker_count": worker_count,
        "contract_status_counts": {"executed": worker_count},
        "opencode_preflight_report": preflight,
        "worker_ids": worker_ids,
    }


def artifact_ref_key_for_expected_artifact(name: str) -> str:
    return EXPECTED_ARTIFACT_REF_ALIASES.get(name, name)


def compare_artifact_binding(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    if actual.get("path") != expected.get("path") or actual.get("sha256") != expected.get("sha256"):
        raise ValueError(f"{label} must match path and sha256")


def validate_judge_graph_contract(
    architecture: dict[str, Any],
    *,
    opencode_runtime_result: dict[str, Any] | None,
) -> dict[str, Any]:
    graph_runtime = architecture.get("graph_runtime")
    graph_nodes = architecture.get("graph_nodes")
    if graph_runtime is None and graph_nodes is None and opencode_runtime_result is None:
        return {"status": "skipped", "reason": "graph contract not declared"}
    if graph_runtime != "opencode-harness-langgraph-inspired":
        raise ValueError(
            "judge_evidence_index.harness_architecture.graph_runtime must be opencode-harness-langgraph-inspired"
        )
    if not isinstance(graph_nodes, list):
        raise ValueError("judge_evidence_index.harness_architecture.graph_nodes must be a list")
    missing_nodes = [node for node in REQUIRED_JUDGE_GRAPH_NODES if node not in graph_nodes]
    if missing_nodes:
        raise ValueError(f"judge_evidence_index.harness_architecture.graph_nodes missing required nodes: {missing_nodes}")

    retry_policy = require_object(architecture.get("retry_policy"), "judge_evidence_index.harness_architecture.retry_policy")
    if retry_policy.get("checkpoint") != "repair_hints":
        raise ValueError("judge_evidence_index.harness_architecture.retry_policy.checkpoint must be repair_hints")
    if retry_policy.get("round_cap") != 5:
        raise ValueError("judge_evidence_index.harness_architecture.retry_policy.round_cap must be 5")

    parallelism = require_object(architecture.get("parallelism"), "judge_evidence_index.harness_architecture.parallelism")
    worker_count = architecture.get("worker_count")
    if not isinstance(worker_count, int) or worker_count < 1:
        raise ValueError("judge_evidence_index.harness_architecture.worker_count must be a positive integer")
    for field in ("max_workers", "effective_workers"):
        value = parallelism.get(field)
        if not isinstance(value, int) or value < worker_count:
            raise ValueError(f"judge_evidence_index.harness_architecture.parallelism.{field} must be >= worker_count")
    if opencode_runtime_result is not None and opencode_runtime_result["worker_count"] != worker_count:
        raise ValueError("judge_evidence_index.harness_architecture.worker_count must match opencode_agent_runtime.worker_count")

    return {
        "status": "passed",
        "graph_runtime": graph_runtime,
        "graph_nodes": list(graph_nodes),
        "worker_count": worker_count,
        "retry_round_cap": 5,
    }


def validate_judge_headline_contract(
    payload: dict[str, Any],
    *,
    boundary: dict[str, Any],
    architecture: dict[str, Any],
    opencode_runtime_result: dict[str, Any] | None,
) -> dict[str, Any]:
    headline = require_object(payload.get("judge_headline"), "judge_evidence_index.judge_headline")
    if headline.get("report_kind") != "judge-headline":
        raise ValueError("judge_evidence_index.judge_headline.report_kind must be judge-headline")
    if headline.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.judge_headline.semantic_gate must be false")
    if headline.get("semantic_claim_source") != boundary.get("semantic_claim_source"):
        raise ValueError("judge_evidence_index.judge_headline.semantic_claim_source must match claim_boundary")
    if headline.get("generated_draft_semantic_pass") is not boundary.get("generated_draft_semantic_pass"):
        raise ValueError("judge_evidence_index.judge_headline.generated_draft_semantic_pass must match claim_boundary")
    if headline.get("translation_coverage_numerator") != boundary.get("translation_coverage_numerator"):
        raise ValueError("judge_evidence_index.judge_headline.translation_coverage_numerator must match claim_boundary")

    worker_count = architecture.get("worker_count")
    if isinstance(worker_count, int) and headline.get("worker_count") != worker_count:
        raise ValueError("judge_evidence_index.judge_headline.worker_count must match harness_architecture.worker_count")
    graph_runtime = architecture.get("graph_runtime")
    if graph_runtime is not None and headline.get("graph_runtime") != graph_runtime:
        raise ValueError("judge_evidence_index.judge_headline.graph_runtime must match harness_architecture.graph_runtime")
    parallelism = architecture.get("parallelism")
    if isinstance(parallelism, dict) and headline.get("parallelism") != parallelism:
        raise ValueError("judge_evidence_index.judge_headline.parallelism must match harness_architecture.parallelism")
    retry_policy = architecture.get("retry_policy")
    if isinstance(retry_policy, dict):
        if headline.get("repair_round_cap") != retry_policy.get("round_cap"):
            raise ValueError("judge_evidence_index.judge_headline.repair_round_cap must match harness_architecture.retry_policy.round_cap")
        if headline.get("repair_checkpoint") != retry_policy.get("checkpoint"):
            raise ValueError("judge_evidence_index.judge_headline.repair_checkpoint must match harness_architecture.retry_policy.checkpoint")

    runtime_headline = require_object(headline.get("opencode_runtime"), "judge_evidence_index.judge_headline.opencode_runtime")
    if runtime_headline.get("chat_output_is_evidence") is not False:
        raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.chat_output_is_evidence must be false")
    if runtime_headline.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.semantic_gate must be false")
    if opencode_runtime_result is not None:
        if runtime_headline.get("enabled") is not True:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.enabled must be true")
        if runtime_headline.get("worker_count") != opencode_runtime_result["worker_count"]:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.worker_count must match opencode_agent_runtime.worker_count")
        if runtime_headline.get("all_contracts_executed") is not True:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.all_contracts_executed must be true")
    else:
        if runtime_headline.get("enabled") is not False:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.enabled must be false without opencode_agent_runtime")

    return {
        "status": "passed",
        "report_kind": "judge-headline",
        "worker_count": headline.get("worker_count"),
        "repair_round_cap": headline.get("repair_round_cap"),
        "opencode_runtime_enabled": runtime_headline.get("enabled"),
    }


def validate_judge_evidence_artifact_refs(
    payload: dict[str, Any],
    *,
    expected_artifacts: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    opencode_runtime_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refs = payload.get("evidence_artifact_refs")
    if refs is None:
        if expected_artifacts or opencode_runtime_result is not None:
            raise ValueError("judge_evidence_index.evidence_artifact_refs must be an object")
        return {"status": "skipped", "reason": "evidence_artifact_refs not declared"}
    refs_payload = require_object(refs, "judge_evidence_index.evidence_artifact_refs")
    if "judge_evidence_index" in refs_payload:
        raise ValueError("judge_evidence_index.evidence_artifact_refs must not include judge_evidence_index")

    validated_refs = {
        name: validate_artifact_binding_shape(ref, f"judge_evidence_index.evidence_artifact_refs.{name}", repo_root=repo_root)
        for name, ref in sorted(refs_payload.items())
    }
    if expected_artifacts is not None:
        missing: list[str] = []
        for artifact_name in sorted(expected_artifacts):
            if artifact_name == "judge_evidence_index":
                continue
            ref_name = artifact_ref_key_for_expected_artifact(artifact_name)
            if ref_name not in validated_refs:
                missing.append(artifact_name)
                continue
            expected_path = require_string(expected_artifacts[artifact_name], f"expected_artifacts.{artifact_name}")
            try:
                assert_repo_relative_posix(expected_path)
            except ValueError as error:
                raise ValueError(f"expected_artifacts.{artifact_name}: {error}") from error
            if validated_refs[ref_name]["path"] != expected_path:
                raise ValueError(f"judge_evidence_index.evidence_artifact_refs.{ref_name}.path must match expected_artifacts.{artifact_name}")
        if missing:
            raise ValueError(f"judge_evidence_index.evidence_artifact_refs missing expected artifacts: {missing}")
    if opencode_runtime_result is not None:
        if "opencode_preflight_report" not in validated_refs:
            raise ValueError("judge_evidence_index.evidence_artifact_refs missing required OpenCode ref: opencode_preflight_report")
        compare_artifact_binding(
            validated_refs["opencode_preflight_report"],
            opencode_runtime_result["opencode_preflight_report"],
            "judge_evidence_index.evidence_artifact_refs.opencode_preflight_report",
        )

    route_metrics_contract = None
    if repo_root is not None and "route_governance_metrics_report" in validated_refs:
        route_metrics_contract = validate_route_governance_metrics_report_contract(
            validated_refs["route_governance_metrics_report"],
            repo_root=repo_root,
        )

    profile_launch_policy = None
    profile_ref = payload.get("profile")
    if "profile" in validated_refs:
        profile_binding = validated_refs["profile"]
        if isinstance(profile_ref, dict):
            profile_payload_binding = validate_artifact_binding_shape(profile_ref, "judge_evidence_index.profile", repo_root=repo_root)
            compare_artifact_binding(
                profile_binding,
                profile_payload_binding,
                "judge_evidence_index.evidence_artifact_refs.profile",
            )
        if repo_root is not None and opencode_runtime_result is not None:
            profile_payload = load_json(repo_path(profile_binding["path"], repo_root=repo_root))
            if profile_payload.get("mode") == "opencode":
                profile_launch_policy = validate_opencode_profile_launch_policy(
                    profile_payload,
                    entry_id="judge_evidence_index.profile",
                )
                compare_opencode_launch_policy(
                    opencode_runtime_result["opencode_preflight_report"]["launch_policy"],
                    profile_launch_policy,
                    "opencode_agent_runtime.opencode_preflight_report",
                    expected_label="profile launch policy",
                )
    architecture = require_object(payload.get("harness_architecture"), "judge_evidence_index.harness_architecture")
    for name in ("context_pack", "agent_index"):
        ref = architecture.get(name)
        if expected_artifacts is not None and name in expected_artifacts and not isinstance(ref, dict):
            raise ValueError(
                f"judge_evidence_index.harness_architecture.{name} is required "
                f"when expected_artifacts.{name} is declared"
            )
        if isinstance(ref, dict) and name in validated_refs:
            architecture_binding = validate_artifact_binding_shape(
                ref,
                f"judge_evidence_index.harness_architecture.{name}",
                repo_root=repo_root,
            )
            compare_artifact_binding(validated_refs[name], architecture_binding, f"judge_evidence_index.evidence_artifact_refs.{name}")

    result: dict[str, Any] = {
        "status": "passed",
        "ref_count": len(validated_refs),
        "refs": sorted(validated_refs),
    }
    if route_metrics_contract is not None:
        result["route_governance_metrics_report"] = route_metrics_contract
    if profile_launch_policy is not None:
        result["profile_launch_policy"] = profile_launch_policy
    return result


def validate_judge_evidence_index_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
    repo_root: Path | None = None,
    expected_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if payload.get("report_kind") != "judge-evidence-index":
        raise ValueError(f"judge_evidence_index report_kind must be judge-evidence-index: {path_text}")
    boundary = require_object(payload.get("claim_boundary"), "judge_evidence_index.claim_boundary")
    if boundary.get("semantic_claim_source") != "accepted_evidence_binding":
        raise ValueError("judge_evidence_index.claim_boundary.semantic_claim_source must be accepted_evidence_binding")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("judge_evidence_index.claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("judge_evidence_index.claim_boundary.translation_coverage_numerator must be 0")
    if boundary.get("index_is_semantic_gate") is not False:
        raise ValueError("judge_evidence_index.claim_boundary.index_is_semantic_gate must be false")

    architecture = require_object(payload.get("harness_architecture"), "judge_evidence_index.harness_architecture")
    contracts = require_object(architecture.get("architecture_contracts"), "judge_evidence_index.architecture_contracts")
    context_contract = require_object(contracts.get("context_management"), "judge_evidence_index.context_management")
    agent_contract = require_object(contracts.get("agent_coordination"), "judge_evidence_index.agent_coordination")
    if context_contract.get("chat_output_is_evidence") is not False or context_contract.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.context_management must keep chat_output_is_evidence=false and semantic_gate=false")
    if agent_contract.get("chat_output_is_evidence") is not False or agent_contract.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.agent_coordination must keep chat_output_is_evidence=false and semantic_gate=false")
    roles = agent_contract.get("roles")
    if not isinstance(roles, list) or set(roles) != set(REQUIRED_AGENT_ROLES):
        raise ValueError("judge_evidence_index.agent_coordination.roles must list all required roles")
    opencode_runtime_result = None
    evidence_refs = payload.get("evidence_artifact_refs")
    has_opencode_runtime_signal = (
        payload.get("mode") == "opencode"
        or (isinstance(evidence_refs, dict) and "opencode_preflight_report" in evidence_refs)
    )
    if has_opencode_runtime_signal and "opencode_agent_runtime" not in payload:
        raise ValueError("opencode_agent_runtime is required when judge_evidence_index.mode is opencode")
    if "opencode_agent_runtime" in payload:
        opencode_runtime_result = validate_opencode_agent_runtime_contract(
            payload.get("opencode_agent_runtime"),
            repo_root=repo_root,
        )
        if "run_id" in payload and opencode_runtime_result["opencode_preflight_report"].get("run_id") != payload.get("run_id"):
            raise ValueError("opencode_agent_runtime.opencode_preflight_report.run_id must match judge_evidence_index.run_id")
    graph_contract = validate_judge_graph_contract(
        architecture,
        opencode_runtime_result=opencode_runtime_result,
    )
    headline_contract = validate_judge_headline_contract(
        payload,
        boundary=boundary,
        architecture=architecture,
        opencode_runtime_result=opencode_runtime_result,
    )
    artifact_refs = validate_judge_evidence_artifact_refs(
        payload,
        expected_artifacts=expected_artifacts,
        repo_root=repo_root,
        opencode_runtime_result=opencode_runtime_result,
    )
    local_path_scan = validate_local_absolute_path_policy(payload, label=f"judge_evidence_index {path_text}")

    result = {
        "path": path_text,
        "status": "passed",
        "architecture_contracts": "passed",
        "graph_contract": graph_contract,
        "judge_headline": headline_contract,
        "evidence_artifact_refs": artifact_refs,
        "local_absolute_path_scan": local_path_scan,
    }
    if opencode_runtime_result is not None:
        result["opencode_agent_runtime"] = opencode_runtime_result
    return result


def worker_ids_from_entries(entries: Any, *, label: str) -> set[str]:
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{label} must be a non-empty list")
    worker_ids: set[str] = set()
    for index, entry in enumerate(entries):
        entry_payload = require_object(entry, f"{label}[{index}]")
        worker_id = require_string(entry_payload.get("worker_id"), f"{label}[{index}].worker_id")
        worker_ids.add(worker_id)
    if len(worker_ids) != len(entries):
        raise ValueError(f"{label} worker_id values must be unique")
    return worker_ids


def entries_by_worker_id(entries: list[Any], *, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        entry_payload = require_object(entry, f"{label}[{index}]")
        worker_id = require_string(entry_payload.get("worker_id"), f"{label}[{index}].worker_id")
        result[worker_id] = entry_payload
    return result


def validate_context_agent_index_consistency(
    context_payload: dict[str, Any],
    agent_payload: dict[str, Any],
) -> dict[str, Any]:
    context_workers = context_payload.get("workers")
    agents = agent_payload.get("agents")
    agents_by_worker_id = require_object(agent_payload.get("agents_by_worker_id"), "agents_by_worker_id")
    context_worker_ids = worker_ids_from_entries(context_workers, label="context_pack.workers")
    agent_ids = worker_ids_from_entries(agents, label="agent_index.agents")
    indexed_ids = set(agents_by_worker_id)
    if context_worker_ids != agent_ids or context_worker_ids != indexed_ids:
        raise ValueError(
            "context_pack.workers, agent_index.agents, and agents_by_worker_id worker ids must match: "
            f"{sorted(context_worker_ids)} != {sorted(agent_ids)} != {sorted(indexed_ids)}"
        )

    context_by_worker_id = entries_by_worker_id(context_workers, label="context_pack.workers")
    agents_by_list_id = entries_by_worker_id(agents, label="agent_index.agents")
    comparable_fields = (
        "assignment_path",
        "request_path",
        "summary_path",
        "report_path",
        "slice_id",
        "function",
        "source_commit",
        "source_sha256",
    )
    for worker_id in sorted(context_worker_ids):
        context_worker = context_by_worker_id[worker_id]
        agent_entry = require_object(agents_by_worker_id[worker_id], f"agents_by_worker_id.{worker_id}")
        listed_agent = agents_by_list_id[worker_id]
        for field in comparable_fields:
            values = [payload.get(field) for payload in (context_worker, listed_agent, agent_entry) if field in payload]
            if values and any(value != values[0] for value in values[1:]):
                raise ValueError(f"worker {worker_id} field {field} must match across context_pack and agent_index")

    return {"status": "passed", "worker_count": len(context_worker_ids)}


def validate_resume_manifest_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
    expected_artifacts: dict[str, Any],
    context_payload: dict[str, Any] | None,
    agent_payload: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any]:
    if payload.get("report_kind") != "resume-manifest":
        raise ValueError(f"resume_manifest report_kind must be resume-manifest: {path_text}")
    if payload.get("schema_version") != 1:
        raise ValueError("resume_manifest.schema_version must be 1")
    if payload.get("semantic_gate") is not False:
        raise ValueError("resume_manifest.semantic_gate must be false")
    if payload.get("chat_output_is_evidence") is not False:
        raise ValueError("resume_manifest.chat_output_is_evidence must be false")
    boundary = require_object(payload.get("claim_boundary"), "resume_manifest.claim_boundary")
    if boundary.get("semantic_gate") is not False:
        raise ValueError("resume_manifest.claim_boundary.semantic_gate must be false")
    if boundary.get("chat_output_is_evidence") is not False:
        raise ValueError("resume_manifest.claim_boundary.chat_output_is_evidence must be false")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("resume_manifest.claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("resume_manifest.claim_boundary.translation_coverage_numerator must be 0")

    ledger = require_object(payload.get("ledger"), "resume_manifest.ledger")
    if ledger.get("checkpoint_backend") != "sqlite":
        raise ValueError("resume_manifest.ledger.checkpoint_backend must be sqlite")
    ledger_path = require_string(ledger.get("path"), "resume_manifest.ledger.path")
    assert_repo_relative_posix(ledger_path)
    if not repo_path(ledger_path, repo_root=repo_root).is_file():
        raise ValueError("resume_manifest.ledger.path must exist")

    context_binding = validate_artifact_binding_shape(
        payload.get("context_pack"),
        "resume_manifest.context_pack",
        repo_root=repo_root,
    )
    agent_binding = validate_artifact_binding_shape(
        payload.get("agent_index"),
        "resume_manifest.agent_index",
        repo_root=repo_root,
    )
    expected_context = expected_artifacts.get("context_pack")
    expected_agent = expected_artifacts.get("agent_index")
    if isinstance(expected_context, str) and context_binding["path"] != expected_context:
        raise ValueError("resume_manifest.context_pack.path must match expected_artifacts.context_pack")
    if isinstance(expected_agent, str) and agent_binding["path"] != expected_agent:
        raise ValueError("resume_manifest.agent_index.path must match expected_artifacts.agent_index")

    if context_payload is not None:
        entrypoints = require_object(context_payload.get("entrypoints"), "context_pack.entrypoints")
        if entrypoints.get("resume_manifest") != path_text:
            raise ValueError("context_pack.entrypoints.resume_manifest must match expected_artifacts.resume_manifest")
    if agent_payload is not None:
        reports = require_object(agent_payload.get("reports"), "agent_index.reports")
        resume_report = require_object(reports.get("resume_manifest"), "agent_index.reports.resume_manifest")
        if resume_report.get("path") != path_text:
            raise ValueError("agent_index.reports.resume_manifest.path must match expected_artifacts.resume_manifest")

    entrypoints = payload.get("resume_entrypoints")
    if not isinstance(entrypoints, list):
        raise ValueError("resume_manifest.resume_entrypoints must be a list")
    for required in ("evaluate --profile", "run-plan --plan", "run-worker --assignment"):
        if required not in entrypoints:
            raise ValueError(f"resume_manifest.resume_entrypoints missing {required}")

    workers = payload.get("workers")
    if not isinstance(workers, list):
        raise ValueError("resume_manifest.workers must be a list")
    if payload.get("worker_count") != len(workers):
        raise ValueError("resume_manifest.worker_count must match workers length")
    for index, worker in enumerate(workers):
        worker_payload = require_object(worker, f"resume_manifest.workers[{index}]")
        require_string(worker_payload.get("worker_id"), f"resume_manifest.workers[{index}].worker_id")
        for field in ("assignment_path", "request_path", "summary_path", "report_path", "isolated_out_root"):
            value = worker_payload.get(field)
            if isinstance(value, str):
                assert_repo_relative_posix(value)
    local_path_scan = validate_local_absolute_path_policy(payload, label=f"resume_manifest {path_text}")
    return {
        "path": path_text,
        "status": "passed",
        "checkpoint_backend": "sqlite",
        "worker_count": len(workers),
        "local_absolute_path_scan": local_path_scan,
    }


def validate_worker_plan_contract(
    worker_plan_payload: dict[str, Any],
    context_payload: dict[str, Any],
    agent_payload: dict[str, Any],
    *,
    path_text: str,
) -> dict[str, Any]:
    if worker_plan_payload.get("schema_version") != 1:
        raise ValueError("worker_plan.schema_version must be 1")
    if worker_plan_payload.get("status") != "planned":
        raise ValueError("worker_plan.status must be planned")
    raw_planning_mode = worker_plan_payload.get("planning_mode")
    if isinstance(raw_planning_mode, str) and raw_planning_mode:
        planning_mode = raw_planning_mode
    elif isinstance(worker_plan_payload.get("source_file"), str) and worker_plan_payload.get("source_file"):
        planning_mode = "source_file"
    else:
        raise ValueError("worker_plan.planning_mode must be a non-empty string")
    plan_path = require_string(worker_plan_payload.get("plan_path"), "worker_plan.plan_path")
    assert_repo_relative_posix(plan_path)
    if plan_path != path_text:
        raise ValueError("worker_plan.plan_path must match expected_artifacts.worker_plan")

    context_entrypoints = require_object(context_payload.get("entrypoints"), "context_pack.entrypoints")
    context_worker_plan = context_entrypoints.get("worker_plan")
    if isinstance(context_worker_plan, str) and context_worker_plan != path_text:
        raise ValueError("context_pack.entrypoints.worker_plan must match expected_artifacts.worker_plan")

    planner = agent_payload.get("planner")
    if isinstance(planner, dict):
        planner_path = planner.get("plan_path")
        if isinstance(planner_path, str) and planner_path != path_text:
            raise ValueError("agent_index.planner.plan_path must match expected_artifacts.worker_plan")

    units = worker_plan_payload.get("units")
    plan_worker_ids = worker_ids_from_entries(units, label="worker_plan.units")
    context_workers = context_payload.get("workers")
    agents = agent_payload.get("agents")
    agents_by_worker_id = require_object(agent_payload.get("agents_by_worker_id"), "agents_by_worker_id")
    context_worker_ids = worker_ids_from_entries(context_workers, label="context_pack.workers")
    agent_ids = worker_ids_from_entries(agents, label="agent_index.agents")
    indexed_ids = set(agents_by_worker_id)
    if plan_worker_ids != context_worker_ids or plan_worker_ids != agent_ids or plan_worker_ids != indexed_ids:
        raise ValueError(
            "worker_plan.units worker ids must match context_pack.workers and agent_index: "
            f"{sorted(plan_worker_ids)} != {sorted(context_worker_ids)} != {sorted(agent_ids)} != {sorted(indexed_ids)}"
        )

    units_by_worker_id = entries_by_worker_id(units, label="worker_plan.units")
    context_by_worker_id = entries_by_worker_id(context_workers, label="context_pack.workers")
    agents_by_list_id = entries_by_worker_id(agents, label="agent_index.agents")
    comparable_fields = (
        "assignment_path",
        "request_path",
        "slice_id",
        "function",
        "source_commit",
        "require_source_commit",
        "source_file",
        "source_repo_root",
        "source_repository",
        "source_branch",
        "source_sha256",
    )
    for worker_id in sorted(plan_worker_ids):
        unit = units_by_worker_id[worker_id]
        context_worker = context_by_worker_id[worker_id]
        listed_agent = agents_by_list_id[worker_id]
        indexed_agent = require_object(agents_by_worker_id[worker_id], f"agents_by_worker_id.{worker_id}")
        for field in comparable_fields:
            values = [payload.get(field) for payload in (unit, context_worker, listed_agent, indexed_agent) if field in payload]
            if values and any(value != values[0] for value in values[1:]):
                raise ValueError(f"worker {worker_id} field {field} must match across worker_plan, context_pack, and agent_index")
        for field in ("assignment_path", "request_path", "out_root", "slice_spec", "source_repo_root", "source_file"):
            value = unit.get(field)
            if isinstance(value, str):
                assert_repo_relative_posix(value)
        out_root = unit.get("out_root")
        isolated_out_root = indexed_agent.get("isolated_out_root")
        if isinstance(out_root, str) and isinstance(isolated_out_root, str) and out_root != isolated_out_root:
            raise ValueError(f"worker {worker_id} out_root must match agent_index isolated_out_root")

    if isinstance(planner, dict) and planner.get("worker_count") != len(plan_worker_ids):
        raise ValueError("agent_index.planner.worker_count must match worker_plan.units")

    return {
        "status": "passed",
        "path": path_text,
        "planning_mode": planning_mode,
        "worker_count": len(plan_worker_ids),
    }


def validate_context_ledger_contract(
    context_payload: dict[str, Any],
    agent_payload: dict[str, Any],
    *,
    context_path_text: str,
    agent_path_text: str,
    repo_root: Path,
) -> dict[str, Any]:
    contract = require_object(context_payload.get("context_management_contract"), "context_management_contract")
    resume_protocol = require_object(contract.get("resume_protocol"), "context_management_contract.resume_protocol")
    ledger_path_text = require_string(resume_protocol.get("ledger_path"), "context_management_contract.resume_protocol.ledger_path")
    assert_repo_relative_posix(ledger_path_text)
    ledger_path = repo_path(ledger_path_text, repo_root=repo_root)
    if not ledger_path.is_file():
        raise ValueError(f"context_management_contract.resume_protocol.ledger_path does not exist: {ledger_path_text}")

    context_sha = sha256_file(repo_path(context_path_text, repo_root=repo_root))
    agent_sha = sha256_file(repo_path(agent_path_text, repo_root=repo_root))
    try:
        with closing(sqlite3.connect(ledger_path)) as connection:
            context_row = connection.execute(
                """
                select context_pack_id, run_id, artifact_sha256, payload_json
                from context_packs
                where artifact_path=?
                """,
                (context_path_text,),
            ).fetchone()
            if context_row is None:
                raise ValueError("context ledger missing context_packs row for context_pack")
            if context_row[2] != context_sha:
                raise ValueError("context ledger context_packs artifact_sha256 must match context_pack")
            try:
                ledger_payload = json.loads(context_row[3])
            except json.JSONDecodeError as error:
                raise ValueError("context ledger context_packs payload_json must be valid JSON") from error
            if ledger_payload != context_payload:
                raise ValueError("context ledger context_packs payload_json must match context_pack")

            agent_row = connection.execute(
                """
                select sha256, status, semantic_role
                from artifacts
                where kind='agent-index' and repo_rel_path=?
                """,
                (agent_path_text,),
            ).fetchone()
            if agent_row is None:
                raise ValueError("context ledger missing artifacts row for agent_index")
            if agent_row[0] != agent_sha:
                raise ValueError("context ledger agent-index artifact sha256 must match agent_index")
            if agent_row[1] not in {"present", "completed"} or agent_row[2] != "agent-index":
                raise ValueError("context ledger agent-index artifact row must be present/completed with semantic_role=agent-index")

            summary_count = 0
            agents_by_worker_id = require_object(agent_payload.get("agents_by_worker_id"), "agents_by_worker_id")
            for worker_id, agent in sorted(agents_by_worker_id.items()):
                agent_entry = require_object(agent, f"agents_by_worker_id.{worker_id}")
                summary_path_text = require_string(agent_entry.get("summary_path"), f"agents_by_worker_id.{worker_id}.summary_path")
                assert_repo_relative_posix(summary_path_text)
                summary_path = repo_path(summary_path_text, repo_root=repo_root)
                if not summary_path.is_file():
                    raise ValueError(f"context ledger worker summary does not exist: {summary_path_text}")
                summary_sha = sha256_file(summary_path)
                summary_row = connection.execute(
                    """
                    select sha256, status, semantic_role
                    from artifacts
                    where kind='competition-run-summary' and repo_rel_path=?
                    """,
                    (summary_path_text,),
                ).fetchone()
                if summary_row is None:
                    raise ValueError(f"context ledger missing artifacts row for worker summary: {worker_id}")
                if summary_row[0] != summary_sha:
                    raise ValueError(f"context ledger worker summary sha256 must match file: {worker_id}")
                if not worker_summary_row_is_acceptable(
                    row_status=str(summary_row[1]),
                    semantic_role=str(summary_row[2]),
                    context_payload=context_payload,
                    summary_path=summary_path,
                ):
                    raise ValueError(f"context ledger worker summary row must be passed run-summary: {worker_id}")
                summary_count += 1
    except sqlite3.DatabaseError as error:
        raise ValueError(f"context ledger sqlite validation failed: {ledger_path_text}: {error}") from error

    return {
        "path": ledger_path_text,
        "context_pack_id": context_row[0],
        "run_id": context_row[1],
        "context_pack": context_path_text,
        "agent_index": agent_path_text,
        "worker_summary_count": summary_count,
        "status": "passed",
    }


def worker_summary_row_is_acceptable(
    *,
    row_status: str,
    semantic_role: str,
    context_payload: dict[str, Any],
    summary_path: Path,
) -> bool:
    if semantic_role != "run-summary":
        return False
    if row_status == "passed":
        return True
    policy = context_payload.get("attempt_evidence_policy")
    if row_status != "failed" or not isinstance(policy, dict) or policy.get("mode") != "baseline_repair_gate":
        return False
    summary = load_json(summary_path)
    final_gate = summary.get("final_gate") if isinstance(summary.get("final_gate"), dict) else {}
    return final_gate.get("status") == "failed"


def validate_repair_self_heal_contract(context_payload: dict[str, Any]) -> dict[str, Any]:
    policy = context_payload.get("attempt_evidence_policy")
    if policy is None:
        return {"status": "skipped", "reason": "attempt_evidence_policy absent"}
    policy_payload = require_object(policy, "attempt_evidence_policy")
    if policy_payload.get("mode") != "baseline_repair_gate":
        return {"status": "skipped", "reason": f"unsupported attempt_evidence_policy mode: {policy_payload.get('mode')}"}
    baseline = require_object(policy_payload.get("baseline_attempt"), "attempt_evidence_policy.baseline_attempt")
    accepted = require_object(policy_payload.get("accepted_attempt"), "attempt_evidence_policy.accepted_attempt")
    baseline_attempt = baseline.get("attempt_number")
    if baseline_attempt != 1:
        raise ValueError("baseline_repair_gate baseline attempt_number must be 1")
    if baseline.get("expected_final_gate") != "failed":
        raise ValueError("baseline_repair_gate baseline expected_final_gate must be failed")
    root_cause_key = require_string(baseline.get("root_cause_key"), "baseline_repair_gate baseline root_cause_key")
    min_accepted_attempt = accepted.get("min_attempt_number")
    if not isinstance(min_accepted_attempt, int) or min_accepted_attempt < 2:
        raise ValueError("baseline_repair_gate accepted min_attempt_number must be >= 2")
    if accepted.get("require_hint_id") is not True:
        raise ValueError("baseline_repair_gate accepted require_hint_id must be true")

    workers = context_payload.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("baseline_repair_gate requires context_pack.workers")
    checked_workers = 0
    for worker in workers:
        worker_payload = require_object(worker, "context_pack.workers[]")
        attempts = worker_payload.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            continue
        first = next(
            (attempt for attempt in attempts if isinstance(attempt, dict) and attempt.get("attempt") == baseline_attempt),
            None,
        )
        if first is None:
            continue
        if first.get("summary_status") != "failed":
            raise ValueError("baseline_repair_gate attempt 1 summary_status must be failed")
        if first.get("root_cause_key") != root_cause_key:
            raise ValueError("baseline_repair_gate attempt 1 root_cause_key mismatch")
        hint_id = require_string(first.get("hint_id"), "baseline_repair_gate attempt 1 hint_id")
        if first.get("hint_status") != "opened":
            raise ValueError("baseline_repair_gate attempt 1 hint_status must be opened")
        accepted_attempt = next(
            (
                attempt
                for attempt in attempts
                if isinstance(attempt, dict)
                and isinstance(attempt.get("attempt"), int)
                and attempt["attempt"] >= min_accepted_attempt
                and int(attempt.get("exit_code", 1)) == 0
                and attempt.get("summary_status") == "passed"
            ),
            None,
        )
        if accepted_attempt is None:
            raise ValueError("baseline_repair_gate requires a passed accepted retry attempt")
        if accepted_attempt.get("hint_id") != hint_id or accepted_attempt.get("retry_of") != hint_id:
            raise ValueError("baseline_repair_gate accepted retry must bind the opened hint_id")
        rollback = require_object(accepted_attempt.get("rollback_evidence"), "baseline_repair_gate rollback_evidence")
        assert_repo_relative_posix(require_string(rollback.get("path"), "baseline_repair_gate rollback_evidence.path"))
        if not isinstance(rollback.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", rollback["sha256"]):
            raise ValueError("baseline_repair_gate rollback_evidence.sha256 must be a sha256 hex string")
        final_decision = require_object(worker_payload.get("final_decision"), "baseline_repair_gate worker final_decision")
        if final_decision.get("status") != "accepted":
            raise ValueError("baseline_repair_gate worker final_decision.status must be accepted")
        checked_workers += 1
    if checked_workers == 0:
        raise ValueError("baseline_repair_gate did not find a worker with repair attempts")
    return {"status": "passed", "checked_workers": checked_workers, "repair_round_cap": 5}


def validate_expected_json_local_path_policy(
    artifacts: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    scanned: list[str] = []
    allowed_locations: list[str] = []
    for name, value in sorted(artifacts.items()):
        path_text = require_string(value, f"expected_artifacts.{name}")
        if not path_text.endswith(".json"):
            continue
        path = repo_path(path_text, repo_root=repo_root)
        if not path.is_file():
            continue
        scan = validate_local_absolute_path_policy(load_json(path), label=f"expected_artifacts.{name} {path_text}")
        scanned.append(path_text)
        for location in scan["host_trace_allowed_locations"]:
            allowed_locations.append(f"{path_text}{location}")
    return {
        "status": "passed",
        "scanned_count": len(scanned),
        "scanned_artifacts": scanned,
        "host_trace_allowed_count": len(allowed_locations),
        "host_trace_allowed_locations": allowed_locations,
    }


def validate_harness_artifact_contracts(
    artifacts: dict[str, Any],
    *,
    require_local_artifacts: bool,
    repo_root: Path,
    environment_profile: dict[str, Any] | None = None,
    smoke_contract: dict[str, Any] | None = None,
    entrypoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not require_local_artifacts:
        return {"status": "skipped", "reason": "require_local_artifacts=false"}
    result: dict[str, Any] = {"status": "passed"}
    context_payload: dict[str, Any] | None = None
    agent_payload: dict[str, Any] | None = None
    result["expected_json_local_path_policy"] = validate_expected_json_local_path_policy(artifacts, repo_root=repo_root)
    if "context_pack" in artifacts:
        context_path = repo_path(str(artifacts["context_pack"]), repo_root=repo_root)
        context_payload = load_json(context_path)
        result["context_pack"] = validate_context_management_contract(
            context_payload,
            path_text=str(artifacts["context_pack"]),
            expected_artifacts=artifacts,
            repo_root=repo_root,
        )
    if "agent_index" in artifacts:
        agent_path = repo_path(str(artifacts["agent_index"]), repo_root=repo_root)
        agent_payload = load_json(agent_path)
        result["agent_index"] = validate_agent_coordination_contract(
            agent_payload,
            path_text=str(artifacts["agent_index"]),
        )
    if context_payload is not None and agent_payload is not None:
        result["context_agent_consistency"] = validate_context_agent_index_consistency(
            context_payload,
            agent_payload,
        )
        if "worker_plan" in artifacts:
            worker_plan_path = repo_path(str(artifacts["worker_plan"]), repo_root=repo_root)
            result["worker_plan"] = validate_worker_plan_contract(
                load_json(worker_plan_path),
                context_payload,
                agent_payload,
                path_text=str(artifacts["worker_plan"]),
            )
        result["ledger_context_index"] = validate_context_ledger_contract(
            context_payload,
            agent_payload,
            context_path_text=str(artifacts["context_pack"]),
            agent_path_text=str(artifacts["agent_index"]),
            repo_root=repo_root,
        )
    if "resume_manifest" in artifacts:
        resume_manifest_path = repo_path(str(artifacts["resume_manifest"]), repo_root=repo_root)
        result["resume_manifest"] = validate_resume_manifest_contract(
            load_json(resume_manifest_path),
            path_text=str(artifacts["resume_manifest"]),
            expected_artifacts=artifacts,
            context_payload=context_payload,
            agent_payload=agent_payload,
            repo_root=repo_root,
        )
    if context_payload is not None:
        repair_contract = validate_repair_self_heal_contract(context_payload)
        if repair_contract.get("status") != "skipped":
            result["repair_self_heal"] = repair_contract
    if "judge_evidence_index" in artifacts:
        judge_index_path = repo_path(str(artifacts["judge_evidence_index"]), repo_root=repo_root)
        result["judge_evidence_index"] = validate_judge_evidence_index_contract(
            load_json(judge_index_path),
            path_text=str(artifacts["judge_evidence_index"]),
            repo_root=repo_root,
            expected_artifacts=artifacts,
        )
    if "competition_summary" in artifacts:
        competition_summary_path = repo_path(str(artifacts["competition_summary"]), repo_root=repo_root)
        entrypoint_proof_class = None
        entrypoint_run_id = None
        if entrypoint is not None:
            if entrypoint.get("proof_class") is not None:
                entrypoint_proof_class = str(entrypoint.get("proof_class"))
            if entrypoint.get("run_id") is not None:
                entrypoint_run_id = str(entrypoint.get("run_id"))
        result["competition_summary"] = validate_competition_summary_entrypoint_contract(
            load_json(competition_summary_path),
            expected_artifacts=artifacts,
            summary_path=competition_summary_path,
            environment_profile=environment_profile,
            entrypoint_proof_class=entrypoint_proof_class,
            entrypoint_run_id=entrypoint_run_id,
            repo_root=repo_root,
        )
    if "competition_smoke_summary" in artifacts:
        if smoke_contract is None:
            raise ValueError("competition_smoke_summary requires smoke_contract context")
        smoke_summary_path = repo_path(str(artifacts["competition_smoke_summary"]), repo_root=repo_root)
        smoke_summary_payload = load_json(smoke_summary_path)
        result["competition_smoke_summary"] = validate_competition_smoke_summary_contract(
            smoke_summary_payload,
            expected_artifacts=artifacts,
            environment_profile=environment_profile,
            entrypoint_proof_class=str(smoke_contract.get("proof_class")),
            entrypoint_run_id=str(smoke_contract.get("run_id")),
            repo_root=repo_root,
            verify_command_log_sha=True,
        )
        if "command_log" in artifacts:
            command_log_path = repo_path(str(artifacts["command_log"]), repo_root=repo_root)
            result["competition_smoke_command_log"] = validate_competition_smoke_command_log_contract(command_log_path)
        if "vendored_clang_verification" in artifacts:
            vendored_clang_path = repo_path(str(artifacts["vendored_clang_verification"]), repo_root=repo_root)
            result["vendored_clang_verification"] = validate_vendored_clang_verification_contract(
                load_json(vendored_clang_path),
                smoke_summary=smoke_summary_payload,
                environment_profile=environment_profile,
            )
    return result


def validate_config(
    config_path: Path,
    *,
    require_local_artifacts: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config_path = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json(config_path)
    errors: list[str] = []
    entrypoint_results: list[dict[str, Any]] = []

    try:
        if config.get("schema_version") != 1:
            raise ValueError("schema_version must be 1")
        if config.get("manifest_kind") != "judge-entrypoints":
            raise ValueError("manifest_kind must be judge-entrypoints")
        if config.get("status") != "active":
            raise ValueError("status must be active")
        claim_boundary = validate_claim_boundary(config)
        validate_ref(config["environment_profile"], repo_root=repo_root)
        competition_env_bundle_contract = validate_competition_env_bundle_contract(config, repo_root=repo_root)
        assert_no_local_absolute_path(str(config.get("source_pin", {}).get("checkout_command", "")))
    except (KeyError, ValueError) as error:
        errors.append(str(error))
        claim_boundary = {}
        competition_env_bundle_contract = {}

    entrypoints = config.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        errors.append("entrypoints must be a non-empty list")
        entrypoints = []

    dict_entrypoints = [entry for entry in entrypoints if isinstance(entry, dict)]
    try:
        proof_class_contract = validate_proof_class_contract(config, dict_entrypoints)
    except ValueError as error:
        proof_class_contract = {}
        errors.append(str(error))
    try:
        source_pin_contract = validate_source_pin_contract(config, repo_root=repo_root)
    except ValueError as error:
        source_pin_contract = {}
        errors.append(str(error))

    valid_entrypoints: list[dict[str, Any]] = []
    for entry in entrypoints:
        try:
            if not isinstance(entry, dict):
                raise ValueError("entrypoint must be an object")
            valid_entrypoints.append(entry)
            command = entry.get("command")
            if not isinstance(command, str) or "python -B" not in command:
                raise ValueError(f"entrypoint command must use python -B: {entry.get('id')}")
            assert_no_local_absolute_path(command)
            for command_text in entry.get("verification_commands", []):
                assert_no_local_absolute_path(str(command_text))
            audit_command = entry.get("audit_command")
            if isinstance(audit_command, str):
                assert_no_local_absolute_path(audit_command)
            expected_artifacts = entry.get("expected_artifacts", {})
            review_checklist_result = validate_entrypoint_review_checklist_ref(entry, repo_root=repo_root)
            if is_competition_smoke_entrypoint(entry):
                smoke_contract = validate_competition_smoke_entrypoint_contract(entry)
                entry_result = entrypoint_metadata(entry)
                entry_result.update(
                    {
                        "status": "passed",
                        "smoke_contract": smoke_contract,
                        "review_checklist": review_checklist_result["ref"],
                        "review_checklist_contract": review_checklist_result["contract"],
                        "expected_artifacts": validate_expected_artifacts(
                            expected_artifacts,
                            require_local_artifacts=require_local_artifacts,
                            repo_root=repo_root,
                        ),
                        "harness_contracts": validate_harness_artifact_contracts(
                            expected_artifacts,
                            require_local_artifacts=require_local_artifacts,
                            repo_root=repo_root,
                            environment_profile=config.get("environment_profile"),
                            smoke_contract=smoke_contract,
                            entrypoint=entry,
                        ),
                    }
                )
                entrypoint_results.append(
                    entry_result
                )
                continue
            entry_result = entrypoint_metadata(entry)
            entry_result.update(
                {
                    "status": "passed",
                    "profile": validate_ref(entry["profile"], repo_root=repo_root),
                    "profile_contract": (
                        validate_entrypoint_profile_contract(
                            entry,
                            config=config,
                            source_pin_contract=source_pin_contract,
                            repo_root=repo_root,
                        )
                        if source_pin_contract
                        else {"status": "skipped", "reason": "source_pin_contract_failed"}
                    ),
                    "tracked_manifest": validate_ref(entry["tracked_manifest"], repo_root=repo_root),
                    "tracked_manifest_contract": validate_tracked_manifest_contract(
                        entry,
                        config=config,
                        claim_boundary=claim_boundary,
                        source_pin_contract=source_pin_contract,
                        repo_root=repo_root,
                    ),
                    "review_checklist": review_checklist_result["ref"],
                    "review_checklist_contract": review_checklist_result["contract"],
                    "expected_artifacts": validate_expected_artifacts(
                        expected_artifacts,
                        require_local_artifacts=require_local_artifacts,
                        repo_root=repo_root,
                    ),
                    "harness_contracts": validate_harness_artifact_contracts(
                        expected_artifacts,
                        require_local_artifacts=require_local_artifacts,
                        repo_root=repo_root,
                        environment_profile=config.get("environment_profile"),
                        entrypoint=entry,
                    ),
                }
            )
            entrypoint_results.append(
                entry_result
            )
        except (KeyError, ValueError) as error:
            entrypoint_results.append({"id": entry.get("id") if isinstance(entry, dict) else None, "status": "failed"})
            errors.append(str(error))

    try:
        test_contract = validate_test_contract(config, entrypoints=valid_entrypoints, claim_boundary=claim_boundary)
    except ValueError as error:
        test_contract = {}
        errors.append(str(error))

    return {
        "status": "failed" if errors else "passed",
        "config": {"path": repo_relative(config_path, repo_root), "sha256": sha256_file(config_path)},
        "entrypoint_count": len(entrypoint_results),
        "entrypoints": entrypoint_results,
        "claim_boundary": claim_boundary,
        "competition_env_bundle_contract": competition_env_bundle_contract,
        "proof_class_contract": proof_class_contract,
        "source_pin_contract": source_pin_contract,
        "test_contract": test_contract,
        "require_local_artifacts": require_local_artifacts,
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
