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
OPENCODE_GLM_HOST_ACCEPTANCE_PATH = "config/competition-env/review-checklists/opencode-glm-host-acceptance.json"
COMPETITION_ENV_BUNDLE_FILE_ROLES = {
    "config/competition-env/README.en.md": "competition-env-readme",
    "config/competition-env/README.md": "competition-env-readme",
    "config/competition-env/apt/sources.list": "apt-mirror",
    "config/competition-env/cargo/config.toml": "cargo-mirror",
    "config/competition-env/env.sh": "environment-shell-entrypoint",
    "config/competition-env/environment.json": "environment-profile",
    "config/competition-env/judge-entrypoints/flashdb-harness.json": "judge-entrypoint-index",
    "config/competition-env/npm/.npmrc": "npm-mirror",
    "config/competition-env/opencode-single-interaction.en.md": "opencode-runbook",
    "config/competition-env/opencode-single-interaction.md": "opencode-runbook",
    "config/competition-env/pip/pip.conf": "pip-mirror",
    "config/competition-env/planned-batches/demo-store-add-one-before-after.json": "planned-batch-profile",
    "config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json": "planned-batch-profile",
    "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json": "planned-batch-profile",
    "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-deepseek-local-rehearsal.json": "planned-batch-profile",
    "config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json": "planned-batch-profile",
    "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json": "planned-batch-profile",
    "config/competition-env/review-checklists/flashdb-harness-internal-review.json": "review-gate",
    OPENCODE_GLM_HOST_ACCEPTANCE_PATH: "opencode-glm-host-acceptance",
    "config/competition-env/rust/rust-toolchain.toml": "rust-toolchain",
    "config/competition-env/smoke.sh": "competition-smoke-entrypoint",
    "config/competition-env/toolchain-check.sh": "toolchain-smoke",
}
COMPETITION_ENV_EXTERNAL_REF_ROLES = {
    "requirements.txt": "python-dependency-lock",
    "opencode.json": "opencode-config",
    "scripts/bootstrap_flashdb_sources.sh": "source-bootstrap-script",
    "scripts/c2rust-migrator.py": "repo-local-c2rust-migrator-entrypoint",
    ".github/workflows/core-translator-validation-ci.yml": "ci-validation-workflow",
    ".opencode/agents/c2rust-migrator.md": "opencode-agent-runbook",
    "crates/c2r-translator/Cargo.lock": "rust-translator-dependency-lock",
    "validation/l2_slices/Cargo.lock": "l2-slices-dependency-lock",
    "flashDB_rust/Cargo.lock": "flashdb-rust-reference-dependency-lock",
}
ROUTE_GOVERNANCE_METRICS_SCHEMA = REPO_ROOT / "validation" / "route-governance-metrics.schema.json"
LOCAL_ABSOLUTE_PATH = re.compile(
    r"(?:(?:^|[^A-Za-z0-9_])|-(?:isystem|iquote|idirafter|include|isysroot|I|L|o)=?|--sysroot=)(?:"
    r"[A-Za-z]:[\\/]|"
    r"/mnt/[A-Za-z](?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/home(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/Users(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/tmp(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/var(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/root(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/usr(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/workspace(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/__w(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/opt(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"/builds(?:/|(?=$|[\s;&|\"'`,)]))|"
    r"\\\\wsl\$\\|"
    r"//wsl\$/|"
    r"\\\\wsl\.localhost\\|"
    r"//wsl\.localhost/|"
    r"\\\\[^\\/\s]+\\[^\\/\s]+(?:\\|(?=$|[\s;&|\"'`,)]))|"
    r"(?<!:)//[^/\s]+/[^/\s]+(?:/|(?=$|[\s;&|\"'`,)]))"
    r")"
)
COMPETITION_SMOKE_REPO_INPUT_FLAGS = {
    "--coverage-report",
    "--out",
    "--output",
    "--slice-spec",
}
COMPETITION_SMOKE_OUTPUT_FLAGS = {
    "--coverage-report",
    "--out",
    "--output",
}
OUT_ROOT_REF_PREFIX = "out-root:"
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
PROFILE_WORKER_PLAN_TUPLE_FIELDS = (
    "target_id",
    "slice_id",
    "function",
    "source_repo_root",
    "source_file",
    "source_commit",
    "require_source_commit",
    "slice_spec",
)
REQUIRED_COMPETITION_SMOKE_STEPS = (
    "environment-check",
    "vendored-clang-verification",
    "core-auto-evidence-validator",
    "evidence-governance",
    "translator-coverage-matrix",
    "milestone-release-report",
    "lightweight-unittest",
)
COMPETITION_SMOKE_PYTHON_STEP_SCRIPTS = {
    "vendored-clang-verification": "validation/tools/verify_vendored_clang.py",
    "core-auto-evidence-validator": "validation/tools/validate_auto_translation_evidence.py",
    "evidence-governance": "validation/tools/evidence_governance.py",
    "translator-coverage-matrix": "validation/tools/translator_coverage_matrix.py",
    "milestone-release-report": "validation/tools/milestone_release_report.py",
}
EXPECTED_ARTIFACT_REF_ALIASES = {
    "competition_summary": "competition_run_summary",
}
BASE_JUDGE_EVIDENCE_REF_KEYS = (
    "agent_index",
    "competition_run_summary",
    "context_pack",
    "internal_review_checklist",
    "milestone_review_checklist",
    "opencode_preflight_report",
    "profile",
    "route_governance_metrics_report",
    "verified_unsafe_baseline",
    "worker_plan",
    "workflow_metrics",
)
VERIFIED_UNSAFE_BASELINE_SAME_OUTPUT_GATES = (
    "c_oracle",
    "rust_replay",
    "schema_diff",
    "negative_diff",
    "unsafe_scan",
    "unsafe_ledger",
    "final_verification",
)
PORTABLE_PYTHON_COMMAND = "python3"
COMPETITION_OPENCODE_COMMAND = "opencode"
COMPETITION_OPENCODE_MODEL = "GLM-5.1"
COMPETITION_OPENCODE_VARIANT = "max"
COMPETITION_OPENCODE_AGENT = "c2rust-migrator"
OPENCODE_RUNTIME_ENV_KEYS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--entrypoint-id",
        action="append",
        default=[],
        help="Entrypoint id to validate. Omit to validate every entrypoint in config order.",
    )
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
        entrypoint_ids=args.entrypoint_id,
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
        "environment_profile_contract": result.get("environment_profile_contract", {}),
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
    errors = [str(error) for error in result.get("errors", []) if str(error)]
    blockers = [classify_readiness_error(error) for error in errors]
    blocker_root_cause_counts: dict[str, int] = {}
    for blocker in blockers:
        root_cause = str(blocker["root_cause_key"])
        blocker_root_cause_counts[root_cause] = blocker_root_cause_counts.get(root_cause, 0) + 1
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
            "blocker_count": len(blockers),
            "blocker_root_cause_counts": blocker_root_cause_counts,
        },
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_claim_source": claim_boundary.get("semantic_claim_source", "accepted_evidence_binding"),
            "generated_draft_semantic_pass": claim_boundary.get("generated_draft_semantic_pass", False),
            "translation_coverage_numerator": claim_boundary.get("translation_coverage_numerator", 0),
        },
        "blockers": blockers,
        "entrypoints": entrypoint_summaries,
    }


