import json
import shlex
import tempfile
import unittest
from pathlib import Path

from validation.tools import milestone_release_notes
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
    launch_policy = {
        "opencode_agent": None,
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
            "launch_policy": launch_policy,
            "launch_policy_sha256": launch_policy_sha256,
            "opencode_runtime_env": runtime_env,
        },
    )
    write_json(
        session_path,
        {
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
        },
    )
    preflight_path = root / "harness" / "opencode-preflight-report.json"
    preflight_payload = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "passed",
        "process_returncode": 0,
        "marker_exists": True,
        "marker_path": repo_relative(marker_path),
        "opencode_run_launched": True,
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
        "opencode_model": "GLM-5.1",
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
    refs = {
        "summary": write_text_artifact(evidence_root / "summary.json", '{"final_gate_status":"passed"}\n'),
        "workflow_metrics": write_text_artifact(evidence_root / "workflow-metrics.json", '{"status":"passed"}\n'),
        "baseline": write_text_artifact(evidence_root / "baseline-unsafe.rs", "unsafe fn baseline() {}\n"),
        "final": write_text_artifact(evidence_root / "final-safe.rs", "fn final_safe() {}\n"),
        "accepted_patch": write_text_artifact(evidence_root / "accepted.patch", "accepted patch\n"),
        "patch_log": write_text_artifact(evidence_root / "patch-log.jsonl", '{"round":1}\n'),
        "oracle": write_text_artifact(evidence_root / "oracle.json", '{"status":"passed"}\n'),
        "schema_diff": write_text_artifact(evidence_root / "schema-diff.json", '{"status":"passed"}\n'),
        "unsafe_scan": write_text_artifact(evidence_root / "unsafe-scan.json", '{"status":"passed"}\n'),
    }
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
    packet["publication_manifest"].setdefault("published_artifact_refs", []).append(json.loads(json.dumps(attempt_ref)))

    bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
    bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
    write_json(bundle_path, bundle_payload)
    packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)

    notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
    notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
    packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)


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
    write_json(session_path, session_payload)
    session_ref["sha256"] = judge_validator.sha256_file(session_path)
    write_json(preflight_path, preflight_payload)
    packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = (
        judge_validator.sha256_file(preflight_path)
    )


def sync_packet_bound_bundle(packet: dict) -> None:
    bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
    bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_payload["opencode_runtime"]["preflight_proof_summary"] = json.loads(
        json.dumps(packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"])
    )
    write_json(bundle_path, bundle_payload)
    packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)

    notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
    notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
    packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)


