import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "validation" / "judge-milestone-bundle.schema.json"
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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    stdout_path: Path,
    stderr_path: Path,
) -> None:
    from validation.tools import judge_milestone_bundle as bundle

    ensure_opencode_jsonl_session_events(session_payload)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(opencode_session_stdout_jsonl(session_payload["session_events"]), encoding="utf-8", newline="\n")
    stderr_path.write_text("", encoding="utf-8", newline="\n")
    session_payload["stdout_path"] = repo_relative(stdout_path)
    session_payload["stderr_path"] = repo_relative(stderr_path)
    session_payload["stdout_sha256"] = bundle.validator.sha256_file(stdout_path)
    session_payload["stderr_sha256"] = bundle.validator.sha256_file(stderr_path)


def artifact_ref(path: Path) -> dict:
    from validation.tools import judge_milestone_bundle as bundle

    return {
        "path": repo_relative(path),
        "status": "present",
        "sha256": bundle.validator.sha256_file(path),
    }


def opencode_runtime_env_contract(base_root: Path, *, scope: str) -> dict:
    from validation.tools import judge_milestone_bundle as bundle

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
        "env_sha256": bundle.validator.sha256_text(json.dumps(digest_payload, sort_keys=True)),
        "semantic_gate": False,
        "evidence_boundary": "runtime env isolation is audit evidence only",
    }


def write_opencode_preflight_fixture(root: Path, *, run_id: str = "opencode") -> dict:
    from validation.tools import judge_milestone_bundle as bundle

    marker_path = root / "harness" / "opencode-preflight-marker.json"
    handoff_path = root / "harness" / "opencode-preflight-contract.json"
    session_path = root / "logs" / "opencode-preflight-session-evidence.json"
    session_stdout_path = root / "logs" / "opencode-preflight.stdout.log"
    session_stderr_path = root / "logs" / "opencode-preflight.stderr.log"
    preflight_path = root / "harness" / "opencode-preflight-report.json"
    model_stdout_path = root / "logs" / "opencode-models.stdout.log"
    model_stderr_path = root / "logs" / "opencode-models.stderr.log"
    runtime_env = opencode_runtime_env_contract(root, scope="preflight")
    worker_command = [
        "python3",
        "-B",
        "validation/tools/opencode_agent_harness.py",
        "write-preflight-marker",
        "--marker",
        repo_relative(marker_path),
        "--run-id",
        run_id,
    ]
    worker_command_line = bundle.validator.shell_command_line(worker_command)
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
    opencode_command_line = bundle.validator.shell_command_line(opencode_argv)
    launch_policy = {
        "opencode_agent": "c2rust-migrator",
        "opencode_command": "opencode",
        "opencode_model": "GLM-5.1",
        "opencode_skip_permissions": False,
        "opencode_variant": "max",
    }
    launch_policy_sha256 = bundle.validator.sha256_text(json.dumps(launch_policy, sort_keys=True))
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
            "worker_command": worker_command,
            "worker_command_line": worker_command_line,
            "worker_command_sha256": bundle.validator.sha256_text(worker_command_line),
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
                            "command": worker_command_line,
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
    model_stdout_path.parent.mkdir(parents=True, exist_ok=True)
    model_stdout_path.write_text("GLM-5.1\n", encoding="utf-8")
    model_stderr_path.write_text("", encoding="utf-8")
    write_json(
        preflight_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": "passed",
            "exit_code": 0,
            "process_returncode": 0,
            "argv": opencode_argv,
            "opencode_run_launched": True,
            "marker_path": repo_relative(marker_path),
            "marker_exists": True,
            "launch_policy": launch_policy,
            "launch_policy_sha256": launch_policy_sha256,
            "opencode_runtime_env": runtime_env,
            "handoff_contract": {
                "path": repo_relative(handoff_path),
                "sha256": bundle.validator.sha256_file(handoff_path),
            },
            "opencode_session_evidence": {
                "path": repo_relative(session_path),
                "sha256": bundle.validator.sha256_file(session_path),
            },
            "contract_verification": {
                "status": "executed",
                "expected_worker_command_line": worker_command_line,
                "expected_summary_path": repo_relative(marker_path),
                "expected_worker_command_sha256": bundle.validator.sha256_text(worker_command_line),
                "executed_shell_command_count": 1,
                "executed_shell_commands": [worker_command_line],
                "first_tool_name": "bash",
                "first_shell_command": worker_command_line,
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
            "opencode_model_availability": {
                "status": "available",
                "opencode_command": "opencode",
                "required_model": "GLM-5.1",
                "argv": ["opencode", "models"],
                "process_returncode": 0,
                "model_listed": True,
                "stdout_sha256": bundle.validator.sha256_text(model_stdout_path.read_text(encoding="utf-8")),
                "stderr_sha256": bundle.validator.sha256_text(model_stderr_path.read_text(encoding="utf-8")),
                "logs": {
                    "stdout": repo_relative(model_stdout_path),
                    "stderr": repo_relative(model_stderr_path),
                },
            },
        },
    )
    return {
        "preflight_path": preflight_path,
        "session_path": session_path,
        "model_stdout_path": model_stdout_path,
        "model_stderr_path": model_stderr_path,
        "launch_policy": launch_policy,
        "launch_policy_sha256": launch_policy_sha256,
        "worker_command_line": worker_command_line,
    }


def route_metrics_payload(
    *,
    accepted_evidence_semantic_pass_count: int,
    tracked_route_decision_artifacts: int,
    tracked_slice_gate_contexts: int,
    s2_workflow_run_count: int,
    s2_reduced_by: int,
    blocked_repair_count: int = 0,
    blocked_repairs_status: str | None = None,
    c2rust_baseline: dict | None = None,
) -> dict:
    resolved_blocked_repairs_status = blocked_repairs_status or ("observed" if blocked_repair_count else "none")
    resolved_c2rust_baseline = c2rust_baseline or empty_c2rust_baseline_rollup()
    return {
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
            "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
            "tracked_capability_delta_ledgers": 1,
            "tracked_capability_delta_count": 1,
            "tracked_route_decision_artifacts": tracked_route_decision_artifacts,
            "candidate_classification": {},
            "capability_delta_ledger": {
                "ledger_count": 1,
                "delta_count": 1,
                "governance_delta_count": 2,
                "verification_command_count": 3,
                "translator_generated_semantic_pass_count": 0,
                "semantic_pass_count": accepted_evidence_semantic_pass_count,
                "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
                "generated_candidate_status": {"accepted_evidence_authoritative": accepted_evidence_semantic_pass_count},
                "route_levels": {"L4": accepted_evidence_semantic_pass_count},
                "route_statuses": {"accepted": accepted_evidence_semantic_pass_count},
                "by_construct": {"function_call": 1},
                "blocked_callee_count": blocked_repair_count,
            },
            "s2_workflow_metrics": {
                "run_count": s2_workflow_run_count,
                "unsafe_reduction": {
                    "status": "measured" if s2_reduced_by else "not_measured",
                    "reduced_by": s2_reduced_by,
                },
            },
            "candidate_generation_inventory": {},
            "tracked_slice_gate_contexts": tracked_slice_gate_contexts,
            "slice_gate_contexts": [],
            "c2rust_baseline": resolved_c2rust_baseline,
            "blocked_repairs": {
                "status": resolved_blocked_repairs_status,
                "blocked_repair_count": blocked_repair_count,
                "slice_count": 1 if blocked_repair_count else 0,
                "human_action_required_count": blocked_repair_count,
                "status_counts": {resolved_blocked_repairs_status: 1},
                "human_intervention_points": ["Bind external callee semantics before promotion."]
                if blocked_repair_count
                else [],
                "blocked_callees": ["helper_blocked"] if blocked_repair_count else [],
                "ir_feature_gap_kinds": {"external_direct_callee_context": blocked_repair_count}
                if blocked_repair_count
                else {},
                "forbidden_change_counts": {"missing_l1_evidence": blocked_repair_count}
                if blocked_repair_count
                else {},
                "blocked_reason_counts": {
                    "External callee semantics are not bound to oracle evidence.": blocked_repair_count
                }
                if blocked_repair_count
                else {},
                "source_span_kind_counts": {"c_source": blocked_repair_count} if blocked_repair_count else {},
                "smallest_next_tests": [
                    {
                        "kind": "callee_contract_replay",
                        "command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                        "expected_gate": "external callee contract is bound before candidate promotion",
                    }
                ]
                if blocked_repair_count
                else [],
                "next_actions": [
                    {
                        "repair_id": "repair-refused-1",
                        "target_id": "demo",
                        "slice_id": "refused",
                        "pipeline_id": "validation/evidence/demo/auto-translation/refused",
                        "route": "typed_ir",
                        "status": "blocked",
                        "next_action": "bind_external_callee_semantics",
                        "smallest_next_test_kind": "callee_contract_replay",
                        "smallest_next_test_command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                        "expected_gate": "external callee contract is bound before candidate promotion",
                        "human_intervention_point": "Bind external callee semantics before promotion.",
                        "source_span": {
                            "file": "src/demo.c",
                            "line_start": 12,
                            "line_end": 14,
                        },
                        "source_span_kind": "c_source",
                    }
                ]
                if blocked_repair_count
                else [],
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
                "boundary": "Blocked repair rollup is route-governance context only.",
            },
        },
        "denominators": {
            "capability_delta_ledger": "capability delta ledger artifacts",
            "candidate_generation_inventory": "route decision artifacts",
            "slice_gate_contexts": "slice gate contexts",
            "translation_coverage_numerator": "translator-generated semantic-pass named slices only",
            "accepted_evidence_semantic_pass_count": "accepted evidence semantic pass count is separate",
            "s2_workflow_metrics": "hash-bound competition run summaries",
            "c2rust_baseline": "C2Rust baseline manifest status is candidate context only",
            "blocked_repairs": "self-healing blocked repairs artifacts under validation/evidence",
        },
        "claim_boundary": "Route governance metrics are not semantic acceptance evidence.",
        "retention_policy": {
            "report_kind": "route-governance-metrics-retention-policy",
            "report_role": "p0-route-governance-and-capability-metrics",
            "target_artifacts": {
                "retention_class": "reproducible-local-output",
                "committed": False,
                "policy": "Regenerate from committed anchors.",
            },
            "committed_anchors": {
                "retention_class": "release-evidence",
                "policy": "Use validation/evidence manifests and config profiles.",
            },
            "claim_boundary": "Retention policy does not expand semantic acceptance or translation coverage.",
        },
    }


def c2rust_baseline_rollup_fixture() -> dict:
    return {
        "report_kind": "c2rust-baseline-rollup",
        "status": "observed",
        "manifest_count": 2,
        "generated_output_count": 0,
        "skipped_without_output_count": 2,
        "compile_attempted_count": 0,
        "compile_passed_count": 0,
        "compile_semantic_pass_count": 0,
        "status_counts": {"skipped": 2},
        "output_status_counts": {"missing": 2},
        "compile_status_counts": {"missing": 2},
        "manifests": [
            {
                "path": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c2rust-baseline-manifest.json",
                "sha256": "1" * 64,
                "status": "present",
            },
            {
                "path": "validation/evidence/flashdb/auto-translation/real-fdb-blob-make/l3-real-fdb-blob-make-c2rust-baseline-manifest.json",
                "sha256": "2" * 64,
                "status": "present",
            },
        ],
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": "C2Rust baseline status is candidate context only.",
    }


def empty_c2rust_baseline_rollup() -> dict:
    return {
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
    }


