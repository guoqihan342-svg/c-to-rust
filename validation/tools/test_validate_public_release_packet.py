import json
import shlex
import tempfile
import unittest
from pathlib import Path
from typing import Callable

import jsonschema

from validation.tools import milestone_release_notes
from validation.tools import test_validate_judge_entrypoints as judge_entrypoint_fixtures
from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools import validate_public_release_packet as packet_validator


REPO_ROOT = Path(__file__).resolve().parents[2]
OPENCODE_RUNTIME_ENV_KEYS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
)


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def write_text_artifact(path: Path, text: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "path": repo_relative(path),
        "status": "present",
        "sha256": judge_validator.sha256_file(path),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bind_json_ref(ref: dict, path: Path, payload: dict) -> None:
    write_json(path, payload)
    ref.update(
        {
            "path": repo_relative(path),
            "status": "present",
            "sha256": judge_validator.sha256_file(path),
        }
    )


def write_published_judge_evidence_index_fixture(root: Path) -> dict:
    payload = judge_entrypoint_fixtures.valid_deterministic_judge_index_payload()
    refs = payload["evidence_artifact_refs"]
    artifact_root = root / "harness" / "judge-evidence-index-artifacts"
    bind_json_ref(
        refs["competition_run_summary"],
        artifact_root / "summary" / "competition-run-summary.json",
        {"report_kind": "competition-run-summary", "status": "passed"},
    )
    bind_json_ref(
        refs["workflow_metrics"],
        artifact_root / "summary" / "workflow-metrics.json",
        {"report_kind": "workflow-metrics", "status": "passed"},
    )
    bind_json_ref(
        refs["worker_plan"],
        artifact_root / "harness" / "plans" / "workers.json",
        {"report_kind": "worker-plan", "status": "passed"},
    )
    bind_json_ref(
        refs["profile"],
        artifact_root / "profile.json",
        {"schema_version": 1, "profile_id": "public-packet-deterministic-fixture", "mode": "deterministic"},
    )
    index_path = root / "harness" / "judge-evidence-index.json"
    write_json(index_path, payload)
    return {
        "artifact_name": "judge_evidence_index",
        "entrypoint_id": "opencode_multi_worker_evaluate_profile",
        "path": repo_relative(index_path),
        "status": "present",
        "sha256": judge_validator.sha256_file(index_path),
    }


def opencode_session_stdout_jsonl(events: list) -> str:
    return "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)


def ensure_opencode_jsonl_session_events(session_payload: dict) -> None:
    events = session_payload.get("session_events")
    if not isinstance(events, list):
        return
    while len(events) < 2:
        events.append({"type": "text", "part": {"text": "fixture-jsonl-keepalive"}})


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
    session_payload["stdout_sha256"] = judge_validator.sha256_file(stdout_path)
    session_payload["stderr_sha256"] = judge_validator.sha256_file(stderr_path)


def write_verified_unsafe_baseline_fixture(path: Path) -> dict:
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
        "report_kind": "c2rust-verified-unsafe-baseline",
        "status": "passed",
        "semantic_pass": True,
        "semantic_claim_source": "verified_unsafe_baseline_gates",
        "generated_draft_semantic_pass": False,
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
        "sha256": judge_validator.sha256_file(path),
        "status": "passed",
        "semantic_pass": True,
        "semantic_claim_source": "verified_unsafe_baseline_gates",
        "generated_draft_semantic_pass": False,
    }


def write_competition_summary_fixture(summary_path: Path) -> tuple[dict, dict]:
    metrics_path = summary_path.parent / "workflow-metrics.json"
    summary = {
        "schema_version": 1,
        "run_id": "opencode-run",
        "proof_class": "local-simulation",
        "profile_id": "huawei-competition-ubuntu-24.04",
        "profile_sha256": "a" * 64,
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
    metrics = {
        "schema_version": 1,
        "run_id": "opencode-run",
        "proof_class": "local-simulation",
        "units_total": 1,
        "units_converged": 1,
        "units_baseline_only": 0,
        "unsafe_reduction": {
            "status": "not_measured",
            "baseline_total_unsafe": None,
            "current_total_unsafe": 0,
            "reduced_by": None,
            "ratio": 0.0,
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
        "fail_closed_count": 0,
        "root_cause_counts": {},
        "wall_clock_seconds": 1,
        "llm_calls": 0,
        "per_unit_statuses": [
            {
                "unit_id": "flashdb/real-fdb-calc-crc32",
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
    write_json(metrics_path, metrics)
    summary["workflow_metrics"] = {
        "path": repo_relative(metrics_path),
        "sha256": judge_validator.sha256_file(metrics_path),
    }
    command_log_path = summary_path.parent / "commands.jsonl"
    command_log_ref = repo_relative(command_log_path)
    command_log_path.parent.mkdir(parents=True, exist_ok=True)
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
        "sha256": judge_validator.sha256_file(command_log_path),
    }
    write_json(summary_path, summary)
    return (
        {"path": repo_relative(summary_path), "status": "present", "sha256": judge_validator.sha256_file(summary_path)},
        {"path": repo_relative(metrics_path), "status": "present", "sha256": judge_validator.sha256_file(metrics_path)},
    )


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
        "env_sha256": judge_validator.sha256_text(json.dumps(digest_payload, sort_keys=True)),
        "semantic_gate": False,
        "evidence_boundary": "runtime env isolation is audit evidence only",
    }


def write_opencode_preflight_fixture(root: Path, *, run_id: str = "opencode-run") -> dict:
    stdout_path = root / "logs" / "opencode-models.stdout.log"
    stderr_path = root / "logs" / "opencode-models.stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_bytes(b"zhipu/GLM-5.1\n")
    stderr_path.write_bytes(b"")
    marker_path = root / "harness" / "opencode-preflight-marker.json"
    handoff_path = root / "harness" / "opencode-preflight-contract.json"
    session_path = root / "logs" / "opencode-preflight-session-evidence.json"
    session_stdout_path = root / "logs" / "opencode-preflight.stdout.log"
    session_stderr_path = root / "logs" / "opencode-preflight.stderr.log"
    runtime_env = opencode_runtime_env_contract(root, scope="preflight")
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
    opencode_prompt = f"Run OpenCode preflight marker for {run_id}"
    opencode_argv = [
        "opencode",
        "run",
        "--dir",
        ".",
        "--format",
        "json",
        "--variant",
        "max",
        "--model",
        "GLM-5.1",
        "--agent",
        "c2rust-migrator",
        opencode_prompt,
    ]
    opencode_command_line = shlex.join(opencode_argv)
    launch_policy = {
        "opencode_agent": "c2rust-migrator",
        "opencode_command": "opencode",
        "opencode_model": "GLM-5.1",
        "opencode_skip_permissions": False,
        "opencode_variant": "max",
    }
    launch_policy_sha256 = judge_validator.sha256_text(json.dumps(launch_policy, sort_keys=True))
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
        handoff_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "runner_kind": "opencode-preflight",
            "expected_marker_path": repo_relative(marker_path),
            "worker_command": marker_command,
            "worker_command_line": marker_command_line,
            "worker_command_sha256": judge_validator.sha256_text(marker_command_line),
            "opencode_argv": opencode_argv,
            "opencode_command_line": opencode_command_line,
            "launch_policy": launch_policy,
            "launch_policy_sha256": launch_policy_sha256,
            "prompt": opencode_prompt,
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
        stdout_path=session_stdout_path,
        stderr_path=session_stderr_path,
    )
    write_json(session_path, session_payload)
    preflight_path = root / "harness" / "opencode-preflight-report.json"
    preflight_payload = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "passed",
        "process_returncode": 0,
        "marker_exists": True,
        "marker_path": repo_relative(marker_path),
        "opencode_run_launched": True,
        "argv": opencode_argv,
        "launch_policy": launch_policy,
        "launch_policy_sha256": launch_policy_sha256,
        "opencode_runtime_env": runtime_env,
        "handoff_contract": {
            "path": repo_relative(handoff_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(handoff_path),
        },
        "opencode_session_evidence": {
            "path": repo_relative(session_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(session_path),
        },
        "contract_verification": {
            "status": "executed",
            "expected_worker_command_line": marker_command_line,
            "expected_summary_path": repo_relative(marker_path),
            "expected_worker_command_sha256": judge_validator.sha256_text(marker_command_line),
            "executed_shell_command_count": 1,
            "executed_shell_commands": [marker_command_line],
            "first_shell_command": marker_command_line,
            "first_shell_tool_name": "bash",
            "first_shell_workdir_status": "repo_root",
            "first_shell_command_matches_worker_command": True,
            "first_shell_workdir_matches_repo_root": True,
            "tools_before_first_shell": [],
            "contract_failure_reason": "",
            "worker_command_seen": True,
            "summary_exists": True,
        },
        "opencode_model_availability": {
            "status": "available",
            "opencode_command": "opencode",
            "required_model": "GLM-5.1",
            "argv": ["opencode", "models"],
            "process_returncode": 0,
            "model_listed": True,
            "stdout_sha256": judge_validator.sha256_file(stdout_path),
            "stderr_sha256": judge_validator.sha256_file(stderr_path),
            "logs": {
                "stdout": repo_relative(stdout_path),
                "stderr": repo_relative(stderr_path),
            },
        },
    }
    write_json(preflight_path, preflight_payload)
    return {
        "status": "passed",
        "required_when_opencode_runtime_enabled": True,
        "preflight_report": {
            "path": repo_relative(preflight_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(preflight_path),
        },
        "run_id": run_id,
        "opencode_command": "opencode",
        "opencode_agent": "c2rust-migrator",
        "opencode_model": "GLM-5.1",
        "opencode_variant": "max",
        "required_model": "GLM-5.1",
        "model_availability_status": "available",
        "model_listed": True,
        "model_probe_argv": ["opencode", "models"],
        "process_returncode": 0,
        "model_probe_logs": {
            "stdout": {
                "path": repo_relative(stdout_path),
                "status": "present",
                "sha256": judge_validator.sha256_file(stdout_path),
            },
            "stderr": {
                "path": repo_relative(stderr_path),
                "status": "present",
                "sha256": judge_validator.sha256_file(stderr_path),
            },
        },
        "contract_status": "executed",
        "marker_exists": True,
        "opencode_run_launched": True,
        "opencode_run_argv_bound": True,
        "opencode_runtime_env": runtime_env,
        "opencode_runtime_env_sha256": runtime_env["env_sha256"],
        "proof_class": "local-simulation",
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "OpenCode preflight proves GLM-5.1 command-contract availability only; "
            "it is not semantic acceptance or translator coverage."
        ),
    }


def write_opencode_safety_transform_attempt_fixture(
    root: Path,
    *,
    max_repair_rounds: int = 5,
) -> dict:
    attempt_path = root / "workers" / "worker-a" / "harness" / "opencode-safety-transform-attempt-1.json"
    evidence_root = attempt_path.parent / "attempt-evidence"
    summary_ref, workflow_metrics_ref = write_competition_summary_fixture(evidence_root / "competition-run-summary.json")
    refs = {
        "summary": summary_ref,
        "workflow_metrics": workflow_metrics_ref,
        "baseline": write_text_artifact(evidence_root / "baseline-unsafe.rs", "unsafe fn baseline() {}\n"),
        "final": write_text_artifact(evidence_root / "final-safe.rs", "fn final_safe() {}\n"),
        "accepted_patch": write_text_artifact(evidence_root / "accepted.patch", "accepted patch\n"),
        "patch_log": write_text_artifact(evidence_root / "patch-log.jsonl", '{"round":1}\n'),
        "oracle": write_text_artifact(evidence_root / "oracle.json", '{"status":"passed"}\n'),
        "schema_diff": write_text_artifact(evidence_root / "schema-diff.json", '{"status":"passed"}\n'),
        "unsafe_scan": write_text_artifact(evidence_root / "unsafe-scan.json", '{"status":"passed"}\n'),
        "baseline_verification": write_verified_unsafe_baseline_fixture(evidence_root / "verified-unsafe-baseline.json"),
    }
    workflow_metrics_path = REPO_ROOT / refs["workflow_metrics"]["path"]
    workflow_metrics = json.loads(workflow_metrics_path.read_text(encoding="utf-8"))
    workflow_metrics["unsafe_reduction"] = {
        "status": "measured",
        "baseline_total_unsafe": 2,
        "current_total_unsafe": 0,
        "reduced_by": 2,
        "ratio": 0.0,
    }
    workflow_metrics["translation_before_after"] = {
        "status": "bound",
        "unit_count": 1,
        "measured_unsafe_unit_count": 1,
        "accepted_patch_unit_count": 1,
        "units": [
            {
                "unit_id": "flashdb/real-fdb-calc-crc32",
                "status": "bound",
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                    "ratio": 0.0,
                },
            }
        ],
    }
    workflow_metrics["per_unit_statuses"][0]["translation_before_after"] = {
        "status": "bound",
        "baseline_verification": refs["baseline_verification"],
        "baseline": refs["baseline"],
        "final": refs["final"],
        "accepted_patch": refs["accepted_patch"],
        "patch_log": refs["patch_log"],
        "oracle_evidence": refs["oracle"],
        "semantic_evidence": {"schema_diff": refs["schema_diff"]},
        "unsafe_scan_evidence": refs["unsafe_scan"],
        "unsafe_reduction": {
            "status": "measured",
            "baseline_total_unsafe": 2,
            "current_total_unsafe": 0,
            "reduced_by": 2,
            "ratio": 0.0,
        },
    }
    write_json(workflow_metrics_path, workflow_metrics)
    summary_path = REPO_ROOT / refs["summary"]["path"]
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_payload["workflow_metrics"]["sha256"] = judge_validator.sha256_file(workflow_metrics_path)
    write_json(summary_path, summary_payload)
    refs["workflow_metrics"]["sha256"] = judge_validator.sha256_file(workflow_metrics_path)
    refs["summary"]["sha256"] = judge_validator.sha256_file(summary_path)
    runtime_env = opencode_runtime_env_contract(root, scope="worker-a-attempt")
    handoff_path = evidence_root / "opencode-handoff-contract.json"
    session_path = evidence_root / "opencode-session-evidence.json"
    session_stdout_path = evidence_root / "opencode.stdout.log"
    session_stderr_path = evidence_root / "opencode.stderr.log"
    worker_command = [
        "python3",
        "-B",
        "-m",
        "validation.tools.opencode_agent_harness",
        "run-worker",
        "--worker-id",
        "worker-a",
        "--summary",
        refs["summary"]["path"],
    ]
    worker_command_line = shlex.join(worker_command)
    opencode_prompt = "Run worker-a safety transform"
    opencode_argv = [
        "opencode",
        "run",
        "--dir",
        ".",
        "--format",
        "json",
        "--variant",
        "max",
        "--model",
        "GLM-5.1",
        "--agent",
        "c2rust-migrator",
        opencode_prompt,
    ]
    opencode_command_line = shlex.join(opencode_argv)
    launch_policy = {
        "opencode_agent": "c2rust-migrator",
        "opencode_command": "opencode",
        "opencode_model": "GLM-5.1",
        "opencode_skip_permissions": False,
        "opencode_variant": "max",
    }
    launch_policy_sha256 = judge_validator.sha256_text(json.dumps(launch_policy, sort_keys=True))
    handoff_payload = {
        "schema_version": 1,
        "runner_kind": "opencode-run",
        "run_id": "opencode-run",
        "worker_id": "worker-a",
        "attempt": 1,
        "launch_policy": launch_policy,
        "launch_policy_sha256": launch_policy_sha256,
        "opencode_runtime_env": runtime_env,
        "worker_command": worker_command,
        "worker_command_line": worker_command_line,
        "worker_command_sha256": judge_validator.sha256_text(worker_command_line),
        "expected_summary_path": refs["summary"]["path"],
        "opencode_argv": opencode_argv,
        "opencode_command_line": opencode_command_line,
        "prompt": opencode_prompt,
    }
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
                            "command": worker_command_line,
                            "workdir": str(REPO_ROOT),
                        }
                    },
                }
            }
        ],
    }
    write_json(handoff_path, handoff_payload)
    bind_opencode_session_raw_logs(
        session_path,
        session_payload,
        stdout_path=session_stdout_path,
        stderr_path=session_stderr_path,
    )
    write_json(session_path, session_payload)
    contract_verification = judge_validator.recompute_opencode_contract_execution(
        session_evidence=session_payload,
        worker_command=worker_command,
        summary_path=summary_path,
        repo_root=REPO_ROOT,
    )
    payload = {
        "schema_version": 1,
        "report_kind": "opencode-safety-transform-attempt",
        "run_id": "opencode-run",
        "worker_id": "worker-a",
        "attempt": 1,
        "status": "accepted",
        "summary": {
            **refs["summary"],
            "final_gate_status": "passed",
        },
        "workflow_metrics": refs["workflow_metrics"],
        "contract_verification": contract_verification,
        "handoff_contract": {
            "path": repo_relative(handoff_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(handoff_path),
        },
        "opencode_session_evidence": {
            "path": repo_relative(session_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(session_path),
        },
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
                "unit_id": "flashdb/real-fdb-calc-crc32",
                "status": "converged",
                "attempt": 1,
                "round_contract": {
                    "single_patch_per_round": True,
                    "max_repair_rounds": max_repair_rounds,
                },
                "patch_evidence": {
                    "baseline": refs["baseline"],
                    "final": refs["final"],
                    "accepted_patch": refs["accepted_patch"],
                    "patch_log": refs["patch_log"],
                },
                "verification_delta": {
                    "baseline_verification": refs["baseline_verification"],
                    "compiled": True,
                    "oracle_evidence": refs["oracle"],
                    "semantic_evidence": {"schema_diff": refs["schema_diff"]},
                    "unsafe_scan_evidence": refs["unsafe_scan"],
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 2,
                        "current_total_unsafe": 0,
                        "reduced_by": 2,
                        "ratio": 0.0,
                    },
                },
                "rounds": [
                    {
                        "round": 1,
                        "single_patch_per_round": True,
                        "patch": refs["accepted_patch"],
                        "patch_log": refs["patch_log"],
                        "oracle_evidence": refs["oracle"],
                        "schema_diff": refs["schema_diff"],
                        "unsafe_scan_evidence": refs["unsafe_scan"],
                        "unsafe_delta": {
                            "status": "measured",
                            "baseline_total_unsafe": 2,
                            "current_total_unsafe": 0,
                            "reduced_by": 2,
                            "ratio": 0.0,
                        },
                    }
                ],
                "accepted_retry_hint": {"status": "not_exercised"},
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
            }
        ],
        "evidence_boundary": "OpenCode chat/session output is audit provenance only.",
    }
    write_json(attempt_path, payload)
    return {
        "artifact_name": "opencode_safety_transform_attempt",
        "path": repo_relative(attempt_path),
        "status": "present",
        "sha256": judge_validator.sha256_file(attempt_path),
    }


