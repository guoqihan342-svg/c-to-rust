from contextlib import closing
import hashlib
import json
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import Any

from validation.tools import validate_judge_entrypoints as validator


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENVIRONMENT_SHA256 = validator.sha256_file(REPO_ROOT / "config/competition-env/environment.json")
OPENCODE_RUNTIME_ENV_KEYS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
)


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


def opencode_runtime_env_contract(base_root: Path, *, scope: str) -> dict:
    runtime_root = base_root / "opencode-runtime" / scope
    runtime_paths = {
        "XDG_CONFIG_HOME": runtime_root / "config",
        "XDG_DATA_HOME": runtime_root / "data",
        "XDG_CACHE_HOME": runtime_root / "cache",
        "TMPDIR": runtime_root / "tmp",
        "TEMP": runtime_root / "tmp",
        "TMP": runtime_root / "tmp",
    }
    env = {key: repo_relative(runtime_paths[key]) for key in OPENCODE_RUNTIME_ENV_KEYS}
    runtime_root_rel = repo_relative(runtime_root)
    digest_payload = {
        "scope": scope,
        "runtime_root": runtime_root_rel,
        "env": env,
    }
    return {
        "schema_version": 1,
        "status": "isolated",
        "scope": scope,
        "runtime_root": runtime_root_rel,
        "env": env,
        "env_sha256": validator.sha256_text(json.dumps(digest_payload, sort_keys=True)),
        "semantic_gate": False,
        "evidence_boundary": "runtime env isolation is audit evidence only",
    }


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
    retry_hint_id: str | None = None,
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
    commands = {
        "run_worker": {
            "argv": argv,
            "command": shlex.join(argv),
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "out_root": repo_relative(worker_root),
            "replay_safety": {
                "status": "ready",
                "semantic_gate": False,
                "chat_output_is_evidence": False,
            },
        }
    }
    if retry_hint_id is not None:
        retry_argv = [
            "python3",
            "-B",
            "-m",
            "validation.tools.opencode_agent_harness",
            "retry-worker",
            "--db",
            repo_relative(ledger),
            "--run-id",
            run_id,
            "--worker-id",
            worker_id,
            "--hint-id",
            retry_hint_id,
            "--mode",
            "deterministic",
        ]
        commands["retry_worker"] = {
            "argv": retry_argv,
            "command": shlex.join(retry_argv),
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "out_root": repo_relative(worker_root),
            "replay_safety": {
                "status": "ready",
                "semantic_gate": False,
                "chat_output_is_evidence": False,
            },
        }
    return commands


def write_valid_command_log(
    path: Path,
    steps: list[dict] | None = None,
    *,
    run_id: str = "competition-flashdb-environment-smoke-20260701",
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    command_steps = steps or [
        {
            "step": step,
            "returncode": 0,
        }
        for step in validator.REQUIRED_COMPETITION_SMOKE_STEPS
    ]
    path.write_text(
        "".join(
            json.dumps(
                {
                    "step": step["step"],
                    "command": valid_competition_smoke_step_command(step["step"]),
                    "returncode": step.get("returncode", 0),
                    "stdout": "",
                    "stderr": "",
                    "workdir": ".",
                    "run_id": run_id,
                    "canonical": True,
                    **({"timed_out": True} if step.get("timed_out") is True else {}),
                    **({"timeout_seconds": step["timeout_seconds"]} if "timeout_seconds" in step else {}),
                    **({"failure_class": step["failure_class"]} if "failure_class" in step else {}),
                },
                sort_keys=True,
            )
            + "\n"
            for step in command_steps
        ),
        encoding="utf-8",
    )
    return validator.sha256_file(path)


def write_opencode_model_probe_logs(
    root: Path,
    *,
    stdout: str = "provider/GLM-5.1\n",
    stderr: str = "",
) -> dict[str, Any]:
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / "opencode-models.stdout.log"
    stderr_path = logs_dir / "opencode-models.stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8", newline="\n")
    stderr_path.write_text(stderr, encoding="utf-8", newline="\n")
    return {
        "logs": {
            "stdout": repo_relative(stdout_path),
            "stderr": repo_relative(stderr_path),
        },
        "stdout_sha256": validator.sha256_file(stdout_path),
        "stderr_sha256": validator.sha256_file(stderr_path),
    }