def evidence_governance_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "passed",
        "evidence_root": "validation/evidence",
        "failed_gates": [],
        "policy_compliance": {
            "policy_tier": "ci",
            "status": "passed",
            "failed_gates": [],
            "gates": [
                {"name": "portability", "status": "passed"},
                {"name": "retention_metadata", "status": "passed"},
            ],
        },
        "portability": {
            "status": "passed",
            "claim_anchor_issue_count": 0,
            "profile_hash_issue_count": 0,
            "diagnostic_host_metadata_count": 3,
            "issues": [],
            "profile_hash_issues": [],
        },
        "inventory": {
            "file_count": 3,
            "total_bytes": 120,
            "retention_classes": {
                "committed_release": {"file_count": 2, "total_bytes": 100},
                "diagnostic_only": {"file_count": 1, "total_bytes": 20},
            },
            "pipelines": [
                {
                    "pipeline_id": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32",
                    "artifact_count": 2,
                    "total_bytes": 100,
                    "runtime_ms": 40,
                    "retention_class": "committed_release",
                    "compression_policy": "do_not_compress_claim_anchors",
                    "prune_policy": "do_not_prune_without_manifest_update",
                },
                {
                    "pipeline_id": "validation/evidence/flashdb/auto-translation/diagnostic",
                    "artifact_count": 1,
                    "total_bytes": 20,
                    "runtime_ms": 5,
                    "retention_class": "diagnostic_only",
                    "compression_policy": "compress_when_large_or_superseded",
                    "prune_policy": "may_prune_after_replacement_evidence",
                },
            ],
            "runtime": {
                "observation_count": 2,
                "total_duration_ms": 45,
                "max_duration_ms": 40,
            },
            "retention_policy": {
                "compression_policy": "compress large diagnostic_only logs first",
                "prune_policy": "diagnostic_only may be pruned after replacement evidence is recorded",
            },
        },
    }