def attach_opencode_safety_attempt(packet: dict, attempt_ref: dict) -> None:
    attempt_summary = {
        "path": attempt_ref["path"],
        "sha256": attempt_ref["sha256"],
        "status": "present",
        "artifact_read_status": "passed",
        "attempt_status": "accepted",
        "accepted_retry_hint_status": "not_exercised",
        "accepted_retry_hint_statuses": ["not_exercised"],
        "rollback_ref_count": 0,
        "round_count": 1,
        "max_repair_rounds": 5,
        "unit_count": 1,
    }
    packet["opencode_patch_boundary"]["opencode_safety_transform_attempt"] = attempt_summary
    append_published_artifact_ref(packet, attempt_ref)

    bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
    bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
    write_json(bundle_path, bundle_payload)
    packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)

    notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
    notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
    packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)


def append_published_artifact_ref(packet: dict, ref: dict) -> None:
    refs = packet["publication_manifest"].setdefault("published_artifact_refs", [])
    next_ref = json.loads(json.dumps(ref))
    next_ref.setdefault("entrypoint_id", "opencode_multi_worker_evaluate_profile")
    refs.append(next_ref)
    packet["publication_manifest"]["published_artifact_count"] = len(refs)
    packet["summary"]["published_artifact_ref_status"] = packet_validator.expected_published_artifact_ref_status(
        packet["publication_manifest"]
    )


def packet_preflight_path(packet: dict) -> Path:
    proof = packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]
    return REPO_ROOT / proof["preflight_report"]["path"]


def packet_preflight_marker_command_line(packet: dict) -> str:
    preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
    handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
    handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    return handoff_payload["worker_command_line"]


def rewrite_packet_preflight_session(packet: dict, session_payload: dict) -> None:
    preflight_path = packet_preflight_path(packet)
    preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    session_ref = preflight_payload["opencode_session_evidence"]
    session_path = REPO_ROOT / session_ref["path"]
    existing_session = json.loads(session_path.read_text(encoding="utf-8"))
    if "opencode_runtime_env" not in session_payload and "opencode_runtime_env" in existing_session:
        session_payload["opencode_runtime_env"] = existing_session["opencode_runtime_env"]
    bind_opencode_session_raw_logs(session_path, session_payload)
    write_json(session_path, session_payload)
    session_ref["sha256"] = judge_validator.sha256_file(session_path)
    write_json(preflight_path, preflight_payload)
    packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = (
        judge_validator.sha256_file(preflight_path)
    )


def sync_packet_bound_bundle(packet: dict, *, rebuild_release_notes: bool = True) -> None:
    bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
    bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_payload["opencode_runtime"]["preflight_proof_summary"] = json.loads(
        json.dumps(packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"])
    )
    for field in ("publishability", "competition_host_readiness"):
        if field in packet:
            bundle_payload[field] = json.loads(json.dumps(packet[field]))
    summary = packet.get("summary") if isinstance(packet.get("summary"), dict) else {}
    if isinstance(summary.get("proof_class_rollup"), dict):
        bundle_payload["proof_classes"] = json.loads(json.dumps(summary["proof_class_rollup"]))
        bundle_payload["proof_class_rollup"] = json.loads(json.dumps(summary["proof_class_rollup"]))
    write_json(bundle_path, bundle_payload)
    packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)

    if rebuild_release_notes:
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)


def rewrite_bound_run_report(packet: dict, mutate: Callable[[dict], None]) -> None:
    run_report_path = REPO_ROOT / packet["judge_entrypoints_run_report"]["path"]
    run_report_payload = json.loads(run_report_path.read_text(encoding="utf-8"))
    mutate(run_report_payload)
    write_json(run_report_path, run_report_payload)
    run_report_ref = {
        "path": repo_relative(run_report_path),
        "status": "present",
        "sha256": judge_validator.sha256_file(run_report_path),
    }
    packet["judge_entrypoints_run_report"] = run_report_ref
    packet["publication_manifest"]["judge_entrypoints_run_report"] = json.loads(json.dumps(run_report_ref))
    for ref in packet["publication_manifest"].get("published_artifact_refs", []):
        if isinstance(ref, dict) and ref.get("artifact_name") == "judge_entrypoints_run_report":
            ref.update(json.loads(json.dumps(run_report_ref)))
    bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
    bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_payload["judge_entrypoints_run_report"] = json.loads(json.dumps(run_report_ref))
    bundle_payload["publication_manifest"]["judge_entrypoints_run_report"] = json.loads(json.dumps(run_report_ref))
    for ref in bundle_payload["publication_manifest"].get("published_artifact_refs", []):
        if isinstance(ref, dict) and ref.get("artifact_name") == "judge_entrypoints_run_report":
            ref.update(json.loads(json.dumps(run_report_ref)))
    write_json(bundle_path, bundle_payload)
    packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)


