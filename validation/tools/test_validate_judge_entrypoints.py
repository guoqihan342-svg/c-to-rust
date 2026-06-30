from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from validation.tools import validate_judge_entrypoints as validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_default_config() -> dict:
    return json.loads(validator.DEFAULT_CONFIG.read_text(encoding="utf-8"))


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


def temp_json_ref(path: Path, payload: dict) -> dict:
    write_json(path, payload)
    return {"path": repo_relative(path), "sha256": validator.sha256_file(path)}


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
        self.assertEqual(result["entrypoint_count"], 3)
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
                "before_after_judge_demo",
                "multi_worker_evaluate_profile",
                "opencode_multi_worker_evaluate_profile",
            ],
        )
        for entry in result["entrypoints"]:
            self.assertEqual(entry["status"], "passed")
            self.assertEqual(entry["profile"]["status"], "present")
            self.assertEqual(entry["profile_contract"]["status"], "passed")
            self.assertEqual(entry["tracked_manifest"]["status"], "present")

    def test_judge_evidence_index_requires_valid_opencode_runtime_when_present(self) -> None:
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
                "opencode_preflight_report": {
                    "path": "target/out/harness/opencode-preflight-report.json",
                    "sha256": "a" * 64,
                    "status": "passed",
                    "contract_status": "executed",
                },
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
                        "opencode_preflight_report": {
                            "path": "target/out/harness/opencode-preflight-report.json",
                            "sha256": "a" * 64,
                            "status": "passed",
                            "contract_status": "executed",
                        },
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

    def test_require_local_artifacts_checks_expected_artifact_presence(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [config["entrypoints"][0]]
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

    def test_require_local_artifacts_validates_context_and_agent_contracts(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [config["entrypoints"][0]]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_dir / "out")
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        competition_summary = out_root / "summary" / "competition-run-summary.json"
        workflow_metrics = out_root / "summary" / "workflow-metrics.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"

        for artifact in [competition_summary, workflow_metrics, assignment, request, summary, report]:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("{}\n", encoding="utf-8")

        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(competition_summary),
            "workflow_metrics": repo_relative(workflow_metrics),
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
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
                    },
                    "mode": "baseline_repair_gate",
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
                                    "sha256": "e" * 64,
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
            },
        )
        write_minimal_context_ledger(
            ledger,
            run_id="competition-flashdb-before-after-exhibit",
            context_pack_path=context_pack,
            context_pack_payload=json.loads(context_pack.read_text(encoding="utf-8")),
            agent_index_path=agent_index,
        )

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed", result["errors"])
        contracts = result["entrypoints"][0]["harness_contracts"]
        self.assertEqual(contracts["context_pack"]["repair_round_cap"], 5)
        self.assertEqual(contracts["agent_index"]["worker_count"], 1)
        self.assertEqual(contracts["context_agent_consistency"]["worker_count"], 1)
        self.assertEqual(contracts["ledger_context_index"]["status"], "passed")
        self.assertEqual(contracts["repair_self_heal"]["checked_workers"], 1)

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
        config["entrypoints"] = [config["entrypoints"][0]]
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
        config["entrypoints"] = [config["entrypoints"][0]]
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
        manifest = json.loads((REPO_ROOT / config["entrypoints"][1]["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["reproduction"]["evaluate_profile_command"] = manifest["reproduction"]["evaluate_profile_command"].replace(
            "--run-id harness-flashdb-explicit-workers-evaluate-profile-20260701",
            "--run-id wrong-evaluate-run",
        )
        manifest_path = temp_config.parent / "drifted-explicit-workers-manifest.json"
        config["entrypoints"][1]["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
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
        manifest = json.loads((REPO_ROOT / config["entrypoints"][1]["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["claim_boundary"]["semantic_claim_source"] = "generated_draft"
        manifest_path = temp_config.parent / "drifted-claim-boundary-manifest.json"
        config["entrypoints"][1]["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
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
        manifest = json.loads((REPO_ROOT / config["entrypoints"][1]["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["workers"][0]["source_commit"] = "bad-commit"
        manifest_path = temp_config.parent / "drifted-source-commit-manifest.json"
        config["entrypoints"][1]["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("tracked manifest uses commits outside source_pin_policy" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_reproduction_out_root_bounds_expected_artifacts(self) -> None:
        config = load_default_config()
        config["entrypoints"][1]["expected_artifacts"]["merge_plan"] = "target/outside-harness/merge-plan.json"
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

    def test_merge_execution_argv_allows_host_trace(self) -> None:
        result = validator.validate_local_absolute_path_policy(
            {"merge_execution": {"argv": ["C:\\Python314\\python.exe", "validation/tools/run_competition.py"]}},
            label="merge-execution",
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["host_trace_allowed_locations"], ["$.merge_execution.argv.0"])

    def test_judge_evidence_reproduction_commands_reject_local_absolute_paths(self) -> None:
        payload = {
            "report_kind": "judge-evidence-index",
            "claim_boundary": {
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "index_is_semantic_gate": False,
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
