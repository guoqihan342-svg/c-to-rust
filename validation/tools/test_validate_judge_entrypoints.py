from contextlib import closing
import hashlib
import json
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validation.tools import validate_judge_entrypoints as validator


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENVIRONMENT_SHA256 = validator.sha256_file(REPO_ROOT / "config/competition-env/environment.json")


def load_default_config() -> dict:
    return json.loads(validator.DEFAULT_CONFIG.read_text(encoding="utf-8"))


def entrypoint_by_id(config: dict, entrypoint_id: str) -> dict:
    for entry in config["entrypoints"]:
        if entry.get("id") == entrypoint_id:
            return entry
    raise AssertionError(f"missing entrypoint {entrypoint_id}")


def write_temp_config(payload: dict) -> Path:
    target_dir = REPO_ROOT / "target"
    target_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="judge-entrypoints-test-", dir=target_dir))
    path = temp_dir / "flashdb-harness.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resume_replay_commands(
    *,
    ledger: Path,
    run_id: str,
    worker_id: str,
    assignment: Path,
    request: Path,
    summary: Path,
    report: Path,
    worker_root: Path,
) -> dict:
    argv = [
        "python3",
        "-B",
        "-m",
        "validation.tools.opencode_agent_harness",
        "run-worker",
        "--db",
        repo_relative(ledger),
        "--run-id",
        run_id,
        "--worker-id",
        worker_id,
        "--mode",
        "deterministic",
    ]
    return {
        "run_worker": {
            "argv": argv,
            "command": shlex.join(argv),
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "out_root": repo_relative(worker_root),
        }
    }


def write_valid_command_log(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                {
                    "step": step,
                    "command": ["python3", "-B", "validation/tools/run_competition_smoke.py", "--step", step],
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                },
                sort_keys=True,
            )
            + "\n"
            for step in validator.REQUIRED_COMPETITION_SMOKE_STEPS
        ),
        encoding="utf-8",
    )
    return validator.sha256_file(path)


def temp_json_ref(path: Path, payload: dict) -> dict:
    write_json(path, payload)
    return {"path": repo_relative(path), "sha256": validator.sha256_file(path)}


def artifact_ref(path: str, sha_char: str) -> dict:
    return {"path": path, "sha256": sha_char * 64}


def verified_unsafe_baseline_payload(*, status: str = "passed") -> dict:
    return {
        "report_kind": "c2rust-verified-unsafe-baseline",
        "status": status,
        "semantic_pass": status == "passed",
        "semantic_claim_source": "verified_unsafe_baseline_gates",
        "generated_draft_semantic_pass": False,
    }


def write_verified_unsafe_baseline_ref(path: Path, *, status: str = "passed") -> dict:
    if status == "passed":
        return write_deep_verified_unsafe_baseline_ref(path)
    payload = verified_unsafe_baseline_payload(status=status)
    write_json(path, payload)
    return {
        "path": repo_relative(path),
        "sha256": validator.sha256_file(path),
        "status": status,
        "semantic_pass": status == "passed",
        "semantic_claim_source": "verified_unsafe_baseline_gates",
        "generated_draft_semantic_pass": False,
    }


def write_deep_verified_unsafe_baseline_ref(path: Path) -> dict:
    output_ref = {"path": "validation/evidence/demo/c2rust-output.rs", "sha256": "1" * 64, "status": "generated"}
    compile_ref = {"path": "validation/evidence/demo/c2rust-output.rlib", "sha256": "2" * 64, "status": "compiled"}
    direct_ref = {
        "path": "validation/evidence/demo/l3-demo-c2rust-direct-replay.json",
        "sha256": "3" * 64,
        "status": "passed",
        "binding": "same_c2rust_output",
        "c2rust_output": output_ref,
        "compile_artifact": compile_ref,
        "replay_kind": "direct_c2rust_output_replay",
        "correctness_role": "direct_replay_evidence",
    }
    payload = {
        **verified_unsafe_baseline_payload(status="passed"),
        "c2rust_output": output_ref,
        "compile_artifact": compile_ref,
        "direct_c2rust_replay": {
            "status": "passed",
            "semantic_pass": False,
            "observable_replay_pass": True,
            "artifact": direct_ref,
            "c2rust_output": output_ref,
            "compile_artifact": compile_ref,
        },
        "same_output_gate_refs": {
            "c_oracle": {
                "path": "validation/evidence/demo/c-oracle-status.json",
                "sha256": "4" * 64,
                "status": "C_ORACLE_GENERATED",
                "binding": "same_c2rust_output",
                "c2rust_output": output_ref,
                "compile_artifact": compile_ref,
            },
            "rust_replay": direct_ref,
            "schema_diff": {
                "path": "validation/evidence/demo/diff.json",
                "sha256": "5" * 64,
                "status": "passed",
                "binding": "same_c2rust_output",
                "c2rust_output": output_ref,
                "compile_artifact": compile_ref,
            },
            "negative_diff": {
                "path": "validation/evidence/demo/negative-diff.json",
                "sha256": "6" * 64,
                "status": "expected_failed",
                "binding": "same_c2rust_output",
                "c2rust_output": output_ref,
                "compile_artifact": compile_ref,
            },
            "unsafe_scan": {
                "path": "validation/evidence/demo/unsafe-scan.json",
                "sha256": "7" * 64,
                "status": "passed",
                "binding": "same_c2rust_output",
                "c2rust_output": output_ref,
                "compile_artifact": compile_ref,
            },
            "unsafe_ledger": {
                "path": "validation/evidence/demo/unsafe-ledger.json",
                "sha256": "8" * 64,
                "status": "passed",
                "binding": "same_c2rust_output",
                "c2rust_output": output_ref,
                "compile_artifact": compile_ref,
            },
            "final_verification": {
                "path": "validation/evidence/demo/final-verification.json",
                "status": "passed",
                "binding": "same_c2rust_output",
                "c2rust_output": output_ref,
                "compile_artifact": compile_ref,
            },
        },
    }
    write_json(path, payload)
    return {
        "path": repo_relative(path),
        "sha256": validator.sha256_file(path),
        "status": "passed",
        "semantic_pass": True,
        "semantic_claim_source": "verified_unsafe_baseline_gates",
        "generated_draft_semantic_pass": False,
    }


def write_repair_before_after_ref(
    path: Path,
    verified_ref: dict,
    *,
    unsafe_status: str = "measured",
    reduced_by: int | None = 2,
    baseline_verification: dict | None = None,
) -> dict:
    unsafe_reduction = {
        "status": unsafe_status,
        "baseline_total_unsafe": 2,
        "current_total_unsafe": 0 if reduced_by else 2,
        "reduced_by": reduced_by,
        "ratio": 0.0 if reduced_by else 1.0,
    }
    payload = {
        "schema_version": 1,
        "status": "bound",
        "baseline_verification": baseline_verification or verified_ref,
        "accepted_patch": {"path": "validation/evidence/demo/accepted.patch", "sha256": "a" * 64},
        "patch_log": {"path": "validation/evidence/demo/patch-log.jsonl", "sha256": "b" * 64},
        "unsafe_reduction": unsafe_reduction,
        "claim_boundary": {
            "semantic_claim_source": "accepted_evidence_binding",
            "generated_draft_semantic_pass": False,
        },
    }
    write_json(path, payload)
    return {"path": repo_relative(path), "sha256": validator.sha256_file(path)}


def write_opencode_safety_transform_attempt_ref(path: Path, *, max_repair_rounds: int = 5) -> dict:
    artifact_dir = path.parent / "attempt-evidence"
    refs = {}
    for name in (
        "summary",
        "workflow-metrics",
        "baseline-unsafe.rs",
        "final-safe.rs",
        "accepted.patch",
        "patch-log.jsonl",
        "oracle.json",
        "schema-diff.json",
        "unsafe-scan.json",
        "rollback.json",
    ):
        artifact = artifact_dir / name
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"{name}\n", encoding="utf-8")
        refs[name] = {"path": repo_relative(artifact), "sha256": validator.sha256_file(artifact)}
    payload = {
        "schema_version": 1,
        "report_kind": "opencode-safety-transform-attempt",
        "run_id": "run-test",
        "worker_id": "worker-a",
        "attempt": 2,
        "status": "accepted",
        "summary": {
            **refs["summary"],
            "final_gate_status": "passed",
        },
        "workflow_metrics": refs["workflow-metrics"],
        "contract_verification": {"status": "executed"},
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "attempt_contract": {
            "single_patch_per_round": True,
            "max_repair_rounds": max_repair_rounds,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        "safety_transform_unit_count": 1,
        "safety_transform_units": [
            {
                "unit_id": "demo/store-add-one",
                "status": "converged",
                "attempt": 2,
                "round_contract": {
                    "single_patch_per_round": True,
                    "max_repair_rounds": max_repair_rounds,
                },
                "patch_evidence": {
                    "baseline": refs["baseline-unsafe.rs"],
                    "final": refs["final-safe.rs"],
                    "accepted_patch": refs["accepted.patch"],
                    "patch_log": refs["patch-log.jsonl"],
                },
                "verification_delta": {
                    "compiled": True,
                    "oracle_evidence": refs["oracle.json"],
                    "semantic_evidence": {"schema_diff": refs["schema-diff.json"]},
                    "unsafe_scan_evidence": refs["unsafe-scan.json"],
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 3,
                        "current_total_unsafe": 1,
                        "reduced_by": 2,
                        "ratio": 1 / 3,
                    },
                },
                "rounds": [
                    {
                        "round": 2,
                        "single_patch_per_round": True,
                        "patch": refs["accepted.patch"],
                        "patch_log": refs["patch-log.jsonl"],
                        "oracle_evidence": refs["oracle.json"],
                        "schema_diff": refs["schema-diff.json"],
                        "unsafe_scan_evidence": refs["unsafe-scan.json"],
                        "unsafe_delta": {
                            "status": "measured",
                            "baseline_total_unsafe": 3,
                            "current_total_unsafe": 1,
                            "reduced_by": 2,
                            "ratio": 1 / 3,
                        },
                    }
                ],
                "accepted_retry_hint": {
                    "status": "revalidated_passed",
                    "repair_rounds": 1,
                    "auto_recovered": True,
                    "rollback_ids": [refs["rollback.json"]["path"]],
                    "rollback_evidence": [refs["rollback.json"]],
                },
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
            }
        ],
        "evidence_boundary": "OpenCode chat/session output is audit provenance only.",
    }
    write_json(path, payload)
    return {"path": repo_relative(path), "sha256": validator.sha256_file(path)}


def valid_repair_self_heal_context_payload(*, verified_ref: dict, before_after_ref: dict) -> dict:
    hint_id = "repair:test:worker-001:unsafe_baseline_requires_repair"
    return {
        "attempt_evidence_policy": {
            "accepted_attempt": {
                "min_attempt_number": 2,
                "require_hint_id": True,
            },
            "baseline_attempt": {
                "attempt_number": 1,
                "expected_final_gate": "failed",
                "root_cause_key": "unsafe_baseline_requires_repair",
                "verified_unsafe_baseline": verified_ref,
            },
            "mode": "baseline_repair_gate",
            "translation_before_after": before_after_ref,
        },
        "workers": [
            {
                "attempts": [
                    {
                        "attempt": 1,
                        "exit_code": 1,
                        "hint_id": hint_id,
                        "hint_status": "opened",
                        "root_cause_key": "unsafe_baseline_requires_repair",
                        "summary_status": "failed",
                    },
                    {
                        "attempt": 2,
                        "exit_code": 0,
                        "hint_id": hint_id,
                        "hint_status": "revalidated_passed",
                        "retry_of": hint_id,
                        "rollback_evidence": {
                            "path": "target/out/harness/rollback.json",
                            "sha256": "e" * 64,
                        },
                        "summary_status": "passed",
                    },
                ],
                "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
            }
        ],
    }


def retry_attempt_from_repair_context(context_payload: dict) -> dict:
    return context_payload["workers"][0]["attempts"][1]


def competition_smoke_expected_artifacts() -> dict:
    return {
        "competition_smoke_summary": "target/competition-smoke-flashdb-judge-entrypoint/summary/competition-smoke-summary.json",
        "vendored_clang_verification": "target/competition-smoke-flashdb-judge-entrypoint/summary/vendored-clang-verification.json",
        "evidence_governance_report": "target/competition-smoke-flashdb-judge-entrypoint/reports/evidence-governance.json",
        "translator_coverage_matrix": "target/competition-smoke-flashdb-judge-entrypoint/reports/translator-coverage-matrix.json",
        "milestone_release_report": "target/competition-smoke-flashdb-judge-entrypoint/reports/milestone-release-report.json",
        "command_log": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
    }