def harness_contract_matrix_fixture() -> list[dict]:
    def row(stage: str, graph_node: str, role: str, artifact: str, validator: str) -> dict:
        return {
            "stage": stage,
            "graph_nodes": [graph_node],
            "roles": [role],
            "artifacts": [artifact],
            "validators": [validator],
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "translation_coverage_numerator": 0,
            "boundary": f"{stage} stage is harness contract evidence only.",
        }

    return [
        row("plan", "load_plan", "planner", "worker_plan", "validate_worker_plan_contract"),
        row("translate", "worker", "worker", "worker_report", "validate_opencode_agent_runtime_contract"),
        row("verify", "merge", "verifier", "workflow_metrics", "validate_competition_summary_entrypoint_contract"),
        row("repair", "repair_retry", "repairer", "repair_hints", "validate_repair_self_heal_contract"),
        row("report", "report", "reporter", "judge_evidence_index", "validate_public_release_packet"),
    ]


def evidence_cost_retention_fixture() -> dict:
    return {
        "report_kind": "evidence-cost-retention-rollup",
        "sources": [
            {
                "source": "fixture-evidence-governance",
                "status": "passed",
                "artifact_count": 3,
                "total_bytes": 120,
                "pipeline_count": 2,
                "runtime_observation_count": 2,
                "runtime_total_duration_ms": 45,
                "runtime_max_duration_ms": 40,
                "retention_classes": {
                    "committed_release": {"file_count": 2, "total_bytes": 100},
                    "diagnostic_only": {"file_count": 1, "total_bytes": 20},
                },
                "policy_compliance": {
                    "policy_tier": "release",
                    "status": "passed",
                    "failed_gates": [],
                },
                "claim_anchor_issue_count": 0,
                "profile_hash_issue_count": 0,
                "diagnostic_host_metadata_count": 0,
            }
        ],
        "rollup": {
            "source_count": 1,
            "artifact_count": 3,
            "total_bytes": 120,
            "pipeline_count": 2,
            "runtime_ms": {
                "observation_count": 2,
                "total": 45,
                "max": 40,
            },
            "retention_classes": {
                "committed_release": {"file_count": 2, "total_bytes": 100},
                "diagnostic_only": {"file_count": 1, "total_bytes": 20},
            },
            "all_sources_passed": True,
            "policy_compliance": {
                "all_sources_policy_passed": True,
                "tier_counts": {"release": 1},
                "failed_gate_counts": {},
            },
            "portability_issue_count": 0,
            "diagnostic_host_metadata_count": 0,
        },
        "boundary": "Evidence cost and retention metrics are review-only and not semantic acceptance.",
    }


def c2rust_baseline_milestone_rollup_fixture() -> dict:
    return {
        "report_kind": "c2rust-baseline-milestone-rollup",
        "status": "observed",
        "source_report_count": 2,
        "unique_evidence_root_count": 1,
        "unique_manifest_count": 2,
        "generated_output_count": 0,
        "skipped_without_output_count": 2,
        "compile_attempted_count": 0,
        "compile_passed_count": 0,
        "compile_semantic_pass_count": 0,
        "status_counts": {"skipped": 2},
        "output_status_counts": {"missing": 2},
        "compile_status_counts": {"missing": 2},
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": "C2Rust baseline status is candidate context only.",
    }


def comparison_row_fixture(status: str, evidence_role: str, boundary: str, **extra: object) -> dict:
    return {
        "status": status,
        "evidence_role": evidence_role,
        "semantic_acceptance_claimed": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": boundary,
        **extra,
    }