def valid_competition_smoke_step_command(step: str) -> list[str]:
    script_by_step = {
        "vendored-clang-verification": "validation/tools/verify_vendored_clang.py",
        "core-auto-evidence-validator": "validation/tools/validate_auto_translation_evidence.py",
        "evidence-governance": "validation/tools/evidence_governance.py",
        "translator-coverage-matrix": "validation/tools/translator_coverage_matrix.py",
        "milestone-release-report": "validation/tools/milestone_release_report.py",
    }
    if step == "environment-check":
        return ["bash", "-lc", "source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh"]
    if step == "lightweight-unittest":
        return [
            "python3",
            "-B",
            "-m",
            "unittest",
            "validation.tools.test_competition_environment_profile",
            "validation.tools.test_validate_competition_run_summary",
        ]
    if step == "opencode-glm-model-probe":
        return ["opencode", "models"]
    if step in script_by_step:
        return ["python3", "-B", script_by_step[step]]
    return ["python3", "-B", "validation/tools/run_competition_smoke.py", "--step", step]


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
    verified_baseline_ref = write_verified_unsafe_baseline_ref(artifact_dir / "verified-unsafe-baseline.json")
    summary_path = artifact_dir / "competition-run-summary.json"
    summary_payload = valid_competition_run_summary_payload(run_id="run-test")
    workflow_metrics_path = write_competition_run_summary_with_workflow_metrics(summary_path, summary_payload)
    refs["summary"] = {"path": repo_relative(summary_path), "sha256": validator.sha256_file(summary_path)}
    refs["workflow-metrics"] = {
        "path": repo_relative(workflow_metrics_path),
        "sha256": validator.sha256_file(workflow_metrics_path),
    }
    launch_policy = opencode_launch_policy()
    runtime_env = opencode_runtime_env_contract(artifact_dir, scope="worker-a")
    worker_cmd = worker_command(artifact_dir)
    worker_command_line = shlex.join(worker_cmd)
    opencode_prompt = "Execute test safety transform worker."
    opencode_argv = [
        "opencode",
        "run",
        "--dir",
        ".",
        "--format",
        "json",
        "--variant",
        launch_policy["opencode_variant"],
        "--model",
        launch_policy["opencode_model"],
    ]
    if launch_policy.get("opencode_agent"):
        opencode_argv.extend(["--agent", launch_policy["opencode_agent"]])
    if launch_policy.get("opencode_skip_permissions"):
        opencode_argv.append("--dangerously-skip-permissions")
    opencode_argv.append(opencode_prompt)
    handoff_path = artifact_dir / "opencode-handoff-contract.json"
    handoff_payload = {
        "schema_version": 1,
        "run_id": "run-test",
        "worker_id": "worker-a",
        "attempt": 2,
        "runner_kind": "opencode-run",
        "request_path": repo_relative(artifact_dir / "request.json"),
        "expected_summary_path": repo_relative(summary_path),
        "worker_command": worker_cmd,
        "worker_command_line": worker_command_line,
        "worker_command_sha256": validator.sha256_text(worker_command_line),
        "opencode_argv": opencode_argv,
        "opencode_command_line": shlex.join(opencode_argv),
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "prompt": opencode_prompt,
        "opencode_runtime_env": runtime_env,
        "evidence_boundary": "chat output is diagnostic only; semantic acceptance requires validators",
    }
    write_json(handoff_path, handoff_payload)
    session_path = artifact_dir / "opencode-session-evidence.json"
    stdout_path = artifact_dir / "opencode.stdout.log"
    stderr_path = artifact_dir / "opencode.stderr.log"
    session_payload = {
        "schema_version": 1,
        "process_returncode": 0,
        "parsed": True,
        "format": "jsonl",
        "opencode_runtime_env": runtime_env,
        "session_events": [
            {
                "part": {
                    "tool": "bash",
                    "state": {"input": {"command": worker_command_line, "workdir": str(REPO_ROOT)}},
                }
            }
        ],
    }
    bind_opencode_session_raw_logs(
        session_path,
        session_payload,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    write_json(session_path, session_payload)
    contract_verification = validator.recompute_opencode_contract_execution(
        session_evidence=session_payload,
        worker_command=worker_cmd,
        summary_path=summary_path,
        repo_root=REPO_ROOT,
    )
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
        "handoff_contract": {
            "path": repo_relative(handoff_path),
            "sha256": validator.sha256_file(handoff_path),
        },
        "opencode_session_evidence": {
            "path": repo_relative(session_path),
            "sha256": validator.sha256_file(session_path),
        },
        "contract_verification": contract_verification,
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
                    "baseline_verification": verified_baseline_ref,
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
    workflow_metrics_path = REPO_ROOT / refs["workflow-metrics"]["path"]
    workflow_metrics = json.loads(workflow_metrics_path.read_text(encoding="utf-8"))
    workflow_metrics["unsafe_reduction"] = {
        "status": "measured",
        "baseline_total_unsafe": 3,
        "current_total_unsafe": 1,
        "reduced_by": 2,
        "ratio": 1 / 3,
    }
    workflow_metrics["translation_before_after"] = {
        "status": "bound",
        "unit_count": 1,
        "measured_unsafe_unit_count": 1,
        "accepted_patch_unit_count": 1,
        "units": [
            {
                "unit_id": "demo/store-add-one",
                "status": "bound",
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 3,
                    "current_total_unsafe": 1,
                    "reduced_by": 2,
                    "ratio": 1 / 3,
                },
            }
        ],
    }
    workflow_metrics["per_unit_statuses"] = [
        {
            "unit_id": "demo/store-add-one",
            "source": "slice-spec",
            "status": "converged",
            "compiled": True,
            "semantic_pass": True,
            "refused": False,
            "blocked": False,
            "failed": False,
            "translation_before_after": {
                "status": "bound",
                "baseline_verification": verified_baseline_ref,
                "baseline": refs["baseline-unsafe.rs"],
                "final": refs["final-safe.rs"],
                "accepted_patch": refs["accepted.patch"],
                "patch_log": refs["patch-log.jsonl"],
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
        }
    ]
    write_json(workflow_metrics_path, workflow_metrics)
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_payload["workflow_metrics"]["sha256"] = validator.sha256_file(workflow_metrics_path)
    write_json(summary_path, summary_payload)
    payload["summary"]["sha256"] = validator.sha256_file(summary_path)
    payload["workflow_metrics"]["sha256"] = validator.sha256_file(workflow_metrics_path)
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


def valid_evidence_governance_report_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "passed",
        "evidence_root": "validation/evidence",
        "failed_gates": [],
        "policy_compliance": {
            "policy_tier": "dev",
            "status": "passed",
            "failed_gates": [],
            "gates": [],
        },
        "portability": {
            "status": "passed",
            "claim_anchor_issue_count": 0,
            "profile_hash_issue_count": 0,
        },
        "inventory": {
            "file_count": 0,
            "total_bytes": 0,
        },
    }