def valid_competition_smoke_summary_payload() -> dict:
    return {
        "schema_version": 1,
        "report_kind": "competition-smoke-summary",
        "proof_class": "local-simulation",
        "profile_id": "huawei-competition-ubuntu-24.04",
        "profile_sha256": "a" * 64,
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
        "competition_profile_match": {
            "cargo_mirror_config_present": True,
            "clang_lane_verified": True,
            "kernel_match": True,
            "os_name_match": True,
            "profile_id": "huawei-competition-ubuntu-24.04",
            "profile_sha256_actual": "a" * 64,
            "python_version_match": True,
        },
        "execution_environment": {
            "detected_ci": False,
            "detected_wsl": False,
            "kernel": "5.10.0-182.0.0.95.r194_123.hce2.x86_64",
            "kind": "local-linux",
            "machine": "x86_64",
            "python_version": "3.12.3",
            "release": "5.10.0-182.0.0.95.r194_123.hce2.x86_64",
            "runner_name": "local",
            "system": "Ubuntu",
            "version": "competition-host",
        },
        "environment_deviations": [],
        "timeout_policy": {
            "per_step_timeout_seconds": 600,
            "timeout_exit_code": 124,
            "timeout_is_final_gate_failure": True,
        },
        "smoke_entrypoint": {
            "semantic_acceptance_boundary": "does_not_translate_new_slices",
        },
        "vendored_clang_verification": {
            "path": "target/competition-smoke-flashdb-judge-entrypoint/summary/vendored-clang-verification.json",
        },
        "reports": {
            "evidence_governance": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/evidence-governance.json",
            },
            "translator_coverage_matrix": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/translator-coverage-matrix.json",
            },
        },
        "milestone_release_report": {
            "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/milestone-release-report.json",
            "semantic_acceptance_claim": False,
        },
        "command_log": {
            "path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            "sha256": "a" * 64,
        },
        "final_gate": {"status": "passed"},
        "steps": [
            {
                "step": "environment-check",
                "status": "degraded",
                "returncode": 1,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
                "proof_class_effect": "exactness_blocker",
            },
            {
                "step": "vendored-clang-verification",
                "status": "passed",
                "returncode": 0,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
            {
                "step": "core-auto-evidence-validator",
                "status": "passed",
                "returncode": 0,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
            {
                "step": "evidence-governance",
                "status": "passed",
                "returncode": 0,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
            {
                "step": "translator-coverage-matrix",
                "status": "passed",
                "returncode": 0,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
            {
                "step": "milestone-release-report",
                "status": "passed",
                "returncode": 0,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
            {
                "step": "lightweight-unittest",
                "status": "passed",
                "returncode": 0,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
        ],
    }


def valid_vendored_clang_verification_payload() -> dict:
    return {
        "schema_version": 1,
        "artifact_kind": "vendored-clang-verification",
        "proof_class": "local-simulation",
        "profile_id": "huawei-competition-ubuntu-24.04",
        "profile_sha256": "a" * 64,
        "status": "passed",
        "clang": {
            "source": "CLANG_PATH",
            "path": "tools/llvm/bin/clang-18",
            "version": "clang version 18.1.8",
        },
        "clang_required": False,
        "clang_lane_verified": True,
        "checks": {},
        "command_logs": [],
        "final_gate": {"status": "passed"},
    }


def valid_competition_run_summary_payload(
    *,
    run_id: str,
    proof_class: str = "local-simulation",
    profile_id: str = "huawei-competition-ubuntu-24.04",
    profile_sha256: str = DEFAULT_ENVIRONMENT_SHA256,
) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "proof_class": proof_class,
        "profile_id": profile_id,
        "profile_sha256": profile_sha256,
        "clang_source": "missing",
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": 1,
        "translator_version": "test-fixture",
        "slices": {
            "attempted": 1,
            "typed_ir_generated": 1,
            "compiled": 1,
            "semantic_pass": 1,
            "refused": 0,
            "blocked": 0,
            "failed": 0,
        },
        "unsafe_budget": {
            "status": "passed",
            "total_first_party_non_test_unsafe": 0,
            "ratio": 0.0,
        },
        "artifact_roots": [
            "target/competition-out/evidence",
            "target/competition-out/summary",
            "target/competition-out/logs",
        ],
        "final_gate": {
            "status": "passed",
            "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
        },
    }


def workflow_metrics_for_competition_summary(summary: dict) -> dict:
    slices = summary["slices"]
    return {
        "schema_version": 1,
        "run_id": summary["run_id"],
        "proof_class": summary["proof_class"],
        "units_total": slices["attempted"],
        "units_converged": slices["semantic_pass"],
        "units_baseline_only": max(0, int(slices["compiled"]) - int(slices["semantic_pass"])),
        "unsafe_reduction": {
            "status": "not_measured",
            "baseline_total_unsafe": None,
            "current_total_unsafe": summary["unsafe_budget"]["total_first_party_non_test_unsafe"],
            "reduced_by": None,
            "ratio": summary["unsafe_budget"]["ratio"],
        },
        "translation_before_after": {
            "status": "not_provided",
            "unit_count": 0,
            "measured_unsafe_unit_count": 0,
            "accepted_patch_unit_count": 0,
            "units": [],
        },
        "avg_repair_rounds": 0.0,
        "auto_recovery_rate": 0.0,
        "human_interventions": 0,
        "always_compiles": False,
        "always_equivalent": False,
        "fail_closed_count": int(slices["refused"]) + int(slices["blocked"]),
        "root_cause_counts": {},
        "wall_clock_seconds": summary["elapsed_seconds"],
        "llm_calls": 0,
        "per_unit_statuses": [
            {
                "unit_id": "demo/unit-1",
                "source": "slice-spec",
                "status": "converged",
                "compiled": True,
                "semantic_pass": True,
                "refused": False,
                "blocked": False,
                "failed": False,
            }
        ],
    }


def write_competition_run_summary_with_workflow_metrics(summary_path: Path, summary: dict) -> Path:
    metrics_path = summary_path.parent / "workflow-metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(workflow_metrics_for_competition_summary(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary["workflow_metrics"] = {
        "path": repo_relative(metrics_path),
        "sha256": validator.sha256_file(metrics_path),
    }
    write_json(summary_path, summary)
    return metrics_path


def opencode_launch_policy() -> dict:
    return {
        "opencode_command": "opencode",
        "opencode_model": None,
        "opencode_agent": None,
        "opencode_variant": "max",
        "opencode_skip_permissions": False,
    }


def opencode_launch_policy_sha256(policy: dict) -> str:
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode("utf-8")).hexdigest()


def set_artifact_ref(ref: dict, path: Path, payload: dict | None = None) -> None:
    if payload is None:
        payload = {"report_kind": "test-artifact"}
    write_json(path, payload)
    ref["path"] = repo_relative(path)
    ref["sha256"] = validator.sha256_file(path)


def set_all_opencode_preflight_refs(payload: dict, path: Path, *, run_id: str, launch_policy: dict) -> None:
    preflight_payload = {
        "report_kind": "opencode-preflight-report",
        "status": "passed",
        "marker_exists": True,
        "run_id": run_id,
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "contract_verification": {
            "status": "executed",
            "first_shell_command_matches_worker_command": True,
            "worker_command_seen": True,
            "summary_exists": True,
            "tools_before_first_shell": [],
        },
    }
    write_json(path, preflight_payload)
    binding = {
        "path": repo_relative(path),
        "sha256": validator.sha256_file(path),
        "status": "passed",
        "contract_status": "executed",
        "run_id": run_id,
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
    }
    payload["evidence_artifact_refs"]["opencode_preflight_report"] = json.loads(json.dumps(binding))
    payload["opencode_agent_runtime"]["opencode_preflight_report"] = json.loads(json.dumps(binding))
    for worker in payload["opencode_agent_runtime"]["workers"]:
        worker["opencode_preflight_report"] = json.loads(json.dumps(binding))


def materialize_opencode_judge_index_artifacts(payload: dict, root: Path, *, profile_payload: dict) -> None:
    profile_path = root / "profile.json"
    set_artifact_ref(payload["evidence_artifact_refs"]["profile"], profile_path, profile_payload)
    set_artifact_ref(
        payload["evidence_artifact_refs"]["competition_run_summary"],
        root / "summary" / "competition-run-summary.json",
    )
    set_artifact_ref(payload["evidence_artifact_refs"]["workflow_metrics"], root / "summary" / "workflow-metrics.json")
    set_artifact_ref(payload["evidence_artifact_refs"]["worker_plan"], root / "harness" / "plans" / "workers.json")
    launch_policy = payload["opencode_agent_runtime"]["opencode_preflight_report"]["launch_policy"]
    set_all_opencode_preflight_refs(
        payload,
        root / "harness" / "opencode-preflight-report.json",
        run_id=payload["run_id"],
        launch_policy=launch_policy,
    )
    for worker in payload["opencode_agent_runtime"]["workers"]:
        worker_id = worker["worker_id"]
        worker_root = root / "workers" / worker_id
        set_artifact_ref(worker["summary"], worker_root / "summary" / "competition-run-summary.json")
        set_artifact_ref(worker["worker_report"], worker_root / "harness" / "run-worker-report.json")
        set_artifact_ref(worker["handoff_contract"], worker_root / "harness" / "opencode-handoff-contract.json")
        set_artifact_ref(worker["opencode_session_evidence"], worker_root / "logs" / "opencode-session-evidence.json")
        set_artifact_ref(worker["logs"]["stdout"], worker_root / "logs" / "stdout.log")
        set_artifact_ref(worker["logs"]["stderr"], worker_root / "logs" / "stderr.log")


def valid_opencode_judge_index_payload() -> dict:
    launch_policy = opencode_launch_policy()
    preflight = {
        "path": "target/out/harness/opencode-preflight-report.json",
        "sha256": "a" * 64,
        "status": "passed",
        "contract_status": "executed",
        "run_id": "run-test",
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
    }
    preflight_for_worker = json.loads(json.dumps(preflight))
    preflight_for_refs = json.loads(json.dumps(preflight))
    preflight_for_runtime = json.loads(json.dumps(preflight))
    worker = {
        "worker_id": "worker-a",
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "summary": artifact_ref("target/out/workers/worker-a/summary/competition-run-summary.json", "b"),
        "worker_report": artifact_ref("target/out/workers/worker-a/harness/run-worker-report.json", "c"),
        "logs": {
            "stdout": artifact_ref("target/out/workers/worker-a/logs/stdout.log", "d"),
            "stderr": artifact_ref("target/out/workers/worker-a/logs/stderr.log", "e"),
        },
        "handoff_contract": artifact_ref("target/out/workers/worker-a/harness/opencode-handoff-contract.json", "f"),
        "opencode_session_evidence": artifact_ref("target/out/workers/worker-a/logs/opencode-session-evidence.json", "1"),
        "opencode_preflight_report": preflight_for_worker,
        "contract_verification_status": "executed",
        "opencode_contract_verification": {
            "status": "executed",
            "first_shell_command_matches_worker_command": True,
            "worker_command_seen": True,
            "summary_exists": True,
            "tools_before_first_shell": [],
            "executed_shell_command_count": 1,
            "executed_shell_commands": [
                "python -B scripts/c2rust-migrator.py --phase migrate --input target/out/workers/worker-a/harness/request.json"
            ],
        },
    }
    return {
        "schema_version": 1,
        "report_kind": "judge-evidence-index",
        "status": "completed",
        "run_id": "run-test",
        "mode": "opencode",
        "claim_boundary": {
            "semantic_claim_source": "accepted_evidence_binding",
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "index_is_semantic_gate": False,
        },
        "judge_headline": {
            "report_kind": "judge-headline",
            "status": "completed",
            "mode": "opencode",
            "graph_runtime": "opencode-harness-langgraph-inspired",
            "worker_count": 1,
            "parallelism": {"max_workers": 1, "effective_workers": 1},
            "repair_round_cap": 5,
            "repair_checkpoint": "repair_hints",
            "semantic_gate": False,
            "semantic_claim_source": "accepted_evidence_binding",
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "opencode_runtime": {
                "enabled": True,
                "worker_count": 1,
                "all_contracts_executed": True,
                "chat_output_is_evidence": False,
                "semantic_gate": False,
            },
        },
        "harness_architecture": {
            "graph_runtime": "opencode-harness-langgraph-inspired",
            "graph_nodes": ["load_plan", "fanout_workers", "worker", "repair_retry", "merge", "report"],
            "worker_count": 1,
            "parallelism": {"max_workers": 1, "effective_workers": 1},
            "retry_policy": {"checkpoint": "repair_hints", "enabled": False, "round_cap": 5},
            "architecture_contracts": {
                "context_management": {
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                    "resume_protocol": {"checkpoint_backend": "sqlite"},
                },
                "agent_coordination": {
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                    "checkpoint_backend": "sqlite",
                    "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                },
            },
        },
        "evidence_artifact_refs": {
            "competition_run_summary": artifact_ref("target/out/summary/competition-run-summary.json", "2"),
            "workflow_metrics": artifact_ref("target/out/summary/workflow-metrics.json", "3"),
            "worker_plan": artifact_ref("target/out/harness/plans/workers.json", "4"),
            "profile": artifact_ref("config/competition-env/planned-batches/opencode.json", "5"),
            "opencode_preflight_report": preflight_for_refs,
        },
        "opencode_agent_runtime": {
            "runtime": "opencode",
            "chat_output_is_evidence": False,
            "semantic_gate": False,
            "worker_count": 1,
            "contract_status_counts": {"executed": 1},
            "all_contracts_executed": True,
            "failed_or_missing_contract_workers": [],
            "opencode_preflight_report": preflight_for_runtime,
            "workers": [worker],
        },
    }


def valid_deterministic_judge_index_payload() -> dict:
    payload = valid_opencode_judge_index_payload()
    payload["mode"] = "deterministic"
    payload.pop("opencode_agent_runtime", None)
    payload["evidence_artifact_refs"].pop("opencode_preflight_report", None)
    payload["judge_headline"]["mode"] = "deterministic"
    payload["judge_headline"]["opencode_runtime"] = {
        "enabled": False,
        "worker_count": 0,
        "all_contracts_executed": False,
        "chat_output_is_evidence": False,
        "semantic_gate": False,
    }
    return payload


def write_minimal_context_ledger(
    path: Path,
    *,
    run_id: str,
    context_pack_path: Path,
    context_pack_payload: dict,
    agent_index_path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            create table context_packs(
              context_pack_id text primary key,
              run_id text not null,
              target_id text,
              slice_id text,
              depth integer not null,
              max_tokens integer not null,
              artifact_path text not null,
              artifact_sha256 text not null,
              payload_json text not null
            );
            create table artifacts(
              artifact_id integer primary key autoincrement,
              run_id text not null,
              agent_id text,
              target_id text,
              slice_id text,
              kind text not null,
              repo_rel_path text not null unique,
              sha256 text not null,
              status text not null,
              semantic_role text not null,
              schema_name text,
              payload_status text,
              payload_json text not null,
              created_at text not null
            );
            """
        )
        connection.execute(
            """
            insert into context_packs(
              context_pack_id, run_id, target_id, slice_id, depth, max_tokens,
              artifact_path, artifact_sha256, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}-context-pack",
                run_id,
                "flashdb",
                None,
                1,
                20000,
                repo_relative(context_pack_path),
                validator.sha256_file(context_pack_path),
                json.dumps(context_pack_payload, sort_keys=True),
            ),
        )
        connection.execute(
            """
            insert into artifacts(
              run_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "agent-index",
                repo_relative(agent_index_path),
                validator.sha256_file(agent_index_path),
                "present",
                "agent-index",
                "{}",
                "2026-07-01T00:00:00Z",
            ),
        )
        for worker in context_pack_payload.get("workers", []):
            if not isinstance(worker, dict) or not isinstance(worker.get("summary_path"), str):
                continue
            summary_path = REPO_ROOT / worker["summary_path"]
            if not summary_path.is_file():
                continue
            connection.execute(
                """
                insert into artifacts(
                  run_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "competition-run-summary",
                    worker["summary_path"],
                    validator.sha256_file(summary_path),
                    "passed",
                    "run-summary",
                    "{}",
                    "2026-07-01T00:00:00Z",
                ),
            )
        connection.commit()


def bind_entrypoint_to_out_root(config: dict, temp_config: Path, *, entry_index: int, out_root: Path) -> Path:
    entry = config["entrypoints"][entry_index]
    flags = validator.parsed_command_flags(entry["command"])
    old_out_root = flags["--out-root"]
    new_out_root = repo_relative(out_root)
    entry["command"] = entry["command"].replace(f"--out-root {old_out_root}", f"--out-root {new_out_root}")
    manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
    command_key = validator.expected_manifest_reproduction_command_key(entry)
    manifest["reproduction"][command_key] = entry["command"]
    manifest_path = temp_config.parent / f"{entry['id']}-tracked-manifest.json"
    entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
    return out_root


class JudgeEntrypointsValidatorTests(unittest.TestCase):
    def test_default_flashdb_judge_entrypoints_passes(self) -> None:
        result = validator.validate_config(validator.DEFAULT_CONFIG, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entrypoint_count"], 4)
        self.assertEqual(result["proof_class_contract"]["proof_class_default"], "local-simulation")
        self.assertEqual(result["source_pin_contract"]["canonical_commit"], "f9d0421315c564fb890a1b14eee77b290e0d7bbe")
        self.assertIn(
            "93d175549da579b8abac07bd175ce4c3f9dde829",
            result["source_pin_contract"]["allowed_historical_evidence_commits"],
        )
        self.assertEqual(result["test_contract"]["repair_round_cap"], 5)
        self.assertIn("planner", result["test_contract"]["required_agent_roles"])
        self.assertFalse(result["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(result["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(
            [entry["id"] for entry in result["entrypoints"]],
            [
                "competition_environment_smoke",
                "before_after_judge_demo",
                "multi_worker_evaluate_profile",
                "opencode_multi_worker_evaluate_profile",
            ],
        )
        for entry in result["entrypoints"]:
            self.assertEqual(entry["status"], "passed")
            if entry["id"] == "competition_environment_smoke":
                self.assertEqual(entry["smoke_contract"]["status"], "passed")
                self.assertEqual(entry["review_checklist"]["status"], "skipped")
                continue
            self.assertEqual(entry["profile"]["status"], "present")
            self.assertEqual(entry["profile_contract"]["status"], "passed")
            self.assertEqual(entry["tracked_manifest"]["status"], "present")
        smoke = result["entrypoints"][0]
        self.assertEqual(smoke["priority"], 0)
        smoke_focus = " ".join(smoke["judge_focus"]).lower()
        self.assertIn("competition environment", smoke_focus)
        self.assertIn("smoke", smoke_focus)
        smoke_summary = smoke["expected_artifacts"]["competition_smoke_summary"]
        self.assertIn(smoke_summary["status"], {"missing", "present"})
        self.assertEqual(
            smoke_summary["path"],
            "target/competition-smoke-flashdb-judge-entrypoint/summary/competition-smoke-summary.json",
        )
        self.assertEqual(smoke["smoke_contract"]["reproduction_out_root"], "target/competition-smoke-flashdb-judge-entrypoint")
        before_after = result["entrypoints"][1]
        self.assertEqual(before_after["review_checklist"]["status"], "present")
        self.assertEqual(
            before_after["review_checklist"]["path"],
            "config/competition-env/review-checklists/flashdb-harness-internal-review.json",
        )
        self.assertFalse(before_after["review_checklist_contract"]["semantic_gate"])
        self.assertFalse(before_after["review_checklist_contract"]["review_is_semantic_acceptance"])
        opencode_entry = result["entrypoints"][3]
        self.assertEqual(
            opencode_entry["profile_contract"]["opencode_launch_policy"],
            {
                "opencode_command": "opencode",
                "opencode_model": None,
                "opencode_agent": None,
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            },
        )

    def test_default_flashdb_judge_entrypoints_validates_competition_env_bundle(self) -> None:
        result = validator.validate_config(validator.DEFAULT_CONFIG, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        bundle = result["competition_env_bundle_contract"]
        self.assertEqual(bundle["status"], "passed")
        self.assertEqual(bundle["report_kind"], "competition-env-bundle")
        self.assertEqual(bundle["bundle_root"], "config/competition-env")
        self.assertFalse(bundle["semantic_gate"])
        self.assertGreater(bundle["file_count"], 10)
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
        self.assertTrue(required_paths.issubset(set(bundle["files"])))
        self.assertEqual(
            bundle["canonical_environment_profile"],
            {
                "path": "config/competition-env/environment.json",
                "profile_id": "huawei-competition-ubuntu-24.04",
                "sha256": validator.sha256_file(REPO_ROOT / "config/competition-env/environment.json"),
            },
        )

    def test_context_pack_entrypoints_must_be_repo_relative_when_declared(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="context-pack-entrypoints-", dir=target_dir))
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        primary_report = temp_dir / "out" / "harness" / "evaluate-report.json"
        ledger = temp_dir / "out" / "state" / "opencode-agent-harness.sqlite3"
        payload = {
            "report_kind": "context-pack",
            "entrypoints": {
                "primary_report": repo_relative(primary_report),
                "evaluate_report": repo_relative(primary_report),
                "run_plan_report": "C:\\temp\\stale-run-plan.json",
                "worker_plan": None,
            },
            "context_management_contract": {
                "contract_kind": "context-management",
                "schema_version": 1,
                "chat_output_is_evidence": False,
                "semantic_gate": False,
                "evidence_policy": "on-disk-artifacts-only",
                "context_pack": repo_relative(context_pack),
                "agent_index": repo_relative(agent_index),
                "primary_report": repo_relative(primary_report),
                "report_entrypoint": "evaluate_report",
                "resume_protocol": {
                    "checkpoint_backend": "sqlite",
                    "ledger_path": repo_relative(ledger),
                    "worker_state_source": "agent-index.agents_by_worker_id",
                },
                "pipeline": [
                    {"stage": "plan"},
                    {"stage": "translate", "fanout": True},
                    {"stage": "verify"},
                    {"stage": "repair", "max_rounds": 5},
                ],
            },
        }

        with self.assertRaisesRegex(ValueError, "context_pack.entrypoints.run_plan_report"):
            validator.validate_context_management_contract(
                payload,
                path_text=repo_relative(context_pack),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                },
                repo_root=REPO_ROOT,
            )

    def test_expected_artifacts_rejects_drive_prefix_with_artifact_name(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.command_log: path must not use a drive prefix",
        ):
            validator.validate_expected_artifacts(
                {"command_log": "F:/agent/local/commands.jsonl"},
                require_local_artifacts=False,
                repo_root=REPO_ROOT,
            )

    def test_expected_artifacts_rejects_parent_traversal_with_artifact_name(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.competition_smoke_summary: path must not contain parent traversal",
        ):
            validator.validate_expected_artifacts(
                {"competition_smoke_summary": "target/../summary/competition-smoke-summary.json"},
                require_local_artifacts=False,
                repo_root=REPO_ROOT,
            )

    def test_expected_artifacts_rejects_empty_path_with_artifact_name(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.command_log: path must be a non-empty string",
        ):
            validator.validate_expected_artifacts(
                {"command_log": ""},
                require_local_artifacts=False,
                repo_root=REPO_ROOT,
            )

    def test_competition_env_bundle_rejects_hash_drift(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            if entry["path"] == "config/competition-env/pip/pip.conf":
                entry["sha256"] = "0" * 64
                break
        else:
            raise AssertionError("missing pip config in competition env bundle manifest")
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)

        with self.assertRaisesRegex(ValueError, "competition env bundle file sha256 mismatch"):
            validator.validate_competition_env_bundle_contract(
                load_default_config(),
                manifest_path=temp_manifest,
                repo_root=REPO_ROOT,
            )

    def test_environment_profile_hash_mismatch_preserves_claim_boundary_for_test_contract(self) -> None:
        config = load_default_config()
        config["environment_profile"]["sha256"] = "0" * 64
        temp_config = write_temp_config(config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        joined_errors = "\n".join(result["errors"])
        self.assertIn("artifact ref sha256 mismatch for config/competition-env/environment.json", joined_errors)
        self.assertNotIn("test_contract.semantic_claim_source must match claim_boundary", joined_errors)

    def test_opencode_profile_requires_explicit_launch_policy_fields(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "opencode_multi_worker_evaluate_profile")
        source_profile = json.loads((REPO_ROOT / entry["profile"]["path"]).read_text(encoding="utf-8"))
        source_profile.pop("opencode_skip_permissions", None)
        temp_config = write_temp_config(config)
        profile_path = temp_config.parent / "opencode-profile-missing-policy.json"
        write_json(profile_path, source_profile)
        profile_rel = repo_relative(profile_path)
        entry["profile"]["path"] = profile_rel
        entry["profile"]["sha256"] = validator.sha256_file(profile_path)
        entry["command"] = entry["command"].replace(
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            profile_rel,
        )
        temp_config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        opencode_entry = entrypoint_by_id(result, "opencode_multi_worker_evaluate_profile")
        self.assertEqual(opencode_entry["status"], "failed")
        self.assertIn(
            "opencode_multi_worker_evaluate_profile opencode profile opencode_skip_permissions must be a boolean",
            result["errors"],
        )

    def test_cli_writes_judge_entrypoints_readiness_report(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-readiness-", dir=target_dir))
        report_path = temp_dir / "summary" / "judge-entrypoints-readiness.json"

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "validation.tools.validate_judge_entrypoints",
                "--config",
                validator.DEFAULT_CONFIG.relative_to(REPO_ROOT).as_posix(),
                "--out",
                repo_relative(report_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(report_path.is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["report_kind"], "judge-entrypoints-readiness")
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["semantic_gate"])
        self.assertEqual(report["claim_boundary"]["semantic_claim_source"], "accepted_evidence_binding")
        self.assertEqual(report["entrypoint_count"], 4)
        self.assertIn("4 judge entrypoints ready", report["summary"]["headline"])
        self.assertEqual(report["summary"]["readiness"]["configured_count"], 4)
        self.assertEqual(report["summary"]["readiness"]["validation_status"], "passed")
        self.assertFalse(report["summary"]["claim_boundary"]["semantic_gate"])
        self.assertEqual(
            [entry["id"] for entry in report["summary"]["entrypoints"]],
            [
                "competition_environment_smoke",
                "before_after_judge_demo",
                "multi_worker_evaluate_profile",
                "opencode_multi_worker_evaluate_profile",
            ],
        )
        smoke_focus = " ".join(report["summary"]["entrypoints"][0]["judge_focus"]).lower()
        self.assertIn("competition environment", smoke_focus)
        self.assertIn("smoke", smoke_focus)

    def test_competition_smoke_summary_contract_rejects_semantic_gate_claim(self) -> None:
        payload = {
            "schema_version": 1,
            "report_kind": "competition-smoke-summary",
            "proof_class": "local-simulation",
            "profile_id": "huawei-competition-ubuntu-24.04",
            "claim_boundary": {
                "semantic_gate": True,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "smoke_entrypoint": {
                "semantic_acceptance_boundary": "does_not_translate_new_slices",
            },
            "vendored_clang_verification": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/summary/vendored-clang-verification.json",
            },
            "reports": {
                "evidence_governance": {
                    "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/evidence-governance.json",
                },
                "translator_coverage_matrix": {
                    "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/translator-coverage-matrix.json",
                },
            },
            "milestone_release_report": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/milestone-release-report.json",
                "semantic_acceptance_claim": False,
            },
            "command_log": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
            "final_gate": {"status": "passed"},
            "steps": [],
        }

        with self.assertRaisesRegex(ValueError, "competition_smoke_summary claim_boundary.semantic_gate must be false"):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_profile_sha256_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["profile_sha256"] = "b" * 64

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary profile_sha256 must match environment_profile.sha256",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_profile_id_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["profile_id"] = "drifted-profile"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary profile_id must match environment_profile.profile_id",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_profile_match_profile_id_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["competition_profile_match"]["profile_id"] = "drifted-profile"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary competition_profile_match.profile_id must match environment_profile.profile_id",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_vendored_clang_verification_rejects_local_absolute_clang_path(self) -> None:
        payload = valid_vendored_clang_verification_payload()
        payload["clang"]["path"] = "F:/agent/local/clang.exe"

        with self.assertRaisesRegex(
            ValueError,
            "vendored_clang_verification clang.path must be repo-relative POSIX",
        ):
            validator.validate_vendored_clang_verification_contract(
                payload,
                smoke_summary=valid_competition_smoke_summary_payload(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_profile_match_sha256_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["competition_profile_match"]["profile_sha256_actual"] = "b" * 64

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary competition_profile_match.profile_sha256_actual must match environment_profile.sha256",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_proof_class_must_match_entrypoint(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class must match entrypoint proof_class",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="local-simulation",
            )

    def test_competition_smoke_summary_run_id_must_match_entrypoint(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["run_id"] = "unexpected-run"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary run_id must match entrypoint run_id",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_run_id="competition-flashdb-environment-smoke-20260701",
            )

    def test_competition_smoke_summary_artifact_path_rejects_local_absolute_path(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        artifacts = competition_smoke_expected_artifacts()
        local_absolute = "F:/agent/local/commands.jsonl"
        payload["command_log"]["path"] = local_absolute
        artifacts["command_log"] = local_absolute

        with self.assertRaisesRegex(
            ValueError,
            "path must not use a drive prefix",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=artifacts,
            )

    def test_competition_smoke_summary_artifact_path_rejects_parent_traversal(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        artifacts = competition_smoke_expected_artifacts()
        traversal = "target/competition-smoke-flashdb-judge-entrypoint/reports/../summary/vendored.json"
        payload["vendored_clang_verification"]["path"] = traversal
        artifacts["vendored_clang_verification"] = traversal

        with self.assertRaisesRegex(
            ValueError,
            "path must not contain parent traversal",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=artifacts,
            )

    def test_competition_smoke_summary_artifact_roots_reject_local_absolute_path(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["artifact_roots"] = ["target/competition-smoke/summary", "F:/agent/local/reports"]

        with self.assertRaisesRegex(
            ValueError,
            "path must not use a drive prefix",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_requires_timeout_policy(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload.pop("timeout_policy")

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary timeout_policy must be an object",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_timeout_must_fail_closed(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["timeout_policy"]["timeout_is_final_gate_failure"] = False

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary timeout_policy.timeout_is_final_gate_failure must be true",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_requires_required_gate_steps(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["steps"] = [
            step for step in payload["steps"] if step["step"] != "translator-coverage-matrix"
        ]

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary steps missing required gates",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_exact_smoke_summary_rejects_local_wsl_or_ci_mislabel(self) -> None:
        cases = [
            ("windows-local", {"kind": "windows-local", "system": "Windows"}),
            ("wsl", {"kind": "wsl", "detected_wsl": True}),
            ("ci", {"kind": "linux-ci", "detected_ci": True}),
        ]

        for name, env_patch in cases:
            with self.subTest(name=name):
                payload = valid_competition_smoke_summary_payload()
                payload["proof_class"] = "competition-exact"
                payload["execution_environment"].update(env_patch)

                with self.assertRaisesRegex(
                    ValueError,
                    "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
                ):
                    validator.validate_competition_smoke_summary_contract(
                        payload,
                        expected_artifacts=competition_smoke_expected_artifacts(),
                        entrypoint_proof_class="competition-exact",
                    )

    def test_competition_exact_smoke_summary_requires_full_profile_match(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"
        payload["competition_profile_match"]["kernel_match"] = False

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="competition-exact",
            )

    def test_competition_exact_smoke_summary_requires_host_attestation(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"
        payload["execution_environment"]["competition_exact_host_attested"] = False
        for step in payload["steps"]:
            step["status"] = "passed"
            step["returncode"] = 0
            step.pop("proof_class_effect", None)

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="competition-exact",
            )

    def test_ci_approximation_smoke_summary_rejects_non_ci_environment(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "ci-approximation"
        payload["execution_environment"].update(
            {
                "detected_ci": False,
                "detected_wsl": True,
                "kind": "wsl",
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=ci-approximation requires execution_environment.detected_ci=true",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="ci-approximation",
            )

    def test_wsl_local_simulation_smoke_summary_rejects_non_wsl_environment(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "wsl-local-simulation"
        payload["execution_environment"].update(
            {
                "detected_ci": True,
                "detected_wsl": False,
                "kind": "linux-ci",
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=wsl-local-simulation requires execution_environment.detected_wsl=true",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="wsl-local-simulation",
            )

    def test_judge_evidence_index_requires_valid_opencode_runtime_when_present(self) -> None:
        launch_policy = opencode_launch_policy()
        preflight = {
            "path": "target/out/harness/opencode-preflight-report.json",
            "sha256": "a" * 64,
            "status": "passed",
            "contract_status": "executed",
            "launch_policy": launch_policy,
            "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        }
        payload = {
            "schema_version": 1,
            "report_kind": "judge-evidence-index",
            "status": "completed",
            "claim_boundary": {
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "index_is_semantic_gate": False,
            },
            "judge_headline": {
                "report_kind": "judge-headline",
                "semantic_gate": False,
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "opencode_runtime": {
                    "enabled": False,
                    "worker_count": 0,
                    "all_contracts_executed": False,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                },
            },
            "harness_architecture": {
                "architecture_contracts": {
                    "context_management": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                    "agent_coordination": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                        "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                    },
                },
            },
            "opencode_agent_runtime": {
                "runtime": "opencode",
                "chat_output_is_evidence": False,
                "semantic_gate": False,
                "worker_count": 1,
                "contract_status_counts": {"not-executed": 1},
                "all_contracts_executed": False,
                "failed_or_missing_contract_workers": ["worker-a"],
                "opencode_preflight_report": json.loads(json.dumps(preflight)),
                "workers": [
                    {
                        "worker_id": "worker-a",
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                        "summary": {"path": "target/out/workers/worker-a/summary/competition-run-summary.json", "sha256": "b" * 64},
                        "worker_report": {"path": "target/out/workers/worker-a/harness/run-worker-report.json", "sha256": "c" * 64},
                        "logs": {
                            "stdout": {"path": "target/out/workers/worker-a/logs/stdout.log", "sha256": "d" * 64},
                            "stderr": {"path": "target/out/workers/worker-a/logs/stderr.log", "sha256": "e" * 64},
                        },
                        "handoff_contract": {"path": "target/out/workers/worker-a/harness/opencode-handoff-contract.json", "sha256": "f" * 64},
                        "opencode_session_evidence": {"path": "target/out/workers/worker-a/logs/opencode-session-evidence.json", "sha256": "1" * 64},
                        "opencode_preflight_report": json.loads(json.dumps(preflight)),
                        "contract_verification_status": "not-executed",
                        "opencode_contract_verification": {"status": "not-executed"},
                    },
                ],
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_agent_runtime.all_contracts_executed must be true"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_requires_opencode_runtime_for_opencode_mode(self) -> None:
        payload = {
            "schema_version": 1,
            "report_kind": "judge-evidence-index",
            "status": "completed",
            "mode": "opencode",
            "claim_boundary": {
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "index_is_semantic_gate": False,
            },
            "judge_headline": {
                "report_kind": "judge-headline",
                "semantic_gate": False,
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "opencode_runtime": {
                    "enabled": False,
                    "worker_count": 0,
                    "all_contracts_executed": False,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                },
            },
            "harness_architecture": {
                "architecture_contracts": {
                    "context_management": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                    "agent_coordination": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                        "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                    },
                },
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_agent_runtime is required when judge_evidence_index.mode is opencode"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_deterministic_judge_evidence_index_claim_boundary_fails_closed(self) -> None:
        mutations = [
            ("semantic_claim_source", "competition-run-summary.final_gate", "semantic_claim_source must be accepted_evidence_binding"),
            ("generated_draft_semantic_pass", True, "generated_draft_semantic_pass must be false"),
            ("translation_coverage_numerator", 1, "translation_coverage_numerator must be 0"),
            ("index_is_semantic_gate", True, "index_is_semantic_gate must be false"),
        ]

        for field, value, expected_error in mutations:
            with self.subTest(field=field):
                payload = valid_deterministic_judge_index_payload()
                payload["claim_boundary"][field] = value

                with self.assertRaisesRegex(ValueError, expected_error):
                    validator.validate_judge_evidence_index_contract(
                        payload,
                        path_text="target/out/harness/judge-evidence-index.json",
                    )

    def test_judge_evidence_index_requires_judge_headline(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        payload.pop("judge_headline", None)

        with self.assertRaisesRegex(ValueError, "judge_evidence_index.judge_headline must be an object"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_headline_must_match_boundary_and_architecture(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        payload["judge_headline"]["worker_count"] = 2

        with self.assertRaisesRegex(ValueError, "judge_headline.worker_count must match harness_architecture.worker_count"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_general_artifact_ref_hash_drift_fails(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-ref-drift-", dir=target_dir))
        workflow_metrics = temp_dir / "summary" / "workflow-metrics.json"
        workflow_metrics.parent.mkdir(parents=True)
        workflow_metrics.write_text("{}\n", encoding="utf-8")
        payload = valid_deterministic_judge_index_payload()
        payload["evidence_artifact_refs"] = {
            "workflow_metrics": {
                "path": repo_relative(workflow_metrics),
                "sha256": "0" * 64,
            }
        }

        with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_failed_verified_unsafe_baseline_ref(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-index-verified-baseline-", dir=target_dir))
        root = temp_dir / "out"
        payload = valid_deterministic_judge_index_payload()
        for ref_name, artifact_path in {
            "competition_run_summary": root / "summary" / "competition-run-summary.json",
            "workflow_metrics": root / "summary" / "workflow-metrics.json",
            "worker_plan": root / "harness" / "plans" / "workers.json",
            "profile": root / "profile.json",
        }.items():
            set_artifact_ref(payload["evidence_artifact_refs"][ref_name], artifact_path)
        payload["evidence_artifact_refs"]["verified_unsafe_baseline"] = write_verified_unsafe_baseline_ref(
            root / "evidence" / "verified-baseline.json",
            status="failed",
        )

        with self.assertRaisesRegex(ValueError, "verified_unsafe_baseline.status must be passed"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(root / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_verified_unsafe_baseline_ref_requires_same_output_gate_refs(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-verified-baseline-deep-", dir=target_dir))
        verified_path = temp_dir / "verified-baseline.json"
        verified_ref = write_deep_verified_unsafe_baseline_ref(verified_path)
        payload = json.loads(verified_path.read_text(encoding="utf-8"))
        payload.pop("same_output_gate_refs", None)
        write_json(verified_path, payload)
        verified_ref["sha256"] = validator.sha256_file(verified_path)

        with self.assertRaisesRegex(ValueError, "same_output_gate_refs missing"):
            validator.validate_verified_unsafe_baseline_ref(
                verified_ref,
                "verified_unsafe_baseline",
                repo_root=REPO_ROOT,
            )

    def test_verified_unsafe_baseline_ref_rejects_same_output_gate_compile_artifact_drift(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-verified-baseline-gate-drift-", dir=target_dir))
        verified_path = temp_dir / "verified-baseline.json"
        verified_ref = write_deep_verified_unsafe_baseline_ref(verified_path)
        payload = json.loads(verified_path.read_text(encoding="utf-8"))
        payload["same_output_gate_refs"]["unsafe_ledger"]["compile_artifact"]["sha256"] = "9" * 64
        write_json(verified_path, payload)
        verified_ref["sha256"] = validator.sha256_file(verified_path)

        with self.assertRaisesRegex(ValueError, "same_output_gate_refs.unsafe_ledger.compile_artifact"):
            validator.validate_verified_unsafe_baseline_ref(
                verified_ref,
                "verified_unsafe_baseline",
                repo_root=REPO_ROOT,
            )

    def test_verified_unsafe_baseline_ref_rejects_accepted_rust_report_as_replay_gate(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-verified-baseline-rust-report-", dir=target_dir))
        verified_path = temp_dir / "verified-baseline.json"
        verified_ref = write_deep_verified_unsafe_baseline_ref(verified_path)
        payload = json.loads(verified_path.read_text(encoding="utf-8"))
        payload["same_output_gate_refs"]["rust_replay"]["path"] = "validation/evidence/demo/l3-demo-rust-report.json"
        payload["same_output_gate_refs"]["rust_replay"].pop("replay_kind", None)
        payload["same_output_gate_refs"]["rust_replay"].pop("correctness_role", None)
        write_json(verified_path, payload)
        verified_ref["sha256"] = validator.sha256_file(verified_path)

        with self.assertRaisesRegex(ValueError, "rust_replay.path must point to direct C2Rust replay evidence"):
            validator.validate_verified_unsafe_baseline_ref(
                verified_ref,
                "verified_unsafe_baseline",
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_route_governance_metrics_report_must_match_schema(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-route-metrics-schema-", dir=target_dir))
        route_metrics = temp_dir / "summary" / "route-governance-metrics-report.json"
        write_json(
            route_metrics,
            {
                "schema_version": 1,
                "status": "passed",
                "report_kind": "route-governance-metrics",
                "inputs": {
                    "translator_coverage_matrix": {
                        "path": "validation/translator-coverage-matrix.json",
                        "status": "passed",
                        "capability_count": 11,
                    },
                    "evidence_governance": {
                        "evidence_root": "validation/evidence",
                        "status": "passed",
                        "file_count": 1,
                    },
                },
                "metrics": {
                    "translation_coverage_numerator": 0,
                    "accepted_evidence_semantic_pass_count": 1,
                    "tracked_capability_delta_ledgers": 1,
                    "tracked_capability_delta_count": 1,
                    "tracked_route_decision_artifacts": 1,
                    "s2_workflow_metrics": {},
                    "candidate_generation_inventory": {},
                    "tracked_slice_gate_contexts": 1,
                    "slice_gate_contexts": [],
                    "c2rust_baseline": {
                        "report_kind": "c2rust-baseline-rollup",
                        "status": "none",
                        "manifest_count": 0,
                        "generated_output_count": 0,
                        "skipped_without_output_count": 0,
                        "compile_attempted_count": 0,
                        "compile_passed_count": 0,
                        "compile_semantic_pass_count": 0,
                        "status_counts": {},
                        "output_status_counts": {},
                        "compile_status_counts": {},
                        "manifests": [],
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                        "boundary": "C2Rust baseline status is candidate context only.",
                    },
                    "blocked_repairs": {
                        "status": "none",
                        "blocked_repair_count": 0,
                        "slice_count": 0,
                        "human_action_required_count": 0,
                        "status_counts": {"none": 1},
                        "human_intervention_points": [],
                        "blocked_callees": [],
                        "ir_feature_gap_kinds": {},
                        "forbidden_change_counts": {},
                        "blocked_reason_counts": {},
                        "source_span_kind_counts": {},
                        "smallest_next_tests": [],
                        "next_actions": [],
                        "semantic_gate": False,
                        "translation_coverage_numerator": 0,
                        "boundary": "Blocked repairs are not semantic acceptance evidence.",
                    },
                },
                "denominators": {
                    "capability_delta_ledger": "capability delta ledger artifacts",
                    "candidate_generation_inventory": "route decision artifacts",
                    "slice_gate_contexts": "slice gate contexts",
                    "translation_coverage_numerator": "translator-generated only",
                    "accepted_evidence_semantic_pass_count": "separate accepted evidence count",
                    "s2_workflow_metrics": "competition summaries",
                    "c2rust_baseline": "candidate-context C2Rust baseline manifests",
                    "blocked_repairs": "self-healing blocked repairs artifacts",
                },
                "claim_boundary": "Route governance metrics are not semantic acceptance evidence.",
                "retention_policy": {
                    "report_kind": "route-governance-metrics-retention-policy",
                    "report_role": "p0-route-governance-and-capability-metrics",
                    "target_artifacts": {
                        "retention_class": "reproducible-local-output",
                        "committed": False,
                        "policy": "regenerate from summary inputs",
                    },
                    "committed_anchors": {
                        "retention_class": "release-evidence",
                        "policy": "commit only durable anchors",
                    },
                    "claim_boundary": "Retention policy does not change semantic acceptance.",
                },
            },
        )
        payload = valid_deterministic_judge_index_payload()
        payload["evidence_artifact_refs"] = {
            "route_governance_metrics_report": {
                "path": repo_relative(route_metrics),
                "sha256": validator.sha256_file(route_metrics),
            }
        }

        with self.assertRaisesRegex(ValueError, "route_governance_metrics_report.*s2_workflow_metrics"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts={"route_governance_metrics_report": repo_relative(route_metrics)},
                repo_root=REPO_ROOT,
            )

        full_payload = json.loads(route_metrics.read_text(encoding="utf-8"))
        full_payload["metrics"]["s2_workflow_metrics"] = {
            "run_count": 1,
            "input_summaries": [],
            "units_total": 1,
            "units_converged": 1,
            "units_baseline_only": 0,
            "unsafe_reduction": {
                "status": "measured",
                "baseline_total_unsafe": 2,
                "current_total_unsafe": 0,
                "reduced_by": 2,
                "ratio": 0.0,
            },
            "translation_before_after": {
                "status": "not_provided",
                "input_run_count": 0,
                "unit_count": 0,
                "measured_unsafe_unit_count": 0,
                "accepted_patch_unit_count": 0,
            },
            "measured_unsafe_reduction_run_count": 1,
            "avg_repair_rounds": 1.0,
            "auto_recovery_rate": 1.0,
            "human_interventions": 0,
            "fail_closed_count": 0,
            "root_cause_counts": {},
            "wall_clock_seconds": 1,
            "llm_calls": 1,
            "repair_history_unit_count": 1,
            "auto_recovered_units": 1,
            "claim_boundary": "S2 workflow metrics are not semantic acceptance.",
        }
        write_json(route_metrics, full_payload)
        payload["evidence_artifact_refs"]["route_governance_metrics_report"]["sha256"] = validator.sha256_file(route_metrics)

        result = validator.validate_judge_evidence_index_contract(
            payload,
            path_text="target/out/harness/judge-evidence-index.json",
            expected_artifacts={"route_governance_metrics_report": repo_relative(route_metrics)},
            repo_root=REPO_ROOT,
        )
        self.assertEqual(
            result["evidence_artifact_refs"]["route_governance_metrics_report"]["status"],
            "passed",
        )

    def test_judge_evidence_index_requires_opencode_graph_contract(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["graph_runtime"] = "plain-runtime"

        with self.assertRaisesRegex(ValueError, "judge_evidence_index.harness_architecture.graph_runtime must be opencode-harness-langgraph-inspired"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_requires_all_graph_nodes(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["graph_nodes"].remove("repair_retry")

        with self.assertRaisesRegex(ValueError, "graph_nodes missing required nodes: \\['repair_retry'\\]"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_requires_retry_checkpoint_and_round_cap(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["retry_policy"]["checkpoint"] = "sqlite"

        with self.assertRaisesRegex(ValueError, "retry_policy.checkpoint must be repair_hints"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["retry_policy"]["round_cap"] = 4

        with self.assertRaisesRegex(ValueError, "retry_policy.round_cap must be 5"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_refs_must_cover_expected_artifacts(self) -> None:
        payload = valid_opencode_judge_index_payload()
        del payload["evidence_artifact_refs"]["worker_plan"]
        expected_artifacts = {
            "competition_summary": "target/out/summary/competition-run-summary.json",
            "workflow_metrics": "target/out/summary/workflow-metrics.json",
            "worker_plan": "target/out/harness/plans/workers.json",
        }

        with self.assertRaisesRegex(ValueError, "judge_evidence_index.evidence_artifact_refs missing expected artifacts: \\['worker_plan'\\]"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts=expected_artifacts,
            )

    def test_judge_evidence_index_requires_architecture_context_and_agent_refs_when_expected(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        payload["evidence_artifact_refs"]["context_pack"] = artifact_ref("target/out/harness/context-pack.json", "6")
        payload["evidence_artifact_refs"]["agent_index"] = artifact_ref("target/out/harness/agent-index.json", "7")
        expected_artifacts = {
            "competition_summary": "target/out/summary/competition-run-summary.json",
            "workflow_metrics": "target/out/summary/workflow-metrics.json",
            "worker_plan": "target/out/harness/plans/workers.json",
            "context_pack": "target/out/harness/context-pack.json",
            "agent_index": "target/out/harness/agent-index.json",
        }

        with self.assertRaisesRegex(
            ValueError,
            "judge_evidence_index.harness_architecture.context_pack is required when expected_artifacts.context_pack is declared",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts=expected_artifacts,
            )

    def test_judge_evidence_index_requires_architecture_agent_ref_when_context_ref_is_present(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        context_ref = artifact_ref("target/out/harness/context-pack.json", "6")
        payload["evidence_artifact_refs"]["context_pack"] = context_ref
        payload["evidence_artifact_refs"]["agent_index"] = artifact_ref("target/out/harness/agent-index.json", "7")
        payload["harness_architecture"]["context_pack"] = context_ref
        expected_artifacts = {
            "competition_summary": "target/out/summary/competition-run-summary.json",
            "workflow_metrics": "target/out/summary/workflow-metrics.json",
            "worker_plan": "target/out/harness/plans/workers.json",
            "context_pack": "target/out/harness/context-pack.json",
            "agent_index": "target/out/harness/agent-index.json",
        }

        with self.assertRaisesRegex(
            ValueError,
            "judge_evidence_index.harness_architecture.agent_index is required when expected_artifacts.agent_index is declared",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts=expected_artifacts,
            )

    def test_judge_evidence_index_expected_artifacts_reject_drive_prefix(self) -> None:
        payload = valid_opencode_judge_index_payload()

        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.competition_summary: path must not use a drive prefix",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts={"competition_summary": "F:/agent/local/competition-run-summary.json"},
            )

    def test_judge_evidence_index_requires_opencode_preflight_ref(self) -> None:
        payload = valid_opencode_judge_index_payload()
        del payload["evidence_artifact_refs"]["opencode_preflight_report"]

        with self.assertRaisesRegex(ValueError, "missing required OpenCode ref: opencode_preflight_report"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_preflight_ref_must_match_runtime(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["evidence_artifact_refs"]["opencode_preflight_report"]["sha256"] = "7" * 64

        with self.assertRaisesRegex(ValueError, "evidence_artifact_refs.opencode_preflight_report must match path and sha256"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_preflight_run_id_must_match_runtime(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"]["run_id"] = "stale-run"

        with self.assertRaisesRegex(
            ValueError,
            "opencode_agent_runtime.workers\\[0\\].opencode_preflight_report.run_id must match opencode_agent_runtime.opencode_preflight_report",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_requires_opencode_launch_policy_binding(self) -> None:
        payload = valid_opencode_judge_index_payload()
        del payload["opencode_agent_runtime"]["opencode_preflight_report"]["launch_policy"]

        with self.assertRaisesRegex(ValueError, "opencode_agent_runtime.opencode_preflight_report.launch_policy must be an object"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_rejects_opencode_launch_policy_drift_from_profile_ref(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-profile-drift-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        profile_policy = opencode_launch_policy()
        profile_policy["opencode_skip_permissions"] = True
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile-drift",
                "mode": "opencode",
                **profile_policy,
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "opencode_agent_runtime.opencode_preflight_report.launch_policy must match profile launch policy",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_requires_matching_worker_opencode_launch_policy(self) -> None:
        payload = valid_opencode_judge_index_payload()
        worker_preflight = payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"]
        worker_preflight["launch_policy"]["opencode_skip_permissions"] = True
        worker_preflight["launch_policy_sha256"] = opencode_launch_policy_sha256(worker_preflight["launch_policy"])

        with self.assertRaisesRegex(
            ValueError,
            "opencode_agent_runtime.workers\\[0\\].opencode_preflight_report.launch_policy must match opencode_agent_runtime.opencode_preflight_report",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_refs_must_be_repo_relative(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["evidence_artifact_refs"]["workflow_metrics"]["path"] = "C:/tmp/workflow-metrics.json"

        with self.assertRaisesRegex(ValueError, "path must not use a drive prefix"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_refs_reject_self_reference(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["evidence_artifact_refs"]["judge_evidence_index"] = artifact_ref(
            "target/out/harness/judge-evidence-index.json",
            "6",
        )

        with self.assertRaisesRegex(ValueError, "must not include judge_evidence_index"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_require_local_artifacts_checks_expected_artifact_presence(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        temp_config = write_temp_config(config)
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_config.parent / "out")
        artifact = out_root / "harness" / "validator.txt"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("validator\n", encoding="utf-8")
        config["entrypoints"][0]["expected_artifacts"] = {
            "validator": repo_relative(artifact)
        }
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        config["test_contract"]["required_expected_artifacts"] = ["validator"]
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        artifacts = result["entrypoints"][0]["expected_artifacts"]
        self.assertEqual(artifacts["validator"]["status"], "present")
        self.assertIn("sha256", artifacts["validator"])

    def test_require_local_artifacts_rejects_competition_summary_entrypoint_drift(self) -> None:
        cases = [
            (
                "profile_sha256",
                {"profile_sha256": "b" * 64},
                "competition_summary profile_sha256 must match environment_profile.sha256",
            ),
            (
                "profile_id",
                {"profile_id": "drifted-profile"},
                "competition_summary profile_id must match environment_profile.profile_id",
            ),
            (
                "proof_class",
                {"proof_class": "competition-exact"},
                "competition_summary proof_class must match entrypoint proof_class",
            ),
            (
                "run_id",
                {"run_id": "stale-run"},
                "competition_summary run_id must match entrypoint run_id",
            ),
        ]
        for field, drift, expected_error in cases:
            with self.subTest(field=field):
                config = load_default_config()
                config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
                config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
                config["test_contract"]["required_expected_artifacts"] = ["competition_summary"]
                temp_config = write_temp_config(config)
                out_root = bind_entrypoint_to_out_root(
                    config,
                    temp_config,
                    entry_index=0,
                    out_root=temp_config.parent / f"out-{field}",
                )
                summary = out_root / "summary" / "competition-run-summary.json"
                payload = valid_competition_run_summary_payload(
                    run_id="competition-flashdb-before-after-exhibit",
                )
                payload.update(drift)
                write_competition_run_summary_with_workflow_metrics(summary, payload)
                config["entrypoints"][0]["expected_artifacts"] = {
                    "competition_summary": repo_relative(summary),
                }
                write_json(temp_config, config)

                result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(any(expected_error in error for error in result["errors"]), result["errors"])

    def test_require_local_artifacts_deep_validates_competition_summary_workflow_metrics(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        config["test_contract"]["required_expected_artifacts"] = ["competition_summary", "workflow_metrics"]
        temp_config = write_temp_config(config)
        out_root = bind_entrypoint_to_out_root(
            config,
            temp_config,
            entry_index=0,
            out_root=temp_config.parent / "out-deep-summary",
        )
        summary_path = out_root / "summary" / "competition-run-summary.json"
        summary_payload = valid_competition_run_summary_payload(
            run_id="competition-flashdb-before-after-exhibit",
        )
        metrics_path = write_competition_run_summary_with_workflow_metrics(summary_path, summary_payload)
        metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        metrics_payload["units_total"] = 2
        write_json(metrics_path, metrics_payload)
        summary_payload["workflow_metrics"]["sha256"] = validator.sha256_file(metrics_path)
        write_json(summary_path, summary_payload)
        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(summary_path),
            "workflow_metrics": repo_relative(metrics_path),
        }
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("workflow metrics artifact units_total does not match competition summary" in error for error in result["errors"]),
            result["errors"],
        )

    def test_require_local_artifacts_validates_vendored_clang_missing_summary_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-vendored-clang-contract-test"
            payload["competition_profile_match"]["clang_lane_verified"] = False
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(
                vendored_path,
                {
                    "schema_version": 1,
                    "artifact_kind": "vendored-clang-verification",
                    "proof_class": "local-simulation",
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "profile_sha256": "a" * 64,
                    "status": "missing",
                    "clang": {"source": "missing", "path": None, "version": None},
                    "clang_required": False,
                    "clang_lane_verified": False,
                    "checks": {},
                    "command_logs": [],
                    "final_gate": {"status": "passed"},
                },
            )
            payload["command_log"]["sha256"] = write_valid_command_log(command_log)
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "vendored_clang_verification missing status requires reason=missing_clang_path",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-vendored-clang-contract-test",
                    },
                )

    def test_require_local_artifacts_rejects_vendored_clang_summary_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-vendored-clang-drift-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(
                vendored_path,
                {
                    "schema_version": 1,
                    "artifact_kind": "vendored-clang-verification",
                    "proof_class": "local-simulation",
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "profile_sha256": "a" * 64,
                    "status": "missing",
                    "reason": "missing_clang_path",
                    "clang": {"source": "missing", "path": None, "version": None},
                    "clang_required": False,
                    "clang_lane_verified": False,
                    "checks": {},
                    "command_logs": [],
                    "final_gate": {"status": "passed"},
                },
            )
            payload["command_log"]["sha256"] = write_valid_command_log(command_log)
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "vendored_clang_verification clang_lane_verified must match competition_smoke_summary",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-vendored-clang-drift-test",
                    },
                )

    def test_require_local_artifacts_rejects_missing_command_log(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-missing-command-log-contract-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_json(evidence_governance, {})
            write_json(coverage_matrix, {})
            write_json(milestone, {})

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log path must exist",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-missing-command-log-contract-test",
                    },
                )

    def test_competition_smoke_summary_command_log_requires_sha256(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["command_log"].pop("sha256", None)

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary.command_log.sha256",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
                entrypoint_proof_class="local-simulation",
                entrypoint_run_id=None,
            )

    def test_competition_smoke_summary_step_log_path_must_match_command_log(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["steps"][0]["log_path"] = "target/other-smoke/logs/commands.jsonl"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary step environment-check.log_path must match command_log.path",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
                entrypoint_proof_class="local-simulation",
                entrypoint_run_id=None,
            )

    def test_require_local_artifacts_rejects_command_log_sha256_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-command-log-sha-drift-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            payload["command_log"]["sha256"] = "0" * 64
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_json(evidence_governance, {})
            write_json(coverage_matrix, {})
            write_json(milestone, {})
            write_valid_command_log(command_log)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_summary.command_log.sha256 must match command_log artifact",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-command-log-sha-drift-test",
                    },
                )

    def test_require_local_artifacts_rejects_command_log_missing_summary_step(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-command-log-step-coverage-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_json(evidence_governance, {})
            write_json(coverage_matrix, {})
            write_json(milestone, {})
            command_log.parent.mkdir(parents=True, exist_ok=True)
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["python3", "-B", "validation/tools/run_competition_smoke.py"],
                        "returncode": 0,
                        "stdout": "",
                        "stderr": "",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            payload["command_log"]["sha256"] = validator.sha256_file(command_log)
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log missing summary steps",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-command-log-step-coverage-test",
                    },
                )

    def test_require_local_artifacts_rejects_command_log_local_absolute_command(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-command-log-path-contract-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_json(evidence_governance, {})
            write_json(coverage_matrix, {})
            write_json(milestone, {})
            command_log.parent.mkdir(parents=True, exist_ok=True)
            command_log.write_text(
                json.dumps(
                    {
                        "step": "core-auto-evidence-validator",
                        "command": ["C:\\Python314\\python.exe", "validation/tools/validator.py"],
                        "returncode": 0,
                        "stdout": "",
                        "stderr": "",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            payload["command_log"]["sha256"] = validator.sha256_file(command_log)
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log command contains forbidden local absolute path",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-command-log-path-contract-test",
                    },
                )

    def test_require_local_artifacts_validates_context_and_agent_contracts(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_dir / "out")
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        competition_summary = out_root / "summary" / "competition-run-summary.json"
        workflow_metrics = out_root / "summary" / "workflow-metrics.json"
        verified_baseline = out_root / "evidence" / "verified-baseline.json"
        before_after = out_root / "evidence" / "translation-before-after.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"

        competition_summary.parent.mkdir(parents=True, exist_ok=True)
        write_competition_run_summary_with_workflow_metrics(
            competition_summary,
            valid_competition_run_summary_payload(run_id="competition-flashdb-before-after-exhibit"),
        )
        for artifact in [assignment, request, summary, report]:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("{}\n", encoding="utf-8")
        verified_ref = write_verified_unsafe_baseline_ref(verified_baseline)
        before_after_ref = write_repair_before_after_ref(before_after, verified_ref)

        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(competition_summary),
            "workflow_metrics": repo_relative(workflow_metrics),
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
            "resume_manifest": repo_relative(resume_manifest),
        }
        config["test_contract"]["required_expected_artifacts"] = [
            "competition_summary",
            "workflow_metrics",
            "context_pack",
            "agent_index",
        ]
        write_json(temp_config, config)
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "attempt_evidence_policy": {
                    "accepted_attempt": {
                        "min_attempt_number": 2,
                        "require_hint_id": True,
                    },
                    "baseline_attempt": {
                        "attempt_number": 1,
                        "expected_final_gate": "failed",
                        "root_cause_key": "unsafe_baseline_requires_repair",
                        "verified_unsafe_baseline": verified_ref,
                    },
                    "mode": "baseline_repair_gate",
                    "translation_before_after": before_after_ref,
                },
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan", "role": "planner", "evidence": "entrypoints.worker_plan"},
                        {"stage": "translate", "role": "worker", "fanout": True},
                        {"stage": "verify", "role": "verifier", "reduce": "merge"},
                        {"stage": "repair", "role": "repairer", "max_rounds": 5},
                    ],
                    "primary_report": repo_relative(competition_summary),
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "ledger_path": repo_relative(ledger),
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                },
                "entrypoints": {
                    "resume_manifest": repo_relative(resume_manifest),
                },
                "workers": [
                    {
                        "assignment_path": repo_relative(assignment),
                        "function": "demo_unit",
                        "report_path": repo_relative(report),
                        "request_path": repo_relative(request),
                        "slice_id": "demo-unit",
                        "source_commit": "abc123",
                        "source_sha256": "f" * 64,
                        "summary_path": repo_relative(summary),
                        "worker_id": "worker-001",
                        "attempts": [
                            {
                                "attempt": 1,
                                "exit_code": 1,
                                "hint_id": "repair:test:worker-001:unsafe_baseline_requires_repair",
                                "hint_status": "opened",
                                "root_cause_key": "unsafe_baseline_requires_repair",
                                "summary_status": "failed",
                            },
                            {
                                "attempt": 2,
                                "exit_code": 0,
                                "hint_id": "repair:test:worker-001:unsafe_baseline_requires_repair",
                                "hint_status": "revalidated_passed",
                                "retry_of": "repair:test:worker-001:unsafe_baseline_requires_repair",
                                "rollback_evidence": {
                                    "path": repo_relative(report),
                                    "sha256": validator.sha256_file(report),
                                },
                                "summary_status": "passed",
                            },
                        ],
                        "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
                    }
                ],
            },
        )
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 1,
                },
                "agents": [
                    {
                        "assignment_path": repo_relative(assignment),
                        "function": "demo_unit",
                        "report_path": repo_relative(report),
                        "request_path": repo_relative(request),
                        "slice_id": "demo-unit",
                        "source_commit": "abc123",
                        "source_sha256": "f" * 64,
                        "summary_path": repo_relative(summary),
                        "worker_id": "worker-001",
                    }
                ],
                "agents_by_worker_id": {
                    "worker-001": {
                        "assignment_path": repo_relative(assignment),
                        "function": "demo_unit",
                        "isolated_out_root": repo_relative(worker_root),
                        "report_path": repo_relative(report),
                        "request_path": repo_relative(request),
                        "slice_id": "demo-unit",
                        "source_commit": "abc123",
                        "source_sha256": "f" * 64,
                        "summary_path": repo_relative(summary),
                        "worker_id": "worker-001",
                    }
                },
                "reports": {
                    "resume_manifest": {
                        "path": repo_relative(resume_manifest),
                        "report_kind": "resume-manifest",
                        "status": "passed",
                    },
                },
            },
        )
        write_json(
            resume_manifest,
            {
                "schema_version": 1,
                "report_kind": "resume-manifest",
                "run_id": "competition-flashdb-before-after-exhibit",
                "status": "passed",
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "claim_boundary": {
                    "semantic_gate": False,
                    "chat_output_is_evidence": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
                "ledger": {
                    "path": repo_relative(ledger),
                    "checkpoint_backend": "sqlite",
                },
                "context_pack": {
                    "path": repo_relative(context_pack),
                    "sha256": validator.sha256_file(context_pack),
                },
                "agent_index": {
                    "path": repo_relative(agent_index),
                    "sha256": validator.sha256_file(agent_index),
                },
                "resume_entrypoints": [
                    "evaluate --profile",
                    "run-plan --plan",
                    "run-worker --assignment",
                ],
                "workers": [
                    {
                        "worker_id": "worker-001",
                        "assignment_path": repo_relative(assignment),
                        "request_path": repo_relative(request),
                        "summary_path": repo_relative(summary),
                        "report_path": repo_relative(report),
                        "isolated_out_root": repo_relative(worker_root),
                        "replay_commands": resume_replay_commands(
                            ledger=ledger,
                            run_id="competition-flashdb-before-after-exhibit",
                            worker_id="worker-001",
                            assignment=assignment,
                            request=request,
                            summary=summary,
                            report=report,
                            worker_root=worker_root,
                        ),
                    }
                ],
                "worker_count": 1,
                "boundary": "Resume manifest is an index only and not a semantic acceptance gate.",
            },
        )
        write_minimal_context_ledger(
            ledger,
            run_id="competition-flashdb-before-after-exhibit",
            context_pack_path=context_pack,
            context_pack_payload=json.loads(context_pack.read_text(encoding="utf-8")),
            agent_index_path=agent_index,
        )
        write_json(
            summary,
            {
                "final_gate": {
                    "status": "failed",
                    "validator": "baseline_repair_gate",
                },
                "slices": {
                    "attempted": 1,
                    "failed": 1,
                    "semantic_pass": 0,
                },
            },
        )
        with closing(sqlite3.connect(ledger)) as connection:
            connection.execute(
                "update artifacts set sha256=?, status=? where kind='competition-run-summary'",
                (validator.sha256_file(summary), "failed"),
            )
            connection.commit()

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed", result["errors"])
        contracts = result["entrypoints"][0]["harness_contracts"]
        self.assertEqual(contracts["context_pack"]["repair_round_cap"], 5)
        self.assertEqual(contracts["agent_index"]["worker_count"], 1)
        self.assertEqual(contracts["resume_manifest"]["status"], "passed")
        self.assertEqual(contracts["resume_manifest"]["worker_count"], 1)
        self.assertEqual(contracts["context_agent_consistency"]["worker_count"], 1)
        self.assertEqual(contracts["ledger_context_index"]["status"], "passed")
        self.assertEqual(contracts["repair_self_heal"]["checked_workers"], 1)

    def test_repair_self_heal_contract_requires_bound_baseline_verification(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        other_verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "other-verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(
            temp_dir / "translation-before-after.json",
            verified_ref,
            baseline_verification=other_verified_ref,
        )
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )

        with self.assertRaisesRegex(ValueError, "baseline_verification must match.*verified_unsafe_baseline"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_requires_measured_unsafe_reduction(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(
            temp_dir / "translation-before-after.json",
            verified_ref,
            unsafe_status="not_measured",
            reduced_by=None,
        )
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )

        with self.assertRaisesRegex(ValueError, "translation_before_after.unsafe_reduction.status must be measured"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_requires_positive_unsafe_reduction(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(
            temp_dir / "translation-before-after.json",
            verified_ref,
            reduced_by=0,
        )
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )

        with self.assertRaisesRegex(ValueError, "translation_before_after.unsafe_reduction.reduced_by must be > 0"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_requires_revalidated_retry_hint_status(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(temp_dir / "translation-before-after.json", verified_ref)
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )
        retry_attempt_from_repair_context(context_payload)["hint_status"] = "opened"

        with self.assertRaisesRegex(ValueError, "accepted retry hint_status must be revalidated_passed"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_rejects_rollback_evidence_sha_mismatch(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(temp_dir / "translation-before-after.json", verified_ref)
        rollback = temp_dir / "rollback.json"
        write_json(rollback, {"rollback": "before retry"})
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )
        retry_attempt_from_repair_context(context_payload)["rollback_evidence"] = {
            "path": repo_relative(rollback),
            "sha256": "0" * 64,
        }

        with self.assertRaisesRegex(ValueError, "rollback_evidence.sha256 does not match artifact"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_contract_accepts_per_round_patch_delta_and_rollback(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )

        result = validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["unit_count"], 1)
        self.assertEqual(result["round_count"], 1)
        self.assertEqual(result["repair_round_cap"], 5)
        self.assertFalse(result["semantic_gate"])
        self.assertEqual(result["translation_coverage_numerator"], 0)

    def test_opencode_safety_transform_attempt_contract_rejects_non_five_round_cap(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json",
            max_repair_rounds=6,
        )

        with self.assertRaisesRegex(ValueError, "attempt_contract.max_repair_rounds must be 5"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_contract_requires_before_after_refs(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        del payload["safety_transform_units"][0]["patch_evidence"]["baseline"]
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = validator.sha256_file(attempt_path)

        with self.assertRaisesRegex(ValueError, "patch_evidence.baseline"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_harness_artifact_contracts_deep_validates_opencode_safety_transform_attempt(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )

        result = validator.validate_harness_artifact_contracts(
            {"opencode_safety_transform_attempt": attempt_ref["path"]},
            require_local_artifacts=True,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(result["opencode_safety_transform_attempt"]["status"], "passed")
        self.assertEqual(result["opencode_safety_transform_attempt"]["round_count"], 1)

    def test_resume_manifest_claim_boundary_fails_closed(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-boundary-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"
        for path in [ledger, assignment, request, summary, report]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        write_json(context_pack, {"entrypoints": {"resume_manifest": repo_relative(resume_manifest)}})
        write_json(agent_index, {"reports": {"resume_manifest": {"path": repo_relative(resume_manifest)}}})

        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-boundary",
            "status": "passed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {
                "path": repo_relative(context_pack),
                "sha256": validator.sha256_file(context_pack),
            },
            "agent_index": {
                "path": repo_relative(agent_index),
                "sha256": validator.sha256_file(agent_index),
            },
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [
                {
                    "worker_id": "worker-001",
                    "assignment_path": repo_relative(assignment),
                    "request_path": repo_relative(request),
                    "summary_path": repo_relative(summary),
                    "report_path": repo_relative(report),
                    "isolated_out_root": repo_relative(worker_root),
                }
            ],
            "worker_count": 1,
        }
        expected_artifacts = {
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
            "resume_manifest": repo_relative(resume_manifest),
        }
        cases = [
            ("resume_manifest.semantic_gate", lambda draft: draft.__setitem__("semantic_gate", True)),
            (
                "resume_manifest.claim_boundary.translation_coverage_numerator",
                lambda draft: draft["claim_boundary"].__setitem__("translation_coverage_numerator", 1),
            ),
            (
                "resume_manifest.claim_boundary.chat_output_is_evidence",
                lambda draft: draft["claim_boundary"].__setitem__("chat_output_is_evidence", True),
            ),
        ]
        for expected_error, mutate in cases:
            with self.subTest(expected_error=expected_error):
                draft = json.loads(json.dumps(payload))
                mutate(draft)
                with self.assertRaisesRegex(ValueError, expected_error):
                    validator.validate_resume_manifest_contract(
                        draft,
                        path_text=repo_relative(resume_manifest),
                        expected_artifacts=expected_artifacts,
                        context_payload=json.loads(context_pack.read_text(encoding="utf-8")),
                        agent_payload=json.loads(agent_index.read_text(encoding="utf-8")),
                        repo_root=REPO_ROOT,
                    )

    def test_resume_manifest_workers_must_match_context_and_agent_index_workers(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-worker-drift-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"
        for path in [ledger, assignment, request, summary, report]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        worker_fields = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "slice_id": "demo-unit",
            "function": "demo_unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
        }
        context_payload = {
            "entrypoints": {"resume_manifest": repo_relative(resume_manifest)},
            "workers": [worker_fields],
        }
        agent_payload = {
            "reports": {"resume_manifest": {"path": repo_relative(resume_manifest)}},
            "agents": [worker_fields],
            "agents_by_worker_id": {
                "worker-001": {
                    **worker_fields,
                    "isolated_out_root": repo_relative(worker_root),
                },
            },
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-worker-drift",
            "status": "passed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [
                {
                    **worker_fields,
                    "worker_id": "stale-worker-999",
                    "isolated_out_root": repo_relative(worker_root),
                    "replay_commands": resume_replay_commands(
                        ledger=ledger,
                        run_id="resume-worker-drift",
                        worker_id="stale-worker-999",
                        assignment=assignment,
                        request=request,
                        summary=summary,
                        report=report,
                        worker_root=worker_root,
                    ),
                }
            ],
            "worker_count": 1,
        }

        with self.assertRaisesRegex(
            ValueError,
            "resume_manifest.workers worker ids must match context_pack.workers and agent_index",
        ):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_resume_manifest_rejects_failed_verified_unsafe_baseline_ref(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-verified-baseline-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{}\n", encoding="utf-8")
        verified_ref = write_verified_unsafe_baseline_ref(
            out_root / "evidence" / "verified-baseline.json",
            status="failed",
        )
        policy = {"baseline_attempt": {"verified_unsafe_baseline": verified_ref}}
        context_payload = {
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": policy,
        }
        agent_payload = {
            "reports": {
                "resume_manifest": {"path": repo_relative(resume_manifest)},
                "verified_unsafe_baseline": verified_ref,
            },
            "attempt_evidence_policy": policy,
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-verified-baseline",
            "status": "failed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": policy,
            "verified_unsafe_baseline": verified_ref,
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [],
            "worker_count": 0,
        }

        with self.assertRaisesRegex(ValueError, "resume_manifest.verified_unsafe_baseline.status must be passed"):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                    "verified_unsafe_baseline": verified_ref["path"],
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_resume_manifest_verified_unsafe_baseline_must_match_context_and_agent_policy(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-verified-baseline-drift-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{}\n", encoding="utf-8")
        verified_ref = write_verified_unsafe_baseline_ref(out_root / "evidence" / "verified-baseline.json")
        drifted_ref = dict(verified_ref)
        drifted_ref["sha256"] = "0" * 64
        context_payload = {
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": {"baseline_attempt": {"verified_unsafe_baseline": verified_ref}},
        }
        agent_payload = {
            "reports": {
                "resume_manifest": {"path": repo_relative(resume_manifest)},
                "verified_unsafe_baseline": drifted_ref,
            },
            "attempt_evidence_policy": {"baseline_attempt": {"verified_unsafe_baseline": drifted_ref}},
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-verified-baseline-drift",
            "status": "passed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": {"baseline_attempt": {"verified_unsafe_baseline": verified_ref}},
            "verified_unsafe_baseline": verified_ref,
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [],
            "worker_count": 0,
        }

        with self.assertRaisesRegex(
            ValueError,
            "verified_unsafe_baseline must match across resume_manifest, context_pack, and agent_index",
        ):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                    "verified_unsafe_baseline": verified_ref["path"],
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_resume_manifest_worker_replay_commands_are_required(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-replay-missing-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"
        for path in [ledger, assignment, request, summary, report]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        worker_fields = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "slice_id": "demo-unit",
            "function": "demo_unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
        }
        context_payload = {
            "entrypoints": {"resume_manifest": repo_relative(resume_manifest)},
            "workers": [worker_fields],
        }
        agent_payload = {
            "reports": {"resume_manifest": {"path": repo_relative(resume_manifest)}},
            "agents": [worker_fields],
            "agents_by_worker_id": {
                "worker-001": {
                    **worker_fields,
                    "isolated_out_root": repo_relative(worker_root),
                },
            },
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-replay-missing",
            "status": "passed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [
                {
                    **worker_fields,
                    "isolated_out_root": repo_relative(worker_root),
                }
            ],
            "worker_count": 1,
        }

        with self.assertRaisesRegex(
            ValueError,
            r"resume_manifest\.workers\[0\]\.replay_commands must be an object",
        ):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_worker_plan_units_must_match_context_and_agent_index_workers(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="worker-plan-drift-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        worker_plan = out_root / "harness" / "plans" / "workers.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"

        for artifact in [assignment, request, summary, report]:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("{}\n", encoding="utf-8")
        common_worker = {
            "assignment_path": repo_relative(assignment),
            "function": "demo_unit",
            "report_path": repo_relative(report),
            "request_path": repo_relative(request),
            "slice_id": "demo-unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
            "summary_path": repo_relative(summary),
            "worker_id": "worker-001",
        }
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan", "role": "planner", "evidence": "entrypoints.worker_plan"},
                        {"stage": "translate", "role": "worker", "fanout": True},
                        {"stage": "verify", "role": "verifier", "reduce": "merge"},
                        {"stage": "repair", "role": "repairer", "max_rounds": 5},
                    ],
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "ledger_path": repo_relative(ledger),
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                },
                "entrypoints": {"worker_plan": repo_relative(worker_plan)},
                "workers": [common_worker],
            },
        )
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 1,
                },
                "agents": [common_worker],
                "agents_by_worker_id": {
                    "worker-001": {
                        **common_worker,
                        "isolated_out_root": repo_relative(worker_root),
                    }
                },
                "planner": {
                    "plan_path": repo_relative(worker_plan),
                    "worker_count": 1,
                },
            },
        )
        write_json(
            worker_plan,
            {
                "schema_version": 1,
                "planning_mode": "explicit_workers",
                "status": "planned",
                "target_id": "flashdb",
                "run_id": "worker-plan-drift",
                "plan_path": repo_relative(worker_plan),
                "units": [
                    {
                        **common_worker,
                        "out_root": repo_relative(worker_root),
                        "worker_id": "worker-002",
                    }
                ],
            },
        )
        write_minimal_context_ledger(
            ledger,
            run_id="worker-plan-drift",
            context_pack_path=context_pack,
            context_pack_payload=json.loads(context_pack.read_text(encoding="utf-8")),
            agent_index_path=agent_index,
        )

        with self.assertRaisesRegex(ValueError, "worker_plan.units worker ids must match context_pack.workers"):
            validator.validate_harness_artifact_contracts(
                {
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "worker_plan": repo_relative(worker_plan),
                },
                require_local_artifacts=True,
                repo_root=REPO_ROOT,
            )

    def test_source_file_worker_plan_infers_planning_mode(self) -> None:
        worker_plan_path = "target/out/harness/plans/source-workers.json"
        common_worker = {
            "assignment_path": "target/out/harness/assignments/worker-001.json",
            "function": "demo_unit",
            "request_path": "target/out/harness/assignments/worker-001-request.json",
            "slice_id": "demo-unit",
            "source_commit": "abc123",
            "source_file": "src/demo.c",
            "source_repo_root": "sources/Demo",
            "source_sha256": "f" * 64,
            "worker_id": "worker-001",
        }
        result = validator.validate_worker_plan_contract(
            {
                "schema_version": 1,
                "status": "planned",
                "target_id": "demo",
                "run_id": "source-plan",
                "plan_path": worker_plan_path,
                "source_file": "src/demo.c",
                "units": [
                    {
                        **common_worker,
                        "out_root": "target/out/workers/worker-001",
                        "slice_spec": "validation/slice-specs/demo.json",
                    }
                ],
            },
            {
                "entrypoints": {"worker_plan": worker_plan_path},
                "workers": [common_worker],
            },
            {
                "agents": [common_worker],
                "agents_by_worker_id": {
                    "worker-001": {
                        **common_worker,
                        "isolated_out_root": "target/out/workers/worker-001",
                    }
                },
                "planner": {
                    "plan_path": worker_plan_path,
                    "worker_count": 1,
                },
            },
            path_text=worker_plan_path,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["planning_mode"], "source_file")
        self.assertEqual(result["worker_count"], 1)

    def test_context_pack_ledger_path_must_exist(self) -> None:
        temp_config = write_temp_config(load_default_config())
        temp_dir = temp_config.parent
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        missing_ledger = temp_dir / "out" / "state" / "missing.sqlite3"
        write_json(
            context_pack,
            {
                "context_management_contract": {
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "ledger_path": repo_relative(missing_ledger),
                    },
                }
            },
        )
        write_json(agent_index, {"report_kind": "agent-index"})

        with self.assertRaisesRegex(ValueError, "ledger_path does not exist"):
            validator.validate_context_ledger_contract(
                json.loads(context_pack.read_text(encoding="utf-8")),
                {},
                context_path_text=repo_relative(context_pack),
                agent_path_text=repo_relative(agent_index),
                repo_root=REPO_ROOT,
            )

    def test_context_ledger_worker_summary_hash_drift_fails(self) -> None:
        temp_config = write_temp_config(load_default_config())
        temp_dir = temp_config.parent
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        ledger = temp_dir / "out" / "state" / "opencode-agent-harness.sqlite3"
        summary = temp_dir / "out" / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text('{"status":"passed"}\n', encoding="utf-8")
        context_payload = {
            "context_management_contract": {
                "resume_protocol": {
                    "checkpoint_backend": "sqlite",
                    "ledger_path": repo_relative(ledger),
                },
            },
            "workers": [
                {
                    "worker_id": "worker-001",
                    "summary_path": repo_relative(summary),
                }
            ],
        }
        agent_payload = {
            "agents_by_worker_id": {
                "worker-001": {
                    "worker_id": "worker-001",
                    "summary_path": repo_relative(summary),
                }
            }
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        write_minimal_context_ledger(
            ledger,
            run_id="competition-flashdb-before-after-exhibit",
            context_pack_path=context_pack,
            context_pack_payload=context_payload,
            agent_index_path=agent_index,
        )
        summary.write_text('{"status":"tampered"}\n', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "worker summary sha256 must match"):
            validator.validate_context_ledger_contract(
                context_payload,
                agent_payload,
                context_path_text=repo_relative(context_pack),
                agent_path_text=repo_relative(agent_index),
                repo_root=REPO_ROOT,
            )

    def test_context_pack_workers_must_match_agent_index_workers(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_dir / "out")
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        placeholder = out_root / "summary" / "placeholder.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        other_request = out_root / "harness" / "assignments" / "worker-001-other-request.json"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        summary = out_root / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        report = out_root / "workers" / "worker-001" / "harness" / "run-worker-report.json"
        for artifact in [placeholder, request, other_request, assignment, summary, report]:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("{}\n", encoding="utf-8")
        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(placeholder),
            "workflow_metrics": repo_relative(placeholder),
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
        }
        write_json(temp_config, config)
        common_worker = {
            "assignment_path": repo_relative(assignment),
            "function": "demo_unit",
            "report_path": repo_relative(report),
            "request_path": repo_relative(request),
            "slice_id": "demo-unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
            "summary_path": repo_relative(summary),
            "worker_id": "worker-001",
        }
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "entrypoints": {
                    "primary_report": repo_relative(placeholder),
                    "evaluate_report": repo_relative(placeholder),
                    "worker_plan": None,
                },
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan", "role": "planner"},
                        {"stage": "translate", "role": "worker", "fanout": True},
                        {"stage": "verify", "role": "verifier"},
                        {"stage": "repair", "role": "repairer", "max_rounds": 5},
                    ],
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                },
                "workers": [common_worker],
            },
        )
        drifted_worker = dict(common_worker)
        drifted_worker["request_path"] = repo_relative(other_request)
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 1,
                },
                "agents": [drifted_worker],
                "agents_by_worker_id": {
                    "worker-001": {
                        **drifted_worker,
                        "isolated_out_root": repo_relative(out_root / "workers" / "worker-001"),
                    }
                },
            },
        )

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("field request_path must match" in error for error in result["errors"]),
            result["errors"],
        )

    def test_context_pack_semantic_gate_fails_closed(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_dir / "out")
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        placeholder = out_root / "summary" / "placeholder.json"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_text("{}\n", encoding="utf-8")
        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(placeholder),
            "workflow_metrics": repo_relative(placeholder),
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
        }
        write_json(temp_config, config)
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan"},
                        {"stage": "translate", "fanout": True},
                        {"stage": "verify"},
                        {"stage": "repair", "max_rounds": 5},
                    ],
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": True,
                },
            },
        )
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 0,
                },
                "agents": [],
                "agents_by_worker_id": {},
            },
        )

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("context_management_contract.semantic_gate must be false" in error for error in result["errors"]),
            result["errors"],
        )

    def test_generated_draft_semantic_pass_claim_fails_closed(self) -> None:
        config = load_default_config()
        config["claim_boundary"]["generated_draft_semantic_pass"] = True
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("generated_draft_semantic_pass must be false" in error for error in result["errors"]),
            result["errors"],
        )

    def test_entrypoint_proof_class_must_be_allowed(self) -> None:
        config = load_default_config()
        config["entrypoints"][0]["proof_class"] = "unlisted-proof"
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("entrypoint proof_class must be allowed" in error for error in result["errors"]),
            result["errors"],
        )

    def test_historical_profile_commit_must_be_declared_in_source_pin_policy(self) -> None:
        config = load_default_config()
        config["source_pin_policy"]["allowed_historical_evidence_commits"] = []
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("profile uses commits outside source_pin_policy" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_reproduction_command_must_match_entrypoint_command(self) -> None:
        config = load_default_config()
        temp_config = write_temp_config(config)
        entry = entrypoint_by_id(config, "multi_worker_evaluate_profile")
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["reproduction"]["evaluate_profile_command"] = manifest["reproduction"]["evaluate_profile_command"].replace(
            "--run-id harness-flashdb-explicit-workers-evaluate-profile-20260701",
            "--run-id wrong-evaluate-run",
        )
        manifest_path = temp_config.parent / "drifted-explicit-workers-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("tracked manifest reproduction command must match entrypoint command" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_claim_boundary_must_match_judge_config(self) -> None:
        config = load_default_config()
        temp_config = write_temp_config(config)
        entry = entrypoint_by_id(config, "multi_worker_evaluate_profile")
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["claim_boundary"]["semantic_claim_source"] = "generated_draft"
        manifest_path = temp_config.parent / "drifted-claim-boundary-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("tracked manifest claim_boundary.semantic_claim_source must match judge config" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_source_commits_must_follow_source_pin_policy(self) -> None:
        config = load_default_config()
        temp_config = write_temp_config(config)
        entry = entrypoint_by_id(config, "multi_worker_evaluate_profile")
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["workers"][0]["source_commit"] = "bad-commit"
        manifest_path = temp_config.parent / "drifted-source-commit-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("tracked manifest uses commits outside source_pin_policy" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_reproduction_out_root_bounds_expected_artifacts(self) -> None:
        config = load_default_config()
        entrypoint_by_id(config, "before_after_judge_demo")["expected_artifacts"]["merge_plan"] = "target/outside-harness/merge-plan.json"
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("expected_artifacts.merge_plan must be under reproduction --out-root" in error for error in result["errors"]),
            result["errors"],
        )

    def test_merge_plan_argv_rejects_local_absolute_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "local absolute path"):
            validator.validate_local_absolute_path_policy(
                {"merge_plan": {"argv": ["C:\\Python314\\python.exe", "validation/tools/run_competition.py"]}},
                label="merge-plan",
            )

    def test_merge_plan_argv_rejects_linux_local_absolute_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "local absolute path"):
            validator.validate_local_absolute_path_policy(
                {"merge_plan": {"argv": ["/tmp/python/bin/python", "validation/tools/run_competition.py"]}},
                label="merge-plan",
            )

    def test_competition_smoke_command_log_rejects_wsl_unc_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [
                            "\\\\wsl$\\Ubuntu\\home\\runner\\toolchain-check.sh",
                            "//wsl.localhost/Ubuntu/home/runner/python",
                        ],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_wsl_unc_alias_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [
                            "//wsl$/Ubuntu/home/runner/toolchain-check.sh",
                            "\\\\wsl.localhost\\Ubuntu\\home\\runner\\python",
                        ],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_wsl_drive_mount_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [
                            "/mnt/c/Users/runner/toolchain-check.sh",
                            "bash -lc 'python /mnt/c/Users/runner/tool.py'",
                        ],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_merge_execution_argv_allows_host_trace(self) -> None:
        result = validator.validate_local_absolute_path_policy(
            {"merge_execution": {"argv": ["C:\\Python314\\python.exe", "validation/tools/run_competition.py"]}},
            label="merge-execution",
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["host_trace_allowed_locations"], ["$.merge_execution.argv.0"])

    def test_diagnostic_host_metadata_allows_host_trace(self) -> None:
        result = validator.validate_local_absolute_path_policy(
            {
                "portability": {
                    "diagnostic_host_metadata": [
                        {"code": "diagnostic_host_metadata_path", "value": "F:\\agent\\crustpaper\\0630"}
                    ]
                }
            },
            label="evidence-governance",
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            result["host_trace_allowed_locations"],
            ["$.portability.diagnostic_host_metadata.0.value"],
        )

    def test_judge_evidence_reproduction_commands_reject_local_absolute_paths(self) -> None:
        payload = {
            "report_kind": "judge-evidence-index",
            "claim_boundary": {
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "index_is_semantic_gate": False,
            },
            "judge_headline": {
                "report_kind": "judge-headline",
                "semantic_gate": False,
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "opencode_runtime": {
                    "enabled": False,
                    "worker_count": 0,
                    "all_contracts_executed": False,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                },
            },
            "harness_architecture": {
                "architecture_contracts": {
                    "context_management": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                    "agent_coordination": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                        "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                    },
                }
            },
            "reproduction_commands": {
                "evaluate_profile": "C:\\Python314\\python.exe -m validation.tools.opencode_agent_harness evaluate"
            },
        }

        with self.assertRaisesRegex(ValueError, "local absolute path"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/judge-evidence-index.json")

    def test_core_validation_ci_runs_judge_entrypoints_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("validation.tools.test_validate_judge_entrypoints", workflow)


if __name__ == "__main__":
    unittest.main()
