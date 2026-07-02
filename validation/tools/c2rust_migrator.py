#!/usr/bin/env python3
"""OpenCode-facing request wrapper for the competition runner."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

from validation.tools import run_competition as competition_runner


RUN_COMPETITION = "validation/tools/run_competition.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
DIRECT_REQUIRED_FIELDS = [
    "source_repo_root",
    "source_file",
    "function",
    "target_id",
    "slice_id",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=["migrate", "verify", "audit"])
    parser.add_argument("--change", default="design-c2rust-migration-agent")
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    request = load_request(args.input)
    repair_trace_result = maybe_write_harness_repair_trace_summary(request)
    if repair_trace_result is not None:
        return int(repair_trace_result["exit_code"])
    argv = build_run_competition_argv(request)
    completed = subprocess.run(argv, check=False)
    return completed.returncode


def load_request(path: str | PurePosixPath) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        request = json.load(handle)
    if not isinstance(request, dict):
        raise SystemExit("request input must be a JSON object")
    return request


def build_run_competition_argv(request: dict[str, Any]) -> list[str]:
    argv = ["python", RUN_COMPETITION]
    worker_summaries = request.get("worker_summaries") or []
    slice_specs = request.get("slice_specs") or ([request["slice_spec"]] if request.get("slice_spec") else [])
    if worker_summaries:
        for summary in expect_string_list(worker_summaries, "worker_summaries"):
            argv.extend(["--worker-summary", checked_posix_path(summary)])
    elif slice_specs:
        checked_slice_specs = [checked_posix_path(slice_spec) for slice_spec in expect_string_list(slice_specs, "slice_specs")]
        validate_slice_spec_source_pins(checked_slice_specs, request)
        for slice_spec in checked_slice_specs:
            argv.extend(["--slice-spec", slice_spec])
    else:
        missing = [field for field in DIRECT_REQUIRED_FIELDS if not request.get(field)]
        if missing:
            raise SystemExit(f"missing required request fields: {', '.join(missing)}")
        argv.extend(
            [
                "--source-repo-root",
                checked_posix_path(str(request["source_repo_root"])),
                "--source-file",
                checked_posix_path(str(request["source_file"])),
                "--function",
                str(request["function"]),
                "--target-id",
                str(request["target_id"]),
                "--slice-id",
                str(request["slice_id"]),
            ]
        )
        if request.get("source_repository"):
            argv.extend(["--source-repository", str(request["source_repository"])])
        if request.get("source_branch"):
            argv.extend(["--source-branch", str(request["source_branch"])])
        if request.get("source_commit"):
            argv.extend(["--source-commit", str(request["source_commit"])])
        if request.get("require_source_commit"):
            argv.extend(["--require-source-commit", str(request["require_source_commit"])])
        if request.get("compiler_command_source"):
            argv.extend(["--compiler-command-source", checked_posix_path(str(request["compiler_command_source"]))])
        for include_path in expect_string_list(request.get("include_paths") or [], "include_paths"):
            argv.extend(["--include-path", checked_posix_path(include_path)])
        for define in expect_string_list(request.get("defines") or [], "defines"):
            argv.extend(["--define", define])

    out_root = checked_posix_path(str(request.get("out_root", "target/competition-out")))
    proof_class = str(request.get("proof_class", "local-simulation"))
    argv.extend(["--out-root", out_root, "--proof-class", proof_class])
    if request.get("reuse_accepted_evidence"):
        argv.append("--reuse-accepted-evidence")
        if request.get("accepted_evidence_root"):
            argv.extend(["--accepted-evidence-root", checked_posix_path(str(request["accepted_evidence_root"]))])
    if request.get("run_id"):
        argv.extend(["--run-id", str(request["run_id"])])
    return argv


def maybe_write_harness_repair_trace_summary(request: dict[str, Any]) -> dict[str, Any] | None:
    policy = request.get("harness_repair_trace")
    if not isinstance(policy, dict):
        return None
    if policy.get("mode") != "baseline_repair_gate":
        return None
    attempt_number = request_attempt_number(request)
    baseline_attempt = policy.get("baseline_attempt") if isinstance(policy.get("baseline_attempt"), dict) else {}
    baseline_attempt_number = int(baseline_attempt.get("attempt_number", 1))
    if attempt_number == baseline_attempt_number:
        summary_path = write_baseline_repair_gate_summary(request, policy)
        return {
            "status": "baseline_repair_gate_failed",
            "exit_code": 0,
            "summary_path": summary_path.as_posix(),
        }
    accepted_attempt = policy.get("accepted_attempt") if isinstance(policy.get("accepted_attempt"), dict) else {}
    if accepted_attempt.get("require_hint_id") is True and not request.get("harness_repair_hint_id"):
        raise SystemExit("baseline_repair_gate accepted attempt requires harness_repair_hint_id")
    return None


def request_attempt_number(request: dict[str, Any]) -> int:
    value = request.get("harness_attempt_number")
    if isinstance(value, int) and value >= 1:
        return value
    attempt = request.get("harness_attempt")
    if isinstance(attempt, dict) and isinstance(attempt.get("attempt"), int) and attempt["attempt"] >= 1:
        return int(attempt["attempt"])
    return 1


def write_baseline_repair_gate_summary(request: dict[str, Any], policy: dict[str, Any]) -> Path:
    out_root = REPO_ROOT / checked_posix_path(str(request.get("out_root", "target/competition-out")))
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary").mkdir(parents=True, exist_ok=True)
    (out_root / "logs").mkdir(parents=True, exist_ok=True)
    (out_root / "evidence").mkdir(parents=True, exist_ok=True)
    evidence = load_bound_translation_before_after(policy)
    validate_baseline_repair_gate_request(request, evidence)
    unsafe_reduction = evidence["unsafe_reduction"]
    baseline_total = int(unsafe_reduction["baseline_total_unsafe"])
    current_total = int(unsafe_reduction["current_total_unsafe"])
    root_cause_key = baseline_repair_root_cause(policy)
    summary = {
        "schema_version": 1,
        "run_id": str(request.get("run_id", "baseline-repair-gate")),
        "proof_class": str(request.get("proof_class", "local-simulation")),
        "profile_id": competition_runner.profile_id(REPO_ROOT),
        "profile_sha256": competition_runner.sha256(REPO_ROOT / "config/competition-env/environment.json"),
        "clang_source": competition_runner.clang_source(REPO_ROOT),
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": 0,
        "translator_version": "0.1.0",
        "slices": {
            "attempted": 1,
            "typed_ir_generated": 1,
            "compiled": 1,
            "semantic_pass": 0,
            "refused": 0,
            "blocked": 0,
            "failed": 1,
        },
        "unsafe_budget": {
            "status": "failed",
            "total_first_party_non_test_unsafe": baseline_total,
            "ratio": 1.0 if baseline_total > 0 else 0.0,
        },
        "artifact_roots": [
            "target/competition-out/evidence",
            "target/competition-out/summary",
            "target/competition-out/logs",
        ],
        "final_gate": {
            "status": "failed",
            "validator": "baseline_repair_gate",
        },
    }
    unit_status = {
        "unit_id": f"{evidence['target_id']}/{evidence['slice_id']}",
        "source": "baseline_repair_gate",
        "status": "failed",
        "compiled": True,
        "semantic_pass": False,
        "refused": False,
        "blocked": False,
        "failed": True,
        "root_cause_key": root_cause_key,
        "translation_before_after": evidence,
    }
    return competition_runner.write_summary_with_workflow_metrics(
        summary,
        unit_statuses=[unit_status],
        worker_workflow_metrics=[],
        out_root=out_root,
        repo_root=REPO_ROOT,
    )


def load_bound_translation_before_after(policy: dict[str, Any]) -> dict[str, Any]:
    ref = policy.get("translation_before_after")
    baseline_attempt = policy.get("baseline_attempt") if isinstance(policy.get("baseline_attempt"), dict) else {}
    if ref is None:
        ref = baseline_attempt.get("translation_before_after")
    if isinstance(ref, str):
        path_text = ref
        expected_sha = None
    elif isinstance(ref, dict):
        path_text = str(ref.get("path", ""))
        expected_sha = ref.get("sha256")
    else:
        raise SystemExit("baseline_repair_gate translation_before_after is required")
    path = REPO_ROOT / checked_posix_path(path_text)
    if not path.exists():
        raise SystemExit(f"baseline_repair_gate translation_before_after does not exist: {path_text}")
    if expected_sha is not None and sha256_file(path) != str(expected_sha):
        raise SystemExit("baseline_repair_gate translation_before_after.sha256 mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("baseline_repair_gate translation_before_after must be an object")
    for field in ("baseline", "final", "oracle_evidence", "accepted_patch", "patch_log"):
        validate_path_sha_binding(payload, field)
    unsafe_reduction = payload.get("unsafe_reduction")
    if not isinstance(unsafe_reduction, dict):
        raise SystemExit("baseline_repair_gate unsafe_reduction is required")
    baseline_total = unsafe_reduction.get("baseline_total_unsafe")
    current_total = unsafe_reduction.get("current_total_unsafe")
    if not isinstance(baseline_total, int) or not isinstance(current_total, int) or baseline_total <= current_total:
        raise SystemExit("baseline_repair_gate requires baseline unsafe count above current unsafe count")
    validate_bound_verified_unsafe_baseline(policy, payload)
    return payload


def validate_bound_verified_unsafe_baseline(policy: dict[str, Any], before_after: dict[str, Any]) -> None:
    baseline_attempt = policy.get("baseline_attempt") if isinstance(policy.get("baseline_attempt"), dict) else {}
    policy_ref = baseline_attempt.get("verified_unsafe_baseline")
    if policy_ref is None:
        policy_ref = policy.get("verified_unsafe_baseline")
    evidence_ref = before_after.get("baseline_verification")
    if policy_ref is None and evidence_ref is None:
        return
    if not isinstance(policy_ref, dict):
        raise SystemExit("baseline_repair_gate verified_unsafe_baseline is required")
    if not isinstance(evidence_ref, dict):
        raise SystemExit("baseline_repair_gate translation_before_after.baseline_verification is required")
    policy_path = verified_unsafe_baseline_ref_path(policy_ref, "verified_unsafe_baseline")
    evidence_path = verified_unsafe_baseline_ref_path(evidence_ref, "translation_before_after.baseline_verification")
    if str(policy_ref.get("path")) != str(evidence_ref.get("path")) or str(policy_ref.get("sha256")) != str(evidence_ref.get("sha256")):
        raise SystemExit("baseline_repair_gate verified_unsafe_baseline must match translation_before_after.baseline_verification")
    if policy_path != evidence_path:
        raise SystemExit("baseline_repair_gate verified_unsafe_baseline path mismatch")
    validate_verified_unsafe_baseline_status(policy_ref, "verified_unsafe_baseline")
    validate_verified_unsafe_baseline_status(evidence_ref, "translation_before_after.baseline_verification")
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("baseline_repair_gate verified_unsafe_baseline artifact must be an object")
    validate_verified_unsafe_baseline_status(payload, "verified_unsafe_baseline")


def verified_unsafe_baseline_ref_path(ref: dict[str, Any], label: str) -> Path:
    path_text = ref.get("path")
    expected_sha = ref.get("sha256")
    if not isinstance(path_text, str) or not isinstance(expected_sha, str):
        raise SystemExit(f"baseline_repair_gate {label}.path and sha256 are required")
    path = REPO_ROOT / checked_posix_path(path_text)
    if not path.exists():
        raise SystemExit(f"baseline_repair_gate {label}.path does not exist: {path_text}")
    if sha256_file(path) != expected_sha:
        raise SystemExit(f"baseline_repair_gate {label}.sha256 mismatch")
    return path


def validate_verified_unsafe_baseline_status(payload: dict[str, Any], label: str) -> None:
    if payload.get("status") is not None and payload.get("status") != "passed":
        raise SystemExit(f"baseline_repair_gate {label} status must be passed")
    if payload.get("semantic_pass") is not None and payload.get("semantic_pass") is not True:
        raise SystemExit(f"baseline_repair_gate {label} semantic_pass must be true")
    if payload.get("semantic_claim_source") is not None and payload.get("semantic_claim_source") != "verified_unsafe_baseline_gates":
        raise SystemExit(f"baseline_repair_gate {label} semantic_claim_source must be verified_unsafe_baseline_gates")
    if payload.get("generated_draft_semantic_pass") is not None and payload.get("generated_draft_semantic_pass") is not False:
        raise SystemExit(f"baseline_repair_gate {label} generated_draft_semantic_pass must be false")


def validate_path_sha_binding(payload: dict[str, Any], field: str) -> None:
    binding = payload.get(field)
    if not isinstance(binding, dict):
        raise SystemExit(f"baseline_repair_gate {field} binding is required")
    path_text = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(path_text, str) or not isinstance(expected_sha, str):
        raise SystemExit(f"baseline_repair_gate {field}.path and sha256 are required")
    path = REPO_ROOT / checked_posix_path(path_text)
    if not path.exists():
        raise SystemExit(f"baseline_repair_gate {field}.path does not exist: {path_text}")
    if sha256_file(path) != expected_sha:
        raise SystemExit(f"baseline_repair_gate {field}.sha256 mismatch")


def validate_baseline_repair_gate_request(request: dict[str, Any], evidence: dict[str, Any]) -> None:
    for field in ("target_id", "slice_id"):
        expected = evidence.get(field)
        actual = request.get(field)
        if isinstance(actual, str) and isinstance(expected, str) and actual != expected:
            raise SystemExit(f"baseline_repair_gate {field} mismatch: {actual} != {expected}")
    claim_boundary = evidence.get("claim_boundary")
    if isinstance(claim_boundary, dict):
        required_commit = request.get("require_source_commit") or request.get("source_commit")
        evidence_commit = claim_boundary.get("source_commit")
        if isinstance(required_commit, str) and isinstance(evidence_commit, str) and required_commit != evidence_commit:
            raise SystemExit("baseline_repair_gate source_commit mismatch")


def baseline_repair_root_cause(policy: dict[str, Any]) -> str:
    baseline_attempt = policy.get("baseline_attempt") if isinstance(policy.get("baseline_attempt"), dict) else {}
    value = baseline_attempt.get("root_cause_key")
    return str(value) if isinstance(value, str) and value else "unsafe_baseline_requires_repair"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_slice_spec_source_pins(slice_specs: list[str], request: dict[str, Any]) -> None:
    required_commit = str(request.get("require_source_commit") or request.get("source_commit") or "")
    if not required_commit:
        return
    for slice_spec in slice_specs:
        spec = load_slice_spec(slice_spec)
        actual_commit = spec.get("source_commit") or spec.get("source", {}).get("source_commit")
        if actual_commit != required_commit:
            raise SystemExit(
                f"slice spec source_commit mismatch for {slice_spec}: {actual_commit or 'missing'} != {required_commit}"
            )


def load_slice_spec(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            spec = json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"slice spec not found while validating source_commit: {path}") from exc
    if not isinstance(spec, dict):
        raise SystemExit(f"slice spec must be a JSON object: {path}")
    return spec


def expect_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SystemExit(f"{field} must be a list of strings")
    return value


def checked_posix_path(value: str) -> str:
    if not value or "\\" in value:
        raise SystemExit(f"path must be a non-empty POSIX relative path: {value}")
    if value.startswith("/") or value.startswith("~"):
        raise SystemExit(f"path must be relative: {value}")
    if len(value) >= 2 and value[1] == ":":
        raise SystemExit(f"path must not contain a drive prefix: {value}")
    if ".." in PurePosixPath(value).parts:
        raise SystemExit(f"path must not escape repository: {value}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