def valid_packet(root: Path) -> dict:
    run_report = write_text_artifact(root / "summary" / "judge-entrypoints-run-report.json", "{}\n")
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
            "bytes": config_bundle_manifest.stat().st_size,
        }
    }
    for manifest_file in config_bundle_payload["files"]:
        path_text = manifest_file["path"]
        path = REPO_ROOT / path_text
        archive_files[path_text] = {
            "path": path_text,
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
    bundle_self_ref = {
        "path": repo_relative(bundle_path),
        "status": "self",
    }
    publication_manifest = {
        "publication_scope": "all-entrypoints",
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "judge_milestone_bundle": bundle_self_ref,
        "competition_config_archive": {
            "report_kind": "competition-config-archive",
            "status": "present",
            "root": "config/competition-env",
            "file_count": len(archive_files),
            "bundle_manifest": config_bundle_ref,
        },
        "supported_subset": {
            "claims": ["public packet validator fixture"],
        },
        "known_non_goals": ["semantic translation gate"],
        "claim_boundary": {
            "semantic_gate": False,
            "publication_manifest_is_semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }
    known_gaps = [{"gap_id": "competition-exact-not-run", "status": "open"}]
    bundle_must_not_claim = ["bundle_status_is_not_project_level_translation_success"]
    packet_must_not_claim = [*bundle_must_not_claim, "public_release_packet_is_not_semantic_gate"]
    reproduction_commands = {
        "run_judge_entrypoints": "python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out/summary/judge-entrypoints-run-report.json"
    }
    before_after_repair_exhibit = {
        "report_kind": "before-after-repair-exhibit-rollup",
        "sources": [
            {
                "entrypoint_id": "before_after_judge_demo",
                "before_after_units": [
                    {
                        "unit_id": "flashdb/real-fdb-calc-crc32",
                        "status": "converged",
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
    bundle_payload = {
        "schema_version": 1,
        "report_kind": "judge-milestone-bundle",
        "status": "passed",
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "bundle_is_semantic_gate": False,
        },
        "publishability": {
            "status": "internal_preview",
        },
        "proof_classes": {
            "rollup": {
                "trusted_proof_classes": ["local-simulation"],
                "has_competition_exact": False,
            }
        },
        "harness_architecture_summary": {
            "rollup": {
                "source_count": 1,
                "worker_count": 1,
                "repair_round_cap": 5,
                "roles": ["planner", "worker", "verifier", "repairer", "reporter"],
            }
        },
        "workflow_metrics": {
            "rollup": {
                "repair_activity": {
                    "repair_history_unit_count": 1,
                    "auto_recovered_unit_count": 1,
                }
            }
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
            },
            "boundary": "Progress deltas are copied from the bound bundle for review only.",
        },
        "quantitative_evaluation": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "project_slice_counts": {
                "workflow_units_total": 1,
                "workflow_units_converged": 1,
                "before_after_bound_unit_count": 1,
            },
            "outcome_counts": {
                "accepted_evidence_semantic_pass_count": 1,
                "translator_generated_semantic_pass_count": 0,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "blocked_repair_count": 0,
                "human_interventions": 0,
            },
            "baseline_comparison": {
                "raw_c2rust": {
                    "status": "manifest_status_observed",
                    "evidence_role": "baseline_or_candidate_context_only",
                    "semantic_acceptance_claimed": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                    "c2rust_baseline_rollup": {
                        "report_kind": "c2rust-baseline-milestone-rollup",
                        "status": "observed",
                        "source_report_count": 2,
                        "unique_evidence_root_count": 1,
                        "unique_manifest_count": 2,
                        "compile_passed_count": 0,
                        "translation_coverage_numerator": 0,
                        "semantic_gate": False,
                    },
                    "boundary": "Raw C2Rust baseline manifests are candidate context only.",
                }
            },
            "claim_boundary": {
                "semantic_gate": False,
                "scorecard_is_semantic_gate": False,
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
            "boundary_fields_explicit": True,
            "chat_output_is_evidence_false": True,
            "semantic_gate_false": True,
            "semantic_gate": False,
        },
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "publication_manifest": publication_manifest,
        "before_after_repair_exhibit": before_after_repair_exhibit,
        "known_gaps": known_gaps,
        "must_not_claim": bundle_must_not_claim,
        "reproduction_commands": reproduction_commands,
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
            "publication_scope": "all-entrypoints",
            "readiness": {"status": "passed"},
            "proof_class_rollup": bundle_payload["proof_class_rollup"],
            "workflow_metrics": {
                "repair_activity": bundle_payload["workflow_metrics"]["rollup"]["repair_activity"],
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
                "boundary": (
                    "Public packet workflow metrics are copied from the bound judge milestone bundle for review only. "
                    "They are not a semantic gate and do not increase translation coverage."
                ),
            },
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
        notes_text = (REPO_ROOT / packet["milestone_release_notes"]["path"]).read_text(encoding="utf-8")
        self.assertIn("| raw C2Rust | manifest_status_observed | no | 0 | 2 manifests / 2 sources / 0 compile-pass |", notes_text)

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
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("public_release_packet.status must match judge_milestone_bundle.status" in error for error in result["errors"]),
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
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_milestone_bundle.status must be passed or blocked" in error for error in result["errors"]),
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