def valid_translator_coverage_matrix_report_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "passed",
        "matrix": {
            "path": "validation/translator-coverage-matrix.json",
            "capability_count": 0,
        },
        "capability_count": 0,
        "dimensions": {},
        "capabilities": [],
        "capability_delta_ledger": {
            "schema_version": 1,
            "status": "recorded",
            "ledger_count": 0,
            "delta_count": 0,
            "semantic_pass_count": 0,
            "translator_generated_semantic_pass_count": 0,
            "accepted_evidence_semantic_pass_count": 0,
            "generated_candidate_status": {},
            "route_levels": {},
            "route_statuses": {},
            "by_construct": {},
            "ledgers": [],
        },
        "claim_boundary": "translator coverage report fixture; not semantic acceptance evidence",
    }


def valid_milestone_release_report_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "internal_preview",
        "report_kind": "milestone-release-metrics",
        "inputs": {},
        "harness_architecture": {},
        "core_translation_quality": {
            "translation_coverage_numerator": 0,
        },
        "metrics": {
            "translation_coverage_numerator": 0,
        },
        "readiness": {
            "status": "internal_preview",
            "blockers": ["fixture"],
        },
        "release_note_inputs": {},
        "claim_boundary": "milestone release report fixture; not semantic acceptance evidence",
    }


def write_valid_competition_smoke_report_artifacts(
    evidence_governance: Path,
    coverage_matrix: Path,
    milestone: Path,
) -> None:
    write_json(evidence_governance, valid_evidence_governance_report_payload())
    write_json(coverage_matrix, valid_translator_coverage_matrix_report_payload())
    write_json(milestone, valid_milestone_release_report_payload())