def valid_packet(root: Path) -> dict:
    run_report_path = root / "summary" / "judge-entrypoints-run-report.json"
    readiness = write_text_artifact(root / "summary" / "judge-entrypoints-readiness.json", "{}\n")
    bundle_path = root / "summary" / "judge-milestone-bundle.json"
    opencode_preflight_proof = write_opencode_preflight_fixture(root)
    config_bundle_manifest = REPO_ROOT / "config" / "competition-env" / "bundle-manifest.json"
    config_bundle_payload = json.loads(config_bundle_manifest.read_text(encoding="utf-8"))
    config_bundle_ref = {
        "path": repo_relative(config_bundle_manifest),
        "status": "present",
        "sha256": judge_validator.sha256_file(config_bundle_manifest),
    }
    archive_files = {
        "config/competition-env/bundle-manifest.json": {
            **config_bundle_ref,
            "role": "competition-env-bundle-manifest",
            "bytes": config_bundle_manifest.stat().st_size,
        }
    }
    for manifest_file in config_bundle_payload["files"]:
        path_text = manifest_file["path"]
        path = REPO_ROOT / path_text
        archive_files[path_text] = {
            "path": path_text,
            "role": manifest_file["role"],
            "status": "present",
            "sha256": judge_validator.sha256_file(path),
            "bytes": path.stat().st_size,
        }
    competition_config_archive = {
        "report_kind": "competition-config-archive",
        "status": "present",
        "root": "config/competition-env",
        "file_count": len(archive_files),
        "files": archive_files,
        "external_ref_count": len(judge_validator.COMPETITION_ENV_EXTERNAL_REF_ROLES),
        "external_refs": {
            path: {
                "path": path,
                "role": role,
                "status": "present",
                "sha256": judge_validator.sha256_file(REPO_ROOT / path),
                "bytes": (REPO_ROOT / path).stat().st_size,
            }
            for path, role in judge_validator.COMPETITION_ENV_EXTERNAL_REF_ROLES.items()
        },
        "claim_boundary": {
            "semantic_gate": False,
            "archive_is_semantic_gate": False,
        },
    }
    archive_manifest_path = root / "summary" / "competition-config-archive" / "manifest.json"
    archive_manifest_payload = json.loads(json.dumps(competition_config_archive))
    write_json(archive_manifest_path, archive_manifest_payload)
    archive_manifest_ref = {
        "path": repo_relative(archive_manifest_path),
        "status": "present",
        "sha256": judge_validator.sha256_file(archive_manifest_path),
    }
    competition_config_archive["materialized_manifest"] = archive_manifest_ref
    readiness_summary = {
        "all_entrypoints_executed": True,
        "executed_count": 4,
        "configured_count": 4,
        "validation_status": "passed",
    }
    run_report_payload = {
        "status": "passed",
        "entrypoint_count": 4,
        "entrypoints": [
            {
                "id": "opencode_multi_worker_evaluate_profile",
                "status": "passed",
                "proof_class": "local-simulation",
                "run_id": "fixture-run",
                "competition_exact_host_attested": False,
            }
        ],
        "validation": {
            "status": "passed",
            "proof_class_contract": {
                "status": "passed",
                "entrypoints": {
                    "opencode_multi_worker_evaluate_profile": "local-simulation",
                },
            },
        },
        "summary": {"readiness": readiness_summary},
        "competition_config_archive": competition_config_archive,
    }
    write_json(run_report_path, run_report_payload)
    run_report = {
        "path": repo_relative(run_report_path),
        "status": "present",
        "sha256": judge_validator.sha256_file(run_report_path),
    }
    bundle_self_ref = {
        "path": repo_relative(bundle_path),
        "status": "self",
        "hash_boundary": "self-hash-bound-after-write",
    }
    repo_commit_ref = {
        "status": "present",
        "commit": "1" * 40,
    }
    publication_manifest = {
        "report_kind": "publication-manifest",
        "bundle_version": 1,
        "publication_scope": "internal_preview_full",
        "source_commit": repo_commit_ref,
        "repo_commit": json.loads(json.dumps(repo_commit_ref)),
        "target_source_pin": {
            "status": "passed",
            "target_id": "flashdb",
            "repository": "https://gitcode.com/xwxf/FlashDB.git",
            "branch": "competition",
            "canonical_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        },
        "release_tag_readiness": {
            "report_kind": "release-tag-readiness",
            "status": "not_tagged",
            "tag_name": None,
            "tag_target_commit": None,
            "repo_commit": repo_commit_ref["commit"],
            "tag_matches_repo_commit": False,
            "remote_release_notes_status": "not_published",
            "external_review_record_status": "not_recorded",
            "external_milestone_claim_ready": False,
            "publishability_status": "internal_preview",
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "boundary": (
                "Tag, remote release notes, and external review records are publication readiness evidence only. "
                "They do not create semantic acceptance or translator-generated coverage."
            ),
        },
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "judge_milestone_bundle": bundle_self_ref,
        "judge_config": {
            "path": "config/competition-env/judge-entrypoints/flashdb-harness.json",
            "status": "present",
        },
        "competition_config_archive": {
            "report_kind": "competition-config-archive",
            "status": "present",
            "root": "config/competition-env",
            "file_count": len(archive_files),
            "bundle_manifest": config_bundle_ref,
            "materialized_manifest": archive_manifest_ref,
            "external_ref_count": len(competition_config_archive["external_refs"]),
            "external_refs": {
                path: {
                    "path": ref["path"],
                    "role": ref["role"],
                    "status": ref["status"],
                    "sha256": ref["sha256"],
                }
                for path, ref in competition_config_archive["external_refs"].items()
            },
        },
        "supported_subset": {
            "claims": ["public packet validator fixture"],
        },
        "known_non_goals": ["semantic acceptance", "semantic translation gate"],
        "claim_boundary": {
            "semantic_gate": False,
            "publication_manifest_is_semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }
    publication_manifest["published_entrypoints"] = [
        {
            "id": "opencode_multi_worker_evaluate_profile",
            "status": "passed",
            "proof_class": "local-simulation",
            "run_id": "fixture-run",
        }
    ]
    judge_evidence_index_ref = write_published_judge_evidence_index_fixture(root)
    publication_manifest["published_artifact_refs"] = [
        {
            "artifact_name": "judge_entrypoints_run_report",
            "entrypoint_id": "opencode_multi_worker_evaluate_profile",
            **json.loads(json.dumps(run_report)),
        },
        judge_evidence_index_ref,
    ]
    publication_manifest["published_artifact_count"] = len(publication_manifest["published_artifact_refs"])
    known_gaps = [{"gap_id": "competition-exact-not-run", "status": "open"}]
    bundle_must_not_claim = [
        "accepted_evidence_is_not_translator_generated_coverage",
        "blocked_repairs_are_not_translation_success",
        "before_after_exhibit_is_not_new_semantic_gate",
        "bundle_status_passed_is_not_project_level_translation_success",
        "local_simulation_is_not_competition_exact",
        "bundle_status_is_not_project_level_translation_success",
    ]
    packet_must_not_claim = [*bundle_must_not_claim, "public_release_packet_is_not_semantic_gate"]
    reproduction_commands = {
        "run_judge_entrypoints": "python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out/summary/judge-entrypoints-run-report.json",
        "build_bundle": "python3 -B -m validation.tools.judge_milestone_bundle",
        "entrypoints": [
            {
                "id": "opencode_multi_worker_evaluate_profile",
                "command": "python3 -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/profiles/flashdb-opencode-local-simulation.json",
            }
        ],
    }
    publication_manifest["reproduction_commands"] = reproduction_commands
    publication_manifest["known_gaps"] = known_gaps
    publication_manifest["must_not_claim"] = bundle_must_not_claim
    before_after_repair_exhibit = {
        "report_kind": "before-after-repair-exhibit-rollup",
        "sources": [
            {
                "entrypoint_id": "before_after_judge_demo",
                "before_after_units": [
                    {
                        "unit_id": "flashdb/real-fdb-calc-crc32",
                        "status": "converged",
                        "baseline_verification": {
                            "path": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-verified-unsafe-baseline.json",
                            "status": "passed",
                            "sha256": "1" * 64,
                            "semantic_pass": True,
                            "semantic_claim_source": "verified_unsafe_baseline_gates",
                            "generated_draft_semantic_pass": False,
                        },
                        "accepted_patch": {
                            "path": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/accepted-safe.patch",
                            "status": "accepted",
                            "sha256": "2" * 64,
                        },
                        "unsafe_reduction": {
                            "status": "measured",
                            "baseline_total_unsafe": 2,
                            "current_total_unsafe": 0,
                            "reduced_by": 2,
                        },
                        "patch_origin": {
                            "source": "accepted_safe_evidence",
                            "accepted_patch_bound": True,
                            "opencode_session_bound": False,
                            "repair_history_bound": True,
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                            "semantic_gate": False,
                            "translation_coverage_numerator": 0,
                        },
                        "safety_loop_provenance": {
                            "status": "accepted_evidence_bound",
                            "patch_source": "accepted_safe_evidence",
                            "unsafe_delta": {
                                "status": "measured",
                                "baseline_total_unsafe": 2,
                                "current_total_unsafe": 0,
                                "reduced_by": 2,
                            },
                            "opencode_session_bound": False,
                            "repair_history_bound": True,
                            "repair_rounds": 1,
                            "auto_recovered": True,
                            "semantic_gate": False,
                            "translation_coverage_numerator": 0,
                        },
                    }
                ],
            }
        ],
        "rollup": {
            "source_count": 1,
            "bound_unit_count": 1,
            "measured_unsafe_unit_count": 1,
            "accepted_patch_unit_count": 1,
            "verified_repair_source_count": 1,
            "observed_repair_unit_count": 1,
            "auto_recovered_unit_count": 1,
            "verified_baseline_unit_count": 1,
            "missing_verified_baseline_unit_count": 0,
            "all_units_verified_baseline_bound": True,
            "rollback_evidence_count": 1,
            "repair_round_cap": 5,
            "unsafe_reduced_by": 2,
            "unsafe_reduction": {
                "status": "measured",
                "baseline_total_unsafe": 2,
                "current_total_unsafe": 0,
                "reduced_by": 2,
            },
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": "Before/after repair exhibit is a review rollup, not a semantic gate.",
    }
    claim_scope = {
        "external_review_index_ready": True,
        "semantic_acceptance_ready": False,
        "competition_exact_ready": False,
        "translator_generated_coverage_ready": False,
    }
    unsafe_reduction = {
        "status": "measured",
        "baseline_total_unsafe": 2,
        "current_total_unsafe": 0,
        "reduced_by": 2,
    }
    c2rust_baseline_rollup = c2rust_baseline_milestone_rollup_fixture()
    blocked_repairs_rollup = {
        "report_kind": "blocked-repairs-rollup",
        "sources": [],
        "rollup": {
            "source_count": 0,
            "slice_count": 0,
            "recorded_source_count": 0,
            "blocked_repair_count": 0,
            "human_action_required_count": 0,
            "status_counts": {},
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
            "boundary": "No blocked repair is counted as translation success in this fixture.",
        },
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": "Blocked repairs are review context only.",
    }
    repair_activity = {
        "source_count": 1,
        "observed_source_count": 1,
        "repair_history_unit_count": 1,
        "auto_recovered_unit_count": 1,
        "avg_repair_rounds": 1.0,
        "auto_recovery_rate": 1.0,
        "human_interventions": 0,
        "boundary": "Workflow metrics are review-only and not semantic acceptance.",
    }
    bundle_payload = {
        "schema_version": 1,
        "report_kind": "judge-milestone-bundle",
        "status": "passed",
        "blockers": [],
        "summary": {
            "report_kind": "judge-milestone-bundle-summary",
            "external_milestone_claim_ready": False,
            "claim_scope": claim_scope,
            "blockers": [],
            "readiness": {
                "all_entrypoints_executed": True,
                "executed_count": 4,
                "configured_count": 4,
                "validation_status": "passed",
            },
        },
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "bundle_is_semantic_gate": False,
            "source_semantic_gate": False,
        },
        "claim_scope": claim_scope,
        "publishability": {
            "status": "internal_preview",
            "scope": "full",
            "publication_scope": "internal_preview_full",
            "external_milestone_claim_ready": False,
            "external_milestone": False,
            "blocker_count": 0,
            "blockers": [],
            "all_entrypoints_run_publishable": True,
            "focused_run": False,
            "competition_exact_publishable": False,
            "required_agent_tool": "opencode",
            "required_agent": "c2rust-migrator",
            "required_model": "GLM-5.1",
            "required_variant": "max",
            "opencode_glm51_required": True,
            "opencode_glm51_preflight_status": "passed",
            "opencode_glm51_publishable": True,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "target_artifacts_regenerable": True,
        },
        "competition_host_readiness": {
            "report_kind": "competition-host-readiness",
            "status": "blocked",
            "required_agent_tool": "opencode",
            "required_agent": "c2rust-migrator",
            "required_model": "GLM-5.1",
            "required_variant": "max",
            "required_proof_class": "competition-exact",
            "actual_highest_proof_class": "local-simulation",
            "all_entrypoints_run_publishable": True,
            "all_entrypoints_competition_exact": False,
            "competition_exact_host_verified": False,
            "opencode_glm51_preflight_status": "passed",
            "opencode_glm51_publishable": True,
            "external_milestone_claim_ready": False,
            "missing_requirements": [
                "all_entrypoints_competition_exact",
                "competition_exact_host_verified",
                "external_milestone_claim_ready",
            ],
            "blocker_count": 3,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "boundary": "Competition host readiness is an H9 launch contract, not semantic acceptance.",
        },
        "proof_classes": packet_validator.expected_proof_class_rollup_from_run_report(run_report_payload),
        "semantic_evidence_rollup": {
            "accepted_evidence_semantic_pass_count": 1,
            "translator_generated_semantic_pass_count": 0,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "source_generated_draft_semantic_pass": False,
            "source_translation_coverage_numerator": 0,
            "accepted_evidence_counts_as_translator_coverage": False,
        },
        "core_translation_quality": {
            "report_kind": "core-translation-quality-rollup",
            "sources": [],
            "final_gate_statuses": ["passed"],
            "semantic_pass_count": 1,
            "translation_coverage_numerator": 0,
            "generated_draft_semantic_pass": False,
            "unsafe_reduction": unsafe_reduction,
        },
        "blocked_repairs_rollup": blocked_repairs_rollup,
        "harness_architecture_summary": {
            "report_kind": "harness-architecture-summary",
            "sources": [],
            "graph_runtime": "opencode-harness-langgraph-inspired",
            "graph_nodes": ["load_plan", "worker", "merge", "repair_retry", "report"],
            "worker_count": 1,
            "repair_round_cap": 5,
            "roles": ["planner", "worker", "verifier", "repairer", "reporter"],
            "checkpoint_backend": "sqlite",
            "contract_matrix": harness_contract_matrix_fixture(),
            "chat_output_is_evidence": False,
            "semantic_gate": False,
            "rollup": {
                "source_count": 1,
                "worker_count": 1,
                "repair_round_cap": 5,
                "roles": ["planner", "worker", "verifier", "repairer", "reporter"],
            }
        },
        "route_governance_metrics": {
            "report_kind": "route-governance-metrics-rollup",
            "sources": [],
            "rollup": {
                "source_count": 1,
                "translation_coverage_numerator": 0,
                "accepted_evidence_semantic_pass_count": 1,
                "tracked_route_decision_artifacts": 1,
                "tracked_slice_gate_contexts": 1,
                "s2_workflow_run_count": 1,
                "s2_unsafe_reduction": unsafe_reduction,
                "c2rust_baseline": c2rust_baseline_rollup,
                "all_retention_policies_present": True,
                "all_target_artifacts_reproducible": True,
            },
            "boundary": "Route governance metrics do not create semantic acceptance.",
        },
        "evidence_cost_retention": evidence_cost_retention_fixture(),
        "entrypoints": [
            {
                "id": "opencode_multi_worker_evaluate_profile",
                "status": "passed",
                "proof_class": "local-simulation",
            }
        ],
        "workflow_metrics": {
            "report_kind": "workflow-metrics-rollup",
            "sources": [],
            "rollup": {
                "repair_activity": repair_activity,
            }
        },
        "unsafe_reduction_scope": {
            "scope": "all",
            "all_sources_measured": True,
            "measured_units": 1,
            "total_units": 1,
        },
        "progress_delta_ledger": {
            "report_kind": "progress-delta-ledger",
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "capability_delta": {
                "ledger_count": 1,
                "delta_count": 1,
                "translator_generated_semantic_pass_count": 0,
                "accepted_evidence_semantic_pass_count": 1,
            },
            "governance_delta": {
                "delta_count": 2,
                "verification_command_count": 3,
                "route_decision_artifacts": 1,
                "slice_gate_contexts": 1,
                "blocked_callee_count": 0,
            },
            "workflow_delta": {
                "workflow_source_count": 1,
                "workflow_units_total": 1,
                "workflow_units_converged": 1,
                "repair_history_unit_count": 1,
                "observed_repair_unit_count": 1,
                "auto_recovered_unit_count": 1,
                "rollback_evidence_count": 1,
                "before_after_repair_source_count": 1,
                "repair_delta_source_count": 1,
                "human_interventions": 0,
                "llm_calls": 1,
            },
            "boundary": "Progress deltas are copied from the bound bundle for review only.",
        },
        "quantitative_evaluation": {
            "report_kind": "quantitative-evaluation-scorecard",
            "evaluation_scope": "bounded-mvp",
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "project_slice_counts": {
                "entrypoint_count": 4,
                "workflow_source_count": 1,
                "workflow_units_total": 1,
                "workflow_units_converged": 1,
                "before_after_bound_unit_count": 1,
                "tracked_route_decision_artifacts": 1,
                "tracked_slice_gate_contexts": 1,
            },
            "outcome_counts": {
                "accepted_evidence_semantic_pass_count": 1,
                "translator_generated_semantic_pass_count": 0,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "blocked_repair_count": 0,
                "human_interventions": 0,
            },
            "unsafe_reduction": {
                **unsafe_reduction,
                "scope": "all",
                "all_sources_measured": True,
                "measured_units": 1,
                "total_units": 1,
            },
            "repair_activity": repair_activity,
            "self_heal_classification": {
                "report_kind": "self-heal-classification",
                "source": "blocked_repairs_rollup",
                "status": "none",
                "blocked_repair_count": 0,
                "human_action_required_count": 0,
                "status_counts": {},
                "blocked_reason_counts": {},
                "ir_feature_gap_kinds": {},
                "forbidden_change_counts": {},
                "source_span_kind_counts": {},
                "route_counts": {},
                "next_action_counts": {},
                "smallest_next_test_kind_counts": {},
                "next_action_count": 0,
                "sample_next_action_limit": 5,
                "sample_next_actions": [],
                "semantic_gate": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "boundary": "Self-heal classification is judge-facing repair context only.",
            },
            "baseline_comparison": {
                "raw_c2rust": {
                    **comparison_row_fixture(
                        "manifest_status_observed",
                        "baseline_or_candidate_context_only",
                        "Raw C2Rust baseline manifests are candidate context only.",
                    ),
                    "c2rust_baseline_rollup": c2rust_baseline_rollup,
                },
                "c2rust_repair": comparison_row_fixture(
                    "not_run",
                    "not_semantic_acceptance",
                    "C2Rust repair is not a semantic acceptance row in this fixture.",
                ),
                "typed_ir_route": comparison_row_fixture(
                    "observed",
                    "route_governance_only",
                    "Typed IR route data is diagnostic and not semantic acceptance.",
                    tracked_route_decision_artifacts=1,
                ),
                "opencode_llm_worker": comparison_row_fixture(
                    "preflight_only",
                    "command_contract_audit_only",
                    "OpenCode worker output is not semantic evidence without oracle gates.",
                    chat_output_is_evidence=False,
                ),
                "handwritten_reference": comparison_row_fixture(
                    "accepted_evidence_bound",
                    "accepted_reference_evidence",
                    "Accepted reference evidence is not translator-generated coverage.",
                    counts_as_translator_generated_coverage=False,
                ),
            },
            "claim_boundary": {
                "semantic_gate": False,
                "scorecard_is_semantic_gate": False,
                "baseline_comparison_is_semantic_acceptance": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
        },
        "opencode_runtime": {
            "report_kind": "opencode-runtime-rollup",
            "enabled_entrypoint_count": 1,
            "worker_count": 1,
            "all_contracts_executed": True,
            "chat_output_is_evidence_false": True,
            "semantic_gate_false": True,
            "preflight_proof_summary": opencode_preflight_proof,
        },
        "opencode_evidence_policy": {
            "enabled": True,
            "boundary_fields_explicit": True,
            "chat_output_is_evidence_false": True,
            "semantic_gate_false": True,
            "session_evidence_role": "command_contract_audit_only",
            "logs_evidence_role": "diagnostic_only",
            "semantic_gate": False,
        },
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "publication_manifest": publication_manifest,
        "before_after_repair_exhibit": before_after_repair_exhibit,
        "known_gaps": known_gaps,
        "must_not_claim": bundle_must_not_claim,
        "reproduction_commands": reproduction_commands,
        "retention_policy": {
            "report_kind": "milestone-retention-policy",
            "bundle_role": "external-review-index",
            "target_artifacts": ["summary/judge-milestone-bundle.json"],
            "committed_manifests": ["validation/judge-milestone-bundle.schema.json"],
            "claim_boundary": {
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
                "boundary": "Retention policy is evidence packaging only.",
            },
        },
    }
    bundle_payload["proof_class_rollup"] = bundle_payload["proof_classes"]
    write_json(bundle_path, bundle_payload)
    notes = write_text_artifact(
        root / "summary" / "milestone-release-notes.md",
        milestone_release_notes.build_release_notes(bundle_payload),
    )
    bundle = {
        "path": repo_relative(bundle_path),
        "status": "present",
        "sha256": judge_validator.sha256_file(bundle_path),
    }
    return {
        "schema_version": 1,
        "report_kind": "public-release-packet",
        "status": "passed",
        "summary": {
            "entrypoint_count": 4,
            "publication_scope": "internal_preview_full",
            "readiness": readiness_summary,
            "blockers": [],
            "published_artifact_ref_status": {
                **packet_validator.expected_published_artifact_ref_status(publication_manifest),
            },
            "proof_class_rollup": bundle_payload["proof_class_rollup"],
            "workflow_metrics": packet_validator.expected_workflow_metrics_summary(bundle_payload),
            "progress_delta_ledger": bundle_payload["progress_delta_ledger"],
        },
        "claim_boundary": {
            "semantic_gate": False,
            "packet_is_semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "boundary": "packet index only",
        },
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "judge_milestone_bundle": bundle,
        "milestone_release_notes": notes,
        "competition_config_archive": competition_config_archive,
        "publication_manifest": publication_manifest,
        "publishability": bundle_payload["publishability"],
        "competition_host_readiness": bundle_payload["competition_host_readiness"],
        "harness_architecture_summary": bundle_payload["harness_architecture_summary"],
        "evidence_cost_retention": bundle_payload["evidence_cost_retention"],
        "before_after_repair_exhibit": before_after_repair_exhibit,
        "opencode_patch_boundary": {
            "report_kind": "opencode-patch-boundary",
            "opencode_runtime_enabled": True,
            "before_after_patch_sources": ["accepted_safe_evidence"],
            "before_after_opencode_session_bound_count": 0,
            "opencode_safety_transform_attempt": {"status": "absent"},
            "opencode_preflight_proof_summary": opencode_preflight_proof,
            "chat_output_is_evidence": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "boundary": "OpenCode chat output is not semantic evidence.",
        },
        "quantitative_evaluation": bundle_payload["quantitative_evaluation"],
        "progress_delta_ledger": bundle_payload["progress_delta_ledger"],
        "known_gaps": known_gaps,
        "must_not_claim": packet_must_not_claim,
        "reproduction_commands": reproduction_commands,
    }


class PublicReleasePacketValidatorTests(unittest.TestCase):
    def test_validate_packet_binds_hashes_and_claim_boundary(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["packet"]["path"], repo_relative(packet_path))
        self.assertEqual(result["artifact_refs"]["checked_count"], 4)
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertEqual(result["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(
            packet["before_after_repair_exhibit"]["sources"][0]["before_after_units"][0]["patch_origin"]["source"],
            "accepted_safe_evidence",
        )
        self.assertFalse(packet["before_after_repair_exhibit"]["semantic_gate"])
        self.assertEqual(packet["before_after_repair_exhibit"]["translation_coverage_numerator"], 0)
        self.assertEqual(packet["publishability"]["status"], "internal_preview")
        self.assertFalse(packet["publishability"]["competition_exact_publishable"])
        self.assertEqual(packet["publishability"]["required_agent"], "c2rust-migrator")
        self.assertEqual(packet["publishability"]["required_model"], "GLM-5.1")
        self.assertEqual(packet["publishability"]["required_variant"], "max")
        self.assertEqual(packet["competition_host_readiness"]["status"], "blocked")
        self.assertEqual(packet["competition_host_readiness"]["required_agent"], "c2rust-migrator")
        self.assertEqual(packet["competition_host_readiness"]["required_model"], "GLM-5.1")
        self.assertEqual(packet["competition_host_readiness"]["required_variant"], "max")
        self.assertEqual(packet["competition_host_readiness"]["required_proof_class"], "competition-exact")
        self.assertFalse(packet["competition_host_readiness"]["competition_exact_host_verified"])
        self.assertIn(
            "competition_exact_host_verified",
            packet["competition_host_readiness"]["missing_requirements"],
        )
        self.assertEqual(
            [entry["stage"] for entry in packet["harness_architecture_summary"]["contract_matrix"]],
            ["plan", "translate", "verify", "repair", "report"],
        )
        self.assertFalse(packet["harness_architecture_summary"]["semantic_gate"])
        self.assertEqual(packet["evidence_cost_retention"]["rollup"]["artifact_count"], 3)
        self.assertEqual(packet["evidence_cost_retention"]["rollup"]["total_bytes"], 120)
        notes_text = (REPO_ROOT / packet["milestone_release_notes"]["path"]).read_text(encoding="utf-8")
        self.assertIn("| raw C2Rust | manifest_status_observed | no | 0 | 2 manifests / 2 sources / 0 compile-pass |", notes_text)

    def test_validate_packet_rejects_passed_bundle_without_published_artifact_refs(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-empty-published-refs-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))

        packet["publication_manifest"]["published_artifact_refs"] = []
        packet["publication_manifest"]["published_artifact_count"] = 0
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        packet["summary"]["published_artifact_ref_status"] = packet_validator.expected_published_artifact_ref_status(
            packet["publication_manifest"]
        )
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("passed bundle must publish at least one hash-bound artifact ref" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_passed_bundle_without_published_judge_evidence_index(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-no-judge-index-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        refs = [
            ref
            for ref in packet["publication_manifest"]["published_artifact_refs"]
            if ref.get("artifact_name") != "judge_evidence_index"
        ]
        packet["publication_manifest"]["published_artifact_refs"] = refs
        packet["publication_manifest"]["published_artifact_count"] = len(refs)
        packet["summary"]["published_artifact_ref_status"] = packet_validator.expected_published_artifact_ref_status(
            packet["publication_manifest"]
        )
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("passed bundle must publish a present judge_evidence_index artifact ref" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_config_archive_drift_from_bound_run_report(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)

        run_report_path = REPO_ROOT / packet["judge_entrypoints_run_report"]["path"]
        run_report_payload = json.loads(run_report_path.read_text(encoding="utf-8"))
        drifted_archive = json.loads(json.dumps(packet["competition_config_archive"]))
        drifted_archive["external_ref_count"] += 1
        run_report_payload["competition_config_archive"] = drifted_archive
        write_json(run_report_path, run_report_payload)
        run_report_ref = {
            "path": repo_relative(run_report_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(run_report_path),
        }
        packet["judge_entrypoints_run_report"] = run_report_ref
        packet["publication_manifest"]["judge_entrypoints_run_report"] = run_report_ref
        for ref in packet["publication_manifest"]["published_artifact_refs"]:
            if ref.get("artifact_name") == "judge_entrypoints_run_report":
                ref.update(run_report_ref)

        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["judge_entrypoints_run_report"] = run_report_ref
        bundle_payload["publication_manifest"]["judge_entrypoints_run_report"] = run_report_ref
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)

        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_config_archive must match judge_entrypoints_run_report.competition_config_archive" in error
                for error in result["errors"]
            )
        )

    def test_public_release_packet_schema_requires_summary_blockers(self) -> None:
        schema = json.loads((REPO_ROOT / "validation" / "public-release-packet.schema.json").read_text(encoding="utf-8"))
        self.assertIn("blockers", schema["properties"]["summary"]["required"])
        self.assertEqual(schema["properties"]["summary"]["properties"]["blockers"]["items"]["type"], "string")
        self.assertIn("published_artifact_ref_status", schema["properties"]["summary"]["required"])
        ref_status = schema["properties"]["summary"]["properties"]["published_artifact_ref_status"]
        self.assertEqual(ref_status["properties"]["semantic_gate"]["const"], False)
        self.assertEqual(ref_status["properties"]["translation_coverage_numerator"]["const"], 0)
        self.assertIn("harness_architecture_summary", schema["required"])
        self.assertIn("evidence_cost_retention", schema["required"])
        self.assertIn("competition_host_readiness", schema["required"])
        publishability = schema["properties"]["publishability"]
        self.assertIn("required_variant", publishability["required"])
        self.assertEqual(publishability["properties"]["required_variant"]["const"], "max")
        host_readiness = schema["properties"]["competition_host_readiness"]
        self.assertEqual(host_readiness["$ref"], "#/$defs/competitionHostReadiness")
        host_readiness = schema["$defs"]["competitionHostReadiness"]
        self.assertEqual(host_readiness["properties"]["report_kind"]["const"], "competition-host-readiness")
        self.assertEqual(host_readiness["properties"]["required_agent_tool"]["const"], "opencode")
        self.assertEqual(host_readiness["properties"]["required_agent"]["const"], "c2rust-migrator")
        self.assertEqual(host_readiness["properties"]["required_model"]["const"], "GLM-5.1")
        self.assertEqual(host_readiness["properties"]["required_variant"]["const"], "max")
        self.assertEqual(host_readiness["properties"]["required_proof_class"]["const"], "competition-exact")
        self.assertEqual(host_readiness["properties"]["semantic_gate"]["const"], False)
        self.assertEqual(host_readiness["properties"]["translation_coverage_numerator"]["const"], 0)
        self.assertIn("release_tag_readiness", schema["properties"]["publication_manifest"]["required"])
        tag_readiness = schema["properties"]["publication_manifest"]["properties"]["release_tag_readiness"]
        self.assertEqual(tag_readiness["$ref"], "#/$defs/releaseTagReadiness")
        tag_readiness = schema["$defs"]["releaseTagReadiness"]
        self.assertEqual(tag_readiness["properties"]["report_kind"]["const"], "release-tag-readiness")
        self.assertEqual(tag_readiness["properties"]["semantic_gate"]["const"], False)
        self.assertEqual(tag_readiness["properties"]["translation_coverage_numerator"]["const"], 0)
        preflight_summary = schema["$defs"]["opencodePreflightProofSummary"]
        self.assertIn("opencode_agent", preflight_summary["required"])
        self.assertIn("opencode_variant", preflight_summary["required"])
        self.assertEqual(preflight_summary["properties"]["opencode_agent"]["const"], "c2rust-migrator")
        self.assertEqual(preflight_summary["properties"]["opencode_variant"]["const"], "max")
        before_after_rollup = schema["properties"]["before_after_repair_exhibit"]["properties"]["rollup"]
        self.assertIn("verified_baseline_unit_count", before_after_rollup["required"])
        self.assertIn("missing_verified_baseline_unit_count", before_after_rollup["required"])
        self.assertIn("all_units_verified_baseline_bound", before_after_rollup["required"])

    def test_public_release_packet_schema_requires_before_after_verified_baseline_rollup(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-baseline-rollup-", dir=REPO_ROOT / "target"))
        packet = valid_packet(temp_dir)
        schema = judge_validator.load_json(packet_validator.PACKET_SCHEMA)

        for field in (
            "verified_baseline_unit_count",
            "missing_verified_baseline_unit_count",
            "all_units_verified_baseline_bound",
        ):
            with self.subTest(field=field):
                missing_rollup = json.loads(json.dumps(packet))
                missing_rollup["before_after_repair_exhibit"]["rollup"].pop(field)
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(missing_rollup, schema)

        invalid_rollup = json.loads(json.dumps(packet))
        invalid_rollup["before_after_repair_exhibit"]["rollup"]["all_units_verified_baseline_bound"] = "true"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid_rollup, schema)

    def test_validate_packet_rejects_harness_contract_matrix_missing_report_stage(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-harness-matrix-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["harness_architecture_summary"]["contract_matrix"] = [
            entry
            for entry in packet["harness_architecture_summary"]["contract_matrix"]
            if entry["stage"] != "report"
        ]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("harness_architecture_summary" in error and "contract_matrix" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_evidence_cost_retention_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-evidence-cost-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["evidence_cost_retention"]["rollup"]["total_bytes"] += 1
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "evidence_cost_retention must match judge_milestone_bundle.evidence_cost_retention" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_requires_opencode_patch_boundary(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-boundary-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet.pop("opencode_patch_boundary")
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("opencode_patch_boundary" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_requires_glm_preflight_proof_when_opencode_runtime_enabled(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-preflight-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"].pop("opencode_preflight_proof_summary")
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_preflight_proof_summary" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_non_glm_preflight_proof(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-non-glm-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["required_model"] = "gpt-5.1"
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("required_model must be GLM-5.1" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_rejects_wrong_opencode_agent_in_preflight_proof(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-agent-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["opencode_agent"] = "general"
        sync_packet_bound_bundle(packet, rebuild_release_notes=False)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_agent" in error and "c2rust-migrator" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_wrong_opencode_variant_in_preflight_proof(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-variant-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["opencode_variant"] = "small"
        sync_packet_bound_bundle(packet, rebuild_release_notes=False)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_variant" in error and "max" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_allows_competition_exact_preflight_when_host_ready(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-exact-ready-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )
        packet["competition_host_readiness"].update(
            {
                "status": "ready",
                "actual_highest_proof_class": "competition-exact",
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "external_milestone_claim_ready": True,
                "missing_requirements": [],
                "blocker_count": 0,
            }
        )
        packet["summary"]["proof_class_rollup"].update(
            {
                "all": ["competition-exact"],
                "highest_proof_class": "competition-exact",
                "has_competition_exact": True,
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "proof_class": "competition-exact",
                        "run_id": "fixture-run",
                        "competition_exact_host_attested": True,
                    }
                ],
                "non_exact_entrypoints": [],
                "host_attestation_missing_entrypoints": [],
            }
        )
        rewrite_bound_run_report(
            packet,
            lambda payload: (
                payload["entrypoints"][0].update(
                    {
                        "proof_class": "competition-exact",
                        "competition_exact_host_attested": True,
                    }
                ),
                payload["validation"]["proof_class_contract"]["entrypoints"].__setitem__(
                    "opencode_multi_worker_evaluate_profile",
                    "competition-exact",
                ),
            ),
        )
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed", result["errors"])

    def test_validate_packet_rejects_host_ready_when_proof_class_rollup_is_local_simulation(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-host-ready-rollup-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )
        packet["competition_host_readiness"].update(
            {
                "status": "ready",
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "external_milestone_claim_ready": True,
                "missing_requirements": [],
                "blocker_count": 0,
            }
        )
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_host_readiness.all_entrypoints_competition_exact must match "
                "judge_milestone_bundle.proof_class_rollup.all_entrypoints_competition_exact" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_exact_preflight_when_host_blocked(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-exact-blocked-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet, rebuild_release_notes=False)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("proof_class must not claim competition-exact without host attestation" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_runtime_env_sha_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-runtime-env-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        proof = packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]
        proof["opencode_runtime_env_sha256"] = "0" * 64
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("opencode_runtime_env_sha256" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_accepts_deep_bound_opencode_safety_attempt(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attach_opencode_safety_attempt(packet, attempt_ref)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed", result["errors"])

    def test_validate_packet_rejects_published_judge_index_opencode_attempt_source_mismatch(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-index-attempt-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attach_opencode_safety_attempt(packet, attempt_ref)

        index_payload = judge_entrypoint_fixtures.valid_opencode_judge_index_payload()
        judge_entrypoint_fixtures.materialize_opencode_judge_index_artifacts(
            index_payload,
            temp_dir / "judge-out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **judge_entrypoint_fixtures.opencode_launch_policy(),
                "auto_retry": True,
            },
        )
        worker = index_payload["opencode_agent_runtime"]["workers"][0]
        worker["opencode_safety_transform_attempt"] = json.loads(json.dumps(attempt_ref))
        other_attempt_path = temp_dir / "judge-out" / "workers" / "worker-a" / "harness" / "other-attempt.json"
        write_json(other_attempt_path, {"report_kind": "test-opencode-safety-transform-attempt", "id": "drifted"})
        worker_report_path = REPO_ROOT / worker["worker_report"]["path"]
        worker_report = json.loads(worker_report_path.read_text(encoding="utf-8"))
        worker_report["opencode_safety_transform_attempt"] = {
            "path": repo_relative(other_attempt_path),
            "sha256": judge_validator.sha256_file(other_attempt_path),
        }
        write_json(worker_report_path, worker_report)
        worker["worker_report"]["sha256"] = judge_validator.sha256_file(worker_report_path)

        index_path = temp_dir / "judge-out" / "harness" / "judge-evidence-index.json"
        write_json(index_path, index_payload)
        index_ref = {
            "artifact_name": "judge_evidence_index",
            "entrypoint_id": "opencode_multi_worker_evaluate_profile",
            "path": repo_relative(index_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(index_path),
        }
        append_published_artifact_ref(packet, index_ref)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "publication_manifest.published_artifact_refs[].judge_evidence_index contract failed" in error
                and "worker_report.opencode_safety_transform_attempt must match opencode_safety_transform_attempt"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_safety_attempt_boundary_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-hash-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attach_opencode_safety_attempt(packet, attempt_ref)
        packet["opencode_patch_boundary"]["opencode_safety_transform_attempt"]["sha256"] = "0" * 64
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_safety_transform_attempt.sha256 must match" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_safety_attempt_non_five_round_cap(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-rounds-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir, max_repair_rounds=4)
        attach_opencode_safety_attempt(packet, attempt_ref)
        packet["opencode_patch_boundary"]["opencode_safety_transform_attempt"]["max_repair_rounds"] = 4
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("attempt_contract.max_repair_rounds must be 5" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_safety_attempt_retry_patch_event_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-events-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        evidence_root = attempt_path.parent / "attempt-evidence"
        rollback = write_text_artifact(evidence_root / "rollback.json", '{"status":"rolled_back"}\n')
        patch_events = write_text_artifact(evidence_root / "patch-events.jsonl", '{"event":"repair"}\n')
        payload["safety_transform_units"][0]["accepted_retry_hint"] = {
            "status": "revalidated_passed",
            "repair_rounds": 1,
            "auto_recovered": True,
            "rollback_ids": [rollback["path"]],
            "rollback_evidence": [rollback],
            "patch_events_path": patch_events["path"],
            "patch_events_sha256": "0" * 64,
        }
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = judge_validator.sha256_file(attempt_path)
        attach_opencode_safety_attempt(packet, attempt_ref)
        attempt_summary = packet["opencode_patch_boundary"]["opencode_safety_transform_attempt"]
        attempt_summary["accepted_retry_hint_status"] = "revalidated_passed"
        attempt_summary["accepted_retry_hint_statuses"] = ["revalidated_passed"]
        attempt_summary["rollback_ref_count"] = 1
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("patch_events_sha256" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_rejects_preflight_session_without_shell_call(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-no-shell-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        rewrite_packet_preflight_session(
            packet,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [],
            },
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "contract_verification.status recomputed from opencode_session_evidence must be executed" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_failed_preflight_session_evidence_contract(self) -> None:
        cases = [
            ("nonzero_returncode", {"process_returncode": 1}, "process_returncode must be 0"),
            ("unparsed_session", {"parsed": False}, "parsed must be true"),
            ("non_jsonl_format", {"format": "text"}, "format must be jsonl"),
        ]
        for case_name, updates, expected_error in cases:
            with self.subTest(case=case_name):
                temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-session-contract-", dir=REPO_ROOT / "target"))
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
                session_path = REPO_ROOT / preflight_payload["opencode_session_evidence"]["path"]
                session_payload = json.loads(session_path.read_text(encoding="utf-8"))
                session_payload.update(updates)
                rewrite_packet_preflight_session(packet, session_payload)
                sync_packet_bound_bundle(packet)
                write_json(packet_path, packet)

                result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(
                    any(f"opencode_session_evidence.{expected_error}" in error for error in result["errors"]),
                    result["errors"],
                )

    def test_validate_packet_rejects_preflight_first_shell_mismatch_even_if_marker_runs_later(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-late-marker-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        marker_command_line = packet_preflight_marker_command_line(packet)
        rewrite_packet_preflight_session(
            packet,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": "python3 -B -c 'print(1)'", "workdir": str(REPO_ROOT)}},
                        }
                    },
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": marker_command_line, "workdir": str(REPO_ROOT)}},
                        }
                    },
                ],
            },
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("first_shell_command_mismatch_worker_command_seen_later" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_session_evidence_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-session-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
        session_path = REPO_ROOT / preflight_payload["opencode_session_evidence"]["path"]
        session_payload = json.loads(session_path.read_text(encoding="utf-8"))
        session_payload["session_events"] = []
        write_json(session_path, session_payload)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_session_evidence sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_deep_validates_preflight_even_when_runtime_flag_false(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-runtime-flag-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_runtime_enabled"] = False
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = "0" * 64
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode-preflight-report" in error and "sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_runtime_enabled_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-runtime-enabled-drift-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_runtime_enabled"] = False
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "opencode_patch_boundary.opencode_runtime_enabled must match "
                "judge_milestone_bundle.opencode_runtime.enabled_entrypoint_count" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_handoff_contract_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-handoff-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload["worker_command_line"] = "python3 -B -c 'print(1)'"
        write_json(handoff_path, handoff_payload)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("handoff_contract sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_handoff_missing_opencode_run_argv(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-handoff-missing-argv-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_path = packet_preflight_path(packet)
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload.pop("opencode_argv")
        write_json(handoff_path, handoff_payload)
        preflight_payload["handoff_contract"]["sha256"] = judge_validator.sha256_file(handoff_path)
        write_json(preflight_path, preflight_payload)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = (
            judge_validator.sha256_file(preflight_path)
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("handoff_contract.opencode_argv must be a non-empty string list" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_handoff_launch_policy_drift(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-handoff-policy-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_path = packet_preflight_path(packet)
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload["launch_policy"]["opencode_skip_permissions"] = True
        handoff_payload["launch_policy_sha256"] = judge_validator.sha256_text(
            json.dumps(handoff_payload["launch_policy"], sort_keys=True)
        )
        write_json(handoff_path, handoff_payload)
        preflight_payload["handoff_contract"]["sha256"] = judge_validator.sha256_file(handoff_path)
        write_json(preflight_path, preflight_payload)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = (
            judge_validator.sha256_file(preflight_path)
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("handoff_contract.launch_policy must match preflight_report.launch_policy" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_marker_payload_run_id_drift(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-marker-payload-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
        marker_path = REPO_ROOT / preflight_payload["marker_path"]
        marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
        marker_payload["run_id"] = "different-run"
        write_json(marker_path, marker_payload)
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("marker.run_id must match preflight_report.run_id" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_artifact_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["judge_milestone_bundle"]["sha256"] = "0" * 64
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("sha256 mismatch" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_requires_archive_bundle_manifest_file_ref(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        del packet["competition_config_archive"]["files"]["config/competition-env/bundle-manifest.json"]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.files must include config/competition-env/bundle-manifest.json" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_requires_archive_external_reproduction_refs(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-refs-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_config_archive"]["external_refs"] = {}
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.external_refs missing required refs" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_archive_external_ref_projection_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-publication-refs-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        dropped_ref = next(iter(packet["publication_manifest"]["competition_config_archive"]["external_refs"]))
        del packet["publication_manifest"]["competition_config_archive"]["external_refs"][dropped_ref]
        packet["publication_manifest"]["competition_config_archive"]["external_ref_count"] -= 1

        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "publication_manifest.competition_config_archive.external_refs must match competition_config_archive.external_refs"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_archive_summary_projection_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-publication-summary-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publication_manifest"]["competition_config_archive"]["file_count"] += 1

        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "publication_manifest.competition_config_archive.file_count must match competition_config_archive.file_count"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_requires_archive_manifest_listed_config_files(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-files-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        del packet["competition_config_archive"]["files"]["config/competition-env/environment.json"]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.files missing bundle-manifest listed files" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_archive_bundle_manifest_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_config_archive"]["files"]["config/competition-env/bundle-manifest.json"]["sha256"] = "0" * 64
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.files.config/competition-env/bundle-manifest.json" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_archive_file_role_drift_from_bundle_manifest(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-role-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_config_archive"]["files"]["config/competition-env/environment.json"]["role"] = "wrong-role"
        manifest_payload = json.loads(json.dumps(packet["competition_config_archive"]))
        manifest_payload.pop("materialized_manifest", None)
        archive_manifest_path = REPO_ROOT / packet["competition_config_archive"]["materialized_manifest"]["path"]
        write_json(archive_manifest_path, manifest_payload)
        packet["competition_config_archive"]["materialized_manifest"]["sha256"] = judge_validator.sha256_file(
            archive_manifest_path
        )
        packet["publication_manifest"]["competition_config_archive"]["materialized_manifest"] = json.loads(
            json.dumps(packet["competition_config_archive"]["materialized_manifest"])
        )
        run_report_path = REPO_ROOT / packet["judge_entrypoints_run_report"]["path"]
        run_report_payload = json.loads(run_report_path.read_text(encoding="utf-8"))
        run_report_payload["competition_config_archive"] = json.loads(json.dumps(packet["competition_config_archive"]))
        write_json(run_report_path, run_report_payload)
        packet["judge_entrypoints_run_report"]["sha256"] = judge_validator.sha256_file(run_report_path)
        packet["publication_manifest"]["judge_entrypoints_run_report"] = json.loads(
            json.dumps(packet["judge_entrypoints_run_report"])
        )
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["judge_entrypoints_run_report"] = json.loads(json.dumps(packet["judge_entrypoints_run_report"]))
        bundle_payload["publication_manifest"]["judge_entrypoints_run_report"] = json.loads(
            json.dumps(packet["judge_entrypoints_run_report"])
        )
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_config_archive.files.config/competition-env/environment.json.role must match bundle-manifest"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_requires_materialized_archive_manifest(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        del packet["competition_config_archive"]["materialized_manifest"]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.materialized_manifest must be an object" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_materialized_archive_manifest_payload_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        manifest_path = REPO_ROOT / packet["competition_config_archive"]["materialized_manifest"]["path"]
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload["file_count"] = 0
        write_json(manifest_path, manifest_payload)
        packet["competition_config_archive"]["materialized_manifest"]["sha256"] = judge_validator.sha256_file(manifest_path)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = packet["publication_manifest"]
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.materialized_manifest payload must match" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_materialized_archive_manifest_wrong_fixed_path(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-path-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        wrong_manifest_path = temp_dir / "not-summary" / "competition-config-archive" / "manifest.json"
        manifest_payload = json.loads(json.dumps(packet["competition_config_archive"]))
        manifest_payload.pop("materialized_manifest", None)
        write_json(wrong_manifest_path, manifest_payload)
        wrong_manifest_ref = {
            "path": repo_relative(wrong_manifest_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(wrong_manifest_path),
        }
        packet["competition_config_archive"]["materialized_manifest"] = wrong_manifest_ref
        packet["publication_manifest"]["competition_config_archive"]["materialized_manifest"] = wrong_manifest_ref
        run_report_path = REPO_ROOT / packet["judge_entrypoints_run_report"]["path"]
        run_report_payload = json.loads(run_report_path.read_text(encoding="utf-8"))
        run_report_payload["competition_config_archive"] = json.loads(json.dumps(packet["competition_config_archive"]))
        write_json(run_report_path, run_report_payload)
        packet["judge_entrypoints_run_report"]["sha256"] = judge_validator.sha256_file(run_report_path)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["judge_entrypoints_run_report"] = json.loads(json.dumps(packet["judge_entrypoints_run_report"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_config_archive.materialized_manifest.path must be "
                f"{temp_dir.relative_to(REPO_ROOT).as_posix()}/summary/competition-config-archive/manifest.json"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_manifest_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-bundle-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publication_manifest"] = {
            **packet["publication_manifest"],
            "publication_scope": "focused-run",
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publication_manifest must match judge_milestone_bundle.publication_manifest" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_manifest_missing_identity_fields(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-manifest-identity-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        for field in ("report_kind", "bundle_version", "source_commit", "repo_commit", "target_source_pin"):
            del packet["publication_manifest"][field]
            del bundle_payload["publication_manifest"][field]
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publication_manifest.report_kind must be publication-manifest" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_bound_bundle_schema_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-bundle-schema-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload.pop("retention_policy")
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "judge_milestone_bundle must match validation/judge-milestone-bundle.schema.json" in error
                and "retention_policy" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_public_release_packet_schema_requires_publication_manifest_identity(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-schema-identity-", dir=REPO_ROOT / "target"))
        packet = valid_packet(temp_dir)
        for field in (
            "report_kind",
            "bundle_version",
            "source_commit",
            "repo_commit",
            "target_source_pin",
            "published_artifact_refs",
            "published_artifact_count",
            "release_tag_readiness",
        ):
            del packet["publication_manifest"][field]
        schema = judge_validator.load_json(packet_validator.PACKET_SCHEMA)

        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(packet, schema)

    def test_validate_packet_rejects_status_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-status-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["status"] = "blocked"
        bundle_payload["blockers"] = ["blocked-for-test"]
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# invalid status fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("public_release_packet.status must match judge_milestone_bundle.status" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_requires_summary_blockers_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-summary-blockers-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        blocker = "validated_artifact_sha256_mismatch:before_after_judge_demo:judge_evidence_index"
        bundle_payload["status"] = "blocked"
        bundle_payload["blockers"] = [blocker]
        write_json(bundle_path, bundle_payload)
        packet["status"] = "blocked"
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# invalid status fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("summary.blockers must match judge_milestone_bundle.blockers" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_invalid_bound_bundle_status(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-invalid-bundle-status-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["status"] = "green"
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# invalid status fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_milestone_bundle.status must be passed or blocked" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_bound_bundle_missing_blockers_field(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-missing-bundle-blockers-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload.pop("blockers")
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# missing blockers fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_milestone_bundle.blockers must be a string list" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_quantitative_evaluation_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-scorecard-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["quantitative_evaluation"] = {
            **packet["quantitative_evaluation"],
            "project_slice_counts": {
                **packet["quantitative_evaluation"]["project_slice_counts"],
                "workflow_units_total": 999,
            },
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("quantitative_evaluation must match judge_milestone_bundle.quantitative_evaluation" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_repair_exhibit_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-before-after-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["before_after_repair_exhibit"] = {
            **packet["before_after_repair_exhibit"],
            "rollup": {
                **packet["before_after_repair_exhibit"]["rollup"],
                "bound_unit_count": 999,
            },
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "before_after_repair_exhibit must match judge_milestone_bundle.before_after_repair_exhibit" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_verified_baseline_accounting_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-before-after-accounting-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
        mutated["rollup"]["bound_unit_count"] = 2
        mutated["rollup"]["verified_baseline_unit_count"] = 1
        mutated["rollup"]["missing_verified_baseline_unit_count"] = 0
        mutated["rollup"]["all_units_verified_baseline_bound"] = True
        packet["before_after_repair_exhibit"] = mutated
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["before_after_repair_exhibit"] = mutated
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("before_after_repair_exhibit verified baseline accounting mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_rollup_source_mismatch_even_when_bundle_matches(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-before-after-source-rollup-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
        mutated["rollup"]["bound_unit_count"] = 2
        mutated["rollup"]["verified_baseline_unit_count"] = 1
        mutated["rollup"]["missing_verified_baseline_unit_count"] = 1
        mutated["rollup"]["all_units_verified_baseline_bound"] = False
        packet["before_after_repair_exhibit"] = mutated
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["before_after_repair_exhibit"] = mutated
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("before_after_repair_exhibit rollup must match sources" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_patch_or_unsafe_rollup_source_mismatch(self) -> None:
        drift_cases = {
            "measured_unsafe_unit_count": 2,
            "accepted_patch_unit_count": 2,
        }
        for field, spoofed_value in drift_cases.items():
            with self.subTest(field=field):
                temp_dir = Path(
                    tempfile.mkdtemp(
                        prefix=f"public-release-packet-before-after-{field.replace('_', '-')}-",
                        dir=REPO_ROOT / "target",
                    )
                )
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
                mutated["rollup"][field] = spoofed_value
                packet["before_after_repair_exhibit"] = mutated
                bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
                bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
                bundle_payload["before_after_repair_exhibit"] = mutated
                write_json(bundle_path, bundle_payload)
                packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
                notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
                notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
                packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
                write_json(packet_path, packet)

                result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(
                    any("before_after_repair_exhibit rollup must match sources" in error for error in result["errors"]),
                    result["errors"],
                )

    def test_validate_packet_rejects_before_after_unsafe_reduction_total_source_mismatch(self) -> None:
        drift_cases = (
            ("unsafe_reduced_by", 99),
            ("unsafe_reduction.baseline_total_unsafe", 99),
            ("unsafe_reduction.current_total_unsafe", 99),
            ("unsafe_reduction.reduced_by", 99),
        )
        for field, spoofed_value in drift_cases:
            with self.subTest(field=field):
                temp_dir = Path(
                    tempfile.mkdtemp(
                        prefix=f"public-release-packet-before-after-{field.replace('.', '-').replace('_', '-')}-",
                        dir=REPO_ROOT / "target",
                    )
                )
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
                if field == "unsafe_reduced_by":
                    mutated["rollup"][field] = spoofed_value
                else:
                    _, nested_field = field.split(".", maxsplit=1)
                    mutated["rollup"]["unsafe_reduction"][nested_field] = spoofed_value
                packet["before_after_repair_exhibit"] = mutated
                bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
                bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
                bundle_payload["before_after_repair_exhibit"] = mutated
                write_json(bundle_path, bundle_payload)
                packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
                notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
                notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
                packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
                write_json(packet_path, packet)

                result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(
                    any(
                        "before_after_repair_exhibit unsafe reduction rollup must match sources" in error
                        for error in result["errors"]
                    ),
                    result["errors"],
                )

    def test_validate_packet_requires_publishability_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-missing-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet.pop("publishability", None)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("publishability" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_rejects_publishability_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"] = {
            "status": "external_release_ready",
            "scope": "full",
            "publication_scope": "full",
            "external_milestone_claim_ready": True,
            "external_milestone": True,
            "blocker_count": 0,
            "blockers": [],
            "all_entrypoints_run_publishable": True,
            "focused_run": False,
            "competition_exact_publishable": True,
            "required_agent_tool": "opencode",
            "required_agent": "c2rust-migrator",
            "required_model": "GLM-5.1",
            "required_variant": "max",
            "opencode_glm51_required": True,
            "opencode_glm51_preflight_status": "passed",
            "opencode_glm51_publishable": True,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "target_artifacts_regenerable": True,
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publishability must match judge_milestone_bundle.publishability" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_internal_preview_publication_scope_full(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-scope-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publishability"]["publication_scope"] = "full"
        write_json(bundle_path, bundle_payload)
        packet["publishability"] = json.loads(json.dumps(bundle_payload["publishability"]))
        packet["judge_milestone_bundle"]["sha256"] = packet_validator.judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publishability.publication_scope must match external readiness" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_publishability_required_variant_drift_even_when_bundle_matches(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-variant-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publishability"]["required_variant"] = "lite"
        write_json(bundle_path, bundle_payload)
        packet["publishability"] = json.loads(json.dumps(bundle_payload["publishability"]))
        packet["judge_milestone_bundle"]["sha256"] = packet_validator.judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publishability.required_variant" in error and "max" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_external_ready_when_host_readiness_blocked(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-host-readiness-blocked-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )
        write_json(bundle_path, bundle_payload)
        packet["publishability"] = json.loads(json.dumps(bundle_payload["publishability"]))
        packet["judge_milestone_bundle"]["sha256"] = packet_validator.judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_host_readiness.status must be ready" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_exact_publishable_without_host_attestation(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-exact-publishable-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"]["competition_exact_publishable"] = True
        packet["competition_host_readiness"]["all_entrypoints_competition_exact"] = True
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "publishability.competition_exact_publishable requires competition_host_readiness.competition_exact_host_verified=true"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_host_readiness_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-host-readiness-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_host_readiness"] = {
            **packet["competition_host_readiness"],
            "status": "ready",
            "competition_exact_host_verified": True,
            "missing_requirements": [],
            "blocker_count": 0,
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_host_readiness must match judge_milestone_bundle.competition_host_readiness" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_passed_bundle_with_bad_published_artifact_ref_status(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-bad-published-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bad_ref = {
            "artifact_name": "judge_evidence_index",
            "path": "target/competition-out/summary/judge-evidence-index.json",
            "status": "sha256_mismatch",
            "sha256": "0" * 64,
        }
        append_published_artifact_ref(packet, bad_ref)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("passed bundle cannot publish bad artifact ref status" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_passed_bundle_with_non_present_published_artifact_ref_status(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-missing-published-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        missing_ref = {
            "artifact_name": "judge_evidence_index",
            "path": "target/competition-out/summary/judge-evidence-index.json",
            "status": "missing",
        }
        append_published_artifact_ref(packet, missing_ref)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "passed bundle cannot publish non-present artifact ref status: judge_evidence_index:missing"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_attempt_ref_when_boundary_absent_even_if_ref_unhealthy(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-unhealthy-attempt-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        blocker = "blocked-for-test"
        packet["status"] = "blocked"
        packet["summary"]["blockers"] = [blocker]
        packet["publishability"]["status"] = "blocked"
        packet["publishability"]["scope"] = "blocked"
        packet["publishability"]["publication_scope"] = "blocked"
        packet["publishability"]["blocker_count"] = 1
        packet["publishability"]["blockers"] = [blocker]
        unhealthy_attempt_ref = {
            "artifact_name": "opencode_safety_transform_attempt",
            "path": "target/competition-out/summary/opencode-safety-transform-attempt.json",
            "status": "sha256_mismatch",
            "sha256": "0" * 64,
        }
        append_published_artifact_ref(packet, unhealthy_attempt_ref)

        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["status"] = "blocked"
        bundle_payload["blockers"] = [blocker]
        bundle_payload["publishability"] = json.loads(json.dumps(packet["publishability"]))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "opencode_patch_boundary.opencode_safety_transform_attempt.status must not be absent"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_published_artifact_ref_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-published-ref-hash-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        artifact_ref = write_text_artifact(temp_dir / "harness" / "judge-evidence-index.json", "{}\n")
        bad_ref = {
            **artifact_ref,
            "artifact_name": "judge_evidence_index",
            "sha256": "0" * 64,
        }
        append_published_artifact_ref(packet, bad_ref)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publication_manifest.published_artifact_refs[].sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_published_artifact_ref_status_summary_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-published-ref-summary-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"]["published_artifact_ref_status"]["total_count"] = 999
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "summary.published_artifact_ref_status must match judge_milestone_bundle.publication_manifest.published_artifact_refs"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_summary_identity_drift_from_bound_bundle(self) -> None:
        cases = [
            (
                "entrypoint-count",
                lambda packet: packet["summary"].__setitem__("entrypoint_count", 999),
                "summary.entrypoint_count must match judge_entrypoints_run_report.entrypoint_count",
            ),
            (
                "publication-scope",
                lambda packet: packet["summary"].__setitem__("publication_scope", "full"),
                "summary.publication_scope must match judge_milestone_bundle.publication_manifest",
            ),
            (
                "readiness",
                lambda packet: packet["summary"].__setitem__(
                    "readiness",
                    {**packet["summary"]["readiness"], "executed_count": 999},
                ),
                "summary.readiness must match judge_entrypoints_run_report.summary.readiness",
            ),
        ]
        for suffix, mutate, expected_error in cases:
            with self.subTest(suffix=suffix):
                temp_dir = Path(
                    tempfile.mkdtemp(
                        prefix=f"public-release-packet-summary-{suffix}-",
                        dir=REPO_ROOT / "target",
                    )
                )
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                mutate(packet)
                write_json(packet_path, packet)

                result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(
                    any(expected_error in error for error in result["errors"]),
                    result["errors"],
                )

    def test_validate_packet_rejects_missing_workflow_metrics_summary_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-workflow-summary-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"].pop("workflow_metrics")
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("workflow_metrics" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_progress_delta_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-progress-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"]["progress_delta_ledger"] = {
            **packet["summary"]["progress_delta_ledger"],
            "capability_delta": {
                **packet["summary"]["progress_delta_ledger"]["capability_delta"],
                "delta_count": 999,
            },
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("summary.progress_delta_ledger must match judge_milestone_bundle.progress_delta_ledger" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_summary_proof_class_rollup_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-proof-class-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"]["proof_class_rollup"] = {
            "all": ["competition-exact"],
            "highest_proof_class": "competition-exact",
            "has_competition_exact": True,
            "all_entrypoints_competition_exact": True,
            "competition_exact_host_verified": True,
            "entrypoints": [
                {
                    "id": "forged",
                    "proof_class": "competition-exact",
                    "run_id": "forged-run",
                }
            ],
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "summary.proof_class_rollup must match judge_milestone_bundle.proof_class_rollup" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_bundle_proof_class_rollup_drift_from_run_report(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-proof-class-run-report-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )
        packet["competition_host_readiness"].update(
            {
                "status": "ready",
                "actual_highest_proof_class": "competition-exact",
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "external_milestone_claim_ready": True,
                "missing_requirements": [],
                "blocker_count": 0,
            }
        )
        packet["summary"]["proof_class_rollup"].update(
            {
                "all": ["competition-exact"],
                "highest_proof_class": "competition-exact",
                "has_competition_exact": True,
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "proof_class": "competition-exact",
                        "run_id": "fixture-run",
                        "competition_exact_host_attested": True,
                    }
                ],
                "non_exact_entrypoints": [],
                "host_attestation_missing_entrypoints": [],
            }
        )
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "judge_milestone_bundle.proof_class_rollup must match recomputed "
                "judge_entrypoints_run_report.entrypoints proof_class_rollup" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_run_report_ref_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-run-ref-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        alternate_report = write_text_artifact(
            temp_dir / "summary" / "alternate-judge-entrypoints-run-report.json",
            '{"status":"passed","source":"alternate"}\n',
        )
        packet["judge_entrypoints_run_report"] = alternate_report
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_entrypoints_run_report must match judge_milestone_bundle.judge_entrypoints_run_report" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_release_notes_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-notes-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        stale_notes = write_text_artifact(
            temp_dir / "summary" / "stale-milestone-release-notes.md",
            "# stale notes\n\nThese notes were not rendered from the bound milestone bundle.\n",
        )
        packet["milestone_release_notes"] = stale_notes
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("milestone_release_notes must match judge_milestone_bundle rendered release notes" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_semantic_gate_overclaim(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-overclaim-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["claim_boundary"]["semantic_gate"] = True
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("claim_boundary.semantic_gate must be false" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_local_absolute_path_leak(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-path-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["reproduction_commands"]["run_judge_entrypoints"] = "C:\\Python314\\python.exe -m validation.tools.run_judge_entrypoints"
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("forbidden local absolute path" in error for error in result["errors"]), result["errors"])

    def test_core_validation_ci_runs_public_packet_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("validation.tools.test_validate_public_release_packet", workflow)


if __name__ == "__main__":
    unittest.main()