def classify_readiness_error(message: str) -> dict[str, str]:
    if "context ledger missing artifacts row for worker report" in message:
        return {
            "root_cause_key": "opencode_artifacts_require_regeneration",
            "message": message,
            "proof_class_effect": "h9_release_blocker",
            "recommended_action": (
                "regenerate OpenCode artifacts on a real GLM-5.1/OpenCode host; "
                "do not hand-edit target artifacts"
            ),
        }
    if (
        "opencode_model_unavailable" in message
        or "required_model_not_listed" in message
        or "model_listed must be true" in message
        or ("GLM-5.1" in message and "model" in message.lower())
    ):
        return {
            "root_cause_key": "opencode_model_unavailable",
            "message": message,
            "proof_class_effect": "h9_release_blocker",
            "recommended_action": "rerun on an OpenCode runtime whose model list exposes GLM-5.1",
        }
    if "opencode preflight" in message or "opencode_preflight" in message:
        return {
            "root_cause_key": "opencode_preflight_contract_invalid",
            "message": message,
            "proof_class_effect": "h9_release_blocker",
            "recommended_action": "regenerate the OpenCode preflight report and bound artifacts through the harness",
        }
    return {
        "root_cause_key": "judge_entrypoint_validation_error",
        "message": message,
        "proof_class_effect": "validation_blocker",
        "recommended_action": "inspect the validator error and regenerate the affected harness artifact",
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


LF_STABLE_TEXT_SUFFIXES = {
    ".c",
    ".h",
    ".json",
    ".jsonl",
    ".lock",
    ".md",
    ".conf",
    ".rs",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
LF_STABLE_TEXT_NAMES = {
    ".npmrc",
    "sources.list",
}


def should_normalize_lf_for_hash(path: Path) -> bool:
    return path.suffix.lower() in LF_STABLE_TEXT_SUFFIXES or path.name in LF_STABLE_TEXT_NAMES


def lf_stable_file_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if not should_normalize_lf_for_hash(path):
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(lf_stable_file_bytes(path)).hexdigest()


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


def validate_portable_python3_b_command(command: Any, label: str) -> list[str]:
    if not isinstance(command, str) or not command:
        raise ValueError(f"{label} must use portable python3 -B")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as error:
        raise ValueError(f"{label} must be POSIX-shlex parseable: {error}") from error
    if len(argv) < 3 or argv[0] != PORTABLE_PYTHON_COMMAND or argv[1] != "-B":
        raise ValueError(f"{label} must use portable python3 -B")
    return argv


def validate_entrypoint_command_contract(command: Any, entrypoint_id: Any) -> list[str]:
    return validate_portable_python3_b_command(command, "entrypoint command")


def validate_opencode_preflight_template_command(command: Any, label: str) -> list[str]:
    argv = validate_portable_python3_b_command(command, label)
    expected_prefix = [
        PORTABLE_PYTHON_COMMAND,
        "-B",
        "-m",
        "validation.tools.opencode_agent_harness",
        "opencode-preflight",
    ]
    if argv[: len(expected_prefix)] != expected_prefix:
        raise ValueError(
            f"{label} must run python3 -B -m validation.tools.opencode_agent_harness opencode-preflight"
        )
    allowed_flags = {"--run-id", "--out-root", "--opencode-model", "--opencode-agent", "--opencode-variant"}
    flags: dict[str, str] = {}
    index = len(expected_prefix)
    while index < len(argv):
        flag = argv[index]
        if not flag.startswith("--"):
            raise ValueError(f"{label} has unexpected positional argument: {flag}")
        if flag not in allowed_flags:
            raise ValueError(f"{label} has unexpected {flag}")
        if flag in flags:
            raise ValueError(f"{label} duplicate {flag}")
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise ValueError(f"{label} {flag} must have a value")
        flags[flag] = argv[index + 1]
        index += 2
    for required in ("--run-id", "--out-root"):
        if required not in flags:
            raise ValueError(f"{label} must include {required}")
    if flags.get("--opencode-model") != COMPETITION_OPENCODE_MODEL:
        raise ValueError(f"{label} must include --opencode-model {COMPETITION_OPENCODE_MODEL}")
    if flags.get("--opencode-agent") != COMPETITION_OPENCODE_AGENT:
        raise ValueError(f"{label} must include --opencode-agent {COMPETITION_OPENCODE_AGENT}")
    if flags.get("--opencode-variant") != COMPETITION_OPENCODE_VARIANT:
        raise ValueError(f"{label} must include --opencode-variant {COMPETITION_OPENCODE_VARIANT}")
    return argv


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


def assert_payload_has_no_local_absolute_path(payload: Any, *, label: str) -> None:
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
            forbidden.append(json_path(parts))

    visit(payload, ())
    if forbidden:
        raise ValueError(f"{label} contains forbidden local absolute path at {forbidden}")


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


def shell_double_quoted_constant(script_text: str, name: str) -> str:
    match = re.search(rf'(?m)^{re.escape(name)}="([^"]*)"$', script_text)
    if not match:
        raise ValueError(f"bootstrap_flashdb_sources.sh {name} must be declared")
    return match.group(1)


def validate_flashdb_bootstrap_source_pin(script_path: Path, source_pin: dict[str, Any]) -> None:
    script_text = script_path.read_text(encoding="utf-8")
    expected_values = {
        "FLASHDB_REPOSITORY": require_string(source_pin.get("repository"), "environment.source_pins.flashdb.repository"),
        "FLASHDB_BRANCH": require_string(source_pin.get("branch"), "environment.source_pins.flashdb.branch"),
        "FLASHDB_COMMIT": require_string(source_pin.get("commit"), "environment.source_pins.flashdb.commit"),
    }
    for constant, expected in expected_values.items():
        actual = shell_double_quoted_constant(script_text, constant)
        if actual != expected:
            raise ValueError(f"bootstrap_flashdb_sources.sh {constant} must match environment.source_pins.flashdb")


def markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{re.escape(heading)}\s*\n(?P<body>.*?)(?=^##\s+|\Z)")
    match = pattern.search(text)
    if not match:
        raise ValueError(f"OpenCode agent runbook must include {heading}")
    return match.group("body")


def validate_opencode_agent_runbook_contract(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required_preflight = markdown_section(text, "Required Preflight")
    lower_required_preflight = required_preflight.lower()
    if "opencode-preflight" not in required_preflight:
        raise ValueError("OpenCode agent runbook Required Preflight must include opencode-preflight")
    for required in (
        f"--opencode-model {COMPETITION_OPENCODE_MODEL}",
        f"--opencode-agent {COMPETITION_OPENCODE_AGENT}",
        f"--opencode-variant {COMPETITION_OPENCODE_VARIANT}",
    ):
        if required not in required_preflight:
            raise ValueError(f"OpenCode agent runbook Required Preflight must include {required}")
    if "openspec" in lower_required_preflight or "superpowers" in lower_required_preflight:
        raise ValueError(
            "OpenCode agent runbook Required Preflight must not depend on OpenSpec or superpowers"
        )
    optional_governance = markdown_section(text, "Optional Governance Checks")
    lower_optional_governance = optional_governance.lower()
    if (
        "openspec" not in lower_optional_governance
        or "not" not in lower_optional_governance
        or "competition preflight" not in lower_optional_governance
    ):
        raise ValueError(
            "OpenCode agent runbook Optional Governance Checks must mark OpenSpec as non-gating"
        )


def validate_opencode_glm_host_acceptance_contract(
    payload: dict[str, Any],
    *,
    label: str = "opencode-glm-host-acceptance",
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    if payload.get("schema_version") != 1:
        raise ValueError(f"{label} schema_version must be 1")
    if payload.get("report_kind") != "opencode-glm-host-acceptance":
        raise ValueError(f"{label} report_kind must be opencode-glm-host-acceptance")
    if payload.get("status") != "blocked":
        raise ValueError(f"{label} status must be blocked until real competition host evidence exists")
    if payload.get("required_agent_tool") != COMPETITION_OPENCODE_COMMAND:
        raise ValueError(f"{label} required_agent_tool must be {COMPETITION_OPENCODE_COMMAND}")
    if payload.get("required_agent") != COMPETITION_OPENCODE_AGENT:
        raise ValueError(f"{label} required_agent must be {COMPETITION_OPENCODE_AGENT}")
    if payload.get("required_model") != COMPETITION_OPENCODE_MODEL:
        raise ValueError(f"{label} required_model must be {COMPETITION_OPENCODE_MODEL}")
    if payload.get("required_variant") != COMPETITION_OPENCODE_VARIANT:
        raise ValueError(f"{label} required_variant must be {COMPETITION_OPENCODE_VARIANT}")
    if payload.get("required_proof_class") != "competition-exact":
        raise ValueError(f"{label} required_proof_class must be competition-exact")
    if payload.get("local_simulation_closes_p0_h9") is not False:
        raise ValueError(f"{label} local_simulation_closes_p0_h9 must be false")
    if payload.get("missing_model_root_cause_key") != "opencode_model_unavailable":
        raise ValueError(f"{label} missing_model_root_cause_key must be opencode_model_unavailable")

    required_evidence = require_object(payload.get("required_evidence"), f"{label}.required_evidence")
    for field in (
        "host_attestation",
        "opencode_model_probe",
        "opencode_preflight_report",
        "opencode_session_evidence",
        "public_packet_competition_host_readiness",
    ):
        if required_evidence.get(field) is not True:
            raise ValueError(f"{label}.required_evidence.{field} must be true")

    acceptance_boundary = require_object(payload.get("acceptance_boundary"), f"{label}.acceptance_boundary")
    for field in ("fresh_lf_clone_required", "all_entrypoints_required", "require_local_artifacts"):
        if acceptance_boundary.get(field) is not True:
            raise ValueError(f"{label}.acceptance_boundary.{field} must be true")
    if acceptance_boundary.get("chat_output_is_evidence") is not False:
        raise ValueError(f"{label}.acceptance_boundary.chat_output_is_evidence must be false")

    claim_boundary = require_object(payload.get("claim_boundary"), f"{label}.claim_boundary")
    if claim_boundary.get("semantic_gate") is not False:
        raise ValueError(f"{label}.claim_boundary.semantic_gate must be false")
    if claim_boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError(f"{label}.claim_boundary.generated_draft_semantic_pass must be false")
    if claim_boundary.get("translation_coverage_numerator") != 0:
        raise ValueError(f"{label}.claim_boundary.translation_coverage_numerator must be 0")
    if claim_boundary.get("chat_output_is_evidence") is not False:
        raise ValueError(f"{label}.claim_boundary.chat_output_is_evidence must be false")

    return {
        "status": "passed",
        "required_agent_tool": COMPETITION_OPENCODE_COMMAND,
        "required_agent": COMPETITION_OPENCODE_AGENT,
        "required_model": COMPETITION_OPENCODE_MODEL,
        "required_variant": COMPETITION_OPENCODE_VARIANT,
        "required_proof_class": "competition-exact",
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "local_simulation_closes_p0_h9": False,
    }


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
    environment_payload = load_json(repo_path(require_string(environment_profile.get("path"), "environment_profile.path"), repo_root=repo_root))
    flashdb_source_pin = require_object(
        require_object(environment_payload.get("source_pins"), "environment.source_pins").get("flashdb"),
        "environment.source_pins.flashdb",
    )

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
        expected_role = COMPETITION_ENV_BUNDLE_FILE_ROLES.get(path_text)
        if expected_role is None:
            raise ValueError(f"competition env bundle unexpected file: {path_text}")
        if role != expected_role:
            raise ValueError(f"competition env bundle file role mismatch for {path_text}: {role} != {expected_role}")
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
        if path_text == OPENCODE_GLM_HOST_ACCEPTANCE_PATH:
            validate_opencode_glm_host_acceptance_contract(load_json(path))

    required_paths = set(COMPETITION_ENV_BUNDLE_FILE_ROLES)
    missing_required = sorted(required_paths - set(result_files))
    if missing_required:
        raise ValueError(f"competition env bundle missing required files: {missing_required}")
    bundle_root = repo_path(COMPETITION_ENV_ROOT, repo_root=repo_root)
    actual_config_files = {
        repo_relative(path, repo_root)
        for path in bundle_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and repo_relative(path, repo_root) != COMPETITION_ENV_BUNDLE_MANIFEST.as_posix()
    }
    omitted_config_files = sorted(actual_config_files - set(result_files))
    if omitted_config_files:
        raise ValueError(f"competition env bundle manifest missing in-folder files: {omitted_config_files}")

    external_refs = manifest.get("external_refs")
    if not isinstance(external_refs, list) or not external_refs:
        raise ValueError("competition env bundle external_refs must be a non-empty list")
    result_external_refs: dict[str, dict[str, Any]] = {}
    external_roles: dict[str, str] = {}
    for ref_entry in external_refs:
        entry = require_object(ref_entry, "competition env bundle external_refs[]")
        path_text = require_string(entry.get("path"), "competition env bundle external_refs[].path")
        role = require_string(entry.get("role"), f"competition env bundle external_ref {path_text}.role")
        expected_sha = require_string(entry.get("sha256"), f"competition env bundle external_ref {path_text}.sha256")
        assert_repo_relative_posix(path_text)
        if path_text.startswith(f"{COMPETITION_ENV_ROOT}/"):
            raise ValueError(f"competition env bundle external_ref must stay outside {COMPETITION_ENV_ROOT}: {path_text}")
        if path_text in result_external_refs:
            raise ValueError(f"competition env bundle duplicate external_ref: {path_text}")
        expected_role = COMPETITION_ENV_EXTERNAL_REF_ROLES.get(path_text)
        if expected_role is None:
            raise ValueError(f"competition env bundle unexpected external_ref: {path_text}")
        if role != expected_role:
            raise ValueError(f"competition env bundle external_ref role mismatch for {path_text}: {role} != {expected_role}")
        path = repo_path(path_text, repo_root=repo_root)
        if not path.is_file():
            raise ValueError(f"competition env bundle external_ref is missing: {path_text}")
        actual_sha = sha256_file(path)
        if expected_sha != actual_sha:
            raise ValueError(
                f"competition env bundle external_ref sha256 mismatch for {path_text}: {expected_sha} != {actual_sha}"
            )
        result_external_refs[path_text] = {
            "path": path_text,
            "role": role,
            "sha256": actual_sha,
            "status": "present",
        }
        external_roles[path_text] = role
        if path_text == "opencode.json":
            opencode_config = load_json(path)
            if opencode_config.get("plugin") != []:
                raise ValueError("opencode.json plugin must be empty for competition profile")
        if path_text == ".opencode/agents/c2rust-migrator.md":
            validate_opencode_agent_runbook_contract(path)
        if path_text == "scripts/bootstrap_flashdb_sources.sh":
            validate_flashdb_bootstrap_source_pin(path, flashdb_source_pin)
    missing_external_refs = sorted(set(COMPETITION_ENV_EXTERNAL_REF_ROLES) - set(result_external_refs))
    if missing_external_refs:
        raise ValueError(f"competition env bundle external_refs missing required refs: {missing_external_refs}")

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
        "external_ref_count": len(result_external_refs),
        "external_refs": sorted(result_external_refs),
        "external_roles": external_roles,
    }


def validate_competition_environment_profile_contract(profile_ref: Any, *, repo_root: Path) -> dict[str, Any]:
    ref = validate_ref(require_object(profile_ref, "environment_profile"), repo_root=repo_root)
    profile = load_json(repo_path(ref["path"], repo_root=repo_root))
    runtime = require_object(profile.get("opencode_runtime"), "environment_profile.opencode_runtime")
    if runtime.get("status") != "required_for_competition_agent_evidence":
        raise ValueError(
            "environment_profile.opencode_runtime.status must be required_for_competition_agent_evidence"
        )
    if runtime.get("command") != COMPETITION_OPENCODE_COMMAND:
        raise ValueError(f"environment_profile.opencode_runtime.command must be {COMPETITION_OPENCODE_COMMAND}")
    if runtime.get("required_model") != COMPETITION_OPENCODE_MODEL:
        raise ValueError(f"environment_profile.opencode_runtime.required_model must be {COMPETITION_OPENCODE_MODEL}")
    if runtime.get("required_agent") != COMPETITION_OPENCODE_AGENT:
        raise ValueError(f"environment_profile.opencode_runtime.required_agent must be {COMPETITION_OPENCODE_AGENT}")
    if runtime.get("required_variant") != COMPETITION_OPENCODE_VARIANT:
        raise ValueError(f"environment_profile.opencode_runtime.required_variant must be {COMPETITION_OPENCODE_VARIANT}")
    probe = require_object(runtime.get("model_probe"), "environment_profile.opencode_runtime.model_probe")
    if probe.get("command") != [COMPETITION_OPENCODE_COMMAND, "models"]:
        raise ValueError("environment_profile.opencode_runtime.model_probe.command must be opencode models")
    if probe.get("required_status") != "available":
        raise ValueError("environment_profile.opencode_runtime.model_probe.required_status must be available")
    if probe.get("required_model_listed") is not True:
        raise ValueError("environment_profile.opencode_runtime.model_probe.required_model_listed must be true")
    if probe.get("missing_model_root_cause_key") != "opencode_model_unavailable":
        raise ValueError(
            "environment_profile.opencode_runtime.model_probe.missing_model_root_cause_key "
            "must be opencode_model_unavailable"
        )
    if probe.get("missing_model_reason") != "required_model_not_listed":
        raise ValueError(
            "environment_profile.opencode_runtime.model_probe.missing_model_reason "
            "must be required_model_not_listed"
        )
    preflight_template = require_string(
        runtime.get("preflight_command_template"),
        "environment_profile.opencode_runtime.preflight_command_template",
    )
    assert_no_local_absolute_path(preflight_template)
    validate_opencode_preflight_template_command(
        preflight_template,
        "environment_profile.opencode_runtime.preflight_command_template",
    )
    boundary = require_object(runtime.get("claim_boundary"), "environment_profile.opencode_runtime.claim_boundary")
    if boundary.get("semantic_gate") is not False:
        raise ValueError("environment_profile.opencode_runtime.claim_boundary.semantic_gate must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError(
            "environment_profile.opencode_runtime.claim_boundary.translation_coverage_numerator must be 0"
        )
    if boundary.get("local_simulation_closes_p0_h9") is not False:
        raise ValueError(
            "environment_profile.opencode_runtime.claim_boundary.local_simulation_closes_p0_h9 must be false"
        )
    return {
        "status": "passed",
        "profile": ref,
        "opencode_runtime": {
            "command": COMPETITION_OPENCODE_COMMAND,
            "required_model": COMPETITION_OPENCODE_MODEL,
            "required_agent": COMPETITION_OPENCODE_AGENT,
            "required_variant": COMPETITION_OPENCODE_VARIANT,
            "model_probe_command": [COMPETITION_OPENCODE_COMMAND, "models"],
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "local_simulation_closes_p0_h9": False,
        },
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
            if part in flags:
                raise ValueError(f"command must not repeat {part}")
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
    expected_prefix = [PORTABLE_PYTHON_COMMAND, "-B", "validation/tools/run_competition_smoke.py"]
    if argv[: len(expected_prefix)] != expected_prefix:
        raise ValueError(
            f"{entry_id} command must execute validation/tools/run_competition_smoke.py as argv[2]"
        )
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