def write_exact_competition_smoke_fixture(
    root: Path,
    *,
    run_id: str,
    availability_stdout: str = "provider/GLM-5.1\n",
    command_log_stdout: str = "provider/GLM-5.1\n",
) -> tuple[dict[str, str], dict[str, Any]]:
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
    payload["proof_class"] = "competition-exact"
    payload["run_id"] = run_id
    payload["execution_environment"].update(
        {
            "competition_exact_host_attested": True,
            "detected_ci": False,
            "detected_wsl": False,
            "kind": "competition-host",
            "system": "Linux",
        }
    )
    payload["competition_profile_match"].update(
        {
            "cargo_mirror_config_present": True,
            "clang_lane_verified": True,
            "kernel_match": True,
            "os_name_match": True,
            "python_version_match": True,
        }
    )
    payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
    payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
    payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
    payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
    payload["command_log"]["path"] = artifacts["command_log"]
    for step in payload["steps"]:
        step["status"] = "passed"
        step["returncode"] = 0
        step["log_path"] = artifacts["command_log"]
        step.pop("proof_class_effect", None)
    payload["steps"].append(
        {
            "step": "opencode-glm-model-probe",
            "status": "passed",
            "returncode": 0,
            "log_path": artifacts["command_log"],
        }
    )
    payload["opencode_model_availability"] = {
        "status": "available",
        "required_model": "GLM-5.1",
        "model_listed": True,
        "opencode_command": "opencode",
        "argv": ["opencode", "models"],
        "process_returncode": 0,
        **write_opencode_model_probe_logs(root, stdout=availability_stdout),
    }

    write_json(summary_path, payload)
    write_json(
        vendored_path,
        {
            **valid_vendored_clang_verification_payload(),
            "proof_class": "competition-exact",
            "clang_required": True,
        },
    )
    write_valid_competition_smoke_report_artifacts(evidence_governance, coverage_matrix, milestone)
    command_log.parent.mkdir(parents=True, exist_ok=True)
    command_log.write_text(
        "".join(
            json.dumps(
                {
                    "step": step["step"],
                    "command": (
                        ["opencode", "models"]
                        if step["step"] == "opencode-glm-model-probe"
                        else valid_competition_smoke_step_command(step["step"])
                    ),
                    "returncode": 0,
                    "stdout": command_log_stdout if step["step"] == "opencode-glm-model-probe" else "",
                    "stderr": "",
                    "workdir": ".",
                    "run_id": run_id,
                    "canonical": True,
                },
                sort_keys=True,
            )
            + "\n"
            for step in payload["steps"]
        ),
        encoding="utf-8",
    )
    payload["command_log"]["sha256"] = validator.sha256_file(command_log)
    write_json(summary_path, payload)
    return artifacts, payload


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
    command_log_path = summary_path.parent / "commands.jsonl"
    command_log_ref = repo_relative(command_log_path)
    command_log_path.write_text(
        json.dumps(
            {
                "canonical": True,
                "command": ["python3", "-B", "-m", "validation.tools.validate_competition_run_summary"],
                "log_path": command_log_ref,
                "returncode": 0,
                "run_id": summary["run_id"],
                "stderr": "",
                "stdout": "",
                "step": "validate-competition-summary",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary["command_log"] = {
        "path": command_log_ref,
        "sha256": validator.sha256_file(command_log_path),
    }
    write_json(summary_path, summary)
    return metrics_path


def opencode_launch_policy() -> dict:
    return {
        "opencode_command": "opencode",
        "opencode_model": "GLM-5.1",
        "opencode_agent": "c2rust-migrator",
        "opencode_variant": "max",
        "opencode_skip_permissions": False,
    }


def opencode_launch_policy_sha256(policy: dict) -> str:
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode("utf-8")).hexdigest()


def opencode_preflight_argv(launch_policy: dict) -> list[str]:
    argv = [
        "opencode",
        "run",
        "--dir",
        ".",
        "--format",
        "json",
        "--variant",
        launch_policy["opencode_variant"],
        "--model",
        launch_policy["opencode_model"],
    ]
    if launch_policy.get("opencode_agent"):
        argv.extend(["--agent", launch_policy["opencode_agent"]])
    if launch_policy.get("opencode_skip_permissions"):
        argv.append("--dangerously-skip-permissions")
    argv.append("Execute test preflight marker.")
    return argv


def set_artifact_ref(ref: dict, path: Path, payload: dict | None = None) -> None:
    if payload is None:
        payload = {"report_kind": "test-artifact"}
    write_json(path, payload)
    ref["path"] = repo_relative(path)
    ref["sha256"] = validator.sha256_file(path)


def opencode_session_stdout_jsonl(events: list) -> str:
    return "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)


def ensure_opencode_jsonl_session_events(session_payload: dict) -> None:
    events = session_payload.get("session_events")
    if not isinstance(events, list):
        return
    while len(events) < 2:
        events.append(
            {
                "type": "text",
                "part": {
                    "text": "fixture-jsonl-keepalive",
                },
            }
        )


def bind_opencode_session_raw_logs(
    session_path: Path,
    session_payload: dict,
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> None:
    existing_session = json.loads(session_path.read_text(encoding="utf-8")) if session_path.is_file() else {}
    if stdout_path is None:
        stdout_path_text = session_payload.get("stdout_path") or existing_session.get("stdout_path")
        stdout_path = REPO_ROOT / stdout_path_text if stdout_path_text else session_path.with_name("stdout.log")
    if stderr_path is None:
        stderr_path_text = session_payload.get("stderr_path") or existing_session.get("stderr_path")
        stderr_path = REPO_ROOT / stderr_path_text if stderr_path_text else session_path.with_name("stderr.log")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    if "session_events" in session_payload:
        ensure_opencode_jsonl_session_events(session_payload)
        stdout_path.write_text(
            opencode_session_stdout_jsonl(session_payload["session_events"]),
            encoding="utf-8",
            newline="\n",
        )
    elif not stdout_path.exists():
        stdout_path.write_text("", encoding="utf-8", newline="\n")
    if not stderr_path.exists():
        stderr_path.write_text("", encoding="utf-8", newline="\n")
    session_payload["stdout_path"] = repo_relative(stdout_path)
    session_payload["stderr_path"] = repo_relative(stderr_path)
    session_payload["stdout_sha256"] = validator.sha256_file(stdout_path)
    session_payload["stderr_sha256"] = validator.sha256_file(stderr_path)


def set_all_opencode_preflight_refs(payload: dict, path: Path, *, run_id: str, launch_policy: dict) -> None:
    base_root = path.parent.parent if path.parent.name == "harness" else path.parent
    harness_dir = base_root / "harness"
    logs_dir = base_root / "logs"
    harness_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    marker_path = harness_dir / "opencode-preflight-marker.json"
    contract_path = harness_dir / "opencode-preflight-contract.json"
    session_path = logs_dir / "opencode-preflight-session-evidence.json"
    stdout_path = logs_dir / "opencode-preflight.stdout.log"
    stderr_path = logs_dir / "opencode-preflight.stderr.log"
    runtime_env = opencode_runtime_env_contract(base_root, scope="preflight")
    marker_command = [
        "python3",
        "-B",
        "validation/tools/opencode_agent_harness.py",
        "write-preflight-marker",
        "--marker",
        repo_relative(marker_path),
        "--run-id",
        run_id,
    ]
    marker_command_line = shlex.join(marker_command)
    preflight_argv = opencode_preflight_argv(launch_policy)
    preflight_command_line = shlex.join(preflight_argv)
    write_json(
        marker_path,
        {
            "schema_version": 1,
            "report_kind": "opencode-preflight-marker",
            "run_id": run_id,
            "status": "written",
        },
    )
    write_json(
        contract_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "runner_kind": "opencode-preflight",
            "expected_marker_path": repo_relative(marker_path),
            "worker_command": marker_command,
            "worker_command_line": marker_command_line,
            "worker_command_sha256": validator.sha256_text(marker_command_line),
            "opencode_argv": preflight_argv,
            "opencode_command_line": preflight_command_line,
            "launch_policy": launch_policy,
            "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
            "prompt": preflight_argv[-1],
            "opencode_runtime_env": runtime_env,
        },
    )
    session_payload = {
        "schema_version": 1,
        "process_returncode": 0,
        "parsed": True,
        "format": "jsonl",
        "opencode_runtime_env": runtime_env,
        "session_events": [
            {
                "part": {
                    "tool": "bash",
                    "state": {
                        "input": {
                            "command": marker_command_line,
                            "workdir": str(REPO_ROOT),
                        }
                    },
                }
            }
        ],
    }
    bind_opencode_session_raw_logs(
        session_path,
        session_payload,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    write_json(session_path, session_payload)
    model_stdout = "GLM-5.1\n"
    model_stderr = ""
    model_stdout_path = logs_dir / "opencode-models.stdout.log"
    model_stderr_path = logs_dir / "opencode-models.stderr.log"
    model_stdout_path.write_text(model_stdout, encoding="utf-8")
    model_stderr_path.write_text(model_stderr, encoding="utf-8")
    preflight_payload = {
        "report_kind": "opencode-preflight-report",
        "status": "passed",
        "process_returncode": 0,
        "argv": preflight_argv,
        "marker_exists": True,
        "marker_path": repo_relative(marker_path),
        "marker": {
            "path": repo_relative(marker_path),
            "sha256": validator.sha256_file(marker_path),
        },
        "opencode_run_launched": True,
        "run_id": run_id,
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "opencode_runtime_env": runtime_env,
        "handoff_contract": {
            "path": repo_relative(contract_path),
            "sha256": validator.sha256_file(contract_path),
        },
        "opencode_session_evidence": {
            "path": repo_relative(session_path),
            "sha256": validator.sha256_file(session_path),
        },
        "opencode_model_availability": {
            "status": "available",
            "opencode_command": "opencode",
            "required_model": "GLM-5.1",
            "argv": ["opencode", "models"],
            "model_listed": True,
            "process_returncode": 0,
            "stdout_sha256": validator.sha256_text(model_stdout),
            "stderr_sha256": validator.sha256_text(model_stderr),
            "logs": {
                "stdout": repo_relative(model_stdout_path),
                "stderr": repo_relative(model_stderr_path),
            },
        },
        "contract_verification": {
            "status": "executed",
            "expected_worker_command_line": marker_command_line,
            "expected_summary_path": repo_relative(marker_path),
            "expected_worker_command_sha256": validator.sha256_text(marker_command_line),
            "executed_shell_command_count": 1,
            "executed_shell_commands": [marker_command_line],
            "first_tool_name": "bash",
            "first_shell_command": marker_command_line,
            "first_shell_tool_name": "bash",
            "first_shell_workdir_status": "repo_root",
            "expected_workdir_status": "repo_root",
            "first_shell_command_matches_worker_command": True,
            "first_shell_workdir_matches_repo_root": True,
            "worker_command_seen": True,
            "summary_exists": True,
            "tools_before_first_shell": [],
            "contract_failure_reason": "",
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


def refresh_all_opencode_preflight_ref_hashes(payload: dict, path: Path) -> None:
    new_sha = validator.sha256_file(path)
    for ref in (
        payload["evidence_artifact_refs"]["opencode_preflight_report"],
        payload["opencode_agent_runtime"]["opencode_preflight_report"],
        payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"],
    ):
        ref["sha256"] = new_sha


def rewrite_preflight_session_evidence(preflight_path: Path, session_payload: dict) -> dict:
    preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    session_ref = preflight_payload["opencode_session_evidence"]
    session_path = REPO_ROOT / session_ref["path"]
    existing_session = json.loads(session_path.read_text(encoding="utf-8"))
    if "opencode_runtime_env" not in session_payload and "opencode_runtime_env" in existing_session:
        session_payload["opencode_runtime_env"] = existing_session["opencode_runtime_env"]
    bind_opencode_session_raw_logs(session_path, session_payload)
    write_json(session_path, session_payload)
    session_ref["sha256"] = validator.sha256_file(session_path)
    write_json(preflight_path, preflight_payload)
    return preflight_payload


def preflight_marker_command_line(preflight_path: Path) -> str:
    preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    contract_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
    contract_payload = json.loads(contract_path.read_text(encoding="utf-8"))
    return contract_payload["worker_command_line"]


def preflight_marker_path(preflight_path: Path) -> Path:
    preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    return REPO_ROOT / preflight_payload["marker_path"]


def worker_command(worker_root: Path) -> list[str]:
    return [
        "python3",
        "-B",
        "scripts/c2rust-migrator.py",
        "--phase",
        "migrate",
        "--input",
        repo_relative(worker_root / "harness" / "request.json"),
    ]


def write_worker_opencode_contract_artifacts(worker: dict, worker_root: Path, *, run_id: str, launch_policy: dict) -> None:
    summary_path = worker_root / "summary" / "competition-run-summary.json"
    worker_report_path = worker_root / "harness" / "run-worker-report.json"
    handoff_path = worker_root / "harness" / "opencode-handoff-contract.json"
    session_path = worker_root / "logs" / "opencode-session-evidence.json"
    stdout_path = worker_root / "logs" / "stdout.log"
    stderr_path = worker_root / "logs" / "stderr.log"
    runtime_env = opencode_runtime_env_contract(worker_root, scope=worker["worker_id"])
    command = worker_command(worker_root)
    command_line = shlex.join(command)
    opencode_prompt = f"Execute worker {worker['worker_id']} handoff contract."
    opencode_argv = [
        "opencode",
        "run",
        "--dir",
        ".",
        "--format",
        "json",
        "--variant",
        launch_policy["opencode_variant"],
        "--model",
        launch_policy["opencode_model"],
    ]
    if launch_policy.get("opencode_agent"):
        opencode_argv.extend(["--agent", launch_policy["opencode_agent"]])
    if launch_policy.get("opencode_skip_permissions"):
        opencode_argv.append("--dangerously-skip-permissions")
    opencode_argv.append(opencode_prompt)
    summary_payload = valid_competition_run_summary_payload(run_id=run_id)
    write_competition_run_summary_with_workflow_metrics(summary_path, summary_payload)
    worker["summary"]["path"] = repo_relative(summary_path)
    worker["summary"]["sha256"] = validator.sha256_file(summary_path)
    set_artifact_ref(
        worker["worker_report"],
        worker_report_path,
        {
            "schema_version": 1,
            "report_kind": "run-worker-report",
            "worker_id": worker["worker_id"],
            "mode": "opencode",
            "runner_kind": "opencode-run",
            "summary_path": repo_relative(summary_path),
            "summary_status": "passed",
            "recorded": True,
            "exit_code": 0,
            "process_returncode": 0,
            "opencode_runtime_env": runtime_env,
        },
    )
    write_json(
        handoff_path,
        {
            "schema_version": 1,
            "runner_kind": "opencode-run",
            "run_id": run_id,
            "worker_id": worker["worker_id"],
            "launch_policy": launch_policy,
            "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
            "worker_command": command,
            "worker_command_line": command_line,
            "worker_command_sha256": validator.sha256_text(command_line),
            "expected_summary_path": repo_relative(summary_path),
            "opencode_argv": opencode_argv,
            "opencode_command_line": shlex.join(opencode_argv),
            "prompt": opencode_prompt,
            "opencode_runtime_env": runtime_env,
        },
    )
    worker["handoff_contract"]["path"] = repo_relative(handoff_path)
    worker["handoff_contract"]["sha256"] = validator.sha256_file(handoff_path)
    session_payload = {
        "schema_version": 1,
        "process_returncode": 0,
        "parsed": True,
        "format": "jsonl",
        "opencode_runtime_env": runtime_env,
        "session_events": [
            {
                "part": {
                    "tool": "bash",
                    "state": {"input": {"command": command_line, "workdir": str(REPO_ROOT)}},
                }
            }
        ],
    }
    bind_opencode_session_raw_logs(
        session_path,
        session_payload,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    write_json(session_path, session_payload)
    worker["opencode_session_evidence"]["path"] = repo_relative(session_path)
    worker["opencode_session_evidence"]["sha256"] = validator.sha256_file(session_path)
    worker["logs"]["stdout"]["path"] = repo_relative(stdout_path)
    worker["logs"]["stdout"]["sha256"] = validator.sha256_file(stdout_path)
    worker["logs"]["stderr"]["path"] = repo_relative(stderr_path)
    worker["logs"]["stderr"]["sha256"] = validator.sha256_file(stderr_path)
    worker["opencode_contract_verification"] = {
        "status": "executed",
        "expected_worker_command_line": command_line,
        "expected_summary_path": repo_relative(summary_path),
        "expected_worker_command_sha256": validator.sha256_text(command_line),
        "executed_shell_command_count": 1,
        "executed_shell_commands": [command_line],
        "first_tool_name": "bash",
        "first_shell_command": command_line,
        "first_shell_tool_name": "bash",
        "first_shell_workdir_status": "repo_root",
        "expected_workdir_status": "repo_root",
        "first_shell_command_matches_worker_command": True,
        "first_shell_workdir_matches_repo_root": True,
        "worker_command_seen": True,
        "summary_exists": True,
        "tools_before_first_shell": [],
        "contract_failure_reason": "",
    }


def rewrite_worker_session_evidence(worker: dict, session_payload: dict) -> None:
    session_path = REPO_ROOT / worker["opencode_session_evidence"]["path"]
    existing_session = json.loads(session_path.read_text(encoding="utf-8"))
    if "opencode_runtime_env" not in session_payload and "opencode_runtime_env" in existing_session:
        session_payload["opencode_runtime_env"] = existing_session["opencode_runtime_env"]
    bind_opencode_session_raw_logs(session_path, session_payload)
    write_json(session_path, session_payload)
    worker["opencode_session_evidence"]["sha256"] = validator.sha256_file(session_path)
    if "logs" in worker:
        stdout_path = REPO_ROOT / session_payload["stdout_path"]
        stderr_path = REPO_ROOT / session_payload["stderr_path"]
        worker["logs"]["stdout"]["path"] = repo_relative(stdout_path)
        worker["logs"]["stdout"]["sha256"] = validator.sha256_file(stdout_path)
        worker["logs"]["stderr"]["path"] = repo_relative(stderr_path)
        worker["logs"]["stderr"]["sha256"] = validator.sha256_file(stderr_path)


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
        write_worker_opencode_contract_artifacts(worker, worker_root, run_id=payload["run_id"], launch_policy=launch_policy)


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


def write_opencode_hostless_rehearsal_fixture(root: Path) -> tuple[Path, dict]:
    out_root = root / "out"
    harness_dir = out_root / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    run_id = "hostless-rehearsal"
    runtime_source = valid_opencode_judge_index_payload()
    runtime_source["run_id"] = run_id
    materialize_opencode_judge_index_artifacts(
        runtime_source,
        out_root,
        profile_payload={"profile_id": "demo-hostless"},
    )
    runtime = runtime_source["opencode_agent_runtime"]
    runtime_worker = runtime["workers"][0]
    worker_id = runtime_worker["worker_id"]
    worker_root = out_root / "workers" / worker_id
    assignment = harness_dir / "assignments" / f"{worker_id}.json"
    request = harness_dir / "assignments" / f"{worker_id}-request.json"
    write_json(assignment, {"worker_id": worker_id, "report_kind": "assignment"})
    write_json(request, {"worker_id": worker_id, "report_kind": "worker-request"})
    worker_context = {
        "assignment_path": repo_relative(assignment),
        "function": "demo_unit",
        "isolated_out_root": repo_relative(worker_root),
        "out_root": repo_relative(worker_root),
        "report_path": runtime_worker["worker_report"]["path"],
        "request_path": repo_relative(request),
        "slice_id": "demo-unit",
        "source_commit": "abc123",
        "source_sha256": "f" * 64,
        "summary_path": runtime_worker["summary"]["path"],
        "worker_id": worker_id,
    }
    batch_report_path = harness_dir / "batch-profile-report.json"
    run_plan_report_path = harness_dir / "run-plan-report.json"
    context_pack_path = harness_dir / "context-pack.json"
    agent_index_path = harness_dir / "agent-index.json"
    write_json(
        batch_report_path,
        {
            "schema_version": 1,
            "report_kind": "batch-profile-report",
            "status": "completed",
            "run_id": run_id,
            "mode": "opencode",
            "proof_class": "local-simulation",
        },
    )
    write_json(
        run_plan_report_path,
        {
            "schema_version": 1,
            "report_kind": "run-plan-report",
            "status": "completed",
            "run_id": run_id,
            "mode": "opencode",
        },
    )
    context_payload = {
        "report_kind": "context-pack",
        "context_management_contract": {
            "agent_index": repo_relative(agent_index_path),
            "chat_output_is_evidence": False,
            "context_pack": repo_relative(context_pack_path),
            "contract_kind": "context-management",
            "evidence_policy": "on-disk-artifacts-only",
            "pipeline": [
                {"stage": "plan", "role": "planner"},
                {"stage": "translate", "role": "worker", "fanout": True},
                {"stage": "verify", "role": "verifier"},
                {"stage": "repair", "role": "repairer", "max_rounds": 5},
            ],
            "primary_report": repo_relative(batch_report_path),
            "resume_protocol": {
                "checkpoint_backend": "sqlite",
                "ledger_path": repo_relative(out_root / "state" / "opencode-agent-harness.sqlite3"),
                "worker_state_source": "agent-index.agents_by_worker_id",
            },
            "schema_version": 1,
            "semantic_gate": False,
        },
        "entrypoints": {
            "primary_report": repo_relative(batch_report_path),
            "batch_profile_report": repo_relative(batch_report_path),
            "run_plan_report": repo_relative(run_plan_report_path),
        },
        "workers": [worker_context],
    }
    agent_payload = {
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
        "agents": [worker_context],
        "agents_by_worker_id": {worker_id: worker_context},
        "reports": {
            "batch_profile_report": {
                "path": repo_relative(batch_report_path),
                "report_kind": "batch-profile-report",
                "status": "completed",
            },
            "run_plan_report": {
                "path": repo_relative(run_plan_report_path),
                "report_kind": "run-plan-report",
                "status": "completed",
            },
        },
    }
    write_json(context_pack_path, context_payload)
    write_json(agent_index_path, agent_payload)
    rehearsal_path = harness_dir / "opencode-hostless-rehearsal-report.json"
    payload = {
        "schema_version": 1,
        "report_kind": "opencode-hostless-rehearsal-report",
        "status": "completed",
        "exit_code": 0,
        "run_id": run_id,
        "profile_id": "demo-hostless",
        "proof_class": "local-simulation",
        "mode": "opencode",
        "rehearsal_runner": "fake/fixture",
        "closes_p0_h9": False,
        "semantic_gate": False,
        "chat_output_is_evidence": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "h9_contract": {
            "status": "blocked",
            "reason": "hostless_rehearsal_is_not_real_opencode_glm51_max_host_evidence",
            "required_agent_tool": "opencode",
            "required_agent": "c2rust-migrator",
            "required_model": "GLM-5.1",
            "required_variant": "max",
            "required_proof_class": "competition-exact",
            "local_simulation_closes_p0_h9": False,
        },
        "batch_profile_report": {
            "path": repo_relative(batch_report_path),
            "sha256": validator.sha256_file(batch_report_path),
        },
        "run_plan_report": {
            "path": repo_relative(run_plan_report_path),
            "sha256": validator.sha256_file(run_plan_report_path),
        },
        "context_pack": {
            "path": repo_relative(context_pack_path),
            "sha256": validator.sha256_file(context_pack_path),
        },
        "agent_index": {
            "path": repo_relative(agent_index_path),
            "sha256": validator.sha256_file(agent_index_path),
        },
        "opencode_preflight_report": json.loads(json.dumps(runtime["opencode_preflight_report"])),
        "opencode_runtime": runtime,
        "workers": [
            {
                "worker_id": worker_id,
                "summary_status": "passed",
                "exit_code": 0,
                "recorded": True,
                "semantic_gate": False,
                "summary": json.loads(json.dumps(runtime_worker["summary"])),
                "report": json.loads(json.dumps(runtime_worker["worker_report"])),
                "handoff_contract": json.loads(json.dumps(runtime_worker["handoff_contract"])),
                "opencode_session_evidence": json.loads(json.dumps(runtime_worker["opencode_session_evidence"])),
                "opencode_preflight_report": json.loads(json.dumps(runtime_worker["opencode_preflight_report"])),
                "opencode_contract_verification": json.loads(json.dumps(runtime_worker["opencode_contract_verification"])),
                "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
            }
        ],
        "worker_count": 1,
        "boundary": "hostless rehearsal only",
    }
    write_json(rehearsal_path, payload)
    return rehearsal_path, payload


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
        agent_index_payload_json = json.dumps(
            json.loads(agent_index_path.read_text(encoding="utf-8")),
            sort_keys=True,
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
                agent_index_payload_json,
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
                  run_id, agent_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    worker.get("worker_id"),
                    "competition-run-summary",
                    worker["summary_path"],
                    validator.sha256_file(summary_path),
                    "passed",
                    "run-summary",
                    "{}",
                    "2026-07-01T00:00:00Z",
                ),
            )
            if isinstance(worker.get("report_path"), str):
                report_path = REPO_ROOT / worker["report_path"]
                if report_path.is_file():
                    connection.execute(
                        """
                        insert into artifacts(
                          run_id, agent_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            worker.get("worker_id"),
                            "run-worker-report",
                            worker["report_path"],
                            validator.sha256_file(report_path),
                            "passed",
                            "worker-execution-report",
                            "{}",
                            "2026-07-01T00:00:00Z",
                        ),
                    )
        connection.commit()


def write_context_ledger_case(
    temp_dir: Path,
    *,
    run_id: str = "context-ledger-case",
    ledger_run_id: str | None = None,
    isolated_out_root: str | None = None,
) -> dict:
    out_root = temp_dir / "out"
    context_pack = out_root / "harness" / "context-pack.json"
    agent_index = out_root / "harness" / "agent-index.json"
    ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
    worker_root = out_root / "workers" / "worker-001"
    summary = worker_root / "summary" / "competition-run-summary.json"
    report = worker_root / "harness" / "run-worker-report.json"
    write_json(summary, {"final_gate": {"status": "passed"}})
    write_json(report, {"report_kind": "run-worker-report", "worker_id": "worker-001"})
    worker = {
        "worker_id": "worker-001",
        "summary_path": repo_relative(summary),
        "report_path": repo_relative(report),
    }
    context_payload = {
        "run_id": run_id,
        "context_management_contract": {
            "resume_protocol": {
                "checkpoint_backend": "sqlite",
                "ledger_path": repo_relative(ledger),
            },
        },
        "workers": [worker],
    }
    agent_payload = {
        "run_id": run_id,
        "agents_by_worker_id": {
            "worker-001": {
                **worker,
                "isolated_out_root": (
                    isolated_out_root if isolated_out_root is not None else repo_relative(worker_root)
                ),
            }
        },
    }
    write_json(context_pack, context_payload)
    write_json(agent_index, agent_payload)
    write_minimal_context_ledger(
        ledger,
        run_id=ledger_run_id if ledger_run_id is not None else run_id,
        context_pack_path=context_pack,
        context_pack_payload=context_payload,
        agent_index_path=agent_index,
    )
    return {
        "context_payload": context_payload,
        "agent_payload": agent_payload,
        "context_pack": context_pack,
        "agent_index": agent_index,
        "ledger": ledger,
    }


def validate_context_ledger_case(case: dict) -> dict:
    return validator.validate_context_ledger_contract(
        case["context_payload"],
        case["agent_payload"],
        context_path_text=repo_relative(case["context_pack"]),
        agent_path_text=repo_relative(case["agent_index"]),
        repo_root=REPO_ROOT,
    )


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

from pathlib import Path as _C2RPartPath

_C2R_PARTS_DIR = _C2RPartPath(__file__).with_name("_test_validate_judge_entrypoints_parts")
for _C2R_PART_NAME in (
    "class_part_00.py",
    "class_part_01.py",
    "class_part_02.py",
    "class_part_03.py",
    "class_part_04.py",
    "class_part_05.py",
    "class_part_06.py",
    "class_part_07.py",
    "class_part_08.py",
    "class_part_09.py",
):
    _C2R_PART_PATH = _C2R_PARTS_DIR / _C2R_PART_NAME
    exec(
        compile(
            _C2R_PART_PATH.read_text(encoding="utf-8"),
            str(_C2R_PART_PATH),
            "exec",
        ),
        globals(),
    )

class JudgeEntrypointsValidatorTests(
    _JudgeEntrypointsValidatorTestsPart00,
    _JudgeEntrypointsValidatorTestsPart01,
    _JudgeEntrypointsValidatorTestsPart02,
    _JudgeEntrypointsValidatorTestsPart03,
    _JudgeEntrypointsValidatorTestsPart04,
    _JudgeEntrypointsValidatorTestsPart05,
    _JudgeEntrypointsValidatorTestsPart06,
    _JudgeEntrypointsValidatorTestsPart07,
    _JudgeEntrypointsValidatorTestsPart08,
    _JudgeEntrypointsValidatorTestsPart09,
    unittest.TestCase,
):
    pass

del _C2RPartPath, _C2R_PARTS_DIR, _C2R_PART_NAME, _C2R_PART_PATH


if __name__ == "__main__":
    unittest.main()