class JudgeMilestoneBundleTests(unittest.TestCase):
    def test_opencode_preflight_proof_summary_binds_runtime_env(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-preflight-runtime-env-", dir=REPO_ROOT / "target"))
        fixture = write_opencode_preflight_fixture(temp_dir / "opencode", run_id="opencode")
        preflight_path = Path(fixture["preflight_path"])
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))

        summary = bundle.opencode_preflight_proof_summary_from_index(
            {
                "opencode_agent_runtime": {
                    "opencode_preflight_report": {
                        "path": repo_relative(preflight_path),
                        "sha256": bundle.validator.sha256_file(preflight_path),
                        "status": "present",
                    }
                }
            },
            entrypoint_id="opencode_multi_worker_evaluate_profile",
            proof_class="local-simulation",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["opencode_agent"], "c2rust-migrator")
        self.assertEqual(summary["opencode_variant"], "max")
        self.assertEqual(summary["opencode_runtime_env"], preflight_payload["opencode_runtime_env"])
        self.assertEqual(summary["opencode_runtime_env_sha256"], preflight_payload["opencode_runtime_env"]["env_sha256"])

    def test_opencode_preflight_proof_summary_recomputes_session_contract(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-preflight-contract-", dir=REPO_ROOT / "target"))
        fixture = write_opencode_preflight_fixture(temp_dir / "opencode", run_id="opencode")
        preflight_path = Path(fixture["preflight_path"])
        session_path = Path(fixture["session_path"])
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        session_payload = json.loads(session_path.read_text(encoding="utf-8"))
        session_payload["session_events"][0]["part"]["state"]["input"]["command"] = (
            "python3 -B validation/tools/opencode_agent_harness.py list-workers --db target/fake.sqlite3"
        )
        write_json(session_path, session_payload)
        preflight_payload["opencode_session_evidence"]["sha256"] = bundle.validator.sha256_file(session_path)
        write_json(preflight_path, preflight_payload)

        summary = bundle.opencode_preflight_proof_summary_from_index(
            {
                "opencode_agent_runtime": {
                    "opencode_preflight_report": {
                        "path": repo_relative(preflight_path),
                        "sha256": bundle.validator.sha256_file(preflight_path),
                        "status": "present",
                    }
                }
            },
            entrypoint_id="opencode_multi_worker_evaluate_profile",
            proof_class="local-simulation",
            repo_root=REPO_ROOT,
        )

        self.assertNotEqual(summary["status"], "passed")

    def test_opencode_preflight_proof_summary_rejects_failed_session_evidence_contract(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        cases = [
            ("nonzero_returncode", {"process_returncode": 1}),
            ("unparsed_session", {"parsed": False}),
            ("non_jsonl_format", {"format": "text"}),
        ]
        for case_name, updates in cases:
            with self.subTest(case=case_name):
                temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-preflight-session-contract-", dir=REPO_ROOT / "target"))
                fixture = write_opencode_preflight_fixture(temp_dir / "opencode", run_id="opencode")
                preflight_path = Path(fixture["preflight_path"])
                session_path = Path(fixture["session_path"])
                preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
                session_payload = json.loads(session_path.read_text(encoding="utf-8"))
                session_payload.update(updates)
                write_json(session_path, session_payload)
                preflight_payload["opencode_session_evidence"]["sha256"] = bundle.validator.sha256_file(session_path)
                write_json(preflight_path, preflight_payload)

                summary = bundle.opencode_preflight_proof_summary_from_index(
                    {
                        "opencode_agent_runtime": {
                            "opencode_preflight_report": {
                                "path": repo_relative(preflight_path),
                                "sha256": bundle.validator.sha256_file(preflight_path),
                                "status": "present",
                            }
                        }
                    },
                    entrypoint_id="opencode_multi_worker_evaluate_profile",
                    proof_class="local-simulation",
                    repo_root=REPO_ROOT,
                )

                self.assertNotEqual(summary["status"], "passed")

    def test_opencode_preflight_proof_summary_requires_opencode_run_argv(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-preflight-opencode-argv-", dir=REPO_ROOT / "target"))
        fixture = write_opencode_preflight_fixture(temp_dir / "opencode", run_id="opencode")
        preflight_path = Path(fixture["preflight_path"])
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload.pop("opencode_argv")
        write_json(handoff_path, handoff_payload)
        preflight_payload["handoff_contract"]["sha256"] = bundle.validator.sha256_file(handoff_path)
        write_json(preflight_path, preflight_payload)

        summary = bundle.opencode_preflight_proof_summary_from_index(
            {
                "opencode_agent_runtime": {
                    "opencode_preflight_report": {
                        "path": repo_relative(preflight_path),
                        "sha256": bundle.validator.sha256_file(preflight_path),
                        "status": "present",
                    }
                }
            },
            entrypoint_id="opencode_multi_worker_evaluate_profile",
            proof_class="local-simulation",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(summary["status"], "failed")
        self.assertFalse(summary.get("opencode_run_argv_bound"))

    def test_bundle_binds_all_entrypoints_metrics_and_opencode_runtime(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-bundle-", dir=REPO_ROOT / "target"))
        readiness_path = temp_dir / "summary" / "judge-entrypoints-readiness.json"
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        before_metrics_path = temp_dir / "before-after" / "summary" / "workflow-metrics.json"
        before_route_metrics_path = temp_dir / "before-after" / "summary" / "route-governance-metrics-report.json"
        before_exhibit_path = temp_dir / "before-after" / "summary" / "before-after-exhibit.json"
        evidence_governance_path = temp_dir / "competition-smoke" / "reports" / "evidence-governance.json"
        before_index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        opencode_metrics_path = temp_dir / "opencode" / "summary" / "workflow-metrics.json"
        opencode_route_metrics_path = temp_dir / "opencode" / "summary" / "route-governance-metrics-report.json"
        opencode_index_path = temp_dir / "opencode" / "harness" / "judge-evidence-index.json"
        c2rust_baseline = c2rust_baseline_rollup_fixture()

        write_json(readiness_path, {"report_kind": "judge-entrypoints-readiness", "status": "passed"})
        preflight_fixture = write_opencode_preflight_fixture(temp_dir / "opencode", run_id="opencode")
        opencode_preflight_path = Path(preflight_fixture["preflight_path"])
        opencode_models_stdout_path = Path(preflight_fixture["model_stdout_path"])
        opencode_models_stderr_path = Path(preflight_fixture["model_stderr_path"])
        launch_policy = dict(preflight_fixture["launch_policy"])
        launch_policy_sha256 = str(preflight_fixture["launch_policy_sha256"])
        preflight_binding = {
            "path": repo_relative(opencode_preflight_path),
            "sha256": bundle.validator.sha256_file(opencode_preflight_path),
            "status": "passed",
            "contract_status": "executed",
            "run_id": "opencode",
            "launch_policy": launch_policy,
            "launch_policy_sha256": launch_policy_sha256,
        }
        preflight_artifact_ref = {
            "path": repo_relative(opencode_preflight_path),
            "sha256": bundle.validator.sha256_file(opencode_preflight_path),
            "status": "present",
        }
        write_json(
            before_metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 1,
                "avg_repair_rounds": 1.0,
                "auto_recovery_rate": 1.0,
                "human_interventions": 0,
                "llm_calls": 1,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                },
                "per_unit_statuses": [
                    {
                        "unit_id": "flashdb/real-fdb-calc-crc32",
                        "repair_rounds": 1,
                        "auto_recovered": True,
                        "repair_history": {"rollback_ids": ["rollback-001"]},
                    }
                ],
            },
        )
        write_json(
            before_route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=1,
                tracked_route_decision_artifacts=2,
                tracked_slice_gate_contexts=1,
                s2_workflow_run_count=1,
                s2_reduced_by=2,
                c2rust_baseline=c2rust_baseline,
            ),
        )
        write_json(evidence_governance_path, evidence_governance_payload())
        write_json(
            before_exhibit_path,
            {
                "report_kind": "before-after-exhibit",
                "status": "passed",
                "units": [
                    {
                        "unit_id": "flashdb/real-fdb-calc-crc32",
                        "baseline_verification": {
                            "path": "validation/evidence/baseline-verification.json",
                            "sha256": "e" * 64,
                            "status": "passed",
                            "semantic_pass": True,
                            "semantic_claim_source": "verified_unsafe_baseline_gates",
                            "generated_draft_semantic_pass": False,
                        },
                        "repair_rounds": 1,
                        "auto_recovered": True,
                        "root_cause_key": "unsafe_baseline_requires_repair",
                        "repair_history": {
                            "patch_events_path": "target/demo/retry-repair-history.jsonl",
                            "patch_events_sha256": "f" * 64,
                            "rollback_ids": ["rollback-001"],
                            "statuses": ["failed", "passed", "verified"],
                            "verified": True,
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
                            "baseline_verification_status": "passed",
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
            },
        )
        write_json(
            before_index_path,
            {
                "report_kind": "judge-evidence-index",
                "evidence_artifact_refs": {
                    "before_after_exhibit": {
                        "path": repo_relative(before_exhibit_path),
                        "sha256": bundle.validator.sha256_file(before_exhibit_path),
                        "status": "present",
                    }
                },
                "harness_architecture": {
                    "graph_runtime": "opencode-harness-langgraph-inspired",
                    "graph_nodes": ["load_plan", "fanout_workers", "worker", "repair_retry", "merge", "report"],
                    "worker_count": 1,
                    "retry_policy": {"round_cap": 5, "checkpoint": "repair_hints"},
                    "architecture_contracts": {
                        "agent_coordination": {
                            "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                            "checkpoint_backend": "sqlite",
                            "chat_output_is_evidence": False,
                            "semantic_gate": False,
                        }
                    },
                },
                "core_translation_quality": {
                    "before_after_units": [
                        {
                            "unit_id": "flashdb/real-fdb-calc-crc32",
                            "status": "converged",
                            "baseline": {"path": "validation/evidence/baseline.rs", "sha256": "a" * 64},
                            "final": {"path": "validation/evidence/final.rs", "sha256": "b" * 64},
                            "accepted_patch": {"path": "validation/evidence/accepted.patch", "sha256": "c" * 64},
                            "oracle_evidence": {"path": "validation/evidence/final-verification.json", "sha256": "d" * 64},
                            "unsafe_reduction": {
                                "status": "measured",
                                "baseline_total_unsafe": 2,
                                "current_total_unsafe": 0,
                                "reduced_by": 2,
                            },
                        }
                    ],
                    "final_gate_status": "passed",
                    "repair_summary": {
                        "status": "verified",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 1,
                        "auto_recovered_unit_count": 1,
                        "rollback_evidence_count": 1,
                    },
                    "semantic_pass_count": 1,
                    "translation_before_after": {
                        "status": "bound",
                        "unit_count": 1,
                        "measured_unsafe_unit_count": 1,
                        "accepted_patch_unit_count": 1,
                    },
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 2,
                        "current_total_unsafe": 0,
                        "reduced_by": 2,
                    },
                },
                "judge_headline": {
                    "report_kind": "judge-headline",
                    "worker_count": 1,
                    "repair_round_cap": 5,
                    "semantic_gate": False,
                    "opencode_runtime": {"enabled": False, "semantic_gate": False},
                },
            },
        )
        write_json(
            opencode_metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 2,
                "units_converged": 2,
                "avg_repair_rounds": 0.0,
                "auto_recovery_rate": 0.0,
                "human_interventions": 0,
                "llm_calls": 0,
                "unsafe_reduction": {"status": "not_measured"},
                "per_unit_statuses": [
                    {"unit_id": "flashdb/real-fdb-blob-make", "repair_rounds": 0, "auto_recovered": False},
                    {"unit_id": "flashdb/real-fdb-kv-set", "repair_rounds": 0, "auto_recovered": False},
                ],
            },
        )
        write_json(
            opencode_route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=2,
                tracked_route_decision_artifacts=2,
                tracked_slice_gate_contexts=2,
                s2_workflow_run_count=1,
                s2_reduced_by=0,
                c2rust_baseline=c2rust_baseline,
            ),
        )
        write_json(
            opencode_index_path,
            {
                "report_kind": "judge-evidence-index",
                "harness_architecture": {
                    "graph_runtime": "opencode-harness-langgraph-inspired",
                    "graph_nodes": ["load_plan", "fanout_workers", "worker", "repair_retry", "merge", "report"],
                    "worker_count": 2,
                    "retry_policy": {"round_cap": 5, "checkpoint": "repair_hints"},
                    "architecture_contracts": {
                        "agent_coordination": {
                            "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                            "checkpoint_backend": "sqlite",
                            "chat_output_is_evidence": False,
                            "semantic_gate": False,
                        }
                    },
                },
                "judge_headline": {
                    "report_kind": "judge-headline",
                    "worker_count": 2,
                    "repair_round_cap": 5,
                    "semantic_gate": False,
                    "opencode_runtime": {
                        "enabled": True,
                        "worker_count": 2,
                        "all_contracts_executed": True,
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                },
                "opencode_agent_runtime": {
                    "runtime": "opencode",
                    "worker_count": 2,
                    "all_contracts_executed": True,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                    "contract_status_counts": {"executed": 2},
                    "worker_ids": ["worker-a", "worker-b"],
                    "opencode_preflight_report": preflight_binding,
                },
                "evidence_artifact_refs": {
                    "worker_plan": {"path": "target/opencode/harness/plans/workers.json", "sha256": "a" * 64},
                    "context_pack": {"path": "target/opencode/harness/context-pack.json", "sha256": "b" * 64},
                    "agent_index": {"path": "target/opencode/harness/agent-index.json", "sha256": "c" * 64},
                    "opencode_preflight_report": preflight_artifact_ref,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 2,
                "readiness_report": {"path": repo_relative(readiness_path), "status": "present"},
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "headline": "Judge entrypoints passed: 2/2 executed; semantic_gate=false",
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 2,
                        "configured_count": 2,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "semantic_claim_source": "validator-owned-artifacts",
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "purpose": "core-translation-before-after-exhibit",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "run_id": "before-after",
                        "judge_focus": ["unsafe reduction"],
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(before_metrics_path),
                            "route_governance_metrics_report": repo_relative(before_route_metrics_path),
                            "evidence_governance_report": repo_relative(evidence_governance_path),
                            "judge_evidence_index": repo_relative(before_index_path),
                        },
                    },
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "run_id": "opencode",
                        "judge_focus": ["OpenCode multi-worker runtime"],
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(opencode_metrics_path),
                            "route_governance_metrics_report": repo_relative(opencode_route_metrics_path),
                            "judge_evidence_index": repo_relative(opencode_index_path),
                        },
                    },
                ],
                "validation": {
                    "status": "passed",
                    "source_pin_contract": {
                        "status": "passed",
                        "target_id": "flashdb",
                        "repository": "https://gitcode.com/xwxf/FlashDB.git",
                        "branch": "competition",
                        "canonical_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
                    },
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "workflow_metrics": artifact_ref(before_metrics_path),
                                "route_governance_metrics_report": artifact_ref(before_route_metrics_path),
                                "evidence_governance_report": artifact_ref(evidence_governance_path),
                                "judge_evidence_index": artifact_ref(before_index_path),
                            },
                        },
                        {
                            "id": "opencode_multi_worker_evaluate_profile",
                            "expected_artifacts": {
                                "workflow_metrics": artifact_ref(opencode_metrics_path),
                                "route_governance_metrics_report": artifact_ref(opencode_route_metrics_path),
                                "judge_evidence_index": artifact_ref(opencode_index_path),
                            },
                        },
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["report_kind"], "judge-milestone-bundle")
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["claim_boundary"]["semantic_gate"])
        self.assertFalse(report["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(report["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertIn("2/2 executed", report["summary"]["headline"])
        self.assertEqual(report["judge_entrypoints_run_report"]["path"], repo_relative(run_report_path))
        self.assertEqual(report["entrypoints"][0]["artifacts"]["workflow_metrics"]["status"], "present")
        self.assertIn("sha256", report["entrypoints"][0]["artifacts"]["workflow_metrics"])
        self.assertEqual(report["workflow_metrics"]["rollup"]["source_count"], 2)
        self.assertEqual(report["workflow_metrics"]["rollup"]["units_total"], 3)
        self.assertEqual(report["workflow_metrics"]["rollup"]["units_converged"], 3)
        self.assertEqual(report["workflow_metrics"]["rollup"]["measured_unsafe_reduction_source_count"], 1)
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["source_count"], 2)
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["observed_source_count"], 1)
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["repair_history_unit_count"], 1)
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["auto_recovered_unit_count"], 1)
        self.assertAlmostEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["avg_repair_rounds"], 1.0 / 3.0)
        self.assertAlmostEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["auto_recovery_rate"], 1.0 / 3.0)
        self.assertIn("semantic gate", report["workflow_metrics"]["rollup"]["repair_activity"]["boundary"])
        self.assertEqual(report["route_governance_metrics"]["report_kind"], "route-governance-metrics-rollup")
        self.assertEqual(report["route_governance_metrics"]["rollup"]["source_count"], 2)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["translation_coverage_numerator"], 0)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["accepted_evidence_semantic_pass_count"], 3)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["tracked_route_decision_artifacts"], 4)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["tracked_slice_gate_contexts"], 3)
        c2rust_route_rollup = report["route_governance_metrics"]["rollup"]["c2rust_baseline"]
        self.assertEqual(c2rust_route_rollup["report_kind"], "c2rust-baseline-milestone-rollup")
        self.assertEqual(c2rust_route_rollup["source_report_count"], 2)
        self.assertEqual(c2rust_route_rollup["unique_evidence_root_count"], 1)
        self.assertEqual(c2rust_route_rollup["unique_manifest_count"], 2)
        self.assertEqual(c2rust_route_rollup["status_counts"], {"skipped": 2})
        self.assertEqual(c2rust_route_rollup["output_status_counts"], {"missing": 2})
        self.assertEqual(c2rust_route_rollup["compile_status_counts"], {"missing": 2})
        self.assertEqual(c2rust_route_rollup["skipped_without_output_count"], 2)
        self.assertEqual(c2rust_route_rollup["compile_passed_count"], 0)
        self.assertFalse(c2rust_route_rollup["semantic_gate"])
        self.assertEqual(c2rust_route_rollup["translation_coverage_numerator"], 0)
        self.assertEqual(report["blocked_repairs_rollup"]["rollup"]["blocked_repair_count"], 0)
        self.assertFalse(report["blocked_repairs_rollup"]["semantic_gate"])
        self.assertEqual(report["blocked_repairs_rollup"]["translation_coverage_numerator"], 0)
        self.assertTrue(report["route_governance_metrics"]["rollup"]["all_target_artifacts_reproducible"])
        self.assertTrue(report["route_governance_metrics"]["rollup"]["all_retention_policies_present"])
        self.assertEqual(report["evidence_cost_retention"]["report_kind"], "evidence-cost-retention-rollup")
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["source_count"], 1)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["artifact_count"], 3)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["total_bytes"], 120)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["pipeline_count"], 2)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["runtime_ms"]["total"], 45)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["runtime_ms"]["max"], 40)
        self.assertEqual(
            report["evidence_cost_retention"]["rollup"]["retention_classes"]["committed_release"]["file_count"],
            2,
        )
        self.assertTrue(report["evidence_cost_retention"]["rollup"]["all_sources_passed"])
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["portability_issue_count"], 0)
        evidence_cost_source = report["evidence_cost_retention"]["sources"][0]
        self.assertEqual(evidence_cost_source["policy_compliance"]["policy_tier"], "ci")
        self.assertEqual(evidence_cost_source["policy_compliance"]["status"], "passed")
        self.assertEqual(evidence_cost_source["policy_compliance"]["failed_gates"], [])
        policy_rollup = report["evidence_cost_retention"]["rollup"]["policy_compliance"]
        self.assertTrue(policy_rollup["all_sources_policy_passed"])
        self.assertEqual(policy_rollup["tier_counts"], {"ci": 1})
        self.assertEqual(policy_rollup["failed_gate_counts"], {})
        self.assertEqual(report["opencode_runtime"]["enabled_entrypoint_count"], 1)
        self.assertTrue(report["opencode_runtime"]["all_contracts_executed"])
        self.assertTrue(report["opencode_runtime"]["chat_output_is_evidence_false"])
        preflight_summary = report["opencode_runtime"]["preflight_proof_summary"]
        self.assertEqual(preflight_summary["status"], "passed")
        self.assertEqual(preflight_summary["opencode_model"], "GLM-5.1")
        self.assertEqual(preflight_summary["required_model"], "GLM-5.1")
        self.assertTrue(preflight_summary["model_listed"])
        self.assertEqual(preflight_summary["preflight_report"]["sha256"], bundle.validator.sha256_file(opencode_preflight_path))
        self.assertEqual(
            preflight_summary["model_probe_logs"]["stdout"]["sha256"],
            bundle.validator.sha256_file(opencode_models_stdout_path),
        )
        self.assertFalse(preflight_summary["semantic_gate"])
        self.assertEqual(preflight_summary["translation_coverage_numerator"], 0)
        self.assertEqual(report["claim_scope"]["external_review_index_ready"], True)
        self.assertEqual(report["claim_scope"]["semantic_acceptance_ready"], False)
        self.assertEqual(report["claim_scope"]["competition_exact_ready"], False)
        self.assertEqual(report["claim_scope"]["translator_generated_coverage_ready"], False)
        self.assertEqual(report["publishability"]["status"], "internal_preview")
        self.assertEqual(report["publishability"]["scope"], "full")
        self.assertEqual(report["publishability"]["publication_scope"], "internal_preview_full")
        self.assertFalse(report["summary"]["external_milestone_claim_ready"])
        self.assertEqual(report["publishability"]["blocker_count"], 0)
        self.assertEqual(report["publishability"]["blockers"], [])
        self.assertFalse(report["publishability"]["external_milestone_claim_ready"])
        self.assertFalse(report["publishability"]["external_milestone"])
        self.assertEqual(report["publishability"]["required_agent"], "c2rust-migrator")
        self.assertEqual(report["publishability"]["required_variant"], "max")
        self.assertTrue(report["publishability"]["opencode_glm51_required"])
        self.assertEqual(report["publishability"]["opencode_glm51_preflight_status"], "passed")
        self.assertTrue(report["publishability"]["opencode_glm51_publishable"])
        self.assertFalse(report["publishability"]["semantic_gate"])
        self.assertEqual(report["publishability"]["translation_coverage_numerator"], 0)
        self.assertEqual(report["publishability"]["all_entrypoints_run_publishable"], True)
        self.assertEqual(report["publishability"]["competition_exact_publishable"], False)
        host_readiness = report["competition_host_readiness"]
        self.assertEqual(host_readiness["report_kind"], "competition-host-readiness")
        self.assertEqual(host_readiness["status"], "blocked")
        self.assertEqual(host_readiness["required_agent_tool"], "opencode")
        self.assertEqual(host_readiness["required_agent"], "c2rust-migrator")
        self.assertEqual(host_readiness["required_model"], "GLM-5.1")
        self.assertEqual(host_readiness["required_variant"], "max")
        self.assertEqual(host_readiness["required_proof_class"], "competition-exact")
        self.assertEqual(host_readiness["actual_highest_proof_class"], "local-simulation")
        self.assertFalse(host_readiness["all_entrypoints_competition_exact"])
        self.assertFalse(host_readiness["competition_exact_host_verified"])
        self.assertTrue(host_readiness["opencode_glm51_publishable"])
        self.assertFalse(host_readiness["external_milestone_claim_ready"])
        self.assertIn("all_entrypoints_competition_exact", host_readiness["missing_requirements"])
        self.assertIn("competition_exact_host_verified", host_readiness["missing_requirements"])
        self.assertFalse(host_readiness["semantic_gate"])
        self.assertEqual(host_readiness["translation_coverage_numerator"], 0)
        self.assertEqual(report["unsafe_reduction_scope"]["scope"], "partial")
        self.assertFalse(report["unsafe_reduction_scope"]["all_sources_measured"])
        self.assertEqual(report["unsafe_reduction_scope"]["measured_units"], 1)
        self.assertEqual(report["unsafe_reduction_scope"]["total_units"], 3)
        self.assertEqual(report["semantic_evidence_rollup"]["translation_coverage_numerator"], 0)
        self.assertFalse(report["semantic_evidence_rollup"]["accepted_evidence_counts_as_translator_coverage"])
        self.assertEqual(report["core_translation_quality"]["final_gate_statuses"], ["passed"])
        self.assertEqual(report["core_translation_quality"]["unsafe_reduction"]["baseline_total_unsafe"], 2)
        self.assertEqual(report["core_translation_quality"]["unsafe_reduction"]["current_total_unsafe"], 0)
        self.assertFalse(report["core_translation_quality"]["generated_draft_semantic_pass"])
        self.assertIn("before_after_repair_exhibit", report)
        self.assertEqual(report["before_after_repair_exhibit"]["report_kind"], "before-after-repair-exhibit-rollup")
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["source_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["bound_unit_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["verified_repair_source_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["auto_recovered_unit_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["verified_baseline_unit_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["missing_verified_baseline_unit_count"], 0)
        self.assertTrue(report["before_after_repair_exhibit"]["rollup"]["all_units_verified_baseline_bound"])
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["unsafe_reduced_by"], 2)
        self.assertFalse(report["before_after_repair_exhibit"]["rollup"]["semantic_gate"])
        self.assertFalse(report["before_after_repair_exhibit"]["rollup"]["generated_draft_semantic_pass"])
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["translation_coverage_numerator"], 0)
        self.assertEqual(
            report["before_after_repair_exhibit"]["sources"][0]["before_after_units"][0]["unit_id"],
            "flashdb/real-fdb-calc-crc32",
        )
        before_after_unit = report["before_after_repair_exhibit"]["sources"][0]["before_after_units"][0]
        self.assertIn("baseline_verification", before_after_unit)
        self.assertEqual(
            before_after_unit["baseline_verification"],
            {
                "path": "validation/evidence/baseline-verification.json",
                "sha256": "e" * 64,
                "status": "passed",
                "semantic_pass": True,
                "semantic_claim_source": "verified_unsafe_baseline_gates",
                "generated_draft_semantic_pass": False,
            },
        )
        self.assertEqual(before_after_unit["repair_rounds"], 1)
        self.assertTrue(before_after_unit["auto_recovered"])
        self.assertEqual(before_after_unit["root_cause_key"], "unsafe_baseline_requires_repair")
        self.assertEqual(
            before_after_unit["repair_history"],
            {
                "patch_events_path": "target/demo/retry-repair-history.jsonl",
                "patch_events_sha256": "f" * 64,
                "rollback_ids": ["rollback-001"],
                "statuses": ["failed", "passed", "verified"],
                "verified": True,
            },
        )
        self.assertEqual(before_after_unit["patch_origin"]["source"], "accepted_safe_evidence")
        self.assertTrue(before_after_unit["patch_origin"]["accepted_patch_bound"])
        self.assertFalse(before_after_unit["patch_origin"]["opencode_session_bound"])
        self.assertTrue(before_after_unit["patch_origin"]["repair_history_bound"])
        self.assertFalse(before_after_unit["patch_origin"]["semantic_gate"])
        self.assertEqual(before_after_unit["patch_origin"]["translation_coverage_numerator"], 0)
        self.assertEqual(before_after_unit["safety_loop_provenance"]["status"], "accepted_evidence_bound")
        self.assertEqual(before_after_unit["safety_loop_provenance"]["patch_source"], "accepted_safe_evidence")
        self.assertEqual(before_after_unit["safety_loop_provenance"]["baseline_verification_status"], "passed")
        self.assertEqual(before_after_unit["safety_loop_provenance"]["unsafe_delta"]["reduced_by"], 2)
        self.assertFalse(before_after_unit["safety_loop_provenance"]["opencode_session_bound"])
        self.assertTrue(before_after_unit["safety_loop_provenance"]["repair_history_bound"])
        self.assertEqual(before_after_unit["safety_loop_provenance"]["repair_rounds"], 1)
        self.assertTrue(before_after_unit["safety_loop_provenance"]["auto_recovered"])
        self.assertFalse(before_after_unit["safety_loop_provenance"]["semantic_gate"])
        self.assertEqual(before_after_unit["safety_loop_provenance"]["translation_coverage_numerator"], 0)
        self.assertFalse(report["before_after_repair_exhibit"]["semantic_gate"])
        self.assertFalse(report["before_after_repair_exhibit"]["generated_draft_semantic_pass"])
        self.assertEqual(report["before_after_repair_exhibit"]["translation_coverage_numerator"], 0)
        self.assertEqual(report["harness_architecture_summary"]["graph_runtime"], "opencode-harness-langgraph-inspired")
        self.assertEqual(report["harness_architecture_summary"]["repair_round_cap"], 5)
        self.assertIn("planner", report["harness_architecture_summary"]["roles"])
        self.assertFalse(report["harness_architecture_summary"]["semantic_gate"])
        contract_matrix = report["harness_architecture_summary"]["contract_matrix"]
        self.assertEqual(
            [entry["stage"] for entry in contract_matrix],
            ["plan", "translate", "verify", "repair", "report"],
        )
        translate_contract = next(entry for entry in contract_matrix if entry["stage"] == "translate")
        self.assertIn("worker", translate_contract["roles"])
        self.assertIn("handoff_contract", translate_contract["artifacts"])
        self.assertIn("opencode_session_evidence", translate_contract["artifacts"])
        self.assertIn("opencode_contract_verification", translate_contract["validators"])
        self.assertFalse(translate_contract["semantic_gate"])
        self.assertFalse(translate_contract["chat_output_is_evidence"])
        self.assertTrue(all(entry["semantic_gate"] is False for entry in contract_matrix))
        self.assertEqual(report["proof_classes"]["all"], ["local-simulation"])
        self.assertEqual(report["proof_class_rollup"]["highest_proof_class"], "local-simulation")
        self.assertFalse(report["proof_classes"]["has_competition_exact"])
        known_gap_ids = [gap["gap_id"] for gap in report["known_gaps"]]
        self.assertIn("local_simulation_not_competition_exact", known_gap_ids)
        self.assertNotIn("c2rust_baseline_output_still_not_verified_here", known_gap_ids)
        self.assertIn("accepted_evidence_is_not_translator_generated_coverage", report["must_not_claim"])
        self.assertIn("opencode_chat_output_is_semantic_evidence", report["must_not_claim"])
        self.assertIn("run_judge_entrypoints", report["reproduction_commands"])
        self.assertEqual(len(report["reproduction_commands"]["entrypoints"]), 2)
        publication_manifest = report["publication_manifest"]
        self.assertEqual(publication_manifest["report_kind"], "publication-manifest")
        self.assertEqual(publication_manifest["bundle_version"], 1)
        self.assertEqual(publication_manifest["publication_scope"], "internal_preview_full")
        self.assertEqual(publication_manifest["source_commit"]["status"], "present")
        self.assertRegex(publication_manifest["source_commit"]["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(publication_manifest["repo_commit"], publication_manifest["source_commit"])
        self.assertEqual(publication_manifest["target_source_pin"]["target_id"], "flashdb")
        self.assertEqual(publication_manifest["target_source_pin"]["branch"], "competition")
        self.assertEqual(
            publication_manifest["target_source_pin"]["canonical_commit"],
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        )
        self.assertEqual(publication_manifest["judge_config"]["path"], "unknown")
        self.assertEqual(publication_manifest["judge_entrypoints_run_report"], report["judge_entrypoints_run_report"])
        self.assertEqual(publication_manifest["readiness_report"], report["readiness_report"])
        self.assertEqual(publication_manifest["judge_milestone_bundle"]["path"], repo_relative(out_path))
        self.assertEqual(publication_manifest["competition_config_archive"]["status"], "absent")
        self.assertEqual(
            [entry["id"] for entry in publication_manifest["published_entrypoints"]],
            ["before_after_judge_demo", "opencode_multi_worker_evaluate_profile"],
        )
        self.assertEqual(publication_manifest["published_entrypoints"][0]["proof_class"], "local-simulation")
        self.assertGreaterEqual(publication_manifest["published_artifact_count"], 6)
        self.assertTrue(
            all(ref["status"] == "present" and "sha256" in ref for ref in publication_manifest["published_artifact_refs"])
        )
        self.assertEqual(publication_manifest["reproduction_commands"], report["reproduction_commands"])
        self.assertEqual(publication_manifest["known_gaps"], report["known_gaps"])
        self.assertIn("semantic acceptance", publication_manifest["known_non_goals"])
        release_tag_readiness = publication_manifest["release_tag_readiness"]
        self.assertEqual(release_tag_readiness["report_kind"], "release-tag-readiness")
        self.assertEqual(release_tag_readiness["status"], "not_tagged")
        self.assertIsNone(release_tag_readiness["tag_name"])
        self.assertIsNone(release_tag_readiness["tag_target_commit"])
        self.assertFalse(release_tag_readiness["tag_matches_repo_commit"])
        self.assertEqual(release_tag_readiness["remote_release_notes_status"], "not_published")
        self.assertEqual(release_tag_readiness["external_review_record_status"], "not_recorded")
        self.assertFalse(release_tag_readiness["external_milestone_claim_ready"])
        self.assertFalse(release_tag_readiness["semantic_gate"])
        self.assertEqual(release_tag_readiness["translation_coverage_numerator"], 0)
        self.assertFalse(publication_manifest["claim_boundary"]["semantic_gate"])
        self.assertFalse(publication_manifest["claim_boundary"]["publication_manifest_is_semantic_gate"])
        self.assertEqual(publication_manifest["claim_boundary"]["translation_coverage_numerator"], 0)
        quantitative_evaluation = report["quantitative_evaluation"]
        self.assertEqual(quantitative_evaluation["report_kind"], "quantitative-evaluation-scorecard")
        self.assertEqual(quantitative_evaluation["evaluation_scope"], "bounded-mvp")
        self.assertFalse(quantitative_evaluation["semantic_gate"])
        self.assertFalse(quantitative_evaluation["generated_draft_semantic_pass"])
        self.assertEqual(quantitative_evaluation["translation_coverage_numerator"], 0)
        self.assertFalse(quantitative_evaluation["claim_boundary"]["semantic_gate"])
        self.assertFalse(quantitative_evaluation["claim_boundary"]["scorecard_is_semantic_gate"])
        self.assertEqual(quantitative_evaluation["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(quantitative_evaluation["project_slice_counts"]["workflow_units_total"], 3)
        self.assertEqual(quantitative_evaluation["project_slice_counts"]["workflow_units_converged"], 3)
        self.assertEqual(quantitative_evaluation["project_slice_counts"]["before_after_bound_unit_count"], 1)
        self.assertEqual(quantitative_evaluation["outcome_counts"]["accepted_evidence_semantic_pass_count"], 3)
        self.assertEqual(quantitative_evaluation["outcome_counts"]["translator_generated_semantic_pass_count"], 0)
        self.assertEqual(quantitative_evaluation["outcome_counts"]["blocked_repair_count"], 0)
        self.assertEqual(quantitative_evaluation["outcome_counts"]["human_interventions"], 0)
        self_heal_classification = quantitative_evaluation["self_heal_classification"]
        self.assertEqual(self_heal_classification["report_kind"], "self-heal-classification")
        self.assertEqual(self_heal_classification["status"], "none")
        self.assertEqual(self_heal_classification["blocked_repair_count"], 0)
        self.assertEqual(self_heal_classification["next_action_count"], 0)
        self.assertEqual(self_heal_classification["sample_next_action_limit"], 5)
        self.assertEqual(self_heal_classification["sample_next_actions"], [])
        self.assertFalse(self_heal_classification["semantic_gate"])
        self.assertEqual(self_heal_classification["translation_coverage_numerator"], 0)
        progress_delta = report["progress_delta_ledger"]
        self.assertEqual(progress_delta["report_kind"], "progress-delta-ledger")
        self.assertFalse(progress_delta["semantic_gate"])
        self.assertFalse(progress_delta["generated_draft_semantic_pass"])
        self.assertEqual(progress_delta["translation_coverage_numerator"], 0)
        self.assertEqual(progress_delta["capability_delta"]["ledger_count"], 2)
        self.assertEqual(progress_delta["capability_delta"]["delta_count"], 2)
        self.assertEqual(progress_delta["capability_delta"]["translator_generated_semantic_pass_count"], 0)
        self.assertEqual(progress_delta["capability_delta"]["accepted_evidence_semantic_pass_count"], 3)
        self.assertEqual(progress_delta["governance_delta"]["delta_count"], 4)
        self.assertEqual(progress_delta["governance_delta"]["verification_command_count"], 6)
        self.assertEqual(progress_delta["governance_delta"]["route_decision_artifacts"], 4)
        self.assertEqual(progress_delta["workflow_delta"]["workflow_units_converged"], 3)
        self.assertEqual(progress_delta["workflow_delta"]["repair_history_unit_count"], 1)
        self.assertEqual(quantitative_evaluation["unsafe_reduction"]["status"], "measured")
        self.assertEqual(quantitative_evaluation["unsafe_reduction"]["baseline_total_unsafe"], 2)
        self.assertEqual(quantitative_evaluation["unsafe_reduction"]["current_total_unsafe"], 0)
        self.assertEqual(quantitative_evaluation["unsafe_reduction"]["reduced_by"], 2)
        self.assertEqual(quantitative_evaluation["unsafe_reduction"]["scope"], "partial")
        raw_c2rust = quantitative_evaluation["baseline_comparison"]["raw_c2rust"]
        self.assertEqual(raw_c2rust["status"], "manifest_status_observed")
        self.assertEqual(raw_c2rust["c2rust_baseline_rollup"]["unique_manifest_count"], 2)
        self.assertEqual(raw_c2rust["c2rust_baseline_rollup"]["source_report_count"], 2)
        self.assertEqual(raw_c2rust["c2rust_baseline_rollup"]["status_counts"], {"skipped": 2})
        self.assertEqual(raw_c2rust["c2rust_baseline_rollup"]["compile_passed_count"], 0)
        self.assertFalse(raw_c2rust["c2rust_baseline_rollup"]["semantic_gate"])
        self.assertEqual(raw_c2rust["c2rust_baseline_rollup"]["translation_coverage_numerator"], 0)
        self.assertFalse(raw_c2rust["semantic_acceptance_claimed"])
        self.assertEqual(
            quantitative_evaluation["baseline_comparison"]["typed_ir_route"]["tracked_route_decision_artifacts"],
            4,
        )
        self.assertEqual(
            quantitative_evaluation["baseline_comparison"]["opencode_llm_worker"]["status"],
            "command_contract_executed",
        )
        self.assertFalse(
            quantitative_evaluation["baseline_comparison"]["opencode_llm_worker"]["chat_output_is_evidence"]
        )
        self.assertEqual(
            quantitative_evaluation["baseline_comparison"]["handwritten_reference"][
                "accepted_evidence_semantic_pass_count"
            ],
            3,
        )
        self.assertFalse(
            quantitative_evaluation["baseline_comparison"]["handwritten_reference"][
                "counts_as_translator_generated_coverage"
            ]
        )
        self.assertEqual(report["retention_policy"]["report_kind"], "milestone-retention-policy")
        self.assertTrue(out_path.is_file())
        self.assertEqual(json.loads(out_path.read_text(encoding="utf-8")), report)

    def test_publication_archive_ref_preserves_external_refs_for_release_notes(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        ref = bundle.publication_archive_ref(
            {
                "status": "present",
                "root": "config/competition-env",
                "report_kind": "competition-config-archive",
                "files": {
                    "config/competition-env/bundle-manifest.json": {
                        "path": "config/competition-env/bundle-manifest.json",
                        "sha256": "1" * 64,
                        "status": "present",
                    }
                },
                "external_refs": {
                    ".opencode/agents/c2rust-migrator.md": {
                        "path": ".opencode/agents/c2rust-migrator.md",
                        "sha256": "3" * 64,
                        "status": "present",
                        "role": "opencode-agent-runbook",
                    },
                },
            }
        )

        self.assertEqual(ref["external_ref_count"], 1)
        self.assertNotIn(".codex/skills/c2rust-migration/SKILL.md", ref["external_refs"])
        self.assertEqual(
            ref["external_refs"][".opencode/agents/c2rust-migrator.md"]["role"],
            "opencode-agent-runbook",
        )

    def test_evidence_policy_compliance_failure_blocks_milestone(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        evidence_cost_retention = bundle.build_evidence_cost_retention_rollup(
            [
                {
                    "entrypoint_id": "competition_environment_smoke",
                    "status": "passed",
                    "policy_compliance": {
                        "policy_tier": "release",
                        "status": "failed",
                        "failed_gates": ["diagnostic_host_metadata"],
                    },
                    "artifact_count": 1,
                    "total_bytes": 10,
                    "pipeline_count": 1,
                    "runtime_observation_count": 0,
                    "runtime_total_duration_ms": 0,
                    "runtime_max_duration_ms": 0,
                    "retention_classes": {},
                    "claim_anchor_issue_count": 0,
                    "profile_hash_issue_count": 0,
                    "diagnostic_host_metadata_count": 1,
                }
            ]
        )

        self.assertFalse(
            evidence_cost_retention["rollup"]["policy_compliance"]["all_sources_policy_passed"]
        )
        self.assertEqual(
            evidence_cost_retention["rollup"]["policy_compliance"]["failed_gate_counts"],
            {"diagnostic_host_metadata": 1},
        )
        blockers = bundle.milestone_blockers(
            {"status": "passed", "summary": {"claim_boundary": {}}},
            {"all_entrypoints_executed": True, "validation_status": "passed"},
            {},
            run_report_contract=[],
            proof_class_contract_errors=[],
            exact_host_revalidation_errors=[],
            opencode_policy={"enabled": False},
            core_translation_quality={
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            before_after_repair_exhibit={"rollup": {}},
            blocked_repairs_rollup={"rollup": {"status_counts": {}}},
            route_governance_metrics={"rollup": {}},
            evidence_cost_retention=evidence_cost_retention,
            opencode_runtime={"enabled_entrypoint_count": 0},
        )

        self.assertIn("evidence_policy_compliance_must_pass", blockers)

    def test_progress_delta_ledger_uses_before_after_repair_when_workflow_metrics_are_sparse(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-progress-repair-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        metrics_path = temp_dir / "before-after" / "summary" / "workflow-metrics.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 0,
                "avg_repair_rounds": 0.0,
                "auto_recovery_rate": 0.0,
                "human_interventions": 0,
                "llm_calls": 0,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                },
                "per_unit_statuses": [{"unit_id": "flashdb/real-fdb-calc-crc32"}],
            },
        )
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "final_gate_status": "failed",
                    "semantic_pass_count": 0,
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "before_after_units": [
                        {
                            "unit_id": "flashdb/real-fdb-calc-crc32",
                            "status": "converged",
                            "accepted_patch": {"path": "validation/evidence/accepted.patch", "sha256": "c" * 64},
                            "unsafe_reduction": {
                                "status": "measured",
                                "baseline_total_unsafe": 2,
                                "current_total_unsafe": 0,
                                "reduced_by": 2,
                            },
                        }
                    ],
                    "repair_summary": {
                        "status": "verified",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 1,
                        "auto_recovered_unit_count": 1,
                        "rollback_evidence_count": 5,
                    },
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 2,
                        "current_total_unsafe": 0,
                        "reduced_by": 2,
                    },
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(metrics_path),
                            "judge_evidence_index": repo_relative(index_path),
                        },
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        workflow_delta = report["progress_delta_ledger"]["workflow_delta"]
        self.assertEqual(workflow_delta["repair_history_unit_count"], 1)
        self.assertEqual(workflow_delta["observed_repair_unit_count"], 1)
        self.assertEqual(workflow_delta["auto_recovered_unit_count"], 1)
        self.assertEqual(workflow_delta["rollback_evidence_count"], 5)
        self.assertEqual(workflow_delta["before_after_repair_source_count"], 1)
        self.assertEqual(workflow_delta["repair_delta_source_count"], 1)
        self.assertFalse(report["progress_delta_ledger"]["semantic_gate"])
        self.assertEqual(report["progress_delta_ledger"]["translation_coverage_numerator"], 0)

    def test_bundle_matches_schema_and_rejects_expanded_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-schema-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        metrics_path = temp_dir / "before-after" / "summary" / "workflow-metrics.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 1,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                },
            },
        )
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "harness_architecture": {
                    "graph_runtime": "opencode-harness-langgraph-inspired",
                    "graph_nodes": ["load_plan", "fanout_workers", "worker", "repair_retry", "merge", "report"],
                    "worker_count": 1,
                    "retry_policy": {"round_cap": 5, "checkpoint": "repair_hints"},
                    "architecture_contracts": {
                        "agent_coordination": {
                            "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                            "checkpoint_backend": "sqlite",
                            "chat_output_is_evidence": False,
                            "semantic_gate": False,
                        }
                    },
                },
                "core_translation_quality": {
                    "final_gate_status": "passed",
                    "semantic_pass_count": 1,
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 2,
                        "current_total_unsafe": 0,
                        "reduced_by": 2,
                    },
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "readiness_report": None,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "purpose": "core-translation-before-after-exhibit",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "run_id": "schema-test",
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(metrics_path),
                            "judge_evidence_index": repo_relative(index_path),
                        },
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        jsonschema.validate(report, schema)

        for field in (
            "verified_baseline_unit_count",
            "missing_verified_baseline_unit_count",
            "all_units_verified_baseline_bound",
        ):
            with self.subTest(missing_before_after_rollup_field=field):
                missing_baseline_rollup = json.loads(json.dumps(report))
                missing_baseline_rollup["before_after_repair_exhibit"]["rollup"].pop(field)
                with self.assertRaises(jsonschema.exceptions.ValidationError):
                    jsonschema.validate(missing_baseline_rollup, schema)

        invalid_baseline_rollup_values = {
            "verified_baseline_unit_count": -1,
            "missing_verified_baseline_unit_count": -1,
            "all_units_verified_baseline_bound": "true",
        }
        for field, value in invalid_baseline_rollup_values.items():
            with self.subTest(invalid_before_after_rollup_field=field):
                invalid_baseline_rollup = json.loads(json.dumps(report))
                invalid_baseline_rollup["before_after_repair_exhibit"]["rollup"][field] = value
                with self.assertRaises(jsonschema.exceptions.ValidationError):
                    jsonschema.validate(invalid_baseline_rollup, schema)

        expanded = json.loads(json.dumps(report))
        expanded["claim_scope"]["semantic_acceptance_ready"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["core_translation_quality"]["translation_coverage_numerator"] = 1
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_evidence_cost = json.loads(json.dumps(report))
        missing_evidence_cost.pop("evidence_cost_retention")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_evidence_cost, schema)

        missing_contract_matrix = json.loads(json.dumps(report))
        missing_contract_matrix["harness_architecture_summary"].pop("contract_matrix")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_contract_matrix, schema)

        valid_matrix = report["harness_architecture_summary"]["contract_matrix"]
        contract_matrix_rewrites = {
            "missing_repair": [
                entry for entry in valid_matrix if entry["stage"] != "repair"
            ],
            "duplicate_translate": [
                valid_matrix[0],
                valid_matrix[1],
                valid_matrix[2],
                json.loads(json.dumps(valid_matrix[1])),
                valid_matrix[4],
            ],
            "wrong_order": [
                valid_matrix[1],
                valid_matrix[0],
                valid_matrix[2],
                valid_matrix[3],
                valid_matrix[4],
            ],
            "unknown_stage": [
                valid_matrix[0],
                valid_matrix[1],
                valid_matrix[2],
                valid_matrix[3],
                {**valid_matrix[4], "stage": "publish"},
            ],
        }
        for label, rewritten_matrix in contract_matrix_rewrites.items():
            with self.subTest(label=label):
                expanded = json.loads(json.dumps(report))
                expanded["harness_architecture_summary"]["contract_matrix"] = rewritten_matrix
                with self.assertRaises(jsonschema.exceptions.ValidationError):
                    jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["harness_architecture_summary"]["contract_matrix"][1]["chat_output_is_evidence"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_publication_manifest = json.loads(json.dumps(report))
        missing_publication_manifest.pop("publication_manifest")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_publication_manifest, schema)

        expanded = json.loads(json.dumps(report))
        expanded["publication_manifest"]["claim_boundary"]["publication_manifest_is_semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["publication_manifest"]["claim_boundary"]["semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["publication_manifest"]["claim_boundary"]["generated_draft_semantic_pass"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["publication_manifest"]["claim_boundary"]["translation_coverage_numerator"] = 1
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_quantitative_evaluation = json.loads(json.dumps(report))
        missing_quantitative_evaluation.pop("quantitative_evaluation")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_quantitative_evaluation, schema)

        missing_progress_delta = json.loads(json.dumps(report))
        missing_progress_delta.pop("progress_delta_ledger")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_progress_delta, schema)

        expanded = json.loads(json.dumps(report))
        expanded["progress_delta_ledger"]["semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["progress_delta_ledger"]["translation_coverage_numerator"] = 1
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_repair_delta = json.loads(json.dumps(report))
        missing_repair_delta["progress_delta_ledger"]["workflow_delta"].pop("observed_repair_unit_count")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_repair_delta, schema)

        missing_repair_delta = json.loads(json.dumps(report))
        missing_repair_delta["progress_delta_ledger"]["workflow_delta"].pop("repair_delta_source_count")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_repair_delta, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["claim_boundary"]["scorecard_is_semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["claim_boundary"]["translation_coverage_numerator"] = 1
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["baseline_comparison"]["raw_c2rust"][
            "semantic_acceptance_claimed"
        ] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_raw_c2rust_rollup = json.loads(json.dumps(report))
        missing_raw_c2rust_rollup["quantitative_evaluation"]["baseline_comparison"]["raw_c2rust"].pop(
            "c2rust_baseline_rollup"
        )
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_raw_c2rust_rollup, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["baseline_comparison"]["raw_c2rust"]["c2rust_baseline_rollup"][
            "translation_coverage_numerator"
        ] = 1
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["baseline_comparison"]["raw_c2rust"]["c2rust_baseline_rollup"][
            "compile_semantic_pass_count"
        ] = 1
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["baseline_comparison"]["opencode_llm_worker"][
            "chat_output_is_evidence"
        ] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["quantitative_evaluation"]["baseline_comparison"]["handwritten_reference"][
            "counts_as_translator_generated_coverage"
        ] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_blocked_repairs = json.loads(json.dumps(report))
        missing_blocked_repairs.pop("blocked_repairs_rollup")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_blocked_repairs, schema)

        expanded = json.loads(json.dumps(report))
        expanded["blocked_repairs_rollup"]["semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_blocked_next_actions = json.loads(json.dumps(report))
        missing_blocked_next_actions["blocked_repairs_rollup"]["rollup"].pop("next_actions")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_blocked_next_actions, schema)

        missing_blocked_reason_counts = json.loads(json.dumps(report))
        missing_blocked_reason_counts["blocked_repairs_rollup"]["rollup"].pop("blocked_reason_counts")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_blocked_reason_counts, schema)

        missing_source_span_kind_counts = json.loads(json.dumps(report))
        missing_source_span_kind_counts["blocked_repairs_rollup"]["rollup"].pop("source_span_kind_counts")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_source_span_kind_counts, schema)

        missing_blocked_claim = json.loads(json.dumps(report))
        missing_blocked_claim["must_not_claim"].remove("blocked_repairs_are_not_translation_success")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_blocked_claim, schema)

    def test_quantitative_evaluation_keeps_opencode_chat_output_non_evidence_when_boundary_missing(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        scorecard = bundle.build_quantitative_evaluation(
            workflow_metrics={"rollup": {}},
            route_governance_metrics={"rollup": {}},
            before_after_repair_exhibit={"rollup": {}},
            blocked_repairs_rollup={"rollup": {}},
            unsafe_scope={},
            semantic_evidence={},
            opencode_runtime={"enabled_entrypoint_count": 1, "all_contracts_executed": False},
            proof_classes={"entrypoints": []},
            publishability={},
        )

        self.assertEqual(
            scorecard["baseline_comparison"]["opencode_llm_worker"]["status"],
            "command_contract_incomplete",
        )
        self.assertFalse(scorecard["baseline_comparison"]["opencode_llm_worker"]["chat_output_is_evidence"])
        self.assertFalse(scorecard["claim_boundary"]["semantic_gate"])
        self.assertFalse(scorecard["semantic_gate"])
        self.assertEqual(scorecard["translation_coverage_numerator"], 0)

    def test_publishability_requires_complete_opencode_preflight_contract(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        publishability = bundle.build_publishability(
            status="passed",
            readiness={"all_entrypoints_executed": True},
            proof_classes={"all_entrypoints_competition_exact": True},
            blockers=[],
            opencode_runtime={
                "enabled_entrypoint_count": 1,
                "preflight_proof_summary": {
                    "status": "passed",
                    "opencode_command": "opencode",
                    "opencode_model": "GLM-5.1",
                    "required_model": "GLM-5.1",
                    "model_listed": True,
                },
            },
        )

        self.assertEqual(publishability["status"], "internal_preview")
        self.assertFalse(publishability["external_milestone_claim_ready"])
        self.assertFalse(publishability["external_milestone"])
        self.assertEqual(publishability["required_agent"], "c2rust-migrator")
        self.assertFalse(publishability["opencode_glm51_publishable"])

    def test_proof_classes_do_not_verify_competition_host_from_proof_class_string_only(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        proof_classes = bundle.build_proof_classes(
            [
                {
                    "id": "competition_environment_smoke",
                    "proof_class": "competition-exact",
                    "run_id": "smoke-without-host-attestation",
                }
            ]
        )

        self.assertTrue(proof_classes["all_entrypoints_competition_exact"])
        self.assertFalse(proof_classes["competition_exact_host_verified"])
        self.assertEqual(proof_classes["host_attestation_missing_entrypoints"], ["competition_environment_smoke"])

    def test_publishability_requires_competition_host_attestation_not_only_exact_proof_string(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        proof_classes = bundle.build_proof_classes(
            [
                {
                    "id": "competition_environment_smoke",
                    "proof_class": "competition-exact",
                    "run_id": "smoke-without-host-attestation",
                }
            ]
        )
        runtime_env = {"env_sha256": "runtime-env"}
        publishability = bundle.build_publishability(
            status="passed",
            readiness={"all_entrypoints_executed": True},
            proof_classes=proof_classes,
            blockers=[],
            opencode_runtime={
                "enabled_entrypoint_count": 1,
                "preflight_proof_summary": {
                    "status": "passed",
                    "required_when_opencode_runtime_enabled": True,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                    "translation_coverage_numerator": 0,
                    "opencode_command": "opencode",
                    "opencode_agent": "c2rust-migrator",
                    "opencode_model": "GLM-5.1",
                    "opencode_variant": "max",
                    "required_model": "GLM-5.1",
                    "model_availability_status": "available",
                    "model_listed": True,
                    "process_returncode": 0,
                    "contract_status": "executed",
                    "marker_exists": True,
                    "opencode_run_launched": True,
                    "opencode_run_argv_bound": True,
                    "model_probe_argv": ["opencode", "models"],
                    "opencode_runtime_env": runtime_env,
                    "opencode_runtime_env_sha256": runtime_env["env_sha256"],
                },
            },
        )

        self.assertEqual(publishability["status"], "internal_preview")
        self.assertFalse(publishability["external_milestone_claim_ready"])
        self.assertFalse(publishability["competition_exact_publishable"])
        self.assertEqual(publishability["required_agent"], "c2rust-migrator")
        self.assertTrue(publishability["opencode_glm51_publishable"])

    def test_publishability_requires_competition_opencode_agent_and_variant(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        def publishability_for(summary_overrides: dict) -> dict:
            preflight_summary = {
                "status": "passed",
                "required_when_opencode_runtime_enabled": True,
                "chat_output_is_evidence": False,
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
                "opencode_command": "opencode",
                "opencode_agent": "c2rust-migrator",
                "opencode_model": "GLM-5.1",
                "opencode_variant": "max",
                "required_model": "GLM-5.1",
                "model_availability_status": "available",
                "model_listed": True,
                "process_returncode": 0,
                "contract_status": "executed",
                "marker_exists": True,
                "opencode_run_launched": True,
                "opencode_run_argv_bound": True,
                "model_probe_argv": ["opencode", "models"],
                "opencode_runtime_env": {"env_sha256": "runtime-env"},
                "opencode_runtime_env_sha256": "runtime-env",
            }
            preflight_summary.update(summary_overrides)
            return bundle.build_publishability(
                status="passed",
                readiness={"all_entrypoints_executed": True},
                proof_classes={
                    "all_entrypoints_competition_exact": True,
                    "competition_exact_host_verified": True,
                },
                blockers=[],
                opencode_runtime={
                    "enabled_entrypoint_count": 1,
                    "preflight_proof_summary": preflight_summary,
                },
            )

        for overrides in [{"opencode_agent": "general"}, {"opencode_variant": "small"}]:
            with self.subTest(overrides=overrides):
                publishability = publishability_for(overrides)

                self.assertFalse(publishability["opencode_glm51_publishable"])
                self.assertFalse(publishability["external_milestone_claim_ready"])
                self.assertEqual(publishability["status"], "internal_preview")

    def test_known_gaps_keep_c2rust_baseline_gap_without_verified_baseline_exhibit(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        gaps = bundle.build_known_gaps(
            proof_classes={"has_competition_exact": False},
            opencode_runtime={"enabled_entrypoint_count": 0},
            before_after_repair_exhibit={
                "sources": [
                    {
                        "before_after_units": [
                            {
                                "baseline_verification": {
                                    "status": "blocked",
                                    "semantic_claim_source": "blocked_missing_direct_c2rust_replay",
                                    "generated_draft_semantic_pass": False,
                                }
                            }
                        ]
                    }
                ]
            },
        )

        self.assertIn("c2rust_baseline_output_still_not_verified_here", [gap["gap_id"] for gap in gaps])

    def test_known_gaps_keep_c2rust_baseline_gap_when_only_some_units_have_verified_baseline(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        gaps = bundle.build_known_gaps(
            proof_classes={"has_competition_exact": False},
            opencode_runtime={"enabled_entrypoint_count": 0},
            before_after_repair_exhibit={
                "sources": [
                    {
                        "before_after_units": [
                            {
                                "unit_id": "demo/verified",
                                "baseline_verification": {
                                    "path": "validation/evidence/verified-baseline.json",
                                    "sha256": "a" * 64,
                                    "status": "passed",
                                    "semantic_pass": True,
                                    "semantic_claim_source": "verified_unsafe_baseline_gates",
                                    "generated_draft_semantic_pass": False,
                                },
                            },
                            {
                                "unit_id": "demo/missing",
                                "repair_history": {"verified": True},
                            },
                        ]
                    }
                ]
            },
        )

        self.assertIn("c2rust_baseline_output_still_not_verified_here", [gap["gap_id"] for gap in gaps])

    def test_known_gaps_require_verified_baseline_semantic_pass(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        gaps = bundle.build_known_gaps(
            proof_classes={"has_competition_exact": False},
            opencode_runtime={"enabled_entrypoint_count": 0},
            before_after_repair_exhibit={
                "sources": [
                    {
                        "before_after_units": [
                            {
                                "unit_id": "demo/not-semantic-pass",
                                "baseline_verification": {
                                    "path": "validation/evidence/verified-baseline.json",
                                    "sha256": "a" * 64,
                                    "status": "passed",
                                    "semantic_pass": False,
                                    "semantic_claim_source": "verified_unsafe_baseline_gates",
                                    "generated_draft_semantic_pass": False,
                                },
                            },
                        ]
                    }
                ]
            },
        )

        self.assertIn("c2rust_baseline_output_still_not_verified_here", [gap["gap_id"] for gap in gaps])

    def test_known_gaps_require_verified_baseline_hash_binding_shape(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        gaps = bundle.build_known_gaps(
            proof_classes={"has_competition_exact": False},
            opencode_runtime={"enabled_entrypoint_count": 0},
            before_after_repair_exhibit={
                "sources": [
                    {
                        "before_after_units": [
                            {
                                "unit_id": "demo/bad-binding",
                                "baseline_verification": {
                                    "path": "",
                                    "sha256": "short",
                                    "status": "passed",
                                    "semantic_pass": True,
                                    "semantic_claim_source": "verified_unsafe_baseline_gates",
                                    "generated_draft_semantic_pass": False,
                                },
                            },
                        ]
                    }
                ]
            },
        )

        self.assertIn("c2rust_baseline_output_still_not_verified_here", [gap["gap_id"] for gap in gaps])

    def test_bundle_blocks_malformed_run_report_contract(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-malformed-run-report-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "report_kind": "wrong-report-kind",
                "status": "passed",
                "entrypoint_count": 2,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("run_report_schema_version_must_be_1", report["blockers"])
        self.assertIn("run_report_kind_must_be_judge_entrypoints_run_report", report["blockers"])
        self.assertIn("run_report_entrypoint_count_mismatch", report["blockers"])

    def test_bundle_blocks_missing_run_report_validation_even_if_readiness_claims_passed(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-missing-validation-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("run_report_validation_missing", report["blockers"])

    def test_bundle_blocks_unvalidated_key_artifacts_without_validation_expected_refs(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-unvalidated-key-artifact-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "headline": "Judge entrypoints passed: 1/1 executed; semantic_gate=false",
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {
                            "judge_evidence_index": "target/unvalidated/judge-evidence-index.json",
                        },
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {},
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn(
            "validated_artifact_binding_missing:before_after_judge_demo:judge_evidence_index",
            report["blockers"],
        )

    def test_bundle_blocks_proof_class_escalation_without_validation_contract(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-proof-escalation-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "competition-exact",
                        "key_artifacts": {},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "proof_class_contract": {
                        "status": "passed",
                        "entrypoints": {"before_after_judge_demo": "local-simulation"},
                    },
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("proof_class_contract_mismatch:before_after_judge_demo", report["blockers"])
        self.assertEqual(report["proof_classes"]["all"], ["local-simulation"])
        self.assertFalse(report["claim_scope"]["competition_exact_ready"])
        self.assertEqual(report["publishability"]["status"], "blocked")
        self.assertEqual(report["publishability"]["scope"], "blocked")
        self.assertEqual(report["publishability"]["publication_scope"], "blocked")
        self.assertFalse(report["publishability"]["external_milestone_claim_ready"])
        self.assertFalse(report["publishability"]["external_milestone"])
        self.assertEqual(report["publishability"]["required_agent"], "c2rust-migrator")
        self.assertEqual(report["publishability"]["blocker_count"], len(report["blockers"]))
        self.assertEqual(report["publishability"]["blockers"], report["blockers"])
        self.assertFalse(report["publishability"]["competition_exact_publishable"])

    def test_bundle_revalidates_exact_host_attestation_before_external_ready(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-forged-exact-host-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        fake_config_path = temp_dir / "missing-judge-entrypoints.json"
        preflight_fixture = write_opencode_preflight_fixture(temp_dir / "opencode", run_id="forged-exact-host")
        preflight_path = Path(preflight_fixture["preflight_path"])
        preflight_ref = {
            "path": repo_relative(preflight_path),
            "sha256": bundle.validator.sha256_file(preflight_path),
            "status": "present",
        }
        judge_index_path = temp_dir / "opencode" / "harness" / "judge-evidence-index.json"
        write_json(
            judge_index_path,
            {
                "judge_headline": {
                    "worker_count": 1,
                    "repair_round_cap": 5,
                    "semantic_gate": False,
                    "opencode_runtime": {
                        "enabled": True,
                        "worker_count": 1,
                        "all_contracts_executed": True,
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                },
                "opencode_agent_runtime": {
                    "runtime": "opencode",
                    "worker_count": 1,
                    "all_contracts_executed": True,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                    "opencode_preflight_report": preflight_ref,
                },
                "evidence_artifact_refs": {
                    "opencode_preflight_report": preflight_ref,
                },
            },
        )
        smoke_path = temp_dir / "smoke" / "summary" / "competition-smoke-summary.json"
        write_json(
            smoke_path,
            {
                "proof_class": "competition-exact",
                "run_id": "forged-exact-host",
                "execution_environment": {
                    "kind": "competition-host",
                    "system": "Linux",
                    "detected_ci": False,
                    "detected_wsl": False,
                    "competition_exact_host_attested": True,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "dry_run": False,
                "config": {
                    "path": repo_relative(fake_config_path),
                    "status": "present",
                    "sha256": "0" * 64,
                },
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "competition_environment_smoke",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "competition-exact",
                        "run_id": "forged-exact-host",
                        "key_artifacts": {},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "proof_class_contract": {
                        "status": "passed",
                        "entrypoints": {"competition_environment_smoke": "competition-exact"},
                    },
                    "entrypoints": [
                        {
                            "id": "competition_environment_smoke",
                            "expected_artifacts": {
                                "judge_evidence_index": {
                                    "path": repo_relative(judge_index_path),
                                    "status": "present",
                                    "sha256": bundle.validator.sha256_file(judge_index_path),
                                },
                                "competition_smoke_summary": {
                                    "path": repo_relative(smoke_path),
                                    "status": "present",
                                    "sha256": bundle.validator.sha256_file(smoke_path),
                                },
                            },
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("run_report_exact_host_revalidation_failed", report["blockers"])
        self.assertFalse(report["claim_scope"]["competition_exact_ready"])
        self.assertEqual(report["publishability"]["status"], "blocked")
        self.assertFalse(report["publishability"]["external_milestone_claim_ready"])
        self.assertFalse(report["competition_host_readiness"]["competition_exact_host_verified"])

    def test_exact_host_revalidation_rejects_bound_config_sha_drift(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-config-ref-drift-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "judge-entrypoints.json"
        write_json(config_path, {"schema_version": 1, "entrypoints": []})
        run_report = {
            "config": {
                "path": repo_relative(config_path),
                "status": "present",
                "sha256": "0" * 64,
            }
        }
        entrypoints = [
            {
                "id": "competition_environment_smoke",
                "proof_class": "competition-exact",
                "competition_exact_host_attested": True,
            }
        ]

        with mock.patch.object(
            bundle.validator,
            "validate_config",
            return_value={
                "status": "passed",
                "config": {"path": repo_relative(config_path)},
                "errors": [],
                "proof_class_contract": {
                    "status": "passed",
                    "entrypoints": {"competition_environment_smoke": "competition-exact"},
                },
            },
        ) as validate_config:
            result = bundle.build_exact_host_revalidation(run_report, entrypoints, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("run_report.config" in error and "sha256" in error for error in result["errors"]))
        validate_config.assert_not_called()

    def test_bundle_blocks_focused_run_from_external_milestone_claim(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-focused-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "headline": "Judge entrypoints passed: 1/4 executed; semantic_gate=false",
                    "readiness": {
                        "all_entrypoints_executed": False,
                        "executed_count": 1,
                        "configured_count": 4,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "key_artifacts": {},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("not_all_entrypoints_executed", report["blockers"])
        self.assertFalse(report["summary"]["external_milestone_claim_ready"])
        self.assertFalse(report["claim_boundary"]["semantic_gate"])

    def test_standalone_bundle_removes_stale_publication_siblings(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-stale-publication-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        stale_packet = temp_dir / "summary" / "public-release-packet.json"
        stale_notes = temp_dir / "summary" / "milestone-release-notes.md"
        stale_packet.parent.mkdir(parents=True, exist_ok=True)
        stale_packet.write_text('{"report_kind":"stale-public-release-packet"}\n', encoding="utf-8")
        stale_notes.write_text("# stale release notes\n", encoding="utf-8")
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "headline": "Judge entrypoints passed: 1/4 executed; semantic_gate=false",
                    "readiness": {
                        "all_entrypoints_executed": False,
                        "executed_count": 1,
                        "configured_count": 4,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "key_artifacts": {},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("not_all_entrypoints_executed", report["blockers"])
        self.assertFalse(stale_packet.exists())
        self.assertFalse(stale_notes.exists())

    def test_bundle_prefers_post_run_validation_artifact_refs_over_key_artifact_paths(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-validated-refs-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        metrics_path = temp_dir / "validated" / "summary" / "workflow-metrics.json"
        write_json(
            metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 1,
                "unsafe_reduction": {"status": "not_measured"},
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "multi_worker_evaluate_profile",
                        "status": "passed",
                        "exit_code": 0,
                        "key_artifacts": {"workflow_metrics": "target/missing/path/workflow-metrics.json"},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "multi_worker_evaluate_profile",
                            "expected_artifacts": {
                                "workflow_metrics": {
                                    "path": repo_relative(metrics_path),
                                    "sha256": bundle.validator.sha256_file(metrics_path),
                                    "status": "present",
                                }
                            },
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        workflow_ref = report["entrypoints"][0]["artifacts"]["workflow_metrics"]
        self.assertEqual(workflow_ref["path"], repo_relative(metrics_path))
        self.assertEqual(workflow_ref["status"], "present")
        self.assertIn("sha256", workflow_ref)
        self.assertEqual(report["workflow_metrics"]["rollup"]["source_count"], 1)

    def test_bundle_blocks_validator_expected_artifact_hash_drift(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-validated-drift-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "validated" / "harness" / "judge-evidence-index.json"
        write_json(index_path, {"report_kind": "judge-evidence-index", "judge_headline": {"opencode_runtime": {"enabled": False}}})
        validated_sha = bundle.validator.sha256_file(index_path)
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "judge_evidence_index": {
                                    "path": repo_relative(index_path),
                                    "sha256": validated_sha,
                                    "status": "present",
                                }
                            },
                        }
                    ],
                },
            },
        )
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "judge_headline": {
                    "opencode_runtime": {
                        "enabled": True,
                        "worker_count": 1,
                        "all_contracts_executed": True,
                    }
                },
                "opencode_agent_runtime": {
                    "runtime": "opencode",
                    "worker_count": 1,
                    "all_contracts_executed": True,
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        artifact_ref = report["entrypoints"][0]["artifacts"]["judge_evidence_index"]
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(artifact_ref["status"], "sha256_mismatch")
        self.assertEqual(artifact_ref["expected_sha256"], validated_sha)
        self.assertIn("validated_artifact_sha256_mismatch:before_after_judge_demo:judge_evidence_index", report["blockers"])
        self.assertEqual(report["opencode_runtime"]["enabled_entrypoint_count"], 0)

    def test_bundle_blocks_source_translation_coverage_or_generated_semantic_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-overclaim-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": True,
                        "translation_coverage_numerator": 1,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("source_generated_draft_semantic_pass_must_be_false", report["blockers"])
        self.assertIn("source_translation_coverage_numerator_must_be_zero", report["blockers"])
        self.assertFalse(report["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(report["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(report["semantic_evidence_rollup"]["translator_generated_semantic_pass_count"], 0)
        self.assertEqual(report["semantic_evidence_rollup"]["source_translation_coverage_numerator"], 1)

    def test_bundle_blocks_core_quality_artifact_translation_coverage_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-core-quality-overclaim-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "final_gate_status": "passed",
                    "semantic_pass_count": 1,
                    "translation_coverage_numerator": 1,
                    "generated_draft_semantic_pass": True,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"judge_evidence_index": repo_relative(index_path)},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "judge_evidence_index": artifact_ref(index_path),
                            },
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("core_quality_generated_draft_semantic_pass_must_be_false", report["blockers"])
        self.assertIn("core_quality_translation_coverage_numerator_must_be_zero", report["blockers"])

    def test_bundle_rolls_up_blocked_repairs_from_bound_route_metrics(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-blocked-repairs-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        route_metrics_path = temp_dir / "summary" / "route-governance-metrics-report.json"
        write_json(
            route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=0,
                tracked_route_decision_artifacts=1,
                tracked_slice_gate_contexts=1,
                s2_workflow_run_count=0,
                s2_reduced_by=0,
                blocked_repair_count=2,
            ),
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"route_governance_metrics_report": repo_relative(route_metrics_path)},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "route_governance_metrics_report": artifact_ref(route_metrics_path),
                            },
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        blocked = report["blocked_repairs_rollup"]["rollup"]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["blocked_repairs_rollup"]["report_kind"], "blocked-repairs-rollup")
        self.assertEqual(blocked["source_count"], 1)
        self.assertEqual(blocked["blocked_repair_count"], 2)
        self.assertEqual(blocked["slice_count"], 1)
        self.assertEqual(blocked["human_action_required_count"], 2)
        self.assertEqual(blocked["human_intervention_points"], ["Bind external callee semantics before promotion."])
        self.assertEqual(blocked["blocked_callees"], ["helper_blocked"])
        self.assertEqual(blocked["ir_feature_gap_kinds"], {"external_direct_callee_context": 2})
        self.assertEqual(
            blocked["blocked_reason_counts"],
            {"External callee semantics are not bound to oracle evidence.": 2},
        )
        self.assertEqual(blocked["source_span_kind_counts"], {"c_source": 2})
        self.assertEqual(
            blocked["smallest_next_tests"],
            [
                {
                    "kind": "callee_contract_replay",
                    "command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                    "expected_gate": "external callee contract is bound before candidate promotion",
                }
            ],
        )
        self.assertEqual(
            blocked["next_actions"],
            [
                {
                    "entrypoint_id": "before_after_judge_demo",
                    "repair_id": "repair-refused-1",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "pipeline_id": "validation/evidence/demo/auto-translation/refused",
                    "route": "typed_ir",
                    "status": "blocked",
                    "next_action": "bind_external_callee_semantics",
                    "smallest_next_test_kind": "callee_contract_replay",
                    "smallest_next_test_command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                    "expected_gate": "external callee contract is bound before candidate promotion",
                    "human_intervention_point": "Bind external callee semantics before promotion.",
                    "source_span": {
                        "file": "src/demo.c",
                        "line_start": 12,
                        "line_end": 14,
                    },
                    "source_span_kind": "c_source",
                }
            ],
        )
        self.assertFalse(report["blocked_repairs_rollup"]["semantic_gate"])
        self.assertFalse(report["blocked_repairs_rollup"]["generated_draft_semantic_pass"])
        self.assertEqual(report["blocked_repairs_rollup"]["translation_coverage_numerator"], 0)
        self.assertFalse(blocked["semantic_gate"])
        self.assertEqual(blocked["translation_coverage_numerator"], 0)
        classification = report["quantitative_evaluation"]["self_heal_classification"]
        self.assertEqual(classification["report_kind"], "self-heal-classification")
        self.assertEqual(classification["status"], "observed")
        self.assertEqual(classification["source"], "blocked_repairs_rollup")
        self.assertEqual(classification["blocked_repair_count"], 2)
        self.assertEqual(classification["human_action_required_count"], 2)
        self.assertEqual(classification["blocked_reason_counts"], blocked["blocked_reason_counts"])
        self.assertEqual(classification["ir_feature_gap_kinds"], blocked["ir_feature_gap_kinds"])
        self.assertEqual(classification["source_span_kind_counts"], blocked["source_span_kind_counts"])
        self.assertEqual(classification["route_counts"], {"typed_ir": 1})
        self.assertEqual(classification["next_action_counts"], {"bind_external_callee_semantics": 1})
        self.assertEqual(classification["smallest_next_test_kind_counts"], {"callee_contract_replay": 1})
        self.assertEqual(classification["next_action_count"], 1)
        self.assertEqual(classification["sample_next_action_limit"], 5)
        self.assertEqual(classification["sample_next_actions"], blocked["next_actions"])
        self.assertFalse(classification["semantic_gate"])
        self.assertFalse(classification["generated_draft_semantic_pass"])
        self.assertEqual(classification["translation_coverage_numerator"], 0)
        self.assertIn("blocked_repairs_are_not_translation_success", report["must_not_claim"])
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(report, schema)

        missing_self_heal_classification = json.loads(json.dumps(report))
        missing_self_heal_classification["quantitative_evaluation"].pop("self_heal_classification")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_self_heal_classification, schema)

        missing_self_heal_sample_route = json.loads(json.dumps(report))
        missing_self_heal_sample_route["quantitative_evaluation"]["self_heal_classification"]["sample_next_actions"][0].pop(
            "route"
        )
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_self_heal_sample_route, schema)

        expanded_self_heal_claim = json.loads(json.dumps(report))
        expanded_self_heal_claim["quantitative_evaluation"]["self_heal_classification"]["semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded_self_heal_claim, schema)

        missing_next_action_route = json.loads(json.dumps(report))
        missing_next_action_route["blocked_repairs_rollup"]["rollup"]["next_actions"][0].pop("route")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_next_action_route, schema)

        missing_next_action_command = json.loads(json.dumps(report))
        missing_next_action_command["blocked_repairs_rollup"]["rollup"]["next_actions"][0].pop("next_action")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_next_action_command, schema)

    def test_bundle_blocks_stale_or_incomplete_blocked_repairs_rollup(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-stale-blocked-repairs-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        route_metrics_path = temp_dir / "summary" / "route-governance-metrics-report.json"
        write_json(
            route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=0,
                tracked_route_decision_artifacts=1,
                tracked_slice_gate_contexts=1,
                s2_workflow_run_count=0,
                s2_reduced_by=0,
                blocked_repair_count=1,
                blocked_repairs_status="stale",
            ),
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"route_governance_metrics_report": repo_relative(route_metrics_path)},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("blocked_repairs_rollup_stale_or_incomplete", report["blockers"])

    def test_bundle_blocks_inconsistent_repair_accounting_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-repair-accounting-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "final_gate_status": "passed",
                    "semantic_pass_count": 1,
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "repair_summary": {
                        "status": "verified",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 1,
                        "auto_recovered_unit_count": 2,
                        "rollback_evidence_count": 0,
                    },
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 1,
                        "current_total_unsafe": 0,
                        "reduced_by": 2,
                    },
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"judge_evidence_index": repo_relative(index_path)},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "judge_evidence_index": artifact_ref(index_path),
                            },
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        expected_blockers = {
            "repair_accounting_auto_recovered_exceeds_observed",
            "repair_accounting_unsafe_reduced_by_exceeds_measured_baseline",
            "repair_accounting_rollback_evidence_missing_for_observed_repairs",
        }
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(expected_blockers.issubset(set(report["blockers"])))
        self.assertTrue(expected_blockers.issubset(set(report["summary"]["blockers"])))

    def test_repair_accounting_blocks_inconsistent_verified_baseline_rollup(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        inconsistent = {
            "rollup": {
                "bound_unit_count": 2,
                "verified_baseline_unit_count": 1,
                "missing_verified_baseline_unit_count": 0,
                "all_units_verified_baseline_bound": True,
                "observed_repair_unit_count": 0,
                "auto_recovered_unit_count": 0,
                "rollback_evidence_count": 0,
                "unsafe_reduced_by": 0,
                "unsafe_reduction": {"status": "not_measured"},
            }
        }

        blockers = bundle.repair_accounting_consistency_blockers(inconsistent)

        self.assertIn("repair_accounting_verified_baseline_counts_mismatch", blockers)
        self.assertIn("repair_accounting_verified_baseline_all_bound_mismatch", blockers)

    def test_repair_accounting_blocks_unsafe_delta_rollup_drift_from_units(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        inconsistent = {
            "sources": [
                {
                    "before_after_units": [
                        {
                            "unit_id": "flashdb/real-fdb-calc-crc32",
                            "unsafe_reduction": {
                                "status": "measured",
                                "baseline_total_unsafe": 2,
                                "current_total_unsafe": 1,
                                "reduced_by": 1,
                            },
                        }
                    ]
                }
            ],
            "rollup": {
                "bound_unit_count": 1,
                "verified_baseline_unit_count": 1,
                "missing_verified_baseline_unit_count": 0,
                "all_units_verified_baseline_bound": True,
                "measured_unsafe_unit_count": 1,
                "observed_repair_unit_count": 0,
                "auto_recovered_unit_count": 0,
                "rollback_evidence_count": 0,
                "unsafe_reduced_by": 2,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                },
            },
        }

        blockers = bundle.repair_accounting_consistency_blockers(inconsistent)

        self.assertIn("repair_accounting_unsafe_reduction_rollup_mismatch", blockers)

    def test_bundle_repair_accounting_does_not_require_final_gate_passed(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(
            tempfile.mkdtemp(
                prefix="judge-milestone-repair-accounting-failed-gate-",
                dir=REPO_ROOT / "target",
            )
        )
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "final_gate_status": "failed",
                    "semantic_pass_count": 0,
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "repair_summary": {
                        "status": "verified",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 1,
                        "auto_recovered_unit_count": 1,
                        "rollback_evidence_count": 1,
                    },
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 2,
                        "current_total_unsafe": 1,
                        "reduced_by": 1,
                    },
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"judge_evidence_index": repo_relative(index_path)},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "judge_evidence_index": artifact_ref(index_path),
                            },
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        repair_blockers = [blocker for blocker in report["blockers"] if blocker.startswith("repair_accounting_")]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(repair_blockers, [])

    def test_bundle_blocks_opencode_runtime_missing_explicit_evidence_boundary_fields(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-opencode-missing-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        opencode_index_path = temp_dir / "opencode" / "harness" / "judge-evidence-index.json"
        write_json(
            opencode_index_path,
            {
                "report_kind": "judge-evidence-index",
                "judge_headline": {
                    "opencode_runtime": {
                        "enabled": True,
                        "worker_count": 1,
                        "all_contracts_executed": True,
                    }
                },
                "opencode_agent_runtime": {
                    "runtime": "opencode",
                    "worker_count": 1,
                    "all_contracts_executed": True,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"judge_evidence_index": repo_relative(opencode_index_path)},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("opencode_runtime_boundary_fields_missing", report["blockers"])
        self.assertFalse(report["opencode_evidence_policy"]["boundary_fields_explicit"])


if __name__ == "__main__":
    unittest.main()
