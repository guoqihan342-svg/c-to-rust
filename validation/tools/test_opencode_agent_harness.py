import io
import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


from validation.tools import opencode_agent_harness as harness
from validation.tools import validate_competition_run_summary as summary_validator


REPO_ROOT = Path(__file__).resolve().parents[2]


class OpenCodeAgentHarnessTest(unittest.TestCase):
    def assert_repo_relative_posix_path(self, value: str) -> None:
        self.assertIsInstance(value, str)
        self.assertTrue(value)
        self.assertNotIn("\\", value)
        self.assertFalse(value.startswith("/"))
        self.assertFalse(value.startswith("~"))
        self.assertFalse(len(value) >= 2 and value[1] == ":")
        self.assertNotIn("..", Path(value).parts)

    def assert_context_management_contract(self, contract: dict) -> None:
        self.assertEqual(contract["contract_kind"], "context-management")
        self.assertEqual(contract["role"], "context-index-and-resume-map")
        self.assertEqual(contract["evidence_policy"], "on-disk-artifacts-only")
        self.assertFalse(contract["semantic_gate"])
        self.assertFalse(contract["chat_output_is_evidence"])
        self.assertIn("entrypoints", contract["managed_state"])
        self.assertIn("worker handoffs", contract["managed_state"])
        pipeline = contract["pipeline"]
        self.assertEqual([stage["stage"] for stage in pipeline], ["plan", "translate", "verify", "repair"])
        self.assertEqual([stage["role"] for stage in pipeline], ["planner", "worker", "verifier", "repairer"])
        self.assertEqual(pipeline[0]["evidence"], "entrypoints.worker_plan")
        self.assertEqual(pipeline[1]["evidence"], "workers[*].summary_path")
        self.assertTrue(pipeline[1]["fanout"])
        self.assertEqual(pipeline[2]["reduce"], "merge")
        self.assertEqual(pipeline[3]["loopback_to"], "translate")
        self.assertEqual(pipeline[3]["max_rounds"], 5)
        resume_protocol = contract["resume_protocol"]
        self.assertEqual(resume_protocol["checkpoint_backend"], "sqlite")
        self.assertEqual(resume_protocol["worker_state_source"], "agent-index.agents_by_worker_id")
        self.assertIn("repair_hints", resume_protocol["open_repair_hint_source"])
        self.assertIn("worker summaries", resume_protocol["merge_precondition"])

    def assert_agent_coordination_contract(self, contract: dict, *, expected_worker_count: int | None = None) -> None:
        self.assertEqual(contract["contract_kind"], "agent-coordination")
        self.assertEqual(contract["coordination_state"], "sqlite-ledger-and-on-disk-reports")
        self.assertEqual(contract["checkpoint_backend"], "sqlite")
        self.assertFalse(contract["semantic_gate"])
        self.assertFalse(contract["chat_output_is_evidence"])
        self.assertEqual(contract["planner_ownership"]["mode"], "single-planner-per-run")
        self.assertIn("BEGIN IMMEDIATE", contract["planner_ownership"]["assignment_transaction"])
        self.assertEqual(contract["lease_policy"]["fencing_token"], "audit-only-monotonic-counter")
        self.assertTrue(contract["lease_policy"]["not_acceptance_gate"])
        if expected_worker_count is not None:
            self.assertEqual(contract["worker_count"], expected_worker_count)
        roles = contract["roles"]
        self.assertEqual(set(roles), {"planner", "worker", "repairer", "verifier", "reporter"})
        self.assertEqual(roles["worker"]["isolation"], "per-worker out_root")
        self.assertEqual(roles["repairer"]["round_cap"], 5)
        self.assertEqual(roles["verifier"]["acceptance_authority"], "competition-run-summary validator")
        self.assertEqual(roles["reporter"]["acceptance_authority"], "none")
        resume_protocol = contract["resume_protocol"]
        self.assertIn("evaluate --profile", resume_protocol["resume_entrypoints"])
        self.assertEqual(resume_protocol["worker_state_source"], "agent-index.agents_by_worker_id")

    def test_write_preflight_marker_emits_judge_required_report_kind(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="opencode-marker-test-", dir=target_dir) as tmp:
            marker_path = Path(tmp) / "harness" / "opencode-preflight-marker.json"
            marker_rel = Path(harness.repo_relative(marker_path, repo_root=REPO_ROOT))

            result = harness.write_opencode_preflight_marker(
                marker_path=marker_rel,
                run_id="preflight-marker-kind-test",
                repo_root=REPO_ROOT,
            )

            payload = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "written")
            self.assertEqual(payload.get("report_kind"), "opencode-preflight-marker")
            self.assertEqual(payload.get("run_id"), "preflight-marker-kind-test")
            self.assertEqual(payload.get("status"), "written")

    def assert_architecture_contracts(self, contracts: dict) -> None:
        context_contract = contracts["context_management"]
        self.assertEqual(context_contract["contract_kind"], "context-management")
        self.assertEqual(context_contract["evidence_policy"], "on-disk-artifacts-only")
        self.assertFalse(context_contract["semantic_gate"])
        self.assertFalse(context_contract["chat_output_is_evidence"])
        self.assertEqual(
            [stage["stage"] for stage in context_contract["pipeline"]],
            ["plan", "translate", "verify", "repair"],
        )
        agent_contract = contracts["agent_coordination"]
        self.assertEqual(agent_contract["contract_kind"], "agent-coordination")
        self.assertEqual(set(agent_contract["roles"]), {"planner", "worker", "repairer", "verifier", "reporter"})
        self.assertEqual(agent_contract["planner_ownership"]["mode"], "single-planner-per-run")
        self.assertEqual(agent_contract["lease_policy"]["fencing_token"], "audit-only-monotonic-counter")
        self.assertFalse(agent_contract["semantic_gate"])
        self.assertFalse(agent_contract["chat_output_is_evidence"])

    def test_init_run_creates_sqlite_ledger_with_run_and_profile(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"

            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(db_path, out_root / "state" / "opencode-agent-harness.sqlite3")
            rows = fetch_rows(db_path, "select run_id, out_root, proof_class, profile_id from runs")
            self.assertEqual(
                rows,
                [
                    (
                        "run-test",
                        repo_rel(out_root),
                        "local-simulation",
                        "huawei-competition-ubuntu-24.04",
                    )
                ],
            )
            profile_rows = fetch_rows(db_path, "select profile_id, profile_path from profiles")
            self.assertEqual(profile_rows, [("huawei-competition-ubuntu-24.04", "config/competition-env/environment.json")])

    def test_sqlite_connection_sets_parallel_worker_busy_timeout(self) -> None:
        with temp_repo_dir() as tmp:
            db_path = Path(tmp) / "parallel.sqlite3"

            connection = harness.connect(db_path)
            try:
                busy_timeout = connection.execute("pragma busy_timeout").fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(busy_timeout, 30000)

    def test_assign_slice_creates_worker_task_slice_lease_and_assignment_file(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            spec_path = out_root / "slice-specs" / "demo-add-one.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(json.dumps({"target_id": "demo", "slice_id": "demo-add-one"}), encoding="utf-8")
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            assignment = harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                source_repository="https://gitcode.com/example/demo.git",
                source_branch="competition",
                require_source_commit="abc123",
                compiler_command_source="compile_commands.json",
                include_paths=["include", "src/include"],
                defines=["DEMO=1", "USE_FAST"],
                reuse_accepted_evidence=True,
                accepted_evidence_root="validation/evidence",
                slice_spec=repo_rel(spec_path),
                out_root=out_root / "workers" / "worker-a",
                lease_ttl_seconds=900,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(assignment["worker_id"], "worker-a")
            self.assertEqual(assignment["run_id"], "run-test")
            self.assertEqual(assignment["slice"]["slice_id"], "demo-add-one")
            self.assertEqual(assignment["slice"]["source_repository"], "https://gitcode.com/example/demo.git")
            self.assertEqual(assignment["slice"]["source_branch"], "competition")
            self.assertEqual(assignment["slice"]["require_source_commit"], "abc123")
            self.assertEqual(assignment["out_root"], repo_rel(out_root / "workers" / "worker-a"))
            self.assertTrue((out_root / "harness" / "assignments" / "worker-a.json").exists())
            request_path = out_root / "harness" / "assignments" / "worker-a-request.json"
            self.assertTrue(request_path.exists())
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["source_repo_root"], "external/demo")
            self.assertEqual(request["source_repository"], "https://gitcode.com/example/demo.git")
            self.assertEqual(request["source_branch"], "competition")
            self.assertEqual(request["require_source_commit"], "abc123")
            self.assertEqual(request["source_file"], "src/demo.c")
            self.assertEqual(request["out_root"], repo_rel(out_root / "workers" / "worker-a"))
            self.assertEqual(request["compiler_command_source"], "compile_commands.json")
            self.assertEqual(request["include_paths"], ["include", "src/include"])
            self.assertEqual(request["defines"], ["DEMO=1", "USE_FAST"])
            self.assertIs(request["reuse_accepted_evidence"], True)
            self.assertEqual(request["accepted_evidence_root"], "validation/evidence")
            self.assertEqual(request["slice_specs"], [repo_rel(spec_path)])
            task_rows = fetch_rows(db_path, "select worker_name, role, status from agents")
            self.assertEqual(task_rows, [("worker-a", "slice-worker", "assigned")])
            slice_rows = fetch_rows(db_path, "select slice_spec_path, slice_spec_sha256 from slices")
            self.assertEqual(slice_rows[0][0], repo_rel(spec_path))
            self.assertIsNotNone(slice_rows[0][1])
            lease_rows = fetch_rows(db_path, "select resource_key, lease_owner, status from leases")
            self.assertEqual(lease_rows, [("slice:demo/demo-add-one", "worker-a", "active")])

            with self.assertRaises(SystemExit) as raised:
                harness.assign_slice(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-b",
                    target_id="demo",
                    slice_id="demo-add-one",
                    source_repo_root=Path("external/demo"),
                    source_file="src/demo.c",
                    function="add_one",
                    source_commit="abc123",
                    out_root=out_root / "workers" / "worker-b",
                    repo_root=REPO_ROOT,
                )
            self.assertIn("active lease already exists", str(raised.exception))

    def test_assign_slice_rejects_duplicate_isolated_out_root_for_different_workers_in_run(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "shared",
                repo_root=REPO_ROOT,
            )

            with self.assertRaisesRegex(SystemExit, "isolated out_root already assigned"):
                harness.assign_slice(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-b",
                    target_id="demo",
                    slice_id="demo-add-two",
                    source_repo_root=Path("external/demo"),
                    source_file="src/demo.c",
                    function="add_two",
                    source_commit="abc123",
                    out_root=out_root / "workers" / "shared",
                    repo_root=REPO_ROOT,
                )

    def test_assign_slice_cli_dispatches_source_pin_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "assign-slice",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
            "--worker-id",
            "worker-a",
            "--target-id",
            "flashdb",
            "--slice-id",
            "real-fdb-calc-crc32",
            "--source-repo-root",
            "sources/FlashDB",
            "--source-repository",
            "https://gitcode.com/xwxf/FlashDB.git",
            "--source-branch",
            "competition",
            "--source-file",
            "src/fdb_utils.c",
            "--function",
            "fdb_calc_crc32",
            "--source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--require-source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--out-root",
            "target/competition-out/workers/worker-a",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()), patch.object(
            harness,
            "assign_slice",
            return_value={"status": "assigned"},
        ) as assign:
            self.assertEqual(harness.main(), 0)

        assign.assert_called_once()
        self.assertEqual(assign.call_args.kwargs["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(assign.call_args.kwargs["source_branch"], "competition")
        self.assertEqual(
            assign.call_args.kwargs["require_source_commit"],
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        )

    def test_plan_source_file_creates_ordered_worker_assignments_from_c_functions(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    if (value > 0) {
                        return value + 1;
                    }
                    return value;
                }

                static int second_unit(void)
                {
                    return first_unit(1);
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                source_repository="https://gitcode.com/xwxf/FlashDB.git",
                source_branch="competition",
                require_source_commit="abc123",
                compiler_command_source="compile_commands.json",
                include_paths=["inc"],
                defines=["FDB_USING_KVDB"],
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(plan["status"], "planned")
            self.assertEqual([unit["function"] for unit in plan["units"]], ["first_unit", "second_unit"])
            self.assertEqual([unit["slice_id"] for unit in plan["units"]], ["real-demo-first-unit", "real-demo-second-unit"])
            self.assertEqual([unit["worker_id"] for unit in plan["units"]], ["worker-001-first-unit", "worker-002-second-unit"])
            plan_path = REPO_ROOT / plan["plan_path"]
            self.assertTrue(plan_path.exists())

            first_request = out_root / "harness" / "assignments" / "worker-001-first-unit-request.json"
            second_request = out_root / "harness" / "assignments" / "worker-002-second-unit-request.json"
            self.assertTrue(first_request.exists())
            self.assertTrue(second_request.exists())
            first_payload = json.loads(first_request.read_text(encoding="utf-8"))
            self.assertEqual(first_payload["function"], "first_unit")
            self.assertEqual(first_payload["slice_id"], "real-demo-first-unit")
            self.assertEqual(first_payload["out_root"], repo_rel(out_root / "workers" / "worker-001-first-unit"))
            self.assertEqual(first_payload["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
            self.assertEqual(first_payload["source_branch"], "competition")
            self.assertEqual(first_payload["require_source_commit"], "abc123")
            self.assertEqual(first_payload["compiler_command_source"], "compile_commands.json")
            self.assertEqual(first_payload["include_paths"], ["inc"])
            self.assertEqual(first_payload["defines"], ["FDB_USING_KVDB"])

            rows = fetch_rows(db_path, "select agent_id, isolated_out_root from agents order by agent_id")
            self.assertEqual(
                rows,
                [
                    ("worker-001-first-unit", repo_rel(out_root / "workers" / "worker-001-first-unit")),
                    ("worker-002-second-unit", repo_rel(out_root / "workers" / "worker-002-second-unit")),
                ],
            )

    def test_plan_source_file_filters_functions_and_binds_slice_specs(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }

                int second_unit(int value) {
                    return value + 2;
                }
                """,
                encoding="utf-8",
            )
            spec_path = Path(tmp) / "slice-specs" / "second-unit.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(
                json.dumps(
                    {
                        "target_id": "flashdb",
                        "slice_id": "real-demo-second-unit",
                        "function_name": "second_unit",
                        "source_commit": "abc123",
                    }
                ),
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                reuse_accepted_evidence=True,
                accepted_evidence_root="validation/evidence",
                out_root=out_root,
                slice_id_prefix="wrong-prefix",
                worker_prefix="worker",
                functions=["second_unit"],
                slice_specs=[repo_rel(spec_path)],
                repo_root=REPO_ROOT,
            )

            self.assertEqual([unit["function"] for unit in plan["units"]], ["second_unit"])
            self.assertEqual([unit["slice_id"] for unit in plan["units"]], ["real-demo-second-unit"])
            self.assertEqual(plan["units"][0]["slice_spec"], repo_rel(spec_path))
            request_path = out_root / "harness" / "assignments" / "worker-001-second-unit-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["function"], "second_unit")
            self.assertEqual(request["slice_id"], "real-demo-second-unit")
            self.assertIs(request["reuse_accepted_evidence"], True)
            self.assertEqual(request["accepted_evidence_root"], "validation/evidence")
            self.assertEqual(request["slice_specs"], [repo_rel(spec_path)])
            rows = fetch_rows(db_path, "select slice_id, function_name, slice_spec_path from slices")
            self.assertEqual(rows, [("real-demo-second-unit", "second_unit", repo_rel(spec_path))])

    def test_plan_source_file_rejects_mismatched_slice_spec_binding(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int second_unit(int value) { return value + 2; }\n", encoding="utf-8")
            spec_path = Path(tmp) / "slice-specs" / "second-unit.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(
                json.dumps(
                    {
                        "target_id": "other-target",
                        "slice_id": "real-demo-second-unit",
                        "function_name": "second_unit",
                        "source_commit": "abc123",
                    }
                ),
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            with self.assertRaises(SystemExit) as raised:
                harness.plan_source_file(
                    db_path=db_path,
                    run_id="run-test",
                    target_id="flashdb",
                    source_repo_root=source_root,
                    source_file="src/demo.c",
                    source_commit="abc123",
                    out_root=out_root,
                    slice_id_prefix="real-demo",
                    functions=["second_unit"],
                    slice_specs=[repo_rel(spec_path)],
                    repo_root=REPO_ROOT,
                )

            self.assertIn("slice spec target_id mismatch", str(raised.exception))

    def test_run_plan_executes_planned_workers_and_writes_merge_plan(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }

                int second_unit(int value) {
                    return value + 2;
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            calls: list[str] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                worker_id = Path(request["out_root"]).name
                calls.append(worker_id)
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout=f"{worker_id} ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(calls, ["worker-001-first-unit", "worker-002-second-unit"])
            self.assertEqual([worker["exit_code"] for worker in result["workers"]], [0, 0])
            self.assertEqual(
                [worker["summary_status"] for worker in result["workers"]],
                ["passed", "passed"],
            )
            report_path = REPO_ROOT / result["report_path"]
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["plan_path"], plan["plan_path"])
            self.assertEqual(report["worker_count"], 2)
            self.assertEqual(report["failed_workers"], 0)
            merge_plan_path = out_root / "harness" / "merge-plan.json"
            self.assertTrue(merge_plan_path.exists())
            merge_plan = json.loads(merge_plan_path.read_text(encoding="utf-8"))
            first_summary = out_root / "workers" / "worker-001-first-unit" / "summary" / "competition-run-summary.json"
            second_summary = out_root / "workers" / "worker-002-second-unit" / "summary" / "competition-run-summary.json"
            self.assertEqual(
                merge_plan["worker_summaries"],
                [repo_rel(first_summary), repo_rel(second_summary)],
            )

    def test_run_plan_auto_retries_failed_worker_before_merge(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int repairable_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            worker_attempts = 0
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts < 3:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                merge_calls.append(argv)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(worker_attempts, 3)
            self.assertEqual(len(merge_calls), 1)
            self.assertEqual(result["failed_workers"], 0)
            self.assertEqual(result["workers"][0]["summary_status"], "passed")
            self.assertEqual(result["workers"][0]["auto_retry"]["attempt_count"], 2)
            self.assertEqual(result["workers"][0]["auto_retry"]["final_hint_status"], "revalidated_passed")
            hint_rows = fetch_rows(db_path, "select status from repair_hints")
            self.assertEqual(hint_rows, [("revalidated_passed",)])

    def test_run_plan_auto_retry_has_defensive_outer_cap_if_retry_worker_regresses(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-outer-cap",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan_path = out_root / "harness" / "worker-plan.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-outer-cap",
                        "plan_path": repo_rel(plan_path),
                        "units": [{"worker_id": "worker-a", "slice_id": "demo-add-one", "function": "add_one"}],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            outer_cap = harness.REPAIR_ROUND_CAP + 2
            retry_calls = 0

            def fake_run_worker(**kwargs: object) -> dict[str, object]:
                return {
                    "exit_code": 1,
                    "process_returncode": 1,
                    "summary_status": "failed",
                    "summary_path": repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                    "report_path": repo_rel(out_root / "workers" / "worker-a" / "harness" / "run-worker-report.json"),
                    "logs": {},
                    "recorded": False,
                    "repair_hint": {"hint_id": "repair:run-outer-cap:worker-a:compile_failed"},
                }

            def fake_retry_worker(**kwargs: object) -> dict[str, object]:
                nonlocal retry_calls
                retry_calls += 1
                if retry_calls > outer_cap:
                    raise AssertionError("run_plan auto_retry did not stop at the defensive outer cap")
                return {
                    "exit_code": 1,
                    "process_returncode": 1,
                    "status": "revalidated_failed",
                    "hint_id": "repair:run-outer-cap:worker-a:compile_failed",
                    "hint_status": "revalidated_failed",
                    "summary_status": "failed",
                    "summary_path": repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                    "report_path": repo_rel(out_root / "workers" / "worker-a" / "harness" / "run-worker-report.json"),
                    "logs": {},
                    "recorded": False,
                }

            with patch.object(harness, "run_worker", side_effect=fake_run_worker), patch.object(
                harness, "retry_worker", side_effect=fake_retry_worker
            ):
                result = harness.run_plan(
                    db_path=db_path,
                    run_id="run-outer-cap",
                    plan_path=plan_path,
                    out_root=out_root,
                    proof_class="local-simulation",
                    auto_retry=True,
                    repo_root=REPO_ROOT,
                )

            worker = result["workers"][0]
            self.assertEqual(retry_calls, outer_cap)
            self.assertEqual(worker["auto_retry"]["attempt_count"], outer_cap)
            self.assertEqual(worker["auto_retry"]["outer_round_cap"], outer_cap)
            self.assertEqual(worker["auto_retry"]["final_hint_status"], "outer_retry_limit_exceeded")
            self.assertEqual(
                worker["auto_retry"]["attempts"][-1]["outer_retry_limit"],
                {
                    "max_outer_rounds": outer_cap,
                    "reason": "retry_worker did not return success or retry_limit_exceeded",
                },
            )

    def test_run_plan_report_preserves_retry_attempt_timeline_rollback_and_final_decision(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int repairable_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-retry-timeline",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-retry-timeline",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="timeline",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            worker_attempts = 0

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts == 1:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-retry-timeline", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-retry-timeline",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            worker = result["workers"][0]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(worker["final_decision"], {"status": "accepted", "reason": "worker_summary_passed"})
            self.assertEqual([attempt["attempt"] for attempt in worker["attempts"]], [1, 2])
            self.assertEqual([attempt["summary_status"] for attempt in worker["attempts"]], ["failed", "passed"])
            self.assertEqual(worker["attempts"][0]["hint_status"], "opened")
            self.assertEqual(worker["attempts"][1]["hint_status"], "revalidated_passed")
            rollback = worker["attempts"][1]["rollback_evidence"]
            self.assertRegex(rollback["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue((REPO_ROOT / rollback["path"]).exists())
            persisted = json.loads((out_root / "harness" / "run-plan-report.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["workers"][0]["attempts"], worker["attempts"])
            self.assertEqual(persisted["workers"][0]["final_decision"], worker["final_decision"])

    def test_evaluate_context_pack_records_auto_retry_success(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int repairable_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            worker_attempts = 0

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts < 3:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-evaluate-retry", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate-retry",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["repairable_unit"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-retry",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(worker_attempts, 3)
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            worker = context_pack["workers"][0]
            agent = agent_index["agents"][0]
            self.assertTrue(worker["recorded"])
            self.assertEqual(worker["summary_status"], "passed")
            self.assertEqual(worker["auto_retry"]["attempt_count"], 2)
            self.assertEqual(worker["auto_retry"]["final_hint_status"], "revalidated_passed")
            self.assertEqual([attempt["hint_status"] for attempt in worker["auto_retry"]["attempts"]], ["revalidated_failed", "revalidated_passed"])
            self.assertEqual(worker["final_decision"], {"status": "accepted", "reason": "worker_summary_passed"})
            self.assertEqual([attempt["summary_status"] for attempt in worker["attempts"]], ["failed", "failed", "passed"])
            self.assertEqual([attempt["hint_status"] for attempt in worker["attempts"]], ["opened", "revalidated_failed", "revalidated_passed"])
            self.assertEqual(agent["status"], "passed")
            self.assertTrue(agent["recorded"])
            self.assertEqual(agent["final_decision"], worker["final_decision"])
            self.assertEqual(agent["attempts"], worker["attempts"])
            hint_rows = fetch_rows(Path(REPO_ROOT / result["db_path"]), "select status from repair_hints")
            self.assertEqual(hint_rows, [("revalidated_passed",)])

    def test_evaluate_context_pack_records_retry_limit_exceeded(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int never_recovers(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            worker_attempts = 0
            merge_called = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts, merge_called
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                if "validation/tools/run_competition.py" in argv:
                    merge_called = True
                return subprocess.CompletedProcess(argv, 0, stdout="merge should not run\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate-retry-limit",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["never_recovers"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-retry-limit",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(worker_attempts, 6)
            self.assertTrue(merge_called)
            self.assertEqual(result["run_plan"]["merge_execution"]["exit_code"], 1)
            self.assertFalse(result["run_plan"]["merge_execution"]["summary_exists"])
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            worker = context_pack["workers"][0]
            agent = agent_index["agents"][0]
            self.assertTrue(worker["recorded"])
            self.assertEqual(worker["summary_status"], "failed")
            self.assertEqual(worker["auto_retry"]["attempt_count"], 6)
            self.assertEqual(worker["auto_retry"]["final_hint_status"], "retry_limit_exceeded")
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["hint_status"], "retry_limit_exceeded")
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["exit_code"], 1)
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["repair_round_cap"], 5)
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["repair_rounds"], 5)
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["retry_limit"]["max_repair_rounds"], 5)
            self.assertEqual(agent["status"], "failed")
            self.assertTrue(agent["recorded"])
            self.assertEqual(agent["auto_retry"]["final_hint_status"], "retry_limit_exceeded")
            self.assertEqual(agent["auto_retry"]["attempts"][-1]["repair_round_cap"], 5)
            hint_rows = fetch_rows(Path(REPO_ROOT / result["db_path"]), "select status, payload_json from repair_hints")
            self.assertEqual(len(hint_rows), 1)
            self.assertEqual(hint_rows[0][0], "retry_limit_exceeded")
            hint_payload = json.loads(hint_rows[0][1])
            self.assertEqual(hint_payload["retry_limit"]["max_repair_rounds"], 5)

    def test_run_plan_executes_workers_in_parallel_when_max_workers_allows(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }

                int second_unit(int value) {
                    return value + 2;
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                functions=["first_unit", "second_unit"],
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            worker_started: list[str] = []
            both_workers_started = threading.Event()
            worker_lock = threading.Lock()

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    with worker_lock:
                        worker_started.append(str(request["run_id"]))
                        if len(worker_started) == 2:
                            both_workers_started.set()
                    self.assertTrue(both_workers_started.wait(2), "run-plan did not overlap worker execution")
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=2)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                max_workers=2,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(result["graph"]["runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(result["graph"]["checkpoint_backend"], "sqlite")
            self.assertIn("fanout_workers", result["graph"]["nodes"])
            self.assertIn("repair_retry", result["graph"]["nodes"])
            self.assertIn(
                {
                    "from": "worker",
                    "to": "repair_retry",
                    "condition": "exit_code != 0 and auto_retry",
                },
                result["graph"]["edges"],
            )
            self.assertEqual(result["graph"]["parallel_map"]["max_workers"], 2)
            self.assertEqual(result["graph"]["parallel_map"]["result_order"], "planner_order")
            self.assertEqual([worker["worker_id"] for worker in result["workers"]], [unit["worker_id"] for unit in plan["units"]])
            self.assertEqual(len(worker_started), 2)

    def test_run_plan_can_execute_final_merge_and_finalize_run(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                merge_calls.append(argv)
                self.assertIn("validation/tools/run_competition.py", argv)
                self.assertIn("--worker-summary", argv)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(len(merge_calls), 1)
            self.assertEqual(result["merge_execution"]["exit_code"], 0)
            self.assertEqual(
                result["merge_execution"]["summary_path"],
                repo_rel(out_root / "summary" / "competition-run-summary.json"),
            )
            self.assertTrue((out_root / "harness" / "run-plan-merge.stdout.log").exists())
            run_rows = fetch_rows(
                db_path,
                "select status, final_gate_status, summary_path from runs where run_id=?",
                ("run-test",),
            )
            self.assertEqual(
                run_rows,
                [("completed", "passed", repo_rel(out_root / "summary" / "competition-run-summary.json"))],
            )

    def test_run_plan_execute_merge_skips_partial_worker_summaries(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            merge_called = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal merge_called
                if "validation/tools/run_competition.py" in argv:
                    merge_called = True
                return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertFalse(merge_called)
            self.assertEqual(result["merge_execution"]["status"], "skipped")
            self.assertEqual(result["merge_execution"]["reason"], "unrecorded-worker-summaries")

    def test_run_batch_profile_initializes_plans_and_executes_merge(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }

                int second_unit(int value) {
                    return value + 2;
                }
                """,
                encoding="utf-8",
            )
            spec_root = Path(tmp) / "slice-specs"
            spec_root.mkdir()
            first_spec = write_slice_spec(spec_root / "first-unit.json", "demo", "demo-first", "first_unit", "abc123")
            second_spec = write_slice_spec(spec_root / "second-unit.json", "demo", "demo-second", "second_unit", "abc123")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-two-unit-accepted-evidence",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "require_source_commit": "abc123",
                        "functions": ["first_unit", "second_unit"],
                        "slice_specs": [repo_rel(first_spec), repo_rel(second_spec)],
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "slice_id_prefix": "wrong-prefix",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "auto_retry": True,
                        "max_workers": 2,
                        "emit_route_governance_metrics_report": True,
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                merge_calls.append(argv)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-profile",
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=measured_unsafe_worker_metrics("run-profile"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-profile",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["profile_id"], "demo-two-unit-accepted-evidence")
            self.assertTrue(result["profile_sha256"])
            self.assertEqual(
                result["acceptance_boundary"],
                {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            )
            self.assertEqual(result["worker_count"], 2)
            self.assertEqual(len(merge_calls), 1)
            self.assertEqual(
                [unit["slice_id"] for unit in result["plan"]["units"]],
                ["demo-first", "demo-second"],
            )
            self.assertEqual(result["run_plan"]["merge_execution"]["final_gate_status"], "passed")
            self.assertEqual(result["run_plan"]["auto_retry"], {"enabled": True, "retried_worker_count": 0})
            self.assertEqual(result["run_plan"]["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(result["run_plan"]["graph"]["parallel_map"]["max_workers"], 2)
            self.assertTrue((out_root / "summary" / "competition-run-summary.json").exists())
            route_report_ref = result["route_governance_metrics_report"]
            route_report_path = REPO_ROOT / route_report_ref["path"]
            self.assertTrue(route_report_path.exists())
            self.assertEqual(route_report_ref["sha256"], harness.sha256_file(route_report_path))
            route_report = json.loads(route_report_path.read_text(encoding="utf-8"))
            self.assertEqual(route_report["report_kind"], "route-governance-metrics")
            self.assertEqual(route_report["status"], "passed")
            self.assertIn("translation_coverage_numerator", route_report["metrics"])
            self.assertEqual(route_report["metrics"]["s2_workflow_metrics"]["run_count"], 1)
            self.assertEqual(route_report_ref["s2_workflow_run_count"], 1)
            self.assertEqual(route_report_ref["s2_unsafe_reduction_status"], "measured")
            self.assertEqual(route_report_ref["s2_translation_before_after_status"], "not_provided")
            self.assertEqual(route_report_ref["s2_translation_before_after_unit_count"], 0)
            artifact_rows = fetch_rows(
                result["db_path"],
                "select kind, repo_rel_path, semantic_role from artifacts where kind='route-governance-metrics-report'",
            )
            self.assertEqual(
                artifact_rows,
                [
                    (
                        "route-governance-metrics-report",
                        route_report_ref["path"],
                        "route-governance-metrics",
                    )
                ],
            )
            report = json.loads((out_root / "harness" / "batch-profile-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["report_path"], result["report_path"])
            self.assertEqual(report["acceptance_boundary"], result["acceptance_boundary"])
            self.assertEqual(report["route_governance_metrics_report"], route_report_ref)
            self.assertEqual(report["context_pack"], result["context_pack"])
            self.assertEqual(report["agent_index"], result["agent_index"])
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["run_id"], "run-profile")
            self.assertEqual(context_pack["entrypoints"]["primary_report"], result["report_path"])
            self.assertEqual(context_pack["entrypoints"]["batch_profile_report"], result["report_path"])
            self.assertEqual(context_pack["entrypoints"]["route_governance_metrics_report"], route_report_ref["path"])
            self.assertEqual(context_pack["entrypoints"]["merge_plan"], result["run_plan"]["merge_plan"]["path"])
            self.assertEqual(context_pack["source"]["require_source_commit"], "abc123")
            self.assert_context_management_contract(context_pack["context_management_contract"])
            self.assertEqual(context_pack["acceptance_boundary"]["profile"], result["acceptance_boundary"])
            self.assertEqual(context_pack["report_artifacts"]["route_governance_metrics_report"], route_report_ref)
            self.assert_agent_coordination_contract(agent_index["agent_coordination_contract"], expected_worker_count=2)
            self.assertEqual(agent_index["reports"]["route_governance_metrics_report"], route_report_ref)
            self.assertEqual([worker["worker_id"] for worker in context_pack["workers"]], [unit["worker_id"] for unit in result["plan"]["units"]])
            self.assertEqual([agent["worker_id"] for agent in agent_index["agents"]], [unit["worker_id"] for unit in result["plan"]["units"]])
            self.assertEqual(sorted(agent_index["agents_by_worker_id"]), [unit["worker_id"] for unit in result["plan"]["units"]])
            for unit in result["plan"]["units"]:
                indexed_agent = agent_index["agents_by_worker_id"][unit["worker_id"]]
                self.assertEqual(indexed_agent["assignment_path"], unit["assignment_path"])
                self.assertEqual(indexed_agent["request_path"], unit["request_path"])
                self.assertIn("summary_path", indexed_agent)
                self.assertIn("report_path", indexed_agent)
            context_rows = fetch_rows(
                Path(REPO_ROOT / result["db_path"]),
                "select context_pack_id, artifact_path, artifact_sha256, payload_json from context_packs",
            )
            self.assertEqual(len(context_rows), 1)
            self.assertEqual(
                context_rows[0][:3],
                ("run-profile-context-pack", result["context_pack"]["path"], result["context_pack"]["sha256"]),
            )
            self.assertEqual(json.loads(context_rows[0][3]), context_pack)
            artifact_rows = fetch_rows(
                Path(REPO_ROOT / result["db_path"]),
                """
                select kind, agent_id, repo_rel_path, sha256, semantic_role
                from artifacts
                where kind in ('context-pack', 'agent-index')
                order by kind
                """,
            )
            self.assertEqual(
                artifact_rows,
                [
                    ("agent-index", "planner", result["agent_index"]["path"], result["agent_index"]["sha256"], "agent-index"),
                    ("context-pack", "planner", result["context_pack"]["path"], result["context_pack"]["sha256"], "agent-context-pack"),
                ],
            )
            for path_value in [
                result["context_pack"]["path"],
                result["agent_index"]["path"],
                context_pack["entrypoints"]["primary_report"],
                context_pack["entrypoints"]["batch_profile_report"],
                context_pack["entrypoints"]["run_plan_report"],
                context_pack["entrypoints"]["worker_plan"],
                context_pack["entrypoints"]["merge_plan"],
                context_pack["entrypoints"]["merge_summary"],
                context_pack["entrypoints"]["route_governance_metrics_report"],
            ]:
                self.assert_repo_relative_posix_path(path_value)

    def test_before_after_exhibit_profile_report_fails_closed_when_summary_missing(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after",
                "proof_class": "local-simulation",
                "target_id": "demo",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            artifact = harness.write_before_after_exhibit_profile_report(
                profile=profile,
                profile_path=profile_path,
                run_id="run-missing-summary",
                proof_class="local-simulation",
                mode="deterministic",
                plan={"units": []},
                run_result={
                    "status": "failed",
                    "exit_code": 1,
                    "merge_execution": {
                        "summary_path": repo_rel(out_root / "summary" / "competition-run-summary.json"),
                        "summary_exists": False,
                    },
                },
                route_metrics_artifact=None,
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            self.assertIsNotNone(artifact)
            self.assertEqual(artifact["binding"]["status"], "failed")
            self.assertEqual(artifact["binding"]["reason"], "competition_summary_missing")
            report_path = REPO_ROOT / artifact["binding"]["path"]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["reason"], "competition_summary_missing")
            self.assertEqual(report["core_translation_quality"]["final_gate_status"], "missing")
            self.assertEqual(report["harness_architecture"]["command_status"], "failed")
            self.assertEqual(report["failure_path"]["baseline_role"], "handwritten_or_accepted_evidence_baseline")
            self.assertEqual(report["failure_path"]["next_repair_hint"]["root_cause_key"], "competition_summary_missing")

    def test_before_after_reproduction_command_preserves_proof_class_override(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = Path(tmp) / "planned-batch.json"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path.write_text("{}\n", encoding="utf-8")

            commands = harness.before_after_reproduction_commands(
                profile_path=profile_path,
                run_id="run-exact",
                out_root=out_root,
                summary_path=summary_path,
                proof_class_resolution={
                    "source": "cli-override",
                    "profile_proof_class": "local-simulation",
                    "effective_proof_class": "competition-exact",
                    "override_requested": True,
                    "changed": True,
                    "override_proof_class": "competition-exact",
                },
                repo_root=REPO_ROOT,
            )

            self.assertIn("--proof-class competition-exact", commands["run_command"])

    def test_judge_evidence_index_reproduction_commands_preserve_proof_class_override(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = Path(tmp) / "planned-batch.json"
            evaluate_report_path = out_root / "harness" / "evaluate-report.json"
            profile_path.write_text(
                json.dumps({"schema_version": 1, "profile_id": "demo", "proof_class": "local-simulation"}),
                encoding="utf-8",
            )
            evaluate_report_path.parent.mkdir(parents=True, exist_ok=True)
            evaluate_report_path.write_text("{}\n", encoding="utf-8")

            artifact = harness.write_judge_evidence_index(
                evaluate_report={
                    "status": "blocked",
                    "exit_code": 1,
                    "profile_id": "demo",
                    "proof_class": "competition-exact",
                    "mode": "opencode",
                    "proof_class_resolution": {
                        "source": "cli-override",
                        "profile_proof_class": "local-simulation",
                        "effective_proof_class": "competition-exact",
                        "override_requested": True,
                        "changed": True,
                        "override_proof_class": "competition-exact",
                    },
                    "judge_summary": {},
                },
                evaluate_report_path=evaluate_report_path,
                batch_result={"status": "blocked", "exit_code": 1},
                profile_path=profile_path,
                run_id="run-exact",
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            commands = artifact["payload"]["reproduction_commands"]
            self.assertIn("--proof-class competition-exact", commands["evaluate_profile"])
            self.assertIn("--proof-class competition-exact", commands["run_batch_profile"])

    def test_before_after_exhibit_labels_unbound_baseline_as_harness_exhibit(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-unbound",
                "proof_class": "local-simulation",
                "target_id": "demo",
                "emit_before_after_exhibit_report": True,
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "translation_before_after": "validation/evidence/demo/auto-translation/store-add-one/missing.json",
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            workflow_metrics = measured_unsafe_worker_metrics("run-unbound-before-after")
            write_worker_summary(
                summary_path,
                "run-unbound-before-after",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=workflow_metrics,
            )

            artifact = harness.write_before_after_exhibit_profile_report(
                profile=profile,
                profile_path=profile_path,
                run_id="run-unbound-before-after",
                proof_class="local-simulation",
                mode="deterministic",
                plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                run_result={"status": "completed", "workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                route_metrics_artifact=None,
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            self.assertIsNotNone(artifact)
            self.assertEqual(artifact["binding"]["status"], "not_provided")
            report = artifact["payload"]
            self.assertEqual(report["status"], "not_provided")
            self.assertEqual(report["translation_before_after"]["status"], "not_provided")
            failure_path = report["failure_path"]
            self.assertEqual(failure_path["baseline_role"], "handwritten_or_accepted_evidence_baseline")
            self.assertEqual(failure_path["status"], "harness_exhibit_only")
            self.assertEqual(failure_path["next_repair_hint"]["root_cause_key"], "before_after_not_bound")
            self.assertEqual(failure_path["observable_diff"]["status"], "not_available")
            self.assertIn("run-batch-profile", failure_path["smallest_replay_command"]["command"])
            self.assertIn("validate_competition_run_summary.py", failure_path["smallest_replay_command"]["verify_command"])

    def test_run_batch_profile_supports_explicit_worker_source_pins(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }

                int second_unit(int value) {
                    return value + 2;
                }
                """,
                encoding="utf-8",
            )
            spec_root = Path(tmp) / "slice-specs"
            first_spec = write_slice_spec(spec_root / "first-unit.json", "demo", "demo-first", "first_unit", "commit-one")
            second_spec = write_slice_spec(spec_root / "second-unit.json", "demo", "demo-second", "second_unit", "commit-two")
            worker_profiles = [
                {
                    "worker_id": "explicit-worker-001-first-unit",
                    "target_id": "demo",
                    "source_repo_root": repo_rel(source_root),
                    "source_repository": "https://gitcode.com/example/FlashDB.git",
                    "source_branch": "competition",
                    "source_file": "src/demo.c",
                    "function": "first_unit",
                    "slice_id": "demo-first",
                    "source_commit": "commit-one",
                    "require_source_commit": "commit-one",
                    "slice_spec": repo_rel(first_spec),
                },
                {
                    "worker_id": "explicit-worker-002-second-unit",
                    "target_id": "demo",
                    "source_repo_root": repo_rel(source_root),
                    "source_repository": "https://gitcode.com/example/FlashDB.git",
                    "source_branch": "competition",
                    "source_file": "src/demo.c",
                    "function": "second_unit",
                    "slice_id": "demo-second",
                    "source_commit": "commit-two",
                    "require_source_commit": "commit-two",
                    "slice_spec": repo_rel(second_spec),
                },
            ]
            profile_path = Path(tmp) / "planned-batch-explicit-workers.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-explicit-workers",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repository": "https://gitcode.com/example/FlashDB.git",
                        "source_branch": "competition",
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "worker_prefix": "explicit-worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "auto_retry": False,
                        "max_workers": 2,
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                        },
                        "workers": worker_profiles,
                    }
                ),
                encoding="utf-8",
            )
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"{request['function']} ok\n", stderr="")
                merge_calls.append(argv)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-explicit",
                    status="passed",
                    failed=0,
                    semantic_pass=2,
                    workflow_metrics=measured_unsafe_worker_metrics("run-explicit"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-explicit",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["worker_count"], 2)
            self.assertEqual(result["plan"]["planning_mode"], "explicit_workers")
            self.assertEqual(
                [unit["worker_id"] for unit in result["plan"]["units"]],
                ["explicit-worker-001-first-unit", "explicit-worker-002-second-unit"],
            )
            self.assertEqual([unit["source_commit"] for unit in result["plan"]["units"]], ["commit-one", "commit-two"])
            self.assertEqual(
                [unit["require_source_commit"] for unit in result["plan"]["units"]],
                ["commit-one", "commit-two"],
            )
            self.assertEqual(result["run_plan"]["graph"]["parallel_map"]["effective_workers"], 2)
            self.assertEqual(result["run_plan"]["graph"]["parallel_map"]["result_order"], "planner_order")
            self.assertEqual(result["judge_summary"]["harness_architecture"]["planning_mode"], "explicit_workers")
            self.assertEqual(
                result["judge_summary"]["harness_architecture"]["pipeline"],
                ["init-run", "plan-explicit-workers", "run-plan", "merge", "report"],
            )

            self.assertEqual(len(merge_calls), 1)
            merge_worker_summaries = [
                merge_calls[0][index + 1]
                for index, arg in enumerate(merge_calls[0])
                if arg == "--worker-summary"
            ]
            self.assertEqual(
                merge_worker_summaries,
                [worker["summary_path"] for worker in result["run_plan"]["workers"]],
            )

            for unit in result["plan"]["units"]:
                request = json.loads((REPO_ROOT / unit["request_path"]).read_text(encoding="utf-8"))
                self.assertEqual(request["require_source_commit"], unit["require_source_commit"])
                self.assertEqual(request["source_commit"], unit["source_commit"])
                self.assertEqual(request["source_sha256"], unit["source_sha256"])
                self.assertEqual(request["slice_specs"], [unit["slice_spec"]])

            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["source"]["planning_mode"], "explicit_workers")
            self.assertEqual(
                [source["source_commit"] for source in context_pack["source"]["worker_sources"]],
                ["commit-one", "commit-two"],
            )
            self.assertEqual(
                [worker["require_source_commit"] for worker in context_pack["workers"]],
                ["commit-one", "commit-two"],
            )
            self.assertEqual(
                [agent["source_commit"] for agent in agent_index["agents"]],
                ["commit-one", "commit-two"],
            )

    def test_run_batch_profile_rejects_explicit_worker_slice_spec_mismatch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            spec_root = Path(tmp) / "slice-specs"
            mismatched_spec = write_slice_spec(
                spec_root / "first-unit.json",
                "demo",
                "demo-first",
                "first_unit",
                "commit-one",
            )
            profile_path = Path(tmp) / "planned-batch-explicit-workers.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-explicit-workers-bad-spec",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "mode": "deterministic",
                        "execute_merge": False,
                        "max_workers": 1,
                        "workers": [
                            {
                                "worker_id": "explicit-worker-001-second-unit",
                                "target_id": "demo",
                                "source_repo_root": repo_rel(source_root),
                                "source_file": "src/demo.c",
                                "function": "second_unit",
                                "slice_id": "demo-second",
                                "source_commit": "commit-one",
                                "require_source_commit": "commit-one",
                                "slice_spec": repo_rel(mismatched_spec),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"worker should not run for mismatched slice spec: {argv}")

            with self.assertRaisesRegex(SystemExit, "slice spec function_name mismatch"):
                harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-explicit-bad-spec",
                    out_root=out_root,
                    command_runner=fail_if_called,
                    repo_root=REPO_ROOT,
                )

    def test_run_batch_profile_rejects_explicit_worker_source_hash_mismatch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            spec_root = Path(tmp) / "slice-specs"
            spec_path = write_slice_spec(spec_root / "first-unit.json", "demo", "demo-first", "first_unit", "commit-one")
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec["source"] = {
                "source_commit": "commit-one",
                "source_file_hashes": {
                    "src/demo.c": "0" * 64,
                },
            }
            spec_path.write_text(json.dumps(spec, sort_keys=True) + "\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch-explicit-workers.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-explicit-workers-bad-source-hash",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "mode": "deterministic",
                        "execute_merge": False,
                        "max_workers": 1,
                        "workers": [
                            {
                                "worker_id": "explicit-worker-001-first-unit",
                                "target_id": "demo",
                                "source_repo_root": repo_rel(source_root),
                                "source_file": "src/demo.c",
                                "function": "first_unit",
                                "slice_id": "demo-first",
                                "source_commit": "commit-one",
                                "require_source_commit": "commit-one",
                                "slice_spec": repo_rel(spec_path),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"worker should not run for mismatched source hash: {argv}")

            with self.assertRaisesRegex(SystemExit, "source file sha256 mismatch"):
                harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-explicit-bad-source-hash",
                    out_root=out_root,
                    command_runner=fail_if_called,
                    repo_root=REPO_ROOT,
                )

    def test_c_source_sha256_is_stable_across_line_endings(self) -> None:
        with temp_repo_dir() as tmp:
            source_file = Path(tmp) / "FlashDB" / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_bytes(b"int first_unit(int value) {\r\n    return value + 1;\r\n}\r\n")

            expected = hashlib.sha256(b"int first_unit(int value) {\n    return value + 1;\n}\n").hexdigest()

            self.assertEqual(harness.sha256_file(source_file), expected)

    def test_run_batch_profile_opencode_passes_preflight_report_to_workers(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            profile_path = Path(tmp) / "planned-batch.json"
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-profile-opencode",
            )
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-preflight",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "opencode_preflight_report": repo_rel(preflight_report),
                        "execute_merge": False,
                        "auto_retry": False,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )

            handoff_contract = {"path": "target/opencode/handoff-contract.json", "sha256": "a" * 64}
            session_evidence = {"path": "target/opencode/session-evidence.json", "sha256": "b" * 64}
            contract_verification = {"status": "executed", "matched_command": "python3 -B scripts/c2rust-migrator.py"}
            preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
            }
            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "exit_code": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "recorded": False,
                    "handoff_contract": handoff_contract,
                    "opencode_session_evidence": session_evidence,
                    "opencode_contract_verification": contract_verification,
                    "opencode_preflight_report": preflight_binding,
                },
            ) as runner:
                result = harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-profile-opencode",
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(result["mode"], "opencode")
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["mode"], "opencode")
            self.assertEqual(runner.call_args.kwargs["opencode_preflight_report"], Path(repo_rel(preflight_report)))
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            context_worker = context_pack["workers"][0]
            indexed_agent = agent_index["agents_by_worker_id"][context_worker["worker_id"]]
            self.assertEqual(context_pack["entrypoints"]["opencode_preflight_report"], repo_rel(preflight_report))
            self.assertEqual(agent_index["reports"]["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            for indexed in (context_worker, indexed_agent):
                self.assertEqual(indexed["handoff_contract"], handoff_contract)
                self.assertEqual(indexed["opencode_session_evidence"], session_evidence)
                self.assertEqual(indexed["opencode_contract_verification"], contract_verification)
                self.assertEqual(indexed["opencode_preflight_report"], preflight_binding)

    def test_run_batch_profile_rejects_competition_exact_without_exact_host_before_preflight(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-competition-exact-overclaim",
                        "proof_class": "competition-exact",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "mode": "opencode",
                        "execute_merge": False,
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"competition-exact overclaim should fail before launch: {argv}")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": "0"}):
                with self.assertRaisesRegex(SystemExit, "COMPETITION_EXACT_HOST=1"):
                    harness.run_batch_profile(
                        profile_path=profile_path,
                        run_id="run-profile-competition-exact-overclaim",
                        out_root=out_root,
                        command_runner=fail_if_called,
                        repo_root=REPO_ROOT,
                    )

            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())

    def test_run_batch_profile_rejects_cli_competition_exact_override_without_exact_host(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-cli-exact-override",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "mode": "opencode",
                        "execute_merge": False,
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"competition-exact override should fail before launch: {argv}")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": ""}):
                with self.assertRaisesRegex(SystemExit, "COMPETITION_EXACT_HOST=1"):
                    harness.run_batch_profile(
                        profile_path=profile_path,
                        run_id="run-profile-cli-exact-override",
                        out_root=out_root,
                        proof_class_override="competition-exact",
                        command_runner=fail_if_called,
                        repo_root=REPO_ROOT,
                    )

            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())

    def test_run_batch_profile_records_cli_proof_class_override(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-cli-exact-override",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": False,
                    }
                ),
                encoding="utf-8",
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" not in argv:
                    raise AssertionError(f"unexpected command for no-merge profile: {argv}")
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": "1"}):
                result = harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-profile-cli-exact-override",
                    out_root=out_root,
                    proof_class_override="competition-exact",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["profile_proof_class"], "local-simulation")
            self.assertEqual(result["proof_class"], "competition-exact")
            self.assertEqual(
                result["proof_class_resolution"],
                {
                    "source": "cli-override",
                    "profile_proof_class": "local-simulation",
                    "effective_proof_class": "competition-exact",
                    "override_requested": True,
                    "changed": True,
                    "override_proof_class": "competition-exact",
                },
            )
            rows = fetch_rows(
                Path(REPO_ROOT / result["db_path"]),
                "select proof_class from runs where run_id=?",
                ("run-profile-cli-exact-override",),
            )
            self.assertEqual(rows, [("competition-exact",)])
            report = json.loads((out_root / "harness" / "batch-profile-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["profile_proof_class"], "local-simulation")
            self.assertEqual(report["proof_class"], "competition-exact")
            self.assertEqual(report["proof_class_resolution"], result["proof_class_resolution"])
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["proof_class_resolution"], result["proof_class_resolution"])
            self.assertEqual(agent_index["proof_class_resolution"], result["proof_class_resolution"])

    def test_evaluate_rejects_competition_exact_without_exact_host_before_init_run(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"competition-exact overclaim should fail before worker launch: {argv}")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": ""}):
                with self.assertRaisesRegex(SystemExit, "COMPETITION_EXACT_HOST=1"):
                    harness.evaluate(
                        run_id="run-evaluate-competition-exact-overclaim",
                        target_id="demo",
                        source_repo_root=source_root,
                        source_file="src/demo.c",
                        source_commit="abc123",
                        out_root=out_root,
                        proof_class="competition-exact",
                        functions=["first_unit"],
                        mode="deterministic",
                        execute_merge=False,
                        command_runner=fail_if_called,
                        repo_root=REPO_ROOT,
                    )

            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())

    def test_run_batch_profile_opencode_auto_runs_preflight_when_profile_omits_report(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-auto-preflight",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "execute_merge": False,
                        "auto_retry": False,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )

            preflight_kwargs: dict[str, object] = {}

            def fake_preflight_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                preflight_kwargs.update(kwargs)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="run-profile-opencode-auto")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": "",
                "status": "passed",
            }

            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "exit_code": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "recorded": False,
                    "opencode_preflight_report": preflight_binding,
                },
            ) as runner:
                result = harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-profile-opencode-auto",
                    out_root=out_root,
                    command_runner=fake_preflight_runner,
                    repo_root=REPO_ROOT,
                )

            preflight_report_payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            expected_preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
                "run_id": "run-profile-opencode-auto",
                "contract_status": "executed",
                "launch_policy": {
                    "opencode_command": "opencode",
                    "opencode_model": "GLM-5.1",
                    "opencode_agent": "c2rust-migrator",
                    "opencode_variant": "max",
                    "opencode_skip_permissions": False,
                },
                "launch_policy_sha256": harness.sha256_text(
                    json.dumps(
                        {
                            "opencode_agent": "c2rust-migrator",
                            "opencode_command": "opencode",
                            "opencode_model": "GLM-5.1",
                            "opencode_skip_permissions": False,
                            "opencode_variant": "max",
                        },
                        sort_keys=True,
                    )
                ),
                "opencode_model_availability": {
                    "status": "available",
                    "opencode_command": "opencode",
                    "required_model": "GLM-5.1",
                    "argv": preflight_report_payload["opencode_model_availability"]["argv"],
                    "process_returncode": 0,
                    "model_listed": True,
                },
                "opencode_runtime_env": preflight_report_payload["opencode_runtime_env"],
                "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
            }
            self.assertEqual(result["mode"], "opencode")
            self.assertEqual(result["opencode_preflight_report"], expected_preflight_binding)
            self.assertEqual(preflight_kwargs["timeout"], 13)
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["opencode_preflight_report"], Path(repo_rel(preflight_report)))
            self.assertEqual(runner.call_args.kwargs["timeout_seconds"], 13)
            run_plan = result["run_plan"]
            self.assertEqual(run_plan["opencode_preflight_report"], expected_preflight_binding)
            self.assertEqual(
                run_plan["graph"]["opencode_worker"]["preflight_report"]["path"],
                repo_rel(preflight_report),
            )
            self.assertEqual(run_plan["graph"]["opencode_worker"]["opencode_variant"], "max")
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["entrypoints"]["opencode_preflight_report"], repo_rel(preflight_report))
            self.assertEqual(agent_index["reports"]["opencode_preflight_report"], expected_preflight_binding)

    def test_run_batch_profile_opencode_auto_preflight_failure_writes_blocked_report_before_planning(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-auto-preflight-blocked",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "opencode_model": "GLM-5.1",
                        "execute_merge": False,
                        "auto_retry": False,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )
            stale_files = [
                out_root / "summary" / "competition-run-summary.json",
                out_root / "summary" / "workflow-metrics.json",
                out_root / "summary" / "route-governance-metrics-report.json",
                out_root / "harness" / "run-plan-report.json",
                out_root / "harness" / "judge-evidence-index.json",
                out_root / "harness" / "context-pack.json",
                out_root / "harness" / "agent-index.json",
                out_root / "state" / "opencode-agent-harness.sqlite3",
                out_root / "workers" / "old-worker" / "summary" / "competition-run-summary.json",
                out_root / "harness" / "plans" / "old-workers.json",
            ]
            for stale_file in stale_files:
                stale_file.parent.mkdir(parents=True, exist_ok=True)
                stale_file.write_text(json.dumps({"stale": True}), encoding="utf-8")

            def fake_preflight_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="gpt-5.4\n", stderr="")
                raise AssertionError(f"batch preflight failure must not launch OpenCode worker or marker command: {argv}")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-profile-opencode-preflight-blocked",
                out_root=out_root,
                command_runner=fake_preflight_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["report_kind"], "batch-profile-report")
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["blocked_phase"], "opencode-preflight")
            self.assertEqual(result["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(result["profile_proof_class"], "local-simulation")
            self.assertEqual(result["proof_class"], "local-simulation")
            self.assertEqual(
                result["proof_class_resolution"],
                {
                    "source": "profile",
                    "profile_proof_class": "local-simulation",
                    "effective_proof_class": "local-simulation",
                    "override_requested": False,
                    "changed": False,
                },
            )
            self.assertFalse(result["semantic_gate"])
            self.assertEqual(result["translation_coverage_numerator"], 0)
            self.assertFalse(result["local_simulation_closes_p0_h9"])
            self.assertEqual(result["worker_count"], 0)
            self.assertNotIn("run_plan", result)
            self.assertEqual(result["stale_artifact_cleanup"]["status"], "passed")
            self.assertEqual(
                sorted(result["stale_artifact_cleanup"]["removed_artifacts"]),
                sorted(
                    [
                        repo_rel(out_root / "summary" / "competition-run-summary.json"),
                        repo_rel(out_root / "summary" / "workflow-metrics.json"),
                        repo_rel(out_root / "summary" / "route-governance-metrics-report.json"),
                        repo_rel(out_root / "harness" / "run-plan-report.json"),
                        repo_rel(out_root / "harness" / "judge-evidence-index.json"),
                        repo_rel(out_root / "harness" / "context-pack.json"),
                        repo_rel(out_root / "harness" / "agent-index.json"),
                        repo_rel(out_root / "state" / "opencode-agent-harness.sqlite3"),
                        repo_rel(out_root / "workers"),
                        repo_rel(out_root / "harness" / "plans"),
                    ]
                ),
            )
            for stale_file in stale_files:
                self.assertFalse(stale_file.exists(), stale_file)
            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())
            self.assertFalse((out_root / "harness" / "plans").exists())

            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            self.assertTrue(preflight_report.exists())
            preflight_payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            self.assertEqual(result["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["status"], "failed")
            self.assertEqual(result["opencode_preflight_report"]["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(result["h9_blocker"], preflight_payload["h9_blocker"])
            self.assertFalse(result["h9_blocker"]["opencode_run_launched"])

            batch_report = out_root / "harness" / "batch-profile-report.json"
            self.assertEqual(json.loads(batch_report.read_text(encoding="utf-8")), result)

    def test_run_batch_profile_opencode_hostless_rehearsal_executes_auto_preflight_and_worker_contracts(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-hostless-rehearsal",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": False,
                        "opencode_hostless_rehearsal": True,
                        "opencode_hostless_rehearsal_runner": "fake/fixture",
                        "execute_merge": False,
                        "auto_retry": False,
                        "max_workers": 1,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_opencode_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                if len(calls) == 2:
                    contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                    contract = json.loads(contract_path.read_text(encoding="utf-8"))
                    marker_path = REPO_ROOT / contract["expected_marker_path"]
                    write_valid_preflight_marker(marker_path, run_id="run-profile-opencode-hostless")
                    stdout = json.dumps(
                        {
                            "type": "tool_use",
                            "part": {
                                "tool": "bash",
                                "state": {
                                    "input": {
                                        "command": contract["worker_command_line"],
                                        "workdir": str(REPO_ROOT),
                                    },
                                    "status": "completed",
                                },
                            },
                        }
                    )
                    return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

                handoff_paths = list(out_root.glob("workers/*/harness/opencode-handoff-contract.json"))
                self.assertEqual(len(handoff_paths), 1)
                contract = json.loads(handoff_paths[0].read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / contract["expected_summary_path"]
                write_worker_summary(summary_path, "run-profile-opencode-hostless", status="passed", failed=0, semantic_pass=1)
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {
                                    "command": contract["worker_command_line"],
                                    "workdir": str(REPO_ROOT),
                                },
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-profile-opencode-hostless",
                out_root=out_root,
                command_runner=fake_opencode_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual([call[1] for call in calls], ["models", "run", "run"])
            rehearsal_ref = result["opencode_hostless_rehearsal_report"]
            rehearsal_path = REPO_ROOT / rehearsal_ref["path"]
            self.assertEqual(rehearsal_ref["sha256"], harness.sha256_file(rehearsal_path))
            rehearsal = json.loads(rehearsal_path.read_text(encoding="utf-8"))
            self.assertEqual(rehearsal["report_kind"], "opencode-hostless-rehearsal-report")
            self.assertEqual(rehearsal["proof_class"], "local-simulation")
            self.assertEqual(rehearsal["rehearsal_runner"], "fake/fixture")
            self.assertFalse(rehearsal["closes_p0_h9"])
            self.assertFalse(rehearsal["semantic_gate"])
            self.assertFalse(rehearsal["chat_output_is_evidence"])
            self.assertFalse(rehearsal["generated_draft_semantic_pass"])
            self.assertEqual(rehearsal["translation_coverage_numerator"], 0)
            self.assertEqual(rehearsal["h9_contract"]["status"], "blocked")
            self.assertEqual(rehearsal["h9_contract"]["required_agent_tool"], "opencode")
            self.assertEqual(rehearsal["h9_contract"]["required_agent"], "c2rust-migrator")
            self.assertEqual(rehearsal["h9_contract"]["required_model"], "GLM-5.1")
            self.assertEqual(rehearsal["h9_contract"]["required_variant"], "max")
            self.assertEqual(rehearsal["opencode_preflight_report"], result["opencode_preflight_report"])
            self.assertEqual(rehearsal["context_pack"], result["context_pack"])
            self.assertEqual(rehearsal["agent_index"], result["agent_index"])
            self.assertEqual(rehearsal["run_plan_report"]["path"], result["run_plan"]["report_path"])
            self.assertTrue(rehearsal["opencode_runtime"]["all_contracts_executed"])
            self.assertEqual(rehearsal["opencode_runtime"]["contract_status_counts"], {"executed": 1})
            self.assertEqual(rehearsal["workers"][0]["opencode_contract_verification"]["status"], "executed")
            self.assertEqual(rehearsal["workers"][0]["final_decision"], {"status": "accepted", "reason": "worker_summary_passed"})
            artifact_rows = fetch_rows(
                REPO_ROOT / result["db_path"],
                "select kind, repo_rel_path, semantic_role from artifacts",
            )
            self.assertIn(
                (
                    "opencode-hostless-rehearsal-report",
                    rehearsal_ref["path"],
                    "opencode-hostless-rehearsal",
                ),
                artifact_rows,
            )

    def test_opencode_preflight_uses_repo_local_runtime_env_contract(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            captured_env: dict[str, str] = {}

            def fake_preflight_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                captured_env.update(kwargs["env"])  # type: ignore[arg-type]
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract = json.loads((out_root / "harness" / "opencode-preflight-contract.json").read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="preflight-env")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            report = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-env",
                command_runner=fake_preflight_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(report["status"], "passed")
            runtime_env = report["opencode_runtime_env"]
            self.assertEqual(runtime_env["status"], "isolated")
            self.assertEqual(runtime_env["scope"], "preflight")
            self.assertEqual(runtime_env["env"]["XDG_CONFIG_HOME"], repo_rel(out_root / "opencode-runtime" / "preflight" / "config"))
            self.assertEqual(captured_env["XDG_CONFIG_HOME"], str(out_root / "opencode-runtime" / "preflight" / "config"))
            self.assertEqual(captured_env["XDG_DATA_HOME"], str(out_root / "opencode-runtime" / "preflight" / "data"))
            self.assertEqual(captured_env["XDG_CACHE_HOME"], str(out_root / "opencode-runtime" / "preflight" / "cache"))
            self.assertEqual(captured_env["TMPDIR"], str(out_root / "opencode-runtime" / "preflight" / "tmp"))
            contract = json.loads((out_root / "harness" / "opencode-preflight-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["opencode_runtime_env"], runtime_env)
            session = json.loads((out_root / "logs" / "opencode-preflight-session-evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(session["opencode_runtime_env"], runtime_env)

    def test_validate_opencode_runtime_env_contract_rejects_recomputed_wrong_runtime_root(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="worker-a",
                repo_root=REPO_ROOT,
            )
            bad_root = out_root / "wrong-runtime" / "worker-a"
            runtime_env["runtime_root"] = repo_rel(bad_root)
            runtime_env["env"] = {
                "XDG_CONFIG_HOME": repo_rel(bad_root / "config"),
                "XDG_DATA_HOME": repo_rel(bad_root / "data"),
                "XDG_CACHE_HOME": repo_rel(bad_root / "cache"),
                "TMPDIR": repo_rel(bad_root / "tmp"),
                "TEMP": repo_rel(bad_root / "tmp"),
                "TMP": repo_rel(bad_root / "tmp"),
            }
            runtime_env["env_sha256"] = harness.sha256_text(
                json.dumps(
                    {
                        "scope": runtime_env["scope"],
                        "runtime_root": runtime_env["runtime_root"],
                        "env": runtime_env["env"],
                    },
                    sort_keys=True,
                )
            )

            with self.assertRaisesRegex(SystemExit, "runtime_root must end with opencode-runtime/<scope>"):
                harness.validate_opencode_runtime_env_contract(
                    runtime_env,
                    context="unit-test",
                    repo_root=REPO_ROOT,
                )

    def test_evaluate_runs_planning_workers_and_merge_as_one_command(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }

                int second_unit(int value) {
                    return value + 2;
                }
                """,
                encoding="utf-8",
            )
            worker_run_ids: list[str] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    worker_run_ids.append(str(request["run_id"]))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-evaluate",
                    status="passed",
                    failed=0,
                    semantic_pass=2,
                    workflow_metrics=before_after_worker_metrics(out_root, "run-evaluate"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["first_unit", "second_unit"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-demo",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=True,
                max_workers=2,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["entrypoint"], "evaluate")
            self.assertEqual(result["run_plan"]["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(result["run_plan"]["graph"]["runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(len(worker_run_ids), 2)
            self.assertTrue((out_root / "summary" / "competition-run-summary.json").exists())
            judge_summary = result["judge_summary"]
            self.assertEqual(judge_summary["harness_architecture"]["entrypoint"], "evaluate")
            self.assertEqual(judge_summary["harness_architecture"]["graph_runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(judge_summary["harness_architecture"]["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(judge_summary["harness_architecture"]["context_pack"]["path"], result["context_pack"]["path"])
            self.assertEqual(judge_summary["harness_architecture"]["agent_index"]["path"], result["agent_index"]["path"])
            self.assert_architecture_contracts(judge_summary["harness_architecture"]["architecture_contracts"])
            headline = result["judge_headline"]
            self.assertEqual(headline["report_kind"], "judge-headline")
            self.assertEqual(headline["entrypoint"], "evaluate")
            self.assertEqual(headline["status"], "completed")
            self.assertEqual(headline["graph_runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(headline["worker_count"], 2)
            self.assertEqual(headline["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(headline["repair_round_cap"], 5)
            self.assertEqual(headline["semantic_claim_source"], "final_gate_and_worker_summaries")
            self.assertFalse(headline["semantic_gate"])
            self.assertEqual(headline["context_pack"], result["context_pack"])
            self.assertEqual(headline["agent_index"], result["agent_index"])
            self.assertEqual(judge_summary["core_translation_quality"]["final_gate_status"], "passed")
            self.assertEqual(judge_summary["core_translation_quality"]["semantic_pass_count"], 2)
            self.assertEqual(judge_summary["core_translation_quality"]["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(judge_summary["core_translation_quality"]["translation_before_after"]["status"], "bound")
            self.assertEqual(judge_summary["core_translation_quality"]["translation_before_after"]["unit_count"], 1)
            self.assertEqual(judge_summary["core_translation_quality"]["repair_summary"]["repair_history_unit_count"], 0)
            self.assertEqual(
                [worker["summary_status"] for worker in judge_summary["core_translation_quality"]["workers"]],
                ["passed", "passed"],
            )
            self.assertEqual(
                [worker["final_decision"]["status"] for worker in judge_summary["core_translation_quality"]["workers"]],
                ["accepted", "accepted"],
            )
            context_pack_path = REPO_ROOT / result["context_pack"]["path"]
            agent_index_path = REPO_ROOT / result["agent_index"]["path"]
            context_pack = json.loads(context_pack_path.read_text(encoding="utf-8"))
            agent_index = json.loads(agent_index_path.read_text(encoding="utf-8"))
            self.assertEqual(context_pack["run_id"], "run-evaluate")
            self.assertEqual(context_pack["graph"]["runtime"], "opencode-harness-langgraph-inspired")
            self.assert_context_management_contract(context_pack["context_management_contract"])
            self.assertEqual(context_pack["entrypoints"]["evaluate_report"], result["report_path"])
            self.assertEqual(context_pack["entrypoints"]["merge_plan"], result["run_plan"]["merge_plan"]["path"])
            self.assertEqual(context_pack["entrypoints"]["merge_summary"], result["run_plan"]["merge_execution"]["summary_path"])
            self.assertEqual(len(context_pack["workers"]), 2)
            self.assertEqual(agent_index["run_id"], "run-evaluate")
            self.assert_agent_coordination_contract(agent_index["agent_coordination_contract"], expected_worker_count=2)
            planned_worker_ids = [unit["worker_id"] for unit in result["plan"]["units"]]
            self.assertEqual([worker["worker_id"] for worker in context_pack["workers"]], planned_worker_ids)
            self.assertEqual([agent["worker_id"] for agent in agent_index["agents"]], planned_worker_ids)
            self.assertEqual(sorted(agent_index["agents_by_worker_id"]), planned_worker_ids)
            for unit in result["plan"]["units"]:
                indexed_agent = agent_index["agents_by_worker_id"][unit["worker_id"]]
                self.assertEqual(indexed_agent["assignment_path"], unit["assignment_path"])
                self.assertEqual(indexed_agent["request_path"], unit["request_path"])
                self.assertIn("summary_path", indexed_agent)
                self.assertIn("report_path", indexed_agent)
            db_path = Path(REPO_ROOT / result["db_path"])
            context_rows = fetch_rows(
                db_path,
                """
                select context_pack_id, run_id, target_id, slice_id, depth, max_tokens,
                       artifact_path, artifact_sha256, payload_json
                from context_packs
                """,
            )
            self.assertEqual(len(context_rows), 1)
            context_row = context_rows[0]
            self.assertEqual(context_row[:8], ("run-evaluate-context-pack", "run-evaluate", "flashdb", None, 1, 20000, result["context_pack"]["path"], result["context_pack"]["sha256"]))
            self.assertEqual(json.loads(context_row[8]), context_pack)
            artifact_rows = fetch_rows(
                db_path,
                """
                select kind, agent_id, repo_rel_path, sha256, semantic_role
                from artifacts
                where kind in ('context-pack', 'agent-index', 'evaluate-report')
                order by kind
                """,
            )
            self.assertEqual(
                artifact_rows,
                [
                    ("agent-index", "planner", result["agent_index"]["path"], result["agent_index"]["sha256"], "agent-index"),
                    ("context-pack", "planner", result["context_pack"]["path"], result["context_pack"]["sha256"], "agent-context-pack"),
                    ("evaluate-report", "planner", result["report_path"], harness.sha256_file(REPO_ROOT / result["report_path"]), "evaluate-report"),
                ],
            )
            event_rows = fetch_rows(db_path, "select event_type from events where run_id=? order by event_id", ("run-evaluate",))
            self.assertIn(("context_pack_written",), event_rows)
            self.assertIn(("evaluate_executed",), event_rows)
            paths_to_check = [
                result["db_path"],
                result["report_path"],
                result["context_pack"]["path"],
                result["agent_index"]["path"],
                context_pack["entrypoints"]["evaluate_report"],
                context_pack["entrypoints"]["run_plan_report"],
                context_pack["entrypoints"]["worker_plan"],
                context_pack["entrypoints"]["merge_plan"],
                context_pack["entrypoints"]["merge_summary"],
                context_pack["entrypoints"]["agent_index"],
            ]
            for worker in context_pack["workers"]:
                paths_to_check.extend(
                    [
                        worker["out_root"],
                        worker["assignment_path"],
                        worker["request_path"],
                        worker["summary_path"],
                        worker["report_path"],
                    ]
                )
            for agent in agent_index["agents"]:
                paths_to_check.extend(
                    [
                        agent["isolated_out_root"],
                        agent["assignment_path"],
                        agent["request_path"],
                        agent["summary_path"],
                        agent["report_path"],
                    ]
                )
            for path_value in paths_to_check:
                if path_value is None:
                    continue
                self.assert_repo_relative_posix_path(path_value)

    def test_evaluate_opencode_passes_preflight_report_to_workers(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-evaluate-opencode",
            )

            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "exit_code": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "recorded": False,
                },
            ) as runner:
                result = harness.evaluate(
                    run_id="run-evaluate-opencode",
                    target_id="flashdb",
                    source_repo_root=source_root,
                    source_file="src/demo.c",
                    functions=["first_unit"],
                    source_commit="abc123",
                    out_root=out_root,
                    proof_class="local-simulation",
                    slice_id_prefix="eval-opencode",
                    worker_prefix="eval-worker",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    execute_merge=False,
                    auto_retry=False,
                    command_runner=subprocess.run,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(result["mode"], "opencode")
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["mode"], "opencode")
            self.assertEqual(runner.call_args.kwargs["opencode_preflight_report"], preflight_report)

    def test_evaluate_context_pack_preserves_unrecorded_failed_worker(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int missing_summary_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            merge_called = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal merge_called
                if "validation/tools/run_competition.py" in argv:
                    merge_called = True
                return subprocess.CompletedProcess(argv, 0, stdout="no summary written\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate-failed",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["missing_summary_unit"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-failed",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=False,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertFalse(merge_called)
            self.assertEqual(result["run_plan"]["merge_execution"]["status"], "skipped")
            self.assertEqual(result["run_plan"]["merge_execution"]["reason"], "unrecorded-worker-summaries")
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            worker = context_pack["workers"][0]
            agent = agent_index["agents"][0]
            self.assertFalse(worker["recorded"])
            self.assertEqual(worker["exit_code"], 1)
            self.assertEqual(worker["summary_status"], "missing-summary")
            self.assert_repo_relative_posix_path(worker["summary_path"])
            self.assert_repo_relative_posix_path(worker["report_path"])
            self.assertFalse((REPO_ROOT / worker["summary_path"]).exists())
            self.assertTrue((REPO_ROOT / worker["report_path"]).exists())
            self.assertFalse(agent["recorded"])
            self.assertEqual(agent["status"], "missing-summary")
            self.assertEqual(context_pack["entrypoints"]["merge_summary"], None)
            self.assertEqual(context_pack["acceptance_boundary"]["semantic_acceptance"], "final verification and worker summaries decide acceptance; this pack is an index only")

    def test_run_batch_profile_binds_before_after_exhibit_report(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "demo-source"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int store_add_one(int value, int* out) {
                    out[0] = value + 1;
                    return 0;
                }
                """,
                encoding="utf-8",
            )
            spec_path = write_slice_spec(
                Path(tmp) / "slice-specs" / "store-add-one.json",
                "demo",
                "store-add-one",
                "store_add_one",
                "abc123",
            )
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-before-after",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["store_add_one"],
                        "slice_specs": [repo_rel(spec_path)],
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "slice_id_prefix": "demo",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "emit_before_after_exhibit_report": True,
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                            "claim": "test before/after exhibit",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-before-after",
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=before_after_worker_metrics(out_root, "run-before-after"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-before-after",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            exhibit_ref = result["before_after_exhibit_report"]
            exhibit_path = REPO_ROOT / exhibit_ref["path"]
            self.assertTrue(exhibit_path.exists())
            self.assertEqual(exhibit_ref["sha256"], harness.sha256_file(exhibit_path))
            self.assertEqual(exhibit_ref["status"], "passed")
            self.assertEqual(exhibit_ref["unit_count"], 1)
            exhibit = json.loads(exhibit_path.read_text(encoding="utf-8"))
            self.assertEqual(exhibit["report_kind"], "before-after-exhibit")
            self.assertEqual(exhibit["status"], "passed")
            self.assertEqual(set(exhibit["stage_contracts"]), {"planner", "worker", "verifier", "repairer", "reporter"})
            self.assertEqual(exhibit["stage_contracts"]["planner"]["status"], "planned")
            self.assertEqual(exhibit["stage_contracts"]["planner"]["units"][0]["slice_id"], "store-add-one")
            self.assertEqual(exhibit["translation_before_after"]["status"], "bound")
            self.assertEqual(exhibit["translation_before_after"]["unit_count"], 1)
            unit = exhibit["units"][0]
            self.assertEqual(unit["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(unit["patch_origin"]["source"], "accepted_safe_evidence")
            self.assertFalse(unit["patch_origin"]["opencode_session_bound"])
            self.assertEqual(unit["patch_origin"]["semantic_claim_source"], "accepted_evidence_binding")
            self.assertFalse(unit["patch_origin"]["generated_draft_semantic_pass"])
            provenance = unit["safety_loop_provenance"]
            self.assertEqual(provenance["status"], "accepted_evidence_bound")
            self.assertEqual(provenance["patch_source"], "accepted_safe_evidence")
            self.assertEqual(provenance["unsafe_delta"]["reduced_by"], 3)
            self.assertFalse(provenance["opencode_session_bound"])
            self.assertFalse(provenance["repair_history_bound"])
            self.assertFalse(provenance["semantic_gate"])
            self.assertEqual(provenance["translation_coverage_numerator"], 0)
            rollup = exhibit["safety_loop_provenance"]
            self.assertEqual(rollup["status"], "bound")
            self.assertEqual(rollup["unit_count"], 1)
            self.assertEqual(rollup["accepted_evidence_bound_unit_count"], 1)
            self.assertEqual(rollup["opencode_session_bound_unit_count"], 0)
            self.assertEqual(rollup["repair_history_bound_unit_count"], 0)
            self.assertEqual(rollup["measured_unsafe_reduction_unit_count"], 1)
            self.assertFalse(rollup["semantic_gate"])
            self.assertEqual(rollup["translation_coverage_numerator"], 0)
            self.assertIn("run-batch-profile", exhibit["reproduction"]["run_command"])
            self.assertIn("validate_competition_run_summary.py", exhibit["reproduction"]["verify_command"])
            judge_summary = result["judge_summary"]
            self.assertEqual(judge_summary["harness_architecture"]["entrypoint"], "run-batch-profile")
            self.assertEqual(judge_summary["harness_architecture"]["context_pack"]["path"], result["context_pack"]["path"])
            self.assertEqual(judge_summary["core_translation_quality"]["final_gate_status"], "passed")
            self.assertEqual(judge_summary["core_translation_quality"]["semantic_claim_source"], "accepted_evidence_binding")
            self.assertFalse(judge_summary["core_translation_quality"]["generated_draft_semantic_pass"])
            self.assertEqual(judge_summary["core_translation_quality"]["before_after_exhibit"]["status"], "passed")
            self.assertEqual(judge_summary["core_translation_quality"]["before_after_exhibit"]["unit_count"], 1)
            self.assertEqual(judge_summary["core_translation_quality"]["unsafe_reduction"]["reduced_by"], 3)
            persisted_report = json.loads((out_root / "harness" / "batch-profile-report.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted_report["judge_summary"], judge_summary)
            artifact_rows = fetch_rows(
                result["db_path"],
                "select kind, repo_rel_path, semantic_role from artifacts where kind='before-after-exhibit-report'",
            )
            self.assertEqual(
                artifact_rows,
                [("before-after-exhibit-report", exhibit_ref["path"], "before-after-exhibit")],
            )

    def test_before_after_exhibit_surfaces_bound_repair_history(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-repair",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            workflow_metrics = before_after_worker_metrics(out_root, "run-before-after-repair")
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = workflow_metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["root_cause_key"] = "rustc_compile_failed"
            unit["repair_history"] = {
                "patch_events_path": history_path.name,
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": ["target/competition-out/workers/worker-a/harness/rollback-before-retry.json"],
                "verified": True,
            }
            workflow_metrics["avg_repair_rounds"] = 1.0
            workflow_metrics["auto_recovery_rate"] = 1.0
            workflow_metrics["root_cause_counts"] = {"rustc_compile_failed": 1}
            write_worker_summary(
                summary_path,
                "run-before-after-repair",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=workflow_metrics,
            )

            result = harness.write_before_after_exhibit_profile_report(
                profile=profile,
                profile_path=profile_path,
                run_id="run-before-after-repair",
                proof_class="local-simulation",
                mode="deterministic",
                plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                run_result={"workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                route_metrics_artifact=None,
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            self.assertIsNotNone(result)
            exhibit = result["payload"]
            unit_exhibit = exhibit["units"][0]
            self.assertEqual(unit_exhibit["repair_rounds"], 1)
            self.assertTrue(unit_exhibit["auto_recovered"])
            self.assertEqual(unit_exhibit["repair_history"]["patch_events_sha256"], harness.sha256_file(history_path))
            self.assertEqual(unit_exhibit["root_cause_key"], "rustc_compile_failed")
            self.assertEqual(unit_exhibit["patch_origin"]["source"], "accepted_safe_evidence")
            self.assertTrue(unit_exhibit["patch_origin"]["accepted_patch_bound"])
            self.assertFalse(unit_exhibit["patch_origin"]["opencode_session_bound"])
            self.assertTrue(unit_exhibit["patch_origin"]["repair_history_bound"])
            self.assertFalse(unit_exhibit["patch_origin"]["semantic_gate"])
            self.assertEqual(unit_exhibit["patch_origin"]["translation_coverage_numerator"], 0)
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["status"], "accepted_evidence_bound")
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["patch_source"], "accepted_safe_evidence")
            self.assertTrue(unit_exhibit["safety_loop_provenance"]["repair_history_bound"])
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["repair_rounds"], 1)
            self.assertTrue(unit_exhibit["safety_loop_provenance"]["auto_recovered"])
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["unsafe_delta"]["reduced_by"], 3)
            self.assertFalse(unit_exhibit["safety_loop_provenance"]["semantic_gate"])
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["translation_coverage_numerator"], 0)
            repairer = exhibit["stage_contracts"]["repairer"]
            self.assertEqual(repairer["status"], "verified")
            self.assertEqual(repairer["repair_round_cap"], 5)
            self.assertEqual(repairer["observed_repair_unit_count"], 1)
            self.assertEqual(repairer["avg_repair_rounds"], 1.0)
            self.assertEqual(repairer["auto_recovery_rate"], 1.0)
            self.assertEqual(repairer["root_cause_counts"], {"rustc_compile_failed": 1})
            self.assertEqual(repairer["histories"][0]["unit_id"], "demo/store-add-one")

    def test_before_after_exhibit_requires_verified_repair_trace_when_profile_demands_it(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-strict-repair",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            write_worker_summary(
                summary_path,
                "run-before-after-strict-repair",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=before_after_worker_metrics(out_root, "run-before-after-strict-repair"),
            )

            with self.assertRaisesRegex(SystemExit, "requires verified repair trace"):
                harness.write_before_after_exhibit_profile_report(
                    profile=profile,
                    profile_path=profile_path,
                    run_id="run-before-after-strict-repair",
                    proof_class="local-simulation",
                    mode="deterministic",
                    plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                    run_result={"workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                    route_metrics_artifact=None,
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

    def test_flashdb_before_after_profile_fails_closed_without_repair_trace(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = REPO_ROOT / "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertTrue(profile["require_repair_trace"])
            self.assertEqual(profile["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(
                profile["attempt_evidence_policy"]["translation_before_after"]["path"],
                profile["acceptance_boundary"]["translation_before_after"],
            )
            self.assertEqual(
                profile["attempt_evidence_policy"]["baseline_attempt"]["root_cause_key"],
                "unsafe_baseline_requires_repair",
            )
            write_worker_summary(
                summary_path,
                "run-flashdb-before-after-strict-repair",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=before_after_worker_metrics(out_root, "run-flashdb-before-after-strict-repair"),
            )

            with self.assertRaisesRegex(SystemExit, "requires verified repair trace"):
                harness.write_before_after_exhibit_profile_report(
                    profile=profile,
                    profile_path=profile_path,
                    run_id="run-flashdb-before-after-strict-repair",
                    proof_class="local-simulation",
                    mode="deterministic",
                    plan={"status": "planned", "units": [{"slice_id": "real-fdb-calc-crc32"}]},
                    run_result={"workers": [{"worker_id": "flashdb-worker-001-fdb-calc-crc32", "exit_code": 0}]},
                    route_metrics_artifact=None,
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

    def test_flashdb_before_after_profile_run_batch_fails_closed_without_repair_trace(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = REPO_ROOT / "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-flashdb-before-after-profile-strict",
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=before_after_worker_metrics(out_root, "run-flashdb-before-after-profile-strict"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            with self.assertRaisesRegex(SystemExit, "requires verified repair trace"):
                harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-flashdb-before-after-profile-strict",
                    out_root=out_root,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertFalse((out_root / "summary" / "before-after-exhibit.json").exists())
            self.assertFalse((out_root / "harness" / "batch-profile-report.json").exists())

    def test_run_batch_profile_auto_retry_produces_verified_before_after_repair_exhibit(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "demo-source"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int store_add_one(int value, int* out) {
                    out[0] = value + 1;
                    return 0;
                }
                """,
                encoding="utf-8",
            )
            spec_path = write_slice_spec(
                Path(tmp) / "slice-specs" / "store-add-one.json",
                "demo",
                "store-add-one",
                "store_add_one",
                "abc123",
            )
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-before-after-auto-repair",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["store_add_one"],
                        "slice_specs": [repo_rel(spec_path)],
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "slice_id_prefix": "demo",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "auto_retry": True,
                        "emit_before_after_exhibit_report": True,
                        "require_repair_trace": True,
                        "attempt_evidence_policy": {
                            "mode": "baseline_repair_gate",
                            "baseline_attempt": {
                                "attempt_number": 1,
                                "verified_unsafe_baseline": verified_baseline_ref,
                            },
                            "accepted_attempt": {"min_attempt_number": 2, "require_hint_id": True},
                        },
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                            "claim": "test auto-retry before/after exhibit",
                        },
                    }
                ),
                encoding="utf-8",
            )
            worker_attempts = 0
            seen_requests: list[dict] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    seen_requests.append(request)
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts == 1:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(
                            summary_path,
                            request["run_id"],
                            status="passed",
                            failed=0,
                            semantic_pass=1,
                            workflow_metrics=before_after_worker_metrics(
                                out_root,
                                request["run_id"],
                                baseline_verification=verified_baseline_ref,
                            ),
                        )
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                if "validation/tools/run_competition.py" in argv:
                    runtime_argv = [sys.executable, *argv[1:]]
                    return subprocess.run(
                        runtime_argv,
                        cwd=REPO_ROOT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        capture_output=True,
                    )
                return subprocess.run(
                    argv,
                    cwd=REPO_ROOT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                )

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-before-after-auto-repair",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            run_plan_detail = result.get("run_plan") or {}
            self.assertEqual(
                result["status"],
                "completed",
                json.dumps(
                    {
                        "failed_workers": run_plan_detail.get("failed_workers"),
                        "workers": run_plan_detail.get("workers"),
                        "merge_execution": run_plan_detail.get("merge_execution"),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
            self.assertEqual(worker_attempts, 2)
            self.assertEqual(
                seen_requests[0]["harness_repair_trace"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(
                seen_requests[1]["harness_repair_trace"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(result["run_plan"]["auto_retry"]["retried_worker_count"], 1)
            exhibit_ref = result["before_after_exhibit_report"]
            exhibit = json.loads((out_root / "summary" / "before-after-exhibit.json").read_text(encoding="utf-8"))
            repairer = exhibit["stage_contracts"]["repairer"]
            self.assertEqual(repairer["status"], "verified")
            self.assertEqual(repairer["observed_repair_unit_count"], 1)
            self.assertEqual(repairer["histories"][0]["repair_rounds"], 1)
            self.assertTrue(repairer["histories"][0]["auto_recovered"])
            repair_history = repairer["histories"][0]["repair_history"]
            self.assertTrue(repair_history["verified"])
            self.assertIn("verified", repair_history["statuses"])
            self.assertRegex(repair_history["patch_events_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(repair_history["rollback_ids"]), 1)
            self.assertTrue((REPO_ROOT / repair_history["patch_events_path"]).exists())
            unit = exhibit["units"][0]
            self.assertEqual(unit["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(unit["baseline_verification"], verified_baseline_ref)
            self.assertEqual(unit["repair_history"], repair_history)
            summary_metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_metrics["translation_before_after"]["status"], "bound")
            self.assertEqual(
                summary_metrics["translation_before_after"]["units"][0]["baseline_verification"],
                verified_baseline_ref,
            )
            self.assertEqual(summary_metrics["root_cause_counts"], {"final_gate_failed": 1})
            self.assertEqual(summary_metrics["per_unit_statuses"][0]["root_cause_key"], "final_gate_failed")
            self.assertEqual(summary_metrics["per_unit_statuses"][0]["repair_history"], repair_history)
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(agent_index["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(
                context_pack["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(
                agent_index["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(context_pack["entrypoints"]["before_after_exhibit_report"], exhibit_ref["path"])
            self.assertEqual(context_pack["report_artifacts"]["before_after_exhibit_report"], exhibit_ref)
            self.assertEqual(agent_index["reports"]["before_after_exhibit_report"], exhibit_ref)

            worker_attempts = 0
            seen_requests.clear()
            rerun = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-before-after-auto-repair",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(rerun["status"], "completed")
            self.assertEqual(worker_attempts, 2)
            self.assertEqual(rerun["run_plan"]["auto_retry"]["retried_worker_count"], 1)
            rerun_exhibit = json.loads((out_root / "summary" / "before-after-exhibit.json").read_text(encoding="utf-8"))
            rerun_repairer = rerun_exhibit["stage_contracts"]["repairer"]
            self.assertEqual(rerun_repairer["status"], "verified")
            self.assertEqual(rerun_repairer["histories"][0]["repair_rounds"], 1)

    def test_run_batch_profile_cli_dispatches_profile_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "run-batch-profile",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json",
            "--run-id",
            "run-profile",
            "--out-root",
            "target/competition-out-profile",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "completed", "exit_code": 0},
        ) as runner:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "completed")
        runner.assert_called_once()
        self.assertEqual(
            runner.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json"),
        )
        self.assertEqual(runner.call_args.kwargs["run_id"], "run-profile")
        self.assertEqual(runner.call_args.kwargs["out_root"], Path("target/competition-out-profile"))

    def test_evaluate_cli_dispatches_h1_h5_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "evaluate",
            "--run-id",
            "run-evaluate-cli",
            "--target-id",
            "flashdb",
            "--source-repo-root",
            "sources/FlashDB",
            "--source-repository",
            "https://gitcode.com/xwxf/FlashDB.git",
            "--source-branch",
            "competition",
            "--source-file",
            "src/fdb_utils.c",
            "--function",
            "fdb_calc_crc32",
            "--function",
            "fdb_blob_make",
            "--source-commit",
            "abc123",
            "--require-source-commit",
            "abc123",
            "--slice-spec",
            "validation/slice-specs/flashdb-real-fdb-calc-crc32.json",
            "--compiler-command-source",
            "compile_commands.json",
            "--include-path",
            "inc",
            "--define",
            "FDB_USING_KVDB",
            "--reuse-accepted-evidence",
            "--accepted-evidence-root",
            "validation/evidence",
            "--out-root",
            "target/competition-out-evaluate",
            "--slice-id-prefix",
            "flashdb-fdb-utils",
            "--worker-prefix",
            "flashdb-worker",
            "--limit",
            "2",
            "--proof-class",
            "local-simulation",
            "--mode",
            "opencode",
            "--opencode-command",
            "opencode",
            "--opencode-model",
            "GLM-5.1",
            "--opencode-agent",
            "c2rust-migrator",
            "--opencode-variant",
            "max",
            "--opencode-skip-permissions",
            "--opencode-preflight-report",
            "target/opencode-preflight/harness/opencode-preflight-report.json",
            "--no-execute-merge",
            "--no-auto-retry",
            "--max-workers",
            "4",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "evaluate",
            return_value={"status": "completed", "exit_code": 0},
        ) as runner:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "completed")
        runner.assert_called_once()
        kwargs = runner.call_args.kwargs
        self.assertEqual(kwargs["run_id"], "run-evaluate-cli")
        self.assertEqual(kwargs["target_id"], "flashdb")
        self.assertEqual(kwargs["source_repo_root"], Path("sources/FlashDB"))
        self.assertEqual(kwargs["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(kwargs["source_branch"], "competition")
        self.assertEqual(kwargs["source_file"], "src/fdb_utils.c")
        self.assertEqual(kwargs["functions"], ["fdb_calc_crc32", "fdb_blob_make"])
        self.assertEqual(kwargs["source_commit"], "abc123")
        self.assertEqual(kwargs["require_source_commit"], "abc123")
        self.assertEqual(kwargs["slice_specs"], ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"])
        self.assertEqual(kwargs["compiler_command_source"], "compile_commands.json")
        self.assertEqual(kwargs["include_paths"], ["inc"])
        self.assertEqual(kwargs["defines"], ["FDB_USING_KVDB"])
        self.assertTrue(kwargs["reuse_accepted_evidence"])
        self.assertEqual(kwargs["accepted_evidence_root"], "validation/evidence")
        self.assertEqual(kwargs["out_root"], Path("target/competition-out-evaluate"))
        self.assertEqual(kwargs["slice_id_prefix"], "flashdb-fdb-utils")
        self.assertEqual(kwargs["worker_prefix"], "flashdb-worker")
        self.assertEqual(kwargs["limit"], 2)
        self.assertEqual(kwargs["proof_class"], "local-simulation")
        self.assertEqual(kwargs["mode"], "opencode")
        self.assertEqual(kwargs["opencode_command"], "opencode")
        self.assertEqual(kwargs["opencode_model"], "GLM-5.1")
        self.assertEqual(kwargs["opencode_agent"], "c2rust-migrator")
        self.assertEqual(kwargs["opencode_variant"], "max")
        self.assertTrue(kwargs["opencode_skip_permissions"])
        self.assertEqual(
            kwargs["opencode_preflight_report"],
            Path("target/opencode-preflight/harness/opencode-preflight-report.json"),
        )
        self.assertFalse(kwargs["execute_merge"])
        self.assertFalse(kwargs["auto_retry"])
        self.assertEqual(kwargs["max_workers"], 4)

    def test_evaluate_cli_profile_dispatches_full_batch_profile_path(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "evaluate",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
            "--run-id",
            "run-evaluate-profile",
            "--out-root",
            "target/competition-out-evaluate-profile",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "completed", "exit_code": 0},
        ) as batch_runner, patch.object(
            harness,
            "write_evaluate_profile_report",
            return_value={"status": "completed", "exit_code": 0, "report_kind": "evaluate-report"},
        ) as evaluate_profile_report, patch.object(harness, "evaluate") as direct_evaluate:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["report_kind"], "evaluate-report")
        batch_runner.assert_called_once()
        evaluate_profile_report.assert_called_once()
        direct_evaluate.assert_not_called()
        self.assertEqual(
            batch_runner.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"),
        )
        self.assertEqual(batch_runner.call_args.kwargs["run_id"], "run-evaluate-profile")
        self.assertEqual(batch_runner.call_args.kwargs["out_root"], Path("target/competition-out-evaluate-profile"))
        self.assertIsNone(batch_runner.call_args.kwargs["proof_class_override"])
        self.assertEqual(evaluate_profile_report.call_args.kwargs["batch_result"], {"status": "completed", "exit_code": 0})
        self.assertEqual(
            evaluate_profile_report.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"),
        )

    def test_evaluate_cli_profile_dispatches_proof_class_override(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "evaluate",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            "--run-id",
            "run-evaluate-profile-exact",
            "--out-root",
            "target/competition-out-evaluate-profile-exact",
            "--proof-class",
            "competition-exact",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "blocked", "exit_code": 1},
        ) as batch_runner, patch.object(
            harness,
            "write_evaluate_profile_report",
            return_value={"status": "blocked", "exit_code": 1, "report_kind": "evaluate-report"},
        ) as evaluate_profile_report:
            self.assertEqual(harness.main(), 1)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["report_kind"], "evaluate-report")
        self.assertEqual(batch_runner.call_args.kwargs["proof_class_override"], "competition-exact")
        self.assertEqual(
            batch_runner.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json"),
        )
        evaluate_profile_report.assert_called_once()

    def test_run_batch_profile_cli_dispatches_proof_class_override(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "run-batch-profile",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            "--run-id",
            "run-batch-profile-exact",
            "--out-root",
            "target/competition-out-batch-profile-exact",
            "--proof-class",
            "competition-exact",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "blocked", "exit_code": 1},
        ) as batch_runner:
            self.assertEqual(harness.main(), 1)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(batch_runner.call_args.kwargs["proof_class_override"], "competition-exact")
        self.assertEqual(batch_runner.call_args.kwargs["run_id"], "run-batch-profile-exact")
        self.assertEqual(batch_runner.call_args.kwargs["out_root"], Path("target/competition-out-batch-profile-exact"))

    def test_build_resume_manifest_records_worker_replay_commands(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = out_root / "state" / "opencode-agent-harness.sqlite3"
            worker_root = out_root / "workers" / "worker-001"
            assignment = out_root / "harness" / "assignments" / "worker-001.json"
            request = out_root / "harness" / "assignments" / "worker-001-request.json"
            summary = worker_root / "summary" / "competition-run-summary.json"
            report = worker_root / "harness" / "run-worker-report.json"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            evaluate_report = out_root / "harness" / "evaluate-report.json"
            judge_index = out_root / "harness" / "judge-evidence-index.json"
            resume_manifest = out_root / "harness" / "resume-manifest.json"
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()
            for path in [db_path, assignment, request, summary, report, preflight, evaluate_report, judge_index]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker_fields = {
                "worker_id": "worker-001",
                "slice_id": "demo-unit",
                "function": "demo_unit",
                "assignment_path": repo_rel(assignment),
                "request_path": repo_rel(request),
                "summary_path": repo_rel(summary),
                "report_path": repo_rel(report),
                "out_root": repo_rel(worker_root),
                "source_commit": "abc123",
                "source_sha256": "f" * 64,
                "summary_status": "failed",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "sha256": harness.sha256_file(preflight),
                    "status": "passed",
                    "contract_status": "executed",
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                    "opencode_model_availability": {
                        "status": "available",
                        "opencode_command": "opencode",
                        "required_model": "GLM-5.1",
                        "process_returncode": 0,
                        "model_listed": True,
                    },
                },
            }
            manifest = harness.build_resume_manifest(
                db_path=db_path,
                run_id="run-resume",
                out_root=out_root,
                status="failed",
                context_pack={
                    "entrypoints": {},
                    "attempt_evidence_policy": {
                        "baseline_attempt": {
                            "verified_unsafe_baseline": verified_baseline_ref,
                        }
                    },
                    "workers": [worker_fields],
                },
                context_pack_ref={"path": "target/context-pack.json", "sha256": "a" * 64},
                agent_index={
                    "attempt_evidence_policy": {
                        "baseline_attempt": {
                            "verified_unsafe_baseline": verified_baseline_ref,
                        }
                    },
                    "agents_by_worker_id": {
                        "worker-001": {
                            **worker_fields,
                            "isolated_out_root": repo_rel(worker_root),
                        }
                    }
                },
                agent_index_ref={"path": "target/agent-index.json", "sha256": "b" * 64},
                evaluate_report_path=evaluate_report,
                batch_profile_report_path="target/batch-profile-report.json",
                judge_evidence_index_path=judge_index,
                resume_manifest_path=resume_manifest,
                repair_hints={
                    "source": "sqlite repair_hints",
                    "open_count": 1,
                    "hints": [
                        {
                            "hint_id": "repair:run-resume:worker-001:process_timeout",
                            "status": "open",
                            "worker_id": "worker-001",
                        }
                    ],
                },
                repo_root=REPO_ROOT,
            )

            self.assertEqual(
                manifest["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(manifest["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(manifest["entrypoints"]["verified_unsafe_baseline"], verified_baseline_ref["path"])
            worker = manifest["workers"][0]
            replay = worker["replay_commands"]
            run_worker = replay["run_worker"]
            self.assertEqual(
                run_worker["argv"][:5],
                ["python3", "-B", "-m", "validation.tools.opencode_agent_harness", "run-worker"],
            )
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--db") + 1], repo_rel(db_path))
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--run-id") + 1], "run-resume")
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--worker-id") + 1], "worker-001")
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--mode") + 1], "opencode")
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--opencode-model") + 1], "GLM-5.1")
            self.assertEqual(
                run_worker["argv"][run_worker["argv"].index("--opencode-agent") + 1],
                "c2rust-migrator",
            )
            self.assertIn("--opencode-skip-permissions", run_worker["argv"])
            self.assertEqual(
                run_worker["argv"][run_worker["argv"].index("--opencode-preflight-report") + 1],
                repo_rel(preflight),
            )
            self.assertEqual(run_worker["replay_safety"]["status"], "ready")
            self.assertEqual(run_worker["replay_safety"]["reason"], "opencode_preflight_contract_bound")
            self.assertEqual(run_worker["replay_safety"]["preflight_report"], repo_rel(preflight))
            self.assertEqual(run_worker["replay_safety"]["opencode_runtime_env_sha256"], runtime_env["env_sha256"])
            self.assertEqual(run_worker["assignment_path"], repo_rel(assignment))
            self.assertEqual(run_worker["request_path"], repo_rel(request))
            self.assertEqual(run_worker["summary_path"], repo_rel(summary))
            self.assertEqual(run_worker["out_root"], repo_rel(worker_root))
            self.assertEqual(run_worker["command"], shlex.join(run_worker["argv"]))

            retry_worker = replay["retry_worker"]
            self.assertEqual(
                retry_worker["argv"][:5],
                ["python3", "-B", "-m", "validation.tools.opencode_agent_harness", "retry-worker"],
            )
            self.assertEqual(
                retry_worker["argv"][retry_worker["argv"].index("--hint-id") + 1],
                "repair:run-resume:worker-001:process_timeout",
            )
            self.assertEqual(
                retry_worker["argv"][retry_worker["argv"].index("--opencode-agent") + 1],
                "c2rust-migrator",
            )
            self.assertEqual(retry_worker["command"], shlex.join(retry_worker["argv"]))

    def test_resume_manifest_blocks_opencode_replay_when_preflight_model_is_missing(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": None,
                        "opencode_agent": "default",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["argv"][replay["argv"].index("--opencode-model") + 1], "GLM-5.1")
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_model",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_binding_is_not_passed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            base_preflight = {
                "path": repo_rel(preflight),
                "sha256": "a" * 64,
                "status": "passed",
                "contract_status": "executed",
                "launch_policy": {
                    "opencode_command": "opencode",
                    "opencode_model": "GLM-5.1",
                    "opencode_agent": "c2rust-migrator",
                    "opencode_variant": "max",
                    "opencode_skip_permissions": True,
                },
                "opencode_runtime_env": runtime_env,
                "opencode_model_availability": {
                    "status": "available",
                    "opencode_command": "opencode",
                    "required_model": "GLM-5.1",
                    "process_returncode": 0,
                    "model_listed": True,
                },
            }
            cases = [
                ("failed-status", {"status": "failed"}, "opencode_preflight_report.status"),
                ("not-executed-contract", {"contract_status": "not-executed"}, "opencode_preflight_report.contract_status"),
                ("missing-sha", {"sha256": None}, "opencode_preflight_report.sha256"),
            ]
            for _name, patch_payload, missing_constraint in cases:
                preflight_payload = json.loads(json.dumps(base_preflight))
                for key, value in patch_payload.items():
                    if value is None:
                        preflight_payload.pop(key, None)
                    else:
                        preflight_payload[key] = value
                worker = {
                    "worker_id": "worker-001",
                    "opencode_preflight_report": preflight_payload,
                }

                replay = harness.resume_worker_replay_command(
                    "run-worker",
                    worker=worker,
                    db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                    run_id="run-resume",
                    mode="opencode",
                    repo_root=REPO_ROOT,
                )

                self.assertEqual(replay["replay_safety"]["status"], "blocked")
                self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
                self.assertIn(missing_constraint, replay["replay_safety"]["missing_constraints"])

    def test_resume_manifest_blocks_opencode_replay_when_preflight_sha_mismatches_file(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            preflight.parent.mkdir(parents=True, exist_ok=True)
            preflight.write_text('{"report_kind":"opencode-preflight"}\n', encoding="utf-8")
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "sha256": "a" * 64,
                    "status": "passed",
                    "contract_status": "executed",
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                    "opencode_model_availability": {
                        "status": "available",
                        "opencode_command": "opencode",
                        "required_model": "GLM-5.1",
                        "process_returncode": 0,
                        "model_listed": True,
                    },
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.sha256_mismatch",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_command_is_not_opencode(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "codex",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                    "opencode_model_availability": {
                        "status": "available",
                        "opencode_command": "codex",
                        "required_model": "GLM-5.1",
                        "process_returncode": 0,
                        "model_listed": True,
                    },
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["argv"][replay["argv"].index("--opencode-command") + 1], "codex")
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_command",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_agent_is_not_repo_owned(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "sha256": "a" * 64,
                    "status": "passed",
                    "contract_status": "executed",
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "default",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                    "opencode_model_availability": {
                        "status": "available",
                        "opencode_command": "opencode",
                        "required_model": "GLM-5.1",
                        "process_returncode": 0,
                        "model_listed": True,
                    },
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_agent",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_variant_is_not_competition_max(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "lite",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                    "opencode_model_availability": {
                        "status": "available",
                        "opencode_command": "opencode",
                        "required_model": "GLM-5.1",
                        "process_returncode": 0,
                        "model_listed": True,
                    },
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["argv"][replay["argv"].index("--opencode-variant") + 1], "lite")
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_variant",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_model_availability_is_missing(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertIn("--opencode-model", replay["argv"])
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.opencode_model_availability",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_marks_opencode_replay_blocked_without_preflight_contract(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = out_root / "state" / "opencode-agent-harness.sqlite3"
            worker_root = out_root / "workers" / "worker-001"
            assignment = out_root / "harness" / "assignments" / "worker-001.json"
            request = out_root / "harness" / "assignments" / "worker-001-request.json"
            summary = worker_root / "summary" / "competition-run-summary.json"
            report = worker_root / "harness" / "run-worker-report.json"
            evaluate_report = out_root / "harness" / "evaluate-report.json"
            judge_index = out_root / "harness" / "judge-evidence-index.json"
            resume_manifest = out_root / "harness" / "resume-manifest.json"
            for path in [db_path, assignment, request, summary, report, evaluate_report, judge_index]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

            worker_fields = {
                "worker_id": "worker-001",
                "slice_id": "demo-unit",
                "function": "demo_unit",
                "assignment_path": repo_rel(assignment),
                "request_path": repo_rel(request),
                "summary_path": repo_rel(summary),
                "report_path": repo_rel(report),
                "out_root": repo_rel(worker_root),
                "source_commit": "abc123",
                "source_sha256": "f" * 64,
                "summary_status": "failed",
                "runtime": "opencode",
            }
            manifest = harness.build_resume_manifest(
                db_path=db_path,
                run_id="run-resume",
                out_root=out_root,
                status="failed",
                context_pack={"entrypoints": {}, "mode": "opencode", "workers": [worker_fields]},
                context_pack_ref={"path": "target/context-pack.json", "sha256": "a" * 64},
                agent_index={
                    "agents_by_worker_id": {
                        "worker-001": {
                            **worker_fields,
                            "isolated_out_root": repo_rel(worker_root),
                        }
                    }
                },
                agent_index_ref={"path": "target/agent-index.json", "sha256": "b" * 64},
                evaluate_report_path=evaluate_report,
                batch_profile_report_path="target/batch-profile-report.json",
                judge_evidence_index_path=judge_index,
                resume_manifest_path=resume_manifest,
                repair_hints={
                    "source": "sqlite repair_hints",
                    "open_count": 1,
                    "hints": [
                        {
                            "hint_id": "repair:run-resume:worker-001:process_timeout",
                            "status": "open",
                            "worker_id": "worker-001",
                        }
                    ],
                },
                repo_root=REPO_ROOT,
            )

            replay = manifest["workers"][0]["replay_commands"]
            for command in [replay["run_worker"], replay["retry_worker"]]:
                self.assertEqual(command["argv"][command["argv"].index("--mode") + 1], "opencode")
                self.assertEqual(command["replay_safety"]["status"], "blocked")
                self.assertEqual(command["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
                self.assertIn("opencode_preflight_report", command["replay_safety"]["missing_constraints"])

    def test_write_evaluate_profile_report_updates_context_index_and_ledger(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-evaluate-profile",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()
            profile_path = out_root / "profile.json"
            profile_path.write_text(
                json.dumps({"schema_version": 1, "profile_id": "demo-profile"}),
                encoding="utf-8",
            )
            batch_report_path = out_root / "harness" / "batch-profile-report.json"
            batch_report_path.parent.mkdir(parents=True)
            batch_report_path.write_text(
                json.dumps(
                    {
                        "report_kind": "batch-profile-report",
                        "judge_summary": {
                            "harness_architecture": {
                                "context_pack": {"path": "old", "sha256": "old"},
                                "agent_index": {"path": "old", "sha256": "old"},
                            }
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            context_pack_path = out_root / "harness" / "context-pack.json"
            context_pack_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "report_kind": "context-pack",
                        "context_pack_id": "run-evaluate-profile-context-pack",
                        "run_id": "run-evaluate-profile",
                        "target_id": "demo",
                        "budget": {"depth": 1, "max_tokens": 20000},
                        "entrypoints": {"primary_report": repo_rel(batch_report_path)},
                        "attempt_evidence_policy": {
                            "baseline_attempt": {
                                "verified_unsafe_baseline": verified_baseline_ref,
                            }
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            agent_index_path = out_root / "harness" / "agent-index.json"
            agent_index_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "report_kind": "agent-index",
                        "run_id": "run-evaluate-profile",
                        "target_id": "demo",
                        "reports": {},
                        "attempt_evidence_policy": {
                            "baseline_attempt": {
                                "verified_unsafe_baseline": verified_baseline_ref,
                            }
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            summary_path = out_root / "summary" / "competition-run-summary.json"
            write_worker_summary(
                summary_path,
                "run-evaluate-profile",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=measured_unsafe_worker_metrics("run-evaluate-profile"),
            )
            workflow_metrics_path = summary_path.parent / "workflow-metrics.json"
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            summary_payload["workflow_metrics"]["path"] = repo_rel(workflow_metrics_path)
            summary_path.write_text(json.dumps(summary_payload, sort_keys=True) + "\n", encoding="utf-8")
            run_plan_report_path = out_root / "harness" / "run-plan-report.json"
            merge_plan_path = out_root / "harness" / "merge-plan.json"
            worker_plan_path = out_root / "harness" / "plans" / "workers.json"
            for path, payload in [
                (run_plan_report_path, {"report_kind": "run-plan-report"}),
                (merge_plan_path, {"report_kind": "merge-plan"}),
                (worker_plan_path, {"report_kind": "worker-plan"}),
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            batch_result = {
                "status": "completed",
                "exit_code": 0,
                "run_id": "run-evaluate-profile",
                "out_root": repo_rel(out_root),
                "db_path": repo_rel(db_path),
                "profile_id": "demo-profile",
                "proof_class": "local-simulation",
                "mode": "deterministic",
                "report_path": repo_rel(batch_report_path),
                "plan_path": repo_rel(worker_plan_path),
                "run_plan": {
                    "report_path": repo_rel(run_plan_report_path),
                    "merge_plan": {"path": repo_rel(merge_plan_path)},
                    "merge_execution": {"summary_path": repo_rel(summary_path)},
                },
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
                "context_pack": {"path": repo_rel(context_pack_path), "sha256": "old"},
                "agent_index": {"path": repo_rel(agent_index_path), "sha256": "old"},
                "attempt_evidence_policy": {
                    "baseline_attempt": {
                        "verified_unsafe_baseline": verified_baseline_ref,
                    }
                },
                "judge_summary": {
                    "entrypoint": "run-batch-profile",
                    "harness_architecture": {"entrypoint": "run-batch-profile"},
                    "core_translation_quality": {
                        "semantic_claim_source": "accepted_evidence_binding",
                        "generated_draft_semantic_pass": False,
                        "semantic_pass_count": 1,
                    },
                },
            }

            result = harness.write_evaluate_profile_report(
                batch_result=batch_result,
                profile_path=profile_path,
                run_id="run-evaluate-profile",
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            report_path = out_root / "harness" / "evaluate-report.json"
            index_path = out_root / "harness" / "judge-evidence-index.json"
            resume_manifest_path = out_root / "harness" / "resume-manifest.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(result["report_path"], repo_rel(report_path))
            self.assertEqual(report["entrypoint"], "evaluate --profile")
            self.assertEqual(report["judge_summary"]["entrypoint"], "evaluate")
            self.assertEqual(report["judge_summary"]["harness_architecture"]["entrypoint"], "evaluate")
            self.assertEqual(report["batch_profile_report"]["path"], repo_rel(batch_report_path))
            self.assertEqual(report["judge_summary"]["harness_architecture"]["context_pack"], report["context_pack"])
            self.assertEqual(report["judge_summary"]["harness_architecture"]["agent_index"], report["agent_index"])
            self.assert_architecture_contracts(report["judge_summary"]["harness_architecture"]["architecture_contracts"])
            self.assertEqual(report["summary_validation"]["semantic_pass"], 1)
            headline = report["judge_headline"]
            self.assertEqual(headline["report_kind"], "judge-headline")
            self.assertEqual(headline["entrypoint"], "evaluate")
            self.assertEqual(headline["status"], "completed")
            self.assertEqual(headline["semantic_claim_source"], "accepted_evidence_binding")
            self.assertFalse(headline["semantic_gate"])
            self.assertFalse(headline["generated_draft_semantic_pass"])
            self.assertEqual(headline["translation_coverage_numerator"], 0)
            self.assertEqual(headline["context_pack"], report["context_pack"])
            self.assertEqual(headline["agent_index"], report["agent_index"])
            self.assertEqual(report["sidecar_reports"]["judge_evidence_index"]["path"], repo_rel(index_path))
            self.assertNotIn("sha256", report["sidecar_reports"]["judge_evidence_index"])
            self.assertEqual(report["resume_manifest"]["path"], repo_rel(resume_manifest_path))
            self.assertEqual(report["resume_manifest"]["report_kind"], "resume-manifest")
            self.assertEqual(report["resume_manifest"]["status"], "completed")
            self.assertRegex(report["resume_manifest"]["sha256"], r"^[0-9a-f]{64}$")

            context_pack = json.loads(context_pack_path.read_text(encoding="utf-8"))
            self.assertEqual(context_pack["entrypoints"]["primary_report"], repo_rel(report_path))
            self.assertEqual(context_pack["entrypoints"]["evaluate_report"], repo_rel(report_path))
            self.assertEqual(context_pack["entrypoints"]["batch_profile_report"], repo_rel(batch_report_path))
            self.assertEqual(context_pack["entrypoints"]["judge_evidence_index"], repo_rel(index_path))
            self.assertEqual(context_pack["entrypoints"]["resume_manifest"], repo_rel(resume_manifest_path))
            self.assertEqual(context_pack["entrypoints"]["verified_unsafe_baseline"], verified_baseline_ref["path"])
            self.assertEqual(context_pack["report_artifacts"]["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(
                context_pack["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assert_context_management_contract(context_pack["context_management_contract"])
            agent_index = json.loads(agent_index_path.read_text(encoding="utf-8"))
            self.assertEqual(agent_index["reports"]["evaluate_report"]["path"], repo_rel(report_path))
            self.assertEqual(agent_index["reports"]["batch_profile_report"]["path"], repo_rel(batch_report_path))
            self.assertEqual(agent_index["reports"]["judge_evidence_index"]["path"], repo_rel(index_path))
            self.assertNotIn("sha256", agent_index["reports"]["judge_evidence_index"])
            self.assertEqual(agent_index["reports"]["resume_manifest"]["path"], repo_rel(resume_manifest_path))
            self.assertNotIn("sha256", agent_index["reports"]["resume_manifest"])
            self.assertEqual(agent_index["reports"]["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(
                agent_index["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assert_agent_coordination_contract(agent_index["agent_coordination_contract"], expected_worker_count=0)
            resume_manifest = json.loads(resume_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(resume_manifest["report_kind"], "resume-manifest")
            self.assertEqual(resume_manifest["run_id"], "run-evaluate-profile")
            self.assertFalse(resume_manifest["claim_boundary"]["semantic_gate"])
            self.assertFalse(resume_manifest["claim_boundary"]["chat_output_is_evidence"])
            self.assertFalse(resume_manifest["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(resume_manifest["claim_boundary"]["translation_coverage_numerator"], 0)
            self.assertEqual(resume_manifest["ledger"]["path"], repo_rel(db_path))
            self.assertEqual(resume_manifest["ledger"]["checkpoint_backend"], "sqlite")
            self.assertEqual(resume_manifest["context_pack"]["path"], repo_rel(context_pack_path))
            self.assertEqual(resume_manifest["context_pack"]["sha256"], harness.sha256_file(context_pack_path))
            self.assertEqual(resume_manifest["agent_index"]["path"], repo_rel(agent_index_path))
            self.assertEqual(resume_manifest["agent_index"]["sha256"], harness.sha256_file(agent_index_path))
            self.assertEqual(resume_manifest["expected_judge_evidence_index"], repo_rel(index_path))
            self.assertEqual(resume_manifest["entrypoints"]["verified_unsafe_baseline"], verified_baseline_ref["path"])
            self.assertEqual(resume_manifest["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(
                resume_manifest["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertIn("evaluate --profile", resume_manifest["resume_entrypoints"])
            self.assertIn("run-plan --plan", resume_manifest["resume_entrypoints"])
            self.assertIn("run-worker --assignment", resume_manifest["resume_entrypoints"])
            self.assertEqual(resume_manifest["worker_count"], 0)
            batch_report = json.loads(batch_report_path.read_text(encoding="utf-8"))
            self.assertEqual(batch_report["context_pack"], report["context_pack"])
            self.assertEqual(batch_report["agent_index"], report["agent_index"])
            self.assertEqual(
                batch_report["judge_summary"]["harness_architecture"]["context_pack"],
                report["context_pack"],
            )
            self.assertTrue(index_path.exists())
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["report_kind"], "judge-evidence-index")
            self.assertEqual(index["entrypoint"], "evaluate --profile")
            self.assertEqual(index["profile_id"], "demo-profile")
            self.assertFalse(index["claim_boundary"]["index_is_semantic_gate"])
            self.assertFalse(index["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(index["claim_boundary"]["translation_coverage_numerator"], 0)
            self.assertIn("does not add a semantic acceptance gate", index["claim_boundary"]["boundary"])
            self.assertEqual(index["harness_architecture"]["entrypoint"], "evaluate")
            self.assert_architecture_contracts(index["harness_architecture"]["architecture_contracts"])
            self.assertEqual(index["core_translation_quality"]["semantic_pass_count"], 1)
            self.assertEqual(index["judge_headline"], report["judge_headline"])
            artifact_refs = index["evidence_artifact_refs"]
            self.assertNotIn("judge_evidence_index", artifact_refs)
            self.assertNotIn("context_management_contract", artifact_refs)
            self.assertNotIn("agent_coordination_contract", artifact_refs)
            self.assertEqual(artifact_refs["evaluate_report"]["path"], repo_rel(report_path))
            self.assertEqual(artifact_refs["evaluate_report"]["sha256"], harness.sha256_file(report_path))
            self.assertEqual(artifact_refs["batch_profile_report"]["path"], repo_rel(batch_report_path))
            self.assertEqual(artifact_refs["context_pack"]["path"], report["context_pack"]["path"])
            self.assertEqual(artifact_refs["context_pack"]["sha256"], harness.sha256_file(context_pack_path))
            self.assertEqual(artifact_refs["agent_index"]["path"], report["agent_index"]["path"])
            self.assertEqual(artifact_refs["agent_index"]["sha256"], harness.sha256_file(agent_index_path))
            self.assertEqual(artifact_refs["resume_manifest"]["path"], report["resume_manifest"]["path"])
            self.assertEqual(artifact_refs["resume_manifest"]["sha256"], harness.sha256_file(resume_manifest_path))
            self.assertEqual(artifact_refs["verified_unsafe_baseline"]["path"], verified_baseline_ref["path"])
            self.assertEqual(artifact_refs["verified_unsafe_baseline"]["sha256"], verified_baseline_ref["sha256"])
            self.assertEqual(
                artifact_refs["verified_unsafe_baseline"]["semantic_claim_source"],
                "verified_unsafe_baseline_gates",
            )
            self.assertEqual(artifact_refs["competition_run_summary"]["path"], repo_rel(summary_path))
            self.assertEqual(artifact_refs["workflow_metrics"]["path"], repo_rel(workflow_metrics_path))
            self.assertEqual(
                artifact_refs["workflow_metrics"]["sha256"],
                summary_payload["workflow_metrics"]["sha256"],
            )
            self.assertEqual(artifact_refs["run_plan_report"]["path"], repo_rel(run_plan_report_path))
            self.assertEqual(artifact_refs["merge_plan"]["path"], repo_rel(merge_plan_path))
            self.assertEqual(artifact_refs["worker_plan"]["path"], repo_rel(worker_plan_path))
            self.assertIn("--summary " + repo_rel(summary_path), index["reproduction_commands"]["summary_validation"])

            artifact_rows = fetch_rows(
                db_path,
                "select kind, repo_rel_path, semantic_role from artifacts where kind in ('evaluate-report', 'context-pack', 'agent-index', 'judge-evidence-index', 'resume-manifest') order by kind",
            )
            self.assertEqual(
                artifact_rows,
                [
                    ("agent-index", repo_rel(agent_index_path), "agent-index"),
                    ("context-pack", repo_rel(context_pack_path), "agent-context-pack"),
                    ("evaluate-report", repo_rel(report_path), "evaluate-report"),
                    ("judge-evidence-index", repo_rel(index_path), "judge-evidence-index"),
                    ("resume-manifest", repo_rel(resume_manifest_path), "resume-manifest"),
                ],
            )
            event_rows = fetch_rows(
                db_path,
                "select event_type from events where event_type in ('evaluate_profile_context_refs_updated', 'evaluate_profile_executed', 'judge_evidence_index_written', 'resume_manifest_written') order by event_type",
            )
            self.assertEqual(
                event_rows,
                [
                    ("evaluate_profile_context_refs_updated",),
                    ("evaluate_profile_executed",),
                    ("judge_evidence_index_written",),
                    ("resume_manifest_written",),
                ],
            )

    def test_write_judge_evidence_index_records_opencode_runtime_without_semantic_gate(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            harness_dir = out_root / "harness"
            harness_dir.mkdir(parents=True, exist_ok=True)
            profile_path = out_root / "profile.json"
            evaluate_report_path = harness_dir / "evaluate-report.json"
            run_plan_report_path = harness_dir / "run-plan-report.json"
            worker_plan_path = harness_dir / "worker-plan.json"
            preflight_report = harness_dir / "opencode-preflight-report.json"
            handoff_a = out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json"
            handoff_b = out_root / "workers" / "worker-b" / "harness" / "opencode-handoff-contract.json"
            session_a = out_root / "workers" / "worker-a" / "logs" / "opencode-session-evidence.json"
            session_b = out_root / "workers" / "worker-b" / "logs" / "opencode-session-evidence.json"
            safety_attempt_a = (
                out_root
                / "workers"
                / "worker-a"
                / "harness"
                / "opencode-safety-transform-attempt-1.json"
            )
            summary_a = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary_b = out_root / "workers" / "worker-b" / "summary" / "competition-run-summary.json"
            worker_report_a = out_root / "workers" / "worker-a" / "harness" / "run-worker-report.json"
            worker_report_b = out_root / "workers" / "worker-b" / "harness" / "run-worker-report.json"
            stdout_a = out_root / "workers" / "worker-a" / "logs" / "harness-worker-executor.stdout.log"
            stderr_a = out_root / "workers" / "worker-a" / "logs" / "harness-worker-executor.stderr.log"
            stdout_b = out_root / "workers" / "worker-b" / "logs" / "harness-worker-executor.stdout.log"
            stderr_b = out_root / "workers" / "worker-b" / "logs" / "harness-worker-executor.stderr.log"
            for path, payload in [
                (profile_path, {"schema_version": 1, "profile_id": "demo-opencode"}),
                (evaluate_report_path, {"report_kind": "evaluate-report"}),
                (run_plan_report_path, {"report_kind": "run-plan-report"}),
                (worker_plan_path, {"report_kind": "worker-plan"}),
                (preflight_report, {"report_kind": "opencode-preflight-report", "status": "passed"}),
                (handoff_a, {"report_kind": "opencode-handoff-contract", "worker_id": "worker-a"}),
                (handoff_b, {"report_kind": "opencode-handoff-contract", "worker_id": "worker-b"}),
                (session_a, {"report_kind": "opencode-session-evidence", "worker_id": "worker-a"}),
                (session_b, {"report_kind": "opencode-session-evidence", "worker_id": "worker-b"}),
                (
                    safety_attempt_a,
                    {
                        "report_kind": "opencode-safety-transform-attempt",
                        "worker_id": "worker-a",
                        "attempt": 1,
                        "semantic_gate": False,
                        "translation_coverage_numerator": 0,
                    },
                ),
                (summary_a, {"report_kind": "competition-run-summary", "worker_id": "worker-a"}),
                (summary_b, {"report_kind": "competition-run-summary", "worker_id": "worker-b"}),
                (worker_report_a, {"report_kind": "run-worker-report", "worker_id": "worker-a"}),
                (worker_report_b, {"report_kind": "run-worker-report", "worker_id": "worker-b"}),
                (stdout_a, {"log": "stdout-a"}),
                (stderr_a, {"log": "stderr-a"}),
                (stdout_b, {"log": "stdout-b"}),
                (stderr_b, {"log": "stderr-b"}),
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
                "run_id": "run-opencode-index",
                "contract_status": "executed",
            }
            handoff_a_binding = {"path": repo_rel(handoff_a), "sha256": harness.sha256_file(handoff_a)}
            handoff_b_binding = {"path": repo_rel(handoff_b), "sha256": harness.sha256_file(handoff_b)}
            session_a_binding = {"path": repo_rel(session_a), "sha256": harness.sha256_file(session_a)}
            session_b_binding = {"path": repo_rel(session_b), "sha256": harness.sha256_file(session_b)}
            safety_attempt_a_binding = {
                "path": repo_rel(safety_attempt_a),
                "sha256": harness.sha256_file(safety_attempt_a),
            }
            batch_result = {
                "status": "completed",
                "exit_code": 0,
                "profile_id": "demo-opencode",
                "proof_class": "local-simulation",
                "mode": "opencode",
                "plan_path": repo_rel(worker_plan_path),
                "opencode_preflight_report": preflight_binding,
                "run_plan": {
                    "report_path": repo_rel(run_plan_report_path),
                    "opencode_preflight_report": preflight_binding,
                    "workers": [
                        {
                            "worker_id": "worker-a",
                            "summary_path": repo_rel(summary_a),
                            "report_path": repo_rel(worker_report_a),
                            "logs": {"stdout": repo_rel(stdout_a), "stderr": repo_rel(stderr_a)},
                            "handoff_contract": handoff_a_binding,
                            "opencode_session_evidence": session_a_binding,
                            "opencode_safety_transform_attempt": safety_attempt_a_binding,
                            "opencode_preflight_report": preflight_binding,
                            "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
                            "opencode_contract_verification": {"status": "executed", "matched_command": "cmd-a"},
                        },
                        {
                            "worker_id": "worker-b",
                            "summary_path": repo_rel(summary_b),
                            "report_path": repo_rel(worker_report_b),
                            "logs": {"stdout": repo_rel(stdout_b), "stderr": repo_rel(stderr_b)},
                            "handoff_contract": handoff_b_binding,
                            "opencode_session_evidence": session_b_binding,
                            "opencode_preflight_report": preflight_binding,
                            "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
                            "opencode_contract_verification": {"status": "executed", "matched_command": "cmd-b"},
                        },
                    ],
                },
            }
            evaluate_report = {
                "status": "completed",
                "exit_code": 0,
                "profile_id": "demo-opencode",
                "proof_class": "local-simulation",
                "mode": "opencode",
                "opencode_preflight_report": preflight_binding,
                "judge_summary": {
                    "harness_architecture": {"entrypoint": "evaluate"},
                    "core_translation_quality": {
                        "semantic_claim_source": "accepted_evidence_binding",
                        "generated_draft_semantic_pass": False,
                    },
                },
            }

            result = harness.write_judge_evidence_index(
                evaluate_report=evaluate_report,
                evaluate_report_path=evaluate_report_path,
                batch_result=batch_result,
                profile_path=profile_path,
                run_id="run-opencode-index",
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            payload = result["payload"]
            runtime = payload["opencode_agent_runtime"]
            self.assertFalse(runtime["chat_output_is_evidence"])
            self.assertFalse(runtime["semantic_gate"])
            self.assertEqual(runtime["opencode_preflight_report"], preflight_binding)
            self.assertEqual(runtime["worker_count"], 2)
            self.assertEqual(runtime["contract_status_counts"], {"executed": 2})
            self.assertTrue(runtime["all_contracts_executed"])
            self.assertEqual(runtime["failed_or_missing_contract_workers"], [])
            self.assertEqual([worker["worker_id"] for worker in runtime["workers"]], ["worker-a", "worker-b"])
            self.assertEqual(
                [worker["contract_verification_status"] for worker in runtime["workers"]],
                ["executed", "executed"],
            )
            self.assertFalse(runtime["workers"][0]["chat_output_is_evidence"])
            self.assertFalse(runtime["workers"][0]["semantic_gate"])
            self.assertEqual(runtime["workers"][0]["handoff_contract"], handoff_a_binding)
            self.assertEqual(runtime["workers"][0]["opencode_session_evidence"], session_a_binding)
            self.assertEqual(runtime["workers"][0]["summary"], {"path": repo_rel(summary_a), "sha256": harness.sha256_file(summary_a)})
            self.assertEqual(
                runtime["workers"][0]["worker_report"],
                {"path": repo_rel(worker_report_a), "sha256": harness.sha256_file(worker_report_a)},
            )
            self.assertEqual(
                runtime["workers"][0]["logs"]["stdout"],
                {"path": repo_rel(stdout_a), "sha256": harness.sha256_file(stdout_a)},
            )
            self.assertEqual(
                runtime["workers"][0]["logs"]["stderr"],
                {"path": repo_rel(stderr_a), "sha256": harness.sha256_file(stderr_a)},
            )
            self.assertEqual(runtime["workers"][0]["final_decision"]["status"], "accepted")
            self.assertEqual(payload["evidence_artifact_refs"]["opencode_preflight_report"], preflight_binding)
            self.assertEqual(
                runtime["workers"][0]["opencode_safety_transform_attempt"],
                safety_attempt_a_binding,
            )
            self.assertEqual(
                payload["evidence_artifact_refs"]["opencode_safety_transform_attempt"],
                safety_attempt_a_binding,
            )
            self.assertFalse(payload["claim_boundary"]["index_is_semantic_gate"])

    def test_plan_source_file_cli_dispatches_planner_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "plan-source-file",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
            "--target-id",
            "flashdb",
            "--source-repo-root",
            "sources/FlashDB",
            "--source-repository",
            "https://gitcode.com/xwxf/FlashDB.git",
            "--source-branch",
            "competition",
            "--source-file",
            "src/fdb_utils.c",
            "--function",
            "fdb_calc_crc32",
            "--source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--require-source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--slice-spec",
            "validation/slice-specs/flashdb-real-fdb-calc-crc32.json",
            "--compiler-command-source",
            "compile_commands.json",
            "--include-path",
            "inc",
            "--define",
            "FDB_USING_KVDB",
            "--out-root",
            "target/competition-out",
            "--slice-id-prefix",
            "real-fdb-utils",
            "--worker-prefix",
            "flashdb-worker",
            "--limit",
            "2",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()), patch.object(
            harness,
            "plan_source_file",
            return_value={"status": "planned"},
        ) as planner:
            self.assertEqual(harness.main(), 0)

        planner.assert_called_once()
        self.assertEqual(planner.call_args.kwargs["target_id"], "flashdb")
        self.assertEqual(planner.call_args.kwargs["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(planner.call_args.kwargs["source_branch"], "competition")
        self.assertEqual(
            planner.call_args.kwargs["require_source_commit"],
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        )
        self.assertEqual(planner.call_args.kwargs["include_paths"], ["inc"])
        self.assertEqual(planner.call_args.kwargs["defines"], ["FDB_USING_KVDB"])
        self.assertEqual(planner.call_args.kwargs["slice_id_prefix"], "real-fdb-utils")
        self.assertEqual(planner.call_args.kwargs["worker_prefix"], "flashdb-worker")
        self.assertEqual(planner.call_args.kwargs["limit"], 2)
        self.assertEqual(planner.call_args.kwargs["functions"], ["fdb_calc_crc32"])
        self.assertEqual(
            planner.call_args.kwargs["slice_specs"],
            ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"],
        )

    def test_run_plan_cli_dispatches_batch_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "run-plan",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
            "--plan",
            "target/competition-out/harness/plans/flashdb-fdb-utils-workers.json",
            "--out-root",
            "target/competition-out",
            "--proof-class",
            "local-simulation",
            "--mode",
            "opencode",
            "--opencode-command",
            "opencode",
            "--opencode-model",
            "GLM-5.1",
            "--opencode-agent",
            "c2rust-migrator",
            "--opencode-variant",
            "max",
            "--opencode-skip-permissions",
            "--execute-merge",
            "--auto-retry",
            "--max-workers",
            "3",
            "--timeout-seconds",
            "42",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_plan",
            return_value={"status": "failed", "exit_code": 1},
        ) as runner:
            exit_code = harness.main()

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "failed")
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["run_id"], "run-test")
        self.assertEqual(
            runner.call_args.kwargs["plan_path"],
            Path("target/competition-out/harness/plans/flashdb-fdb-utils-workers.json"),
        )
        self.assertEqual(runner.call_args.kwargs["proof_class"], "local-simulation")
        self.assertEqual(runner.call_args.kwargs["mode"], "opencode")
        self.assertEqual(runner.call_args.kwargs["opencode_model"], "GLM-5.1")
        self.assertEqual(runner.call_args.kwargs["opencode_agent"], "c2rust-migrator")
        self.assertTrue(runner.call_args.kwargs["opencode_skip_permissions"])
        self.assertTrue(runner.call_args.kwargs["execute_merge"])
        self.assertTrue(runner.call_args.kwargs["auto_retry"])
        self.assertEqual(runner.call_args.kwargs["max_workers"], 3)
        self.assertEqual(runner.call_args.kwargs["timeout_seconds"], 42)

    def test_plan_source_file_direct_script_cli_runs_from_repo_root(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "source"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int add_one(int value) { return value + 1; }\n", encoding="utf-8")
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "validation/tools/opencode_agent_harness.py",
                    "plan-source-file",
                    "--db",
                    repo_rel(db_path),
                    "--run-id",
                    "run-test",
                    "--target-id",
                    "demo",
                    "--source-repo-root",
                    repo_rel(source_root),
                    "--source-file",
                    "src/demo.c",
                    "--source-commit",
                    "abc123",
                    "--out-root",
                    repo_rel(out_root),
                    "--slice-id-prefix",
                    "demo",
                    "--limit",
                    "1",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["units"][0]["function"], "add_one")

    def test_record_worker_summary_indexes_artifact_and_merge_plan(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-worker-a",
                        "proof_class": "local-simulation",
                        "final_gate": {"status": "passed", "validator": "validate_auto_translation_evidence.py --require-semantic-pass"},
                        "slices": {"attempted": 1, "typed_ir_generated": 1, "compiled": 1, "semantic_pass": 1, "refused": 0, "blocked": 0, "failed": 0},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            harness.record_worker_summary(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                summary_path=summary_path,
                repo_root=REPO_ROOT,
            )
            merge_plan = harness.write_merge_plan(
                db_path=db_path,
                run_id="run-test",
                out_root=out_root,
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(
                merge_plan["worker_summaries"],
                [repo_rel(summary_path)],
            )
            expected_merge_prefix = harness.portable_python_script_argv("validation/tools/run_competition.py")
            self.assertEqual(merge_plan["argv"][: len(expected_merge_prefix)], expected_merge_prefix)
            self.assertIn("--worker-summary", merge_plan["argv"])
            self.assertIn("--run-id", merge_plan["argv"])
            run_id_idx = merge_plan["argv"].index("--run-id")
            self.assertEqual(merge_plan["argv"][run_id_idx + 1], "run-test")
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertEqual(artifact_rows, [("competition-run-summary", repo_rel(summary_path), "run-summary")])

    def test_record_artifact_conflict_refreshes_identity_metadata(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-old",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            artifact_path = out_root / "harness" / "shared.json"
            write_json(artifact_path, {"version": 1})
            connection = harness.connect(db_path)
            try:
                harness.record_artifact(
                    connection,
                    run_id="run-old",
                    worker_id="worker-a",
                    kind="old-kind",
                    path=artifact_path,
                    status="old",
                    semantic_role="old-role",
                    payload={"version": 1},
                    repo_root=REPO_ROOT,
                )
                connection.commit()

                write_json(artifact_path, {"version": 2})
                harness.record_artifact(
                    connection,
                    run_id="run-new",
                    worker_id="planner",
                    kind="context-pack",
                    path=artifact_path,
                    status="completed",
                    semantic_role="agent-context-pack",
                    payload={"version": 2},
                    repo_root=REPO_ROOT,
                )
                connection.commit()
            finally:
                connection.close()

            artifact_rows = fetch_rows(
                db_path,
                """
                select run_id, agent_id, kind, semantic_role, status
                from artifacts
                where repo_rel_path=?
                """,
                (repo_rel(artifact_path),),
            )
            self.assertEqual(
                artifact_rows,
                [("run-new", "planner", "context-pack", "agent-context-pack", "completed")],
            )

    def test_context_pack_conflict_refreshes_sqlite_metadata(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-context",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            primary_report = out_root / "harness" / "batch-profile-report.json"
            primary_report.parent.mkdir(parents=True, exist_ok=True)
            primary_report.write_text("{}\n", encoding="utf-8")
            plan = {
                "planning_mode": "source_file",
                "plan_path": repo_rel(out_root / "harness" / "plans" / "workers.json"),
                "units": [],
            }
            run_result = {
                "status": "passed",
                "workers": [],
                "parallelism": {"max_workers": 0, "effective_workers": 0},
                "graph": {"checkpoint_backend": "sqlite"},
            }
            harness.write_context_pack_and_agent_index(
                db_path=db_path,
                run_id="run-context",
                target_id="old-target",
                proof_class="local-simulation",
                mode="deterministic",
                out_root=out_root,
                plan=plan,
                run_result=run_result,
                primary_report_path=primary_report,
                report_entrypoint="batch_profile_report",
                repo_root=REPO_ROOT,
            )
            context_ref = harness.write_context_pack_and_agent_index(
                db_path=db_path,
                run_id="run-context",
                target_id="new-target",
                proof_class="local-simulation",
                mode="deterministic",
                out_root=out_root,
                plan=plan,
                run_result=run_result,
                primary_report_path=primary_report,
                report_entrypoint="batch_profile_report",
                repo_root=REPO_ROOT,
            )["context_pack"]

            context_rows = fetch_rows(
                db_path,
                """
                select run_id, target_id, artifact_path, artifact_sha256
                from context_packs
                where context_pack_id=?
                """,
                ("run-context-context-pack",),
            )
            self.assertEqual(
                context_rows,
                [("run-context", "new-target", context_ref["path"], context_ref["sha256"])],
            )

    def test_record_worker_summary_rejects_unassigned_summary_path(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            summary_path = out_root / "workers" / "worker-b" / "summary" / "competition-run-summary.json"
            write_worker_summary(summary_path, "run-worker-b", status="passed", failed=0, semantic_pass=1)

            with self.assertRaisesRegex(SystemExit, "worker summary path .* does not match assigned"):
                harness.record_worker_summary(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    summary_path=summary_path,
                    repo_root=REPO_ROOT,
                )

    def test_run_worker_executes_assignment_and_records_summary(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "run_id": request["run_id"],
                            "proof_class": "local-simulation",
                            "profile_id": "huawei-competition-ubuntu-24.04",
                            "profile_sha256": "0" * 64,
                            "clang_source": "missing",
                            "cargo_mirror_activation": {
                                "method": "CARGO_HOME",
                                "path": "config/competition-env/cargo",
                                "config_file": "config/competition-env/cargo/config.toml",
                            },
                            "elapsed_seconds": 0,
                            "translator_version": "test",
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
                                "ratio": 0,
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
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertTrue(result["recorded"])
            self.assertEqual(result["summary_status"], "passed")
            self.assertEqual(len(calls), 1)
            self.assertIn("scripts/c2rust-migrator.py", calls[0])
            report_path = REPO_ROOT / result["report_path"]
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["report_kind"], "run-worker-report")
            self.assertEqual(report["mode"], "deterministic")
            self.assertEqual(report["runner_kind"], "repo-local-c2rust-migrator")
            report_rel = repo_rel(report_path)
            report_sha = harness.sha256_file(report_path)
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, sha256, status, semantic_role from artifacts")
            self.assertEqual(
                artifact_rows,
                [
                    (
                        "competition-run-summary",
                        repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                        harness.sha256_file(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                        "passed",
                        "run-summary",
                    ),
                    (
                        "run-worker-report",
                        report_rel,
                        report_sha,
                        "passed",
                        "worker-execution-report",
                    )
                ],
            )
            event_rows = fetch_rows(db_path, "select event_type, payload_json from events order by event_id")
            self.assertIn("worker_executed", [row[0] for row in event_rows])
            worker_event = json.loads(event_rows[-1][1])
            self.assertEqual(worker_event["worker_report"], {"path": report_rel, "sha256": report_sha})
            self.assertEqual(worker_event["report_path"], report_rel)

    def test_run_worker_fails_when_recorded_summary_final_gate_fails(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "run_id": request["run_id"],
                            "proof_class": "local-simulation",
                            "profile_id": "huawei-competition-ubuntu-24.04",
                            "profile_sha256": "0" * 64,
                            "clang_source": "missing",
                            "cargo_mirror_activation": {
                                "method": "CARGO_HOME",
                                "path": "config/competition-env/cargo",
                                "config_file": "config/competition-env/cargo/config.toml",
                            },
                            "elapsed_seconds": 0,
                            "translator_version": "test",
                            "slices": {
                                "attempted": 1,
                                "typed_ir_generated": 1,
                                "compiled": 0,
                                "semantic_pass": 0,
                                "refused": 0,
                                "blocked": 0,
                                "failed": 1,
                            },
                            "unsafe_budget": {
                                "status": "passed",
                                "total_first_party_non_test_unsafe": 0,
                                "ratio": 0,
                            },
                            "artifact_roots": [
                                "target/competition-out/evidence",
                                "target/competition-out/summary",
                                "target/competition-out/logs",
                            ],
                            "final_gate": {
                                "status": "failed",
                                "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
                            },
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, stdout="worker reported success\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            self.assertTrue(result["recorded"])
            self.assertEqual(result["summary_status"], "failed")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["exit_code"], 1)

    def test_run_worker_records_repair_hint_when_final_gate_fails(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                return subprocess.CompletedProcess(argv, 0, stdout="worker reported success\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            hint_rows = fetch_rows(
                db_path,
                "select target_id, slice_id, root_cause_key, status, payload_json from repair_hints",
            )
            self.assertEqual(len(hint_rows), 1)
            self.assertEqual(hint_rows[0][:4], ("demo", "demo-add-one", "final_gate_failed", "open"))
            payload = json.loads(hint_rows[0][4])
            self.assertEqual(payload["worker_id"], "worker-a")
            expected_retry_prefix = harness.portable_python_script_argv(
                "validation/tools/opencode_agent_harness.py",
                "retry-worker",
                "--db",
            )
            self.assertEqual(payload["retry_command"][: len(expected_retry_prefix)], expected_retry_prefix)
            self.assertEqual(payload["revalidate_gate"], "competition-run-summary.final_gate.status == passed")

    def test_run_worker_records_structured_error_stack_in_repair_hint_from_stderr(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                stderr = (
                    "error[E0133]: call to unsafe function `std::ptr::read` is unsafe and requires unsafe block\n"
                    "  --> candidate.rs:17:9\n"
                    "Traceback (most recent call last):\n"
                    "  File \"scripts/c2rust-migrator.py\", line 42, in <module>\n"
                    "RuntimeError: rustc failed\n"
                )
                return subprocess.CompletedProcess(argv, 1, stdout="compile failed\n", stderr=stderr)

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            diagnostics = payload["diagnostics"]
            self.assertEqual(diagnostics["primary_error"]["kind"], "rustc")
            self.assertEqual(diagnostics["primary_error"]["code"], "E0133")
            self.assertIn("candidate.rs:17:9", diagnostics["stderr_tail"])
            self.assertIn("RuntimeError: rustc failed", diagnostics["python_traceback"])
            self.assertEqual(payload["attempts"][0]["diagnostics"]["primary_error"]["code"], "E0133")

    def test_run_worker_stale_summary_cleanup_failure_fails_closed_without_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            worker_out_root = out_root / "workers" / "worker-a"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=worker_out_root,
                repo_root=REPO_ROOT,
            )
            summary_path = worker_out_root / "summary" / "competition-run-summary.json"
            write_worker_summary(summary_path, "run-test-worker-a", status="passed", failed=0, semantic_pass=1)
            launched = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal launched
                launched = True
                return subprocess.CompletedProcess(argv, 0, stdout="unexpected launch\n", stderr="")

            original_unlink = Path.unlink

            def fail_for_stale_summary(path: Path, *args: object, **kwargs: object) -> None:
                if path.resolve() == summary_path.resolve():
                    raise PermissionError("locked stale summary")
                original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", fail_for_stale_summary):
                result = harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertFalse(launched)
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["runner_kind"], "stale-summary-cleanup")
            self.assertEqual(result["summary_status"], "stale-summary-cleanup-failed")
            self.assertFalse(result["recorded"])
            self.assertEqual(result["repair_hint"]["root_cause_key"], "stale_summary_cleanup_failed")
            stderr = (worker_out_root / "logs" / "harness-worker-executor.stderr.log").read_text(encoding="utf-8")
            self.assertIn("locked stale summary", stderr)
            hint_rows = fetch_rows(db_path, "select root_cause_key, status from repair_hints")
            self.assertEqual(hint_rows, [("stale_summary_cleanup_failed", "open")])

    def test_worker_repair_diagnostics_redacts_local_absolute_paths(self) -> None:
        with temp_repo_dir() as tmp:
            stdout_path = Path(tmp) / "stdout.log"
            stderr_path = Path(tmp) / "stderr.log"
            stdout_path.write_text(
                'tool output workdir="F:\\agent\\crustpaper\\0625ctr" failed\n',
                encoding="utf-8",
            )
            stderr_path.write_text(
                "Traceback (most recent call last):\n"
                '  File "F:\\agent\\crustpaper\\0630\\scripts\\c2rust-migrator.py", line 42, in <module>\n'
                "FileNotFoundError: missing request under /mnt/c/Users/Administrator/Desktop\n",
                encoding="utf-8",
            )

            diagnostics = harness.worker_repair_diagnostics(
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                process_returncode=0,
                root_cause_key="missing_summary",
            )
            serialized = json.dumps(diagnostics, sort_keys=True)

            self.assertNotIn("F:\\agent", serialized)
            self.assertNotIn("/mnt/c/Users", serialized)
            self.assertIn("<local-absolute-path>", serialized)
            self.assertEqual(diagnostics["primary_error"]["kind"], "python")
            self.assertEqual(diagnostics["root_cause_key"], "missing_summary")

    def test_run_worker_records_report_when_worker_command_cannot_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            def missing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise FileNotFoundError("missing opencode command")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=missing_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 127)
            self.assertEqual(result["process_returncode"], 127)
            self.assertEqual(result["summary_status"], "missing-summary")
            self.assertFalse(result["recorded"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["runner_kind"], "opencode-run")
            self.assertEqual(report["process_returncode"], 127)
            stderr = (REPO_ROOT / report["logs"]["stderr"]).read_text(encoding="utf-8")
            self.assertIn("missing opencode command", stderr)
            hint_rows = fetch_rows(
                db_path,
                "select target_id, slice_id, root_cause_key, status from repair_hints",
            )
            self.assertEqual(hint_rows, [("demo", "demo-add-one", "worker_process_failed", "open")])

    def test_opencode_run_worker_writes_machine_readable_handoff_contract(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 0, stdout="opencode did not write summary\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["summary_status"], "blocked")
            self.assertTrue(result["recorded"])
            self.assertEqual(result["repair_hint"]["root_cause_key"], "opencode_contract_not_executed")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_contract_verification"]["status"], "not-observed")
            contract_binding = report["handoff_contract"]
            contract_path = REPO_ROOT / contract_binding["path"]
            self.assertTrue(contract_path.exists())
            self.assertRegex(contract_binding["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(contract_binding["sha256"], harness.sha256_file(contract_path))
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["runner_kind"], "opencode-run")
            self.assertEqual(
                contract["request_path"],
                repo_rel(out_root / "workers" / "worker-a" / "harness" / "worker-a-request-attempt-1.json"),
            )
            self.assertEqual(
                contract["assignment_request_path"],
                repo_rel(out_root / "harness" / "assignments" / "worker-a-request.json"),
            )
            self.assertEqual(
                contract["expected_summary_path"],
                repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
            )
            expected_worker_prefix = harness.portable_python_script_argv(
                "scripts/c2rust-migrator.py",
                "--phase",
                "migrate",
            )
            self.assertEqual(contract["worker_command"][: len(expected_worker_prefix)], expected_worker_prefix)
            self.assertEqual(contract["opencode_argv"], result["argv"])
            self.assertNotIn("Read the handoff contract before running the command.", contract["prompt"])
            self.assertIn("Handoff contract is audit metadata; do not inspect it before the first command.", contract["prompt"])
            self.assertIn("Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.", contract["prompt"])
            self.assertIn(contract_binding["path"], contract["prompt"])
            session_binding = report["opencode_session_evidence"]
            session_path = REPO_ROOT / session_binding["path"]
            self.assertTrue(session_path.exists())
            self.assertEqual(session_binding["sha256"], harness.sha256_file(session_path))
            session = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertIs(session["parsed"], False)
            self.assertEqual(session["process_returncode"], 0)
            self.assertIn("opencode did not write summary", session["raw_output"])
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            hint_payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            self.assertEqual(hint_payload["handoff_contract"], contract_binding)
            self.assertEqual(hint_payload["opencode_session_evidence"], session_binding)
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["handoff_contract"], contract_binding)
            self.assertEqual(event_payload["opencode_session_evidence"], session_binding)
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertIn(
                ("opencode-handoff-contract", contract_binding["path"], "agent-command-contract"),
                artifact_rows,
            )
            self.assertIn(
                ("opencode-session-evidence", session_binding["path"], "agent-session-evidence"),
                artifact_rows,
            )

    def test_opencode_run_worker_uses_repo_local_runtime_env_contract(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            captured_env: dict[str, str] = {}

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                captured_env.update(kwargs["env"])  # type: ignore[arg-type]
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
                summary_path = REPO_ROOT / contract["expected_summary_path"]
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=1)
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            runtime_env = result["opencode_runtime_env"]
            runtime_root = out_root / "workers" / "worker-a" / "opencode-runtime" / "worker-a"
            self.assertEqual(runtime_env["status"], "isolated")
            self.assertEqual(runtime_env["scope"], "worker-a")
            self.assertEqual(runtime_env["runtime_root"], repo_rel(runtime_root))
            self.assertEqual(runtime_env["env"]["XDG_CONFIG_HOME"], repo_rel(runtime_root / "config"))
            self.assertEqual(captured_env["XDG_CONFIG_HOME"], str(runtime_root / "config"))
            self.assertEqual(captured_env["XDG_DATA_HOME"], str(runtime_root / "data"))
            self.assertEqual(captured_env["XDG_CACHE_HOME"], str(runtime_root / "cache"))
            self.assertEqual(captured_env["TMPDIR"], str(runtime_root / "tmp"))
            self.assertEqual(captured_env["TEMP"], str(runtime_root / "tmp"))
            self.assertEqual(captured_env["TMP"], str(runtime_root / "tmp"))
            contract = json.loads(
                (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(contract["opencode_runtime_env"], runtime_env)
            session = json.loads(
                (out_root / "workers" / "worker-a" / "logs" / "opencode-session-evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(session["opencode_runtime_env"], runtime_env)
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["opencode_runtime_env"], runtime_env)

    def test_opencode_run_worker_binds_session_evidence_into_successful_before_after_metrics(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            worker_out_root = out_root / "workers" / "worker-a"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="store-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="store_add_one",
                source_commit="abc123",
                out_root=worker_out_root,
                repo_root=REPO_ROOT,
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                contract = json.loads(
                    (worker_out_root / "harness" / "opencode-handoff-contract.json").read_text(encoding="utf-8")
                )
                summary_path = REPO_ROOT / contract["expected_summary_path"]
                write_worker_summary(
                    summary_path,
                    "run-test",
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=before_after_worker_metrics(worker_out_root, "run-test"),
                )
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["summary_status"], "passed")
            self.assertIn("opencode_safety_transform_attempt", result)
            attempt_binding = result["opencode_safety_transform_attempt"]
            self.assertEqual(Path(attempt_binding["path"]).name, "opencode-safety-transform-attempt-1.json")
            latest_attempt = worker_out_root / "harness" / "opencode-safety-transform-attempt.json"
            self.assertTrue(latest_attempt.exists())
            attempt = json.loads((REPO_ROOT / attempt_binding["path"]).read_text(encoding="utf-8"))
            self.assertEqual(json.loads(latest_attempt.read_text(encoding="utf-8")), attempt)
            self.assertEqual(attempt["report_kind"], "opencode-safety-transform-attempt")
            self.assertEqual(attempt["status"], "accepted")
            self.assertEqual(attempt["contract_verification"]["status"], "executed")
            self.assertFalse(attempt["semantic_gate"])
            self.assertFalse(attempt["chat_output_is_evidence"])
            self.assertEqual(attempt["translation_coverage_numerator"], 0)
            self.assertEqual(
                attempt["attempt_contract"],
                {
                    "single_patch_per_round": True,
                    "max_repair_rounds": 5,
                    "semantic_gate": False,
                    "translation_coverage_numerator": 0,
                },
            )
            self.assertEqual(attempt["safety_transform_unit_count"], 1)
            safety_unit = attempt["safety_transform_units"][0]
            self.assertEqual(safety_unit["unit_id"], "demo/store-add-one")
            self.assertTrue(safety_unit["round_contract"]["single_patch_per_round"])
            self.assertEqual(safety_unit["round_contract"]["max_repair_rounds"], 5)
            self.assertEqual(safety_unit["patch_evidence"]["baseline"]["path"], "evidence/before-after/baseline-unsafe.rs")
            self.assertEqual(safety_unit["patch_evidence"]["final"]["path"], "evidence/before-after/final-safe.rs")
            self.assertEqual(safety_unit["patch_evidence"]["accepted_patch"]["path"], "evidence/before-after/accepted.patch")
            self.assertEqual(safety_unit["patch_evidence"]["patch_log"]["path"], "evidence/before-after/step-log.jsonl")
            self.assertEqual(safety_unit["verification_delta"]["oracle_evidence"]["path"], "evidence/before-after/oracle-diff.json")
            self.assertEqual(safety_unit["verification_delta"]["unsafe_reduction"]["reduced_by"], 3)
            self.assertTrue(safety_unit["verification_delta"]["compiled"])
            self.assertEqual(
                safety_unit["verification_delta"]["unsafe_scan_evidence"]["path"],
                "evidence/before-after/unsafe-scan.json",
            )
            self.assertEqual(
                safety_unit["verification_delta"]["semantic_evidence"]["schema_diff"]["path"],
                "evidence/before-after/schema-diff.json",
            )
            self.assertEqual(len(safety_unit["rounds"]), 1)
            self.assertEqual(safety_unit["rounds"][0]["round"], 1)
            self.assertEqual(safety_unit["rounds"][0]["patch"]["path"], "evidence/before-after/accepted.patch")
            self.assertEqual(safety_unit["rounds"][0]["patch_log"]["path"], "evidence/before-after/step-log.jsonl")
            self.assertEqual(safety_unit["rounds"][0]["oracle_evidence"]["path"], "evidence/before-after/oracle-diff.json")
            self.assertEqual(safety_unit["rounds"][0]["unsafe_delta"]["reduced_by"], 3)
            self.assertEqual(safety_unit["rounds"][0]["schema_diff"]["path"], "evidence/before-after/schema-diff.json")
            self.assertEqual(safety_unit["accepted_retry_hint"]["status"], "not_exercised")
            self.assertFalse(safety_unit["semantic_gate"])
            self.assertEqual(safety_unit["translation_coverage_numerator"], 0)
            metrics = json.loads((worker_out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            unit = metrics["per_unit_statuses"][0]
            self.assertIn("handoff_contract", unit)
            self.assertIn("opencode_session_evidence", unit)
            self.assertEqual(unit["opencode_contract_verification"]["status"], "executed")
            exhibit_unit = harness.before_after_exhibit_units(metrics)[0]
            self.assertTrue(exhibit_unit["patch_origin"]["opencode_session_bound"])
            self.assertEqual(exhibit_unit["safety_loop_provenance"]["status"], "opencode_session_bound")
            artifact_rows = fetch_rows(
                db_path,
                "select sha256 from artifacts where kind='competition-run-summary' and repo_rel_path=?",
                (repo_rel(worker_out_root / "summary" / "competition-run-summary.json"),),
            )
            self.assertEqual(artifact_rows, [(harness.sha256_file(worker_out_root / "summary" / "competition-run-summary.json"),)])
            attempt_rows = fetch_rows(
                db_path,
                "select kind, repo_rel_path, semantic_role from artifacts where kind='opencode-safety-transform-attempt'",
            )
            self.assertEqual(
                attempt_rows,
                [("opencode-safety-transform-attempt", attempt_binding["path"], "agent-safety-transform-attempt")],
            )

    def test_opencode_safety_transform_attempt_binds_retry_repair_history_and_rollback(self) -> None:
        with temp_repo_dir() as tmp:
            worker_out_root = Path(tmp) / "competition-out" / "workers" / "worker-a"
            summary_path = worker_out_root / "summary" / "competition-run-summary.json"
            metrics = before_after_worker_metrics(worker_out_root, "run-test")
            rollback_path = worker_out_root / "harness" / "rollback-before-retry-demo.json"
            rollback_path.parent.mkdir(parents=True, exist_ok=True)
            rollback_path.write_text(json.dumps({"action": "removed_stale_summary_before_retry"}), encoding="utf-8")
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["root_cause_key"] = "rustc_compile_failed"
            unit["repair_history"] = {
                "patch_events_path": repo_rel(history_path),
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": [repo_rel(rollback_path)],
                "verified": True,
            }
            write_worker_summary(
                summary_path,
                "run-test",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=metrics,
            )

            binding = harness.write_opencode_safety_transform_attempt(
                run_id="run-test",
                worker_id="worker-a",
                attempt_number=2,
                attempt_path=worker_out_root / "harness" / "opencode-safety-transform-attempt.json",
                summary_path=summary_path,
                summary_payload=json.loads(summary_path.read_text(encoding="utf-8")),
                handoff_contract=None,
                opencode_session_evidence=None,
                opencode_contract_verification={"status": "executed"},
                repo_root=REPO_ROOT,
            )

            self.assertEqual(Path(binding["path"]).name, "opencode-safety-transform-attempt-2.json")
            latest_attempt = worker_out_root / "harness" / "opencode-safety-transform-attempt.json"
            self.assertTrue(latest_attempt.exists())
            attempt = json.loads((REPO_ROOT / binding["path"]).read_text(encoding="utf-8"))
            self.assertEqual(json.loads(latest_attempt.read_text(encoding="utf-8")), attempt)
            safety_unit = attempt["safety_transform_units"][0]
            self.assertEqual(safety_unit["accepted_retry_hint"]["status"], "revalidated_passed")
            self.assertEqual(safety_unit["accepted_retry_hint"]["repair_rounds"], 1)
            self.assertEqual(safety_unit["accepted_retry_hint"]["rollback_ids"], [repo_rel(rollback_path)])
            self.assertEqual(
                safety_unit["accepted_retry_hint"]["rollback_evidence"],
                [{"path": repo_rel(rollback_path), "sha256": harness.sha256_file(rollback_path)}],
            )
            self.assertEqual(safety_unit["repair_history"]["patch_events_sha256"], harness.sha256_file(history_path))
            self.assertEqual(safety_unit["root_cause_key"], "rustc_compile_failed")

    def test_opencode_run_worker_classifies_wrong_shell_command_as_contract_not_executed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            wrong_command = (
                "python -m validation.tools.opencode_agent_harness init-run "
                "--out-root target/competition-out --run-id wrong-run --proof-class local-simulation"
            )
            stdout = json.dumps(
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {
                            "input": {"command": wrong_command},
                            "status": "completed",
                        },
                    },
                }
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["summary_status"], "blocked")
            self.assertEqual(result["repair_hint"]["root_cause_key"], "opencode_contract_not_executed")
            verification = result["opencode_contract_verification"]
            self.assertEqual(verification["status"], "not-executed")
            self.assertFalse(verification["worker_command_seen"])
            self.assertEqual(verification["executed_shell_commands"], [wrong_command])
            hint_payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            self.assertEqual(hint_payload["root_cause_key"], "opencode_contract_not_executed")
            self.assertEqual(hint_payload["opencode_contract_verification"]["status"], "not-executed")

    def test_opencode_contract_failure_writes_blocked_worker_summary_for_parent_merge(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            wrong_command = "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"
            stdout = json.dumps(
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": wrong_command}, "status": "completed"}},
                }
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["summary_status"], "blocked")
            self.assertTrue(result["recorded"])
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            self.assertEqual(summary["slices"]["blocked"], 1)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            self.assertTrue(metrics_path.exists())
            self.assertEqual(summary["workflow_metrics"]["path"], "workflow-metrics.json")
            self.assertEqual(summary["workflow_metrics"]["sha256"], harness.sha256_file(metrics_path))
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(metrics["fail_closed_count"], 1)
            self.assertEqual(metrics["per_unit_statuses"][0]["root_cause_key"], "opencode_contract_not_executed")
            self.assertEqual(metrics["per_unit_statuses"][0]["opencode_contract_verification"]["status"], "not-executed")

    def test_opencode_contract_failure_overrides_passing_summary(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            request_path = out_root / "harness" / "assignments" / "worker-a-request.json"
            expected_command = harness.shell_command_line(
                [
                    "python3",
                    "-B",
                    "scripts/c2rust-migrator.py",
                    "--phase",
                    "migrate",
                    "--input",
                    repo_rel(request_path),
                ]
            )
            wrong_command = "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"
            stdout = "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "part": {
                                "tool": "bash",
                                "state": {"input": {"command": wrong_command}, "status": "completed"},
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "part": {
                                "tool": "bash",
                                "state": {"input": {"command": expected_command}, "status": "completed"},
                            },
                        }
                    ),
                ]
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["summary_status"], "blocked")
            self.assertEqual(result["repair_hint"]["root_cause_key"], "opencode_contract_not_executed")
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            self.assertEqual(summary["slices"]["semantic_pass"], 0)
            self.assertEqual(summary["slices"]["blocked"], 1)
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_contract_verification"]["status"], "not-executed")
            rejected = report["rejected_summary_evidence"]
            rejected_path = REPO_ROOT / rejected["path"]
            self.assertTrue(rejected_path.exists())
            rejected_payload = json.loads(rejected_path.read_text(encoding="utf-8"))
            self.assertEqual(rejected_payload["action"], "rejected_summary_due_to_opencode_contract")
            self.assertEqual(rejected_payload["rejected_summary"]["path"], repo_rel(summary_path))
            hint_payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            self.assertEqual(hint_payload["rejected_summary_evidence"], rejected)

    def test_opencode_session_evidence_parses_json_lines_stdout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            logs_dir = out_root / "workers" / "worker-a" / "logs"
            logs_dir.mkdir(parents=True)
            stdout_path = logs_dir / "stdout.log"
            stderr_path = logs_dir / "stderr.log"
            stdout = "\n".join(
                [
                    json.dumps({"type": "step_start", "sessionID": "session-1"}),
                    json.dumps({"type": "text", "part": {"text": "done"}}),
                    "",
                ]
            )
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")

            binding = harness.write_opencode_session_evidence(
                completed=subprocess.CompletedProcess(["opencode"], 0, stdout, ""),
                evidence_path=logs_dir / "opencode-session-evidence.json",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                repo_root=REPO_ROOT,
            )

            evidence = json.loads((REPO_ROOT / binding["path"]).read_text(encoding="utf-8"))
            self.assertIs(evidence["parsed"], True)
            self.assertEqual(evidence["format"], "jsonl")
            self.assertEqual([event["type"] for event in evidence["session_events"]], ["step_start", "text"])

    def test_opencode_worker_prompt_forces_exact_command_and_fresh_summary(self) -> None:
        argv = harness.build_opencode_run_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=True,
            worker_command=[
                sys.executable,
                "scripts/c2rust-migrator.py",
                "--phase",
                "migrate",
                "--input",
                "target/out/harness/assignments/worker-a-request.json",
            ],
            request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        prompt = argv[-1]
        self.assertNotIn("\n", prompt)
        self.assertIn("Use the shell/bash tool to run exactly the Command line string below.", prompt)
        self.assertIn("The first shell/bash/powershell/cmd tool call must be exactly the Command line string.", prompt)
        self.assertIn("Do not run init-run, assign-slice, retry-worker, or any other substitute harness command.", prompt)
        self.assertIn("Do not inspect an existing summary before running the command.", prompt)
        self.assertNotIn("Delete the expected summary file if it already exists", prompt)
        self.assertIn("The harness has already removed any stale expected summary before launching OpenCode.", prompt)
        self.assertIn("Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.", prompt)
        self.assertIn("Do not explore files, spawn subagents, or infer a different slice before executing the command.", prompt)
        self.assertIn("Do not run substitute diagnostics instead of the command.", prompt)
        self.assertIn("scripts/c2rust-migrator.py", prompt)

    def test_opencode_preflight_prompt_is_single_cli_argument_without_newlines(self) -> None:
        marker_command = [
            sys.executable,
            "validation/tools/opencode_agent_harness.py",
            "write-preflight-marker",
            "--marker",
            "target/out/harness/opencode-preflight-marker.json",
            "--run-id",
            "preflight-run",
        ]

        argv = harness.build_opencode_preflight_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=True,
            marker_command=marker_command,
            marker_path=REPO_ROOT / "target/out/harness/opencode-preflight-marker.json",
            contract_path=REPO_ROOT / "target/out/harness/opencode-preflight-contract.json",
            repo_root=REPO_ROOT,
        )

        prompt = argv[-1]
        self.assertNotIn("\n", prompt)
        self.assertIn("Execute this OpenCode preflight command exactly once.", prompt)
        self.assertIn("Command line:", prompt)
        self.assertIn("write-preflight-marker", prompt)

    def test_opencode_contract_requires_first_shell_command_to_match_worker_command(self) -> None:
        worker_command = [
            sys.executable,
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/harness/assignments/worker-a-request.json",
        ]
        expected_command = harness.shell_command_line(worker_command)
        wrong_command = "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": wrong_command, "workdir": str(REPO_ROOT)}}},
                },
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": expected_command, "workdir": str(REPO_ROOT)}}},
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertEqual(verification["first_shell_command"], wrong_command)
        self.assertFalse(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["first_tool_name"], "bash")
        self.assertEqual(verification["tools_before_first_shell"], [])
        self.assertEqual(verification["contract_failure_reason"], "first_shell_command_mismatch_worker_command_seen_later")

    def test_opencode_contract_accepts_argv_equivalent_quoted_worker_command(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        quoted_command = (
            'python3 -B scripts/c2rust-migrator.py --phase migrate --input '
            '"target/out/workers/worker-a/harness/worker-a-request-attempt-1.json"'
        )
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": quoted_command, "workdir": str(REPO_ROOT)}}},
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertEqual(verification["first_shell_command"], quoted_command)
        self.assertTrue(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["contract_failure_reason"], "")

    def test_opencode_contract_rejects_extra_shell_command_after_expected_worker_command(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        expected_command = harness.shell_command_line(worker_command)
        extra_command = "python3 -B validation/tools/opencode_agent_harness.py init-run --run-id unexpected"
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {"input": {"command": expected_command, "workdir": str(REPO_ROOT)}},
                    },
                },
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {"input": {"command": extra_command, "workdir": str(REPO_ROOT)}},
                    },
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertEqual(verification["executed_shell_command_count"], 2)
        self.assertEqual(verification["executed_shell_commands"], [expected_command, extra_command])
        self.assertEqual(verification["contract_failure_reason"], "extra_shell_command_after_contract")

    def test_opencode_contract_uses_posix_shell_join_for_prompt_and_verification(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker a/harness/request 1.json",
        ]
        expected_command_line = shlex.join(worker_command)
        argv = harness.build_opencode_run_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=False,
            worker_command=worker_command,
            request_path=REPO_ROOT / "target/out/workers/worker a/harness/request 1.json",
            summary_path=REPO_ROOT / "target/out/workers/worker a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )
        self.assertIn(f"Command line: {expected_command_line}", argv[-1])

        verification = harness.verify_opencode_contract_execution(
            session_evidence={
                "session_events": [
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": expected_command_line, "workdir": str(REPO_ROOT)}},
                        },
                    }
                ]
            },
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "executed")
        self.assertEqual(verification["expected_worker_command_line"], expected_command_line)

    def test_portable_python_script_argv_uses_runnable_non_absolute_interpreter(self) -> None:
        argv = harness.portable_python_script_argv("-c", "print('portable-python-ok')")

        self.assertFalse(Path(argv[0]).is_absolute())
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )

        self.assertEqual(
            completed.returncode,
            0,
            f"argv={argv!r} stdout={completed.stdout!r} stderr={completed.stderr!r}",
        )
        self.assertIn("portable-python-ok", completed.stdout)

    def test_opencode_contract_rejects_shell_command_from_wrong_workdir(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {
                            "input": {
                                "command": harness.shell_command_line(worker_command),
                                "workdir": str(REPO_ROOT.parent / "0625ctr"),
                            }
                        },
                    },
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertTrue(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["contract_failure_reason"], "opencode_workdir_mismatch")
        self.assertEqual(verification["first_shell_workdir_status"], "non_repo_root")
        self.assertEqual(verification["expected_workdir_status"], "repo_root")

    def test_opencode_contract_rejects_shell_command_without_workdir(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {"input": {"command": harness.shell_command_line(worker_command)}},
                    },
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertTrue(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["contract_failure_reason"], "opencode_workdir_mismatch")
        self.assertEqual(verification["first_shell_workdir_status"], "non_repo_root")
        self.assertFalse(verification["first_shell_workdir_matches_repo_root"])

    def test_opencode_contract_rejects_any_tool_before_first_shell_command(self) -> None:
        worker_command = [
            sys.executable,
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/harness/assignments/worker-a-request.json",
        ]
        expected_command = harness.shell_command_line(worker_command)
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {"tool": "read", "state": {"input": {"file": "README.md"}}},
                },
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": expected_command}}},
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertEqual(verification["first_tool_name"], "read")
        self.assertEqual(verification["first_shell_tool_name"], "bash")
        self.assertEqual(verification["tools_before_first_shell"], ["read"])
        self.assertEqual(verification["contract_failure_reason"], "tool_before_first_shell_command")

    def test_opencode_worker_argv_resolves_path_command_before_launch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opencode-command-shim-") as tmp:
            shim_name = "opencode.cmd" if os.name == "nt" else "opencode"
            shim_path = Path(tmp) / shim_name
            shim_path.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
            if os.name != "nt":
                shim_path.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(Path(tmp)) + os.pathsep + old_path
            try:
                argv = harness.build_opencode_run_argv(
                    opencode_command="opencode",
                    opencode_model=None,
                    opencode_agent="c2rust-migrator",
                    opencode_variant="max",
                    opencode_skip_permissions=False,
                    worker_command=[
                        sys.executable,
                        "scripts/c2rust-migrator.py",
                        "--phase",
                        "migrate",
                        "--input",
                        "target/out/harness/assignments/worker-a-request.json",
                    ],
                    request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
                    summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
                    repo_root=REPO_ROOT,
                )
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(Path(argv[0]).resolve(), shim_path.resolve())

    def test_opencode_worker_argv_rejects_non_opencode_command(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_command must be opencode"):
            harness.build_opencode_run_argv(
                opencode_command="codex",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="max",
                opencode_skip_permissions=False,
                worker_command=[
                    sys.executable,
                    "scripts/c2rust-migrator.py",
                    "--phase",
                    "migrate",
                    "--input",
                    "target/out/harness/assignments/worker-a-request.json",
                ],
                request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
                summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
                repo_root=REPO_ROOT,
            )

    def test_opencode_worker_argv_rejects_non_max_variant(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
            harness.build_opencode_run_argv(
                opencode_command="opencode",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="lite",
                opencode_skip_permissions=False,
                worker_command=[
                    sys.executable,
                    "scripts/c2rust-migrator.py",
                    "--phase",
                    "migrate",
                    "--input",
                    "target/out/harness/assignments/worker-a-request.json",
                ],
                request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
                summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_requires_exact_first_shell_command_and_marker(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="preflight-run")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_skip_permissions=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["contract_verification"]["status"], "executed")
            self.assertTrue(result["marker_exists"])
            self.assertTrue((REPO_ROOT / result["marker_path"]).exists())
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["contract_verification"]["status"], "executed")
            expected_policy = {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": "c2rust-migrator",
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            }
            self.assertEqual(report["launch_policy"], expected_policy)
            self.assertRegex(report["launch_policy_sha256"], r"^[0-9a-f]{64}$")
            contract = json.loads((out_root / "harness" / "opencode-preflight-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["launch_policy"], expected_policy)

    def test_opencode_preflight_rejects_invalid_marker_payload(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(
                    json.dumps({"schema_version": 1, "run_id": "preflight-run", "status": "written"}, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["root_cause_key"], "invalid_preflight_marker")
            self.assertEqual(result["contract_verification"]["status"], "executed")
            self.assertTrue(result["marker_exists"])

    def test_opencode_preflight_fails_closed_when_glm_model_is_not_listed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            resolved_opencode = Path(tmp) / "bin" / "opencode.CMD"
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout="openai/gpt-5.1\nopencode/deepseek-v4-flash-free\n",
                        stderr="",
                    )
                raise AssertionError("opencode run must not start when GLM-5.1 is unavailable")

            with patch.object(harness, "resolve_subprocess_command", return_value=str(resolved_opencode)):
                result = harness.run_opencode_preflight(
                    out_root=out_root,
                    run_id="preflight-run",
                    opencode_model="GLM-5.1",
                    opencode_agent="c2rust-migrator",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], str(resolved_opencode))
            self.assertEqual(calls[0][1], "models")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["root_cause_key"], "opencode_model_unavailable")
            blocker = result["h9_blocker"]
            self.assertEqual(blocker["status"], "blocked")
            self.assertEqual(blocker["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(blocker["required_agent_tool"], "opencode")
            self.assertEqual(blocker["required_agent"], "c2rust-migrator")
            self.assertEqual(blocker["required_model"], "GLM-5.1")
            self.assertEqual(blocker["required_variant"], "max")
            self.assertEqual(blocker["required_proof_class"], "competition-exact")
            self.assertFalse(blocker["local_simulation_closes_p0_h9"])
            self.assertFalse(blocker["opencode_run_launched"])
            self.assertEqual(blocker["observed_model_availability"]["status"], "unavailable")
            self.assertEqual(blocker["next_required_action"], "rerun_on_real_opencode_glm51_max_host")
            self.assertEqual(result["argv"][0], "opencode")
            self.assertEqual(result["argv"][result["argv"].index("--dir") + 1], ".")
            self.assertFalse(result["marker_exists"])
            self.assertFalse(result["opencode_run_launched"])
            self.assertEqual(result["contract_verification"]["status"], "not-observed")
            self.assertEqual(result["contract_verification"]["contract_failure_reason"], "opencode_model_unavailable")
            availability = result["opencode_model_availability"]
            self.assertEqual(availability["status"], "unavailable")
            self.assertEqual(availability["required_model"], "GLM-5.1")
            self.assertFalse(availability["model_listed"])
            self.assertEqual(availability["failure_reason"], "required_model_not_listed")
            self.assertEqual(availability["argv"], ["opencode", "models"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(report["h9_blocker"], blocker)
            contract = json.loads((REPO_ROOT / report["handoff_contract"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(contract["opencode_argv"], result["argv"])
            serialized_report = json.dumps(report, sort_keys=True)
            serialized_contract = json.dumps(contract, sort_keys=True)
            self.assertNotIn(str(resolved_opencode), serialized_report)
            self.assertNotIn(str(resolved_opencode), serialized_contract)
            self.assertNotIn(str(REPO_ROOT), serialized_report)
            self.assertNotIn(str(REPO_ROOT), serialized_contract)
            stdout = (REPO_ROOT / report["opencode_model_availability"]["logs"]["stdout"]).read_text(encoding="utf-8")
            self.assertIn("openai/gpt-5.1", stdout)

    def test_opencode_model_probe_rejects_near_match_model_ids(self) -> None:
        stdout = "zhipu/GLM-5.10\nopencode/not-GLM-5.1\nzhipu/glm-5.1\n"
        self.assertFalse(harness.opencode_models_output_mentions_required_model(stdout, "GLM-5.1"))
        self.assertTrue(harness.opencode_models_output_mentions_required_model("GLM-5.1\n", "GLM-5.1"))
        self.assertTrue(harness.opencode_models_output_mentions_required_model("zhipu/GLM-5.1\n", "GLM-5.1"))

    def test_opencode_launch_policy_defaults_to_repo_owned_agent_and_rejects_wrong_agent(self) -> None:
        policy = harness.opencode_launch_policy(
            opencode_command="opencode",
            opencode_model="GLM-5.1",
            opencode_agent=None,
            opencode_variant="max",
            opencode_skip_permissions=False,
        )
        self.assertEqual(policy["opencode_agent"], "c2rust-migrator")
        with self.assertRaisesRegex(SystemExit, "opencode_agent must be c2rust-migrator"):
            harness.opencode_launch_policy(
                opencode_command="opencode",
                opencode_model="GLM-5.1",
                opencode_agent="default",
                opencode_variant="max",
                opencode_skip_permissions=False,
            )

    def test_validate_opencode_preflight_report_rejects_missing_model_availability(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload.pop("opencode_model_availability")
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability is missing"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_unavailable_glm_model(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload["opencode_model_availability"].update(
                {
                    "status": "unavailable",
                    "failure_reason": "required_model_not_listed",
                    "model_listed": False,
                }
            )
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability is not passed"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_wrong_model_probe_argv(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload["opencode_model_availability"]["argv"] = ["opencode", "list-models"]
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability argv"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_report_argv_drift_from_handoff(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload["argv"] = [
                "opencode",
                "run",
                "--dir",
                ".",
                "--format",
                "json",
                "--variant",
                "max",
                "--model",
                "openai/gpt-5.1",
                "Execute test preflight marker.",
            ]
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report argv must match handoff_contract.opencode_argv"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_local_absolute_report_argv(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            handoff_path = REPO_ROOT / payload["handoff_contract"]["path"]
            handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
            bad_argv = list(payload["argv"])
            bad_argv[0] = "C:/Users/me/AppData/Roaming/npm/opencode.CMD"
            payload["argv"] = bad_argv
            handoff_payload["opencode_argv"] = bad_argv
            handoff_payload["opencode_command_line"] = harness.shell_command_line(bad_argv)
            handoff_path.write_text(json.dumps(handoff_payload, sort_keys=True) + "\n", encoding="utf-8")
            payload["handoff_contract"]["sha256"] = harness.sha256_file(handoff_path)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report argv must be portable"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_model_probe_log_hash_drift(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            stdout_path = REPO_ROOT / payload["opencode_model_availability"]["logs"]["stdout"]
            stdout_path.write_text("openai/gpt-5.1\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability stdout hash mismatch"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_model_probe_stdout_without_glm(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            stdout_text = "openai/gpt-5.1\nopencode/not-GLM-5.1\n"
            stdout_path = REPO_ROOT / payload["opencode_model_availability"]["logs"]["stdout"]
            stdout_path.write_text(stdout_text, encoding="utf-8")
            payload["opencode_model_availability"]["stdout_sha256"] = harness.sha256_text(stdout_text)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability stdout missing GLM-5.1"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_recomputes_marker_contract_from_session_evidence(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            session_path = REPO_ROOT / payload["opencode_session_evidence"]["path"]
            session_payload = json.loads(session_path.read_text(encoding="utf-8"))
            session_payload["session_events"][0]["part"]["state"]["input"]["command"] = (
                "python3 -B validation/tools/opencode_agent_harness.py list-workers --db target/fake.sqlite3"
            )
            session_path.write_text(json.dumps(session_payload, sort_keys=True) + "\n", encoding="utf-8")
            payload["opencode_session_evidence"]["sha256"] = harness.sha256_file(session_path)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight session contract"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_marker_hash_drift(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            marker_path = REPO_ROOT / payload["marker_path"]
            marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
            marker_payload["tampered_after_preflight_report"] = True
            marker_path.write_text(json.dumps(marker_payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, r"opencode preflight marker.sha256 mismatch"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_invalid_marker_payload(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            marker_path = REPO_ROOT / payload["marker_path"]
            marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
            marker_payload["report_kind"] = "not-opencode-preflight-marker"
            marker_path.write_text(json.dumps(marker_payload, sort_keys=True) + "\n", encoding="utf-8")
            payload["marker"]["sha256"] = harness.sha256_file(marker_path)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight marker payload invalid"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_opencode_preflight_defaults_to_glm_51_model(self) -> None:
        argv = harness.build_opencode_preflight_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=False,
            marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
            marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
            contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
            repo_root=REPO_ROOT,
        )

        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "GLM-5.1")
        self.assertIn("--agent", argv)
        self.assertEqual(argv[argv.index("--agent") + 1], "c2rust-migrator")

    def test_opencode_preflight_rejects_non_glm_model(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_model must be GLM-5.1"):
            harness.build_opencode_preflight_argv(
                opencode_command="opencode",
                opencode_model="gpt-5.4",
                opencode_agent="c2rust-migrator",
                opencode_variant="max",
                opencode_skip_permissions=False,
                marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
                marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
                contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_rejects_non_max_variant(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
            harness.build_opencode_preflight_argv(
                opencode_command="opencode",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="lite",
                opencode_skip_permissions=False,
                marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
                marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
                contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_rejects_non_opencode_command(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_command must be opencode"):
            harness.build_opencode_preflight_argv(
                opencode_command="codex",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="max",
                opencode_skip_permissions=False,
                marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
                marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
                contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_rejects_marker_when_first_shell_command_differs(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="preflight-run")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["root_cause_key"], "opencode_contract_not_executed")
            self.assertTrue(result["marker_exists"])
            self.assertEqual(result["contract_verification"]["status"], "not-executed")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["root_cause_key"], "opencode_contract_not_executed")

    def test_opencode_preflight_reports_failure_when_process_crashes(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def crash_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="opencode: not found\n")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=crash_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["process_returncode"], 1)
            self.assertEqual(result["root_cause_key"], "opencode_process_failed")
            self.assertFalse(result["marker_exists"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["root_cause_key"], "opencode_process_failed")
            stderr = (REPO_ROOT / report["logs"]["stderr"]).read_text(encoding="utf-8")
            self.assertIn("opencode: not found", stderr)

    def test_run_worker_process_once_times_out_fail_closed(self) -> None:
        seen_kwargs: dict[str, object] = {}

        def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen_kwargs.update(kwargs)
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="partial stdout", stderr="partial stderr")

        completed = harness.run_worker_process_once(
            argv=["opencode", "run"],
            command_runner=timeout_runner,
            repo_root=REPO_ROOT,
            timeout_seconds=7,
        )

        self.assertEqual(seen_kwargs["timeout"], 7)
        self.assertEqual(completed.returncode, 124)
        self.assertIn("partial stdout", completed.stdout)
        self.assertIn("partial stderr", completed.stderr)
        self.assertIn("timed out after 7 seconds", completed.stderr)

    def test_run_captured_process_with_timeout_kills_process_tree(self) -> None:
        seen_kwargs: dict[str, object] = {}
        killed_pids: list[int] = []

        class HungProcess:
            pid = 4321
            returncode = None

            def communicate(self, timeout: int | None = None) -> tuple[str, str]:
                raise subprocess.TimeoutExpired(
                    ["opencode", "run"],
                    timeout,
                    output="partial stdout",
                    stderr="partial stderr",
                )

        def popen_factory(argv: list[str], **kwargs: object) -> HungProcess:
            seen_kwargs.update(kwargs)
            return HungProcess()

        def kill_process_tree(process: HungProcess) -> None:
            killed_pids.append(process.pid)
            process.returncode = -9

        completed = harness.run_captured_process_with_timeout(
            ["opencode", "run"],
            cwd=REPO_ROOT,
            env={"OPENCODE_CONFIG_HOME": "isolated"},
            timeout_seconds=3,
            popen_factory=popen_factory,
            process_tree_killer=kill_process_tree,
        )

        self.assertEqual(killed_pids, [4321])
        self.assertEqual(seen_kwargs["cwd"], REPO_ROOT)
        self.assertTrue(seen_kwargs["text"])
        self.assertEqual(seen_kwargs["encoding"], "utf-8")
        self.assertEqual(seen_kwargs["errors"], "replace")
        self.assertIs(seen_kwargs["stdout"], subprocess.PIPE)
        self.assertIs(seen_kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(seen_kwargs["env"], {"OPENCODE_CONFIG_HOME": "isolated"})
        self.assertEqual(completed.returncode, 124)
        self.assertIn("partial stdout", completed.stdout)
        self.assertIn("partial stderr", completed.stderr)
        self.assertIn("timed out after 3 seconds", completed.stderr)

    def test_run_worker_process_once_real_subprocess_timeout(self) -> None:
        started_at = time.monotonic()

        completed = harness.run_worker_process_once(
            argv=[sys.executable, "-B", "-c", "import time; time.sleep(5)"],
            command_runner=subprocess.run,
            repo_root=REPO_ROOT,
            timeout_seconds=1,
        )

        elapsed = time.monotonic() - started_at
        self.assertLess(elapsed, 4.0)
        self.assertEqual(completed.returncode, 124)
        self.assertEqual(completed.stdout, "")
        self.assertIn("timed out after 1 seconds", completed.stderr)

    def test_run_captured_process_with_timeout_stops_child_holding_pipes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "child-heartbeat.txt"
            child_code = (
                "import pathlib, sys, time\n"
                "path = pathlib.Path(sys.argv[1])\n"
                "for idx in range(80):\n"
                "    path.write_text(str(idx), encoding='utf-8')\n"
                "    print(f'child heartbeat {idx}', flush=True)\n"
                "    time.sleep(0.1)\n"
            )
            parent_code = (
                "import os, subprocess, sys, time\n"
                "heartbeat = sys.argv[1]\n"
                "child_code = sys.argv[2]\n"
                "subprocess.Popen(\n"
                "    [sys.executable, '-B', '-c', child_code, heartbeat],\n"
                "    stdout=sys.stdout,\n"
                "    stderr=sys.stderr,\n"
                "    close_fds=False,\n"
                ")\n"
                "deadline = time.time() + 3\n"
                "while not os.path.exists(heartbeat) and time.time() < deadline:\n"
                "    time.sleep(0.05)\n"
                "print('parent ready', flush=True)\n"
                "time.sleep(30)\n"
            )

            started_at = time.monotonic()
            completed = harness.run_captured_process_with_timeout(
                [sys.executable, "-B", "-c", parent_code, str(heartbeat), child_code],
                cwd=REPO_ROOT,
                timeout_seconds=1,
            )

            elapsed = time.monotonic() - started_at
            self.assertLess(elapsed, 7.0)
            self.assertEqual(completed.returncode, 124)
            self.assertTrue(heartbeat.exists())
            first_heartbeat = heartbeat.read_text(encoding="utf-8")
            time.sleep(0.6)
            self.assertEqual(heartbeat.read_text(encoding="utf-8"), first_heartbeat)
            self.assertIn("timed out after 1 seconds", completed.stderr)

    def test_opencode_preflight_timeout_records_124_and_logs(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            seen_kwargs: dict[str, object] = {}

            def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="", stderr="agent hung")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=timeout_runner,
                timeout_seconds=9,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(seen_kwargs["timeout"], 9)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_seconds"], 9)
            self.assertEqual(result["root_cause_key"], "process_timeout")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertTrue(report["timed_out"])
            stderr = (REPO_ROOT / report["logs"]["stderr"]).read_text(encoding="utf-8")
            self.assertIn("agent hung", stderr)
            self.assertIn("timed out after 9 seconds", stderr)

    def test_opencode_preflight_default_runner_uses_process_tree_timeout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            seen_kwargs: dict[str, object] = {}

            def captured_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                return subprocess.CompletedProcess(
                    argv,
                    124,
                    stdout="",
                    stderr="timed out after 5 seconds\n",
                )

            with patch.object(harness, "run_captured_process_with_timeout", side_effect=captured_runner) as runner:
                result = harness.run_opencode_preflight(
                    out_root=out_root,
                    run_id="preflight-run",
                    timeout_seconds=5,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(runner.call_count, 2)
            self.assertEqual(seen_kwargs["cwd"], REPO_ROOT)
            self.assertEqual(seen_kwargs["timeout_seconds"], 5)
            self.assertIn("XDG_CONFIG_HOME", seen_kwargs["env"])
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["root_cause_key"], "process_timeout")

    def test_run_worker_timeout_writes_blocked_summary_and_repair_hint(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            worker_out_root = out_root / "workers" / "worker-a"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-timeout",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-timeout",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=worker_out_root,
                repo_root=REPO_ROOT,
            )
            seen_kwargs: dict[str, object] = {}

            def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="worker stdout", stderr="worker stderr")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-timeout",
                worker_id="worker-a",
                command_runner=timeout_runner,
                timeout_seconds=5,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(seen_kwargs["timeout"], 5)
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_seconds"], 5)
            self.assertEqual(result["summary_status"], "blocked")
            self.assertEqual(result["repair_hint"]["root_cause_key"], "process_timeout")
            summary = json.loads((worker_out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            metrics = json.loads((worker_out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["root_cause_counts"], {"process_timeout": 1})

    def test_execute_merge_plan_timeout_records_124(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-timeout",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            seen_kwargs: dict[str, object] = {}

            def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="merge stdout", stderr="merge stderr")

            result = harness.execute_merge_plan(
                db_path=db_path,
                run_id="run-timeout",
                out_root=out_root,
                merge_plan={"argv": ["python3", "-B", "validation/tools/run_competition.py"]},
                command_runner=timeout_runner,
                timeout_seconds=11,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(seen_kwargs["timeout"], 11)
            self.assertEqual(result["exit_code"], 124)
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_seconds"], 11)
            self.assertEqual(result["root_cause_key"], "process_timeout")
            stderr = (out_root / "harness" / "run-plan-merge.stderr.log").read_text(encoding="utf-8")
            self.assertIn("merge stderr", stderr)
            self.assertIn("timed out after 11 seconds", stderr)

    def test_execute_merge_plan_default_runner_uses_process_tree_timeout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-timeout",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            seen_kwargs: dict[str, object] = {}

            def captured_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                return subprocess.CompletedProcess(
                    argv,
                    124,
                    stdout="",
                    stderr="timed out after 13 seconds\n",
                )

            with patch.object(harness, "run_captured_process_with_timeout", side_effect=captured_runner) as runner:
                result = harness.execute_merge_plan(
                    db_path=db_path,
                    run_id="run-timeout",
                    out_root=out_root,
                    merge_plan={"argv": ["python3", "-B", "validation/tools/run_competition.py"]},
                    timeout_seconds=13,
                    repo_root=REPO_ROOT,
                )

            runner.assert_called_once()
            self.assertEqual(seen_kwargs["cwd"], REPO_ROOT)
            self.assertEqual(seen_kwargs["timeout_seconds"], 13)
            self.assertIsNone(seen_kwargs.get("env"))
            self.assertEqual(result["exit_code"], 124)
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["root_cause_key"], "process_timeout")

    def test_opencode_database_locked_matches_equivalent_sqlite_busy_signals(self) -> None:
        for stderr in [
            "sqlite3.OperationalError: database is locked",
            "sqlite3.OperationalError: database table is locked",
            "SQLITE_BUSY: database is busy",
            "sqlite_busy while opening agent store",
            "sqlite busy while opening agent store",
        ]:
            with self.subTest(stderr=stderr):
                self.assertTrue(harness.opencode_database_locked(subprocess.CompletedProcess(["opencode"], 1, stdout="", stderr=stderr)))
        self.assertFalse(harness.opencode_database_locked(subprocess.CompletedProcess(["opencode"], 1, stdout="", stderr="syntax error")))

    def test_atomic_write_text_preserves_existing_file_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "harness" / "report.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("old\n", encoding="utf-8")

            with patch.object(harness.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    harness.atomic_write_text(target, "new\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_atomic_write_json_uses_canonical_json_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "report.json"

            harness.atomic_write_json(target, {"b": 2, "a": 1})

            self.assertEqual(target.read_text(encoding="utf-8"), '{\n  "a": 1,\n  "b": 2\n}\n')

    def test_opencode_preflight_cli_dispatches_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "opencode-preflight",
            "--run-id",
            "preflight-run",
            "--out-root",
            "target/opencode-preflight",
            "--opencode-variant",
            "max",
            "--opencode-skip-permissions",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_opencode_preflight",
            return_value={"status": "passed", "exit_code": 0},
        ) as runner:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "passed")
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["run_id"], "preflight-run")
        self.assertEqual(runner.call_args.kwargs["out_root"], Path("target/opencode-preflight"))
        self.assertEqual(runner.call_args.kwargs["opencode_variant"], "max")
        self.assertTrue(runner.call_args.kwargs["opencode_skip_permissions"])

    def test_run_worker_opencode_rejects_failed_preflight_report_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_report.parent.mkdir(parents=True, exist_ok=True)
            preflight_report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "status": "failed",
                        "exit_code": 1,
                        "marker_exists": False,
                        "contract_verification": {"status": "not-observed"},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report is not passed"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_preflight_report_without_launch_policy_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_report.parent.mkdir(parents=True, exist_ok=True)
            preflight_report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "status": "passed",
                        "exit_code": 0,
                        "marker_exists": True,
                        "contract_verification": {"status": "executed"},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight launch policy is missing"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_preflight_report_without_runtime_env_contract_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            launch_policy = {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": "c2rust-migrator",
                "opencode_variant": "max",
                "opencode_skip_permissions": False,
            }
            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_report.parent.mkdir(parents=True, exist_ok=True)
            logs_dir = out_root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            model_stdout = "GLM-5.1\n"
            model_stderr = ""
            model_stdout_path = logs_dir / "opencode-models.stdout.log"
            model_stderr_path = logs_dir / "opencode-models.stderr.log"
            model_stdout_path.write_text(model_stdout, encoding="utf-8")
            model_stderr_path.write_text(model_stderr, encoding="utf-8")
            preflight_report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "status": "passed",
                        "exit_code": 0,
                        "marker_exists": True,
                        "contract_verification": {"status": "executed"},
                        "launch_policy": launch_policy,
                        "launch_policy_sha256": harness.sha256_text(json.dumps(launch_policy, sort_keys=True)),
                        "opencode_model_availability": {
                            "status": "available",
                            "opencode_command": "opencode",
                            "required_model": "GLM-5.1",
                            "argv": ["opencode", "models"],
                            "process_returncode": 0,
                            "model_listed": True,
                            "stdout_sha256": harness.sha256_text(model_stdout),
                            "stderr_sha256": harness.sha256_text(model_stderr),
                            "logs": {
                                "stdout": repo_rel(model_stdout_path),
                                "stderr": repo_rel(model_stderr_path),
                            },
                        },
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report opencode_runtime_env is missing"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_preflight_launch_policy_mismatch_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    opencode_variant="lite",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_self_consistent_non_max_variant_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
                opencode_variant="lite",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    opencode_variant="lite",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_preflight_report_run_id_mismatch_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="previous-run",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight run_id mismatch"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_plan_opencode_rejects_preflight_launch_policy_mismatch_before_worker_fanout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            source_root = out_root / "external" / "demo"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("int first(void) { return 1; }\nint second(void) { return 2; }\n", encoding="utf-8")
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="demo",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=[],
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="demo",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )

            with patch.object(harness, "run_worker") as runner:
                with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
                    harness.run_plan(
                        db_path=db_path,
                        run_id="run-test",
                        plan_path=Path(str(plan["plan_path"])),
                        out_root=out_root,
                        proof_class="local-simulation",
                        mode="opencode",
                        opencode_preflight_report=preflight_report,
                        opencode_model="GLM-5.1",
                        opencode_variant="lite",
                        command_runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
                        repo_root=REPO_ROOT,
                    )

            runner.assert_not_called()

    def test_run_plan_opencode_rejects_preflight_report_run_id_mismatch_before_worker_fanout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            source_root = out_root / "external" / "demo"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("int first(void) { return 1; }\n", encoding="utf-8")
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="demo",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=[],
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="demo",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="previous-run",
            )

            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "worker_id": "worker-001",
                    "exit_code": 0,
                    "process_returncode": 0,
                    "summary_status": "passed",
                    "summary_path": "target/out/workers/worker-001/summary/competition-run-summary.json",
                    "report_path": "target/out/workers/worker-001/harness/run-worker-report.json",
                    "recorded": True,
                },
            ) as runner:
                with self.assertRaisesRegex(SystemExit, "opencode preflight run_id mismatch"):
                    harness.run_plan(
                        db_path=db_path,
                        run_id="run-test",
                        plan_path=Path(str(plan["plan_path"])),
                        out_root=out_root,
                        proof_class="local-simulation",
                        mode="opencode",
                        opencode_preflight_report=preflight_report,
                        command_runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
                        repo_root=REPO_ROOT,
                    )

            runner.assert_not_called()

    def test_run_worker_opencode_binds_passing_preflight_report(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["sha256"], harness.sha256_file(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["launch_policy"]["opencode_variant"], "max")
            self.assertFalse(result["opencode_preflight_report"]["launch_policy"]["opencode_skip_permissions"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_preflight_report"]["status"], "passed")
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertIn(
                ("opencode-preflight-report", repo_rel(preflight_report), "agent-preflight-evidence"),
                artifact_rows,
            )

    def test_run_worker_opencode_retries_transient_database_lock_before_contract_failure(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(out_root / "harness" / "opencode-preflight-report.json", run_id="run-test")
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="database is locked\n")
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(len(calls), 2)
            self.assertEqual(result["opencode_process_retries"]["transient_lock_retry_count"], 1)
            self.assertEqual(result["opencode_process_retries"]["status"], "recovered")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_process_retries"], result["opencode_process_retries"])
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["opencode_process_retries"], result["opencode_process_retries"])

    def test_run_worker_opencode_database_lock_after_worker_command_does_not_retry(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 1, stdout=stdout + "\n", stderr="database is locked\n")

            with patch.object(harness.time, "sleep", return_value=None):
                result = harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["process_returncode"], 1)
            self.assertNotIn("opencode_process_retries", result)
            self.assertEqual(result["opencode_contract_verification"]["status"], "executed")
            self.assertEqual(
                result["repair_hint"]["root_cause_key"],
                "opencode_database_locked_after_worker_command_seen",
            )

    def test_run_plan_opencode_passes_preflight_report_to_workers(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            source_root = out_root / "external" / "demo"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("int first(void) { return 1; }\nint second(void) { return 2; }\n", encoding="utf-8")
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="demo",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=[],
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            handoff_contract = {"path": "target/opencode/handoff-contract.json", "sha256": "a" * 64}
            session_evidence = {"path": "target/opencode/session-evidence.json", "sha256": "b" * 64}
            contract_verification = {"status": "executed", "matched_command": "python3 -B scripts/c2rust-migrator.py"}
            preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
            }

            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "exit_code": 0,
                    "process_returncode": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "logs": {"stdout": "target/stdout.log", "stderr": "target/stderr.log"},
                    "recorded": False,
                    "handoff_contract": handoff_contract,
                    "opencode_session_evidence": session_evidence,
                    "opencode_contract_verification": contract_verification,
                    "opencode_preflight_report": preflight_binding,
                },
            ) as runner:
                result = harness.run_plan(
                    db_path=db_path,
                    run_id="run-test",
                    plan_path=Path(str(plan["plan_path"])),
                    out_root=out_root,
                    proof_class="local-simulation",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(runner.call_count, 2)
            for call in runner.call_args_list:
                self.assertEqual(call.kwargs["opencode_preflight_report"], preflight_report)
            self.assertEqual(result["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["sha256"], harness.sha256_file(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["launch_policy"]["opencode_variant"], "max")
            self.assertFalse(result["opencode_preflight_report"]["launch_policy"]["opencode_skip_permissions"])
            self.assertEqual(result["graph"]["opencode_worker"]["preflight_report"]["status"], "passed")
            self.assertEqual(result["graph"]["opencode_worker"]["preflight_report"]["contract_status"], "executed")
            self.assertEqual(result["graph"]["opencode_worker"]["opencode_variant"], "max")
            first_attempt = result["workers"][0]["attempts"][0]
            self.assertEqual(first_attempt["handoff_contract"], handoff_contract)
            self.assertEqual(first_attempt["opencode_session_evidence"], session_evidence)
            self.assertEqual(first_attempt["opencode_contract_verification"], contract_verification)
            self.assertEqual(first_attempt["opencode_preflight_report"], preflight_binding)
            report = json.loads((out_root / "harness" / "run-plan-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_preflight_report"], result["opencode_preflight_report"])

    def test_run_worker_ignores_stale_summary_from_before_execution(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            stale_summary = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            write_worker_summary(stale_summary, "stale-run", status="passed", failed=0, semantic_pass=1)

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 0, stdout="did not write summary\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            self.assertFalse(result["recorded"])
            self.assertEqual(result["summary_status"], "missing-summary")
            self.assertFalse(stale_summary.exists())

    def test_retry_worker_consumes_repair_hint_and_marks_revalidated_passed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            call_count = 0

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                if call_count == 1:
                    write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                else:
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {call_count}\n", stderr="")

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )
            self.assertEqual(first["exit_code"], 1)
            hint_id = fetch_rows(db_path, "select hint_id from repair_hints")[0][0]

            retry = harness.retry_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(retry["exit_code"], 0)
            self.assertEqual(retry["hint_status"], "revalidated_passed")
            self.assertEqual(call_count, 2)
            hint_rows = fetch_rows(db_path, "select status from repair_hints where hint_id=?", (hint_id,))
            self.assertEqual(hint_rows, [("revalidated_passed",)])

    def test_retry_worker_enforces_five_round_cap_without_launching_worker(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            def failing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="error[E0308]: mismatched types\n")

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=failing_runner,
                repo_root=REPO_ROOT,
            )
            self.assertEqual(first["exit_code"], 1)
            hint_id = fetch_rows(db_path, "select hint_id from repair_hints")[0][0]
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            payload["attempts"] = [
                {
                    "attempt": attempt,
                    "summary_status": "failed",
                    "process_returncode": 1,
                    "exit_code": 1,
                    "summary_path": first["summary_path"],
                    "worker_report_path": first["report_path"],
                    "logs": first["logs"],
                }
                for attempt in range(1, 7)
            ]
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "update repair_hints set payload_json=? where hint_id=?",
                    (json.dumps(payload, sort_keys=True), hint_id),
                )
                connection.commit()
            finally:
                connection.close()
            call_count = 0

            def should_not_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            retry = harness.retry_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=should_not_run,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(call_count, 0)
            self.assertEqual(retry["exit_code"], 1)
            self.assertEqual(retry["hint_status"], "retry_limit_exceeded")
            self.assertEqual(retry["repair_round_cap"], 5)
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            self.assertEqual(payload["status"], "retry_limit_exceeded")
            self.assertEqual(payload["retry_limit"]["max_repair_rounds"], 5)

    def test_retry_worker_records_attempt_history_and_rollback_evidence(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            call_count = 0
            seen_requests: list[dict[str, object]] = []
            repair_trace = {"mode": "baseline_repair_gate"}

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                seen_requests.append({"path": request_path, "request": request})
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                if call_count == 1:
                    write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                else:
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {call_count}\n", stderr="")

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                repair_trace=repair_trace,
            )
            self.assertEqual(first["exit_code"], 1)
            hint_id = fetch_rows(db_path, "select hint_id from repair_hints")[0][0]

            retry = harness.retry_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                repair_trace=repair_trace,
            )

            self.assertEqual(retry["exit_code"], 0)
            self.assertEqual([item["request"]["harness_attempt_number"] for item in seen_requests], [1, 2])
            self.assertEqual(seen_requests[0]["request"]["harness_repair_trace"], repair_trace)
            self.assertNotIn("harness_repair_hint_id", seen_requests[0]["request"])
            self.assertEqual(seen_requests[1]["request"]["harness_repair_hint_id"], hint_id)
            self.assertEqual(seen_requests[1]["request"]["harness_retry_of"], hint_id)
            self.assertEqual(seen_requests[0]["path"].name, "worker-a-request-attempt-1.json")
            self.assertEqual(seen_requests[1]["path"].name, "worker-a-request-attempt-2.json")
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            self.assertEqual(payload["status"], "revalidated_passed")
            self.assertEqual([attempt["attempt"] for attempt in payload["attempts"]], [1, 2])
            self.assertEqual([attempt["summary_status"] for attempt in payload["attempts"]], ["failed", "passed"])
            self.assertEqual(payload["attempts"][0]["root_cause_key"], "final_gate_failed")
            self.assertEqual(payload["attempts"][1]["retry_of"], hint_id)
            rollback_path = REPO_ROOT / payload["attempts"][1]["rollback_evidence"]["path"]
            self.assertTrue(rollback_path.exists())
            rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
            self.assertEqual(rollback["hint_id"], hint_id)
            self.assertEqual(rollback["worker_id"], "worker-a")
            self.assertEqual(rollback["action"], "removed_stale_summary_before_retry")
            self.assertEqual(rollback["removed_summary"]["path"], first["summary_path"])
            self.assertRegex(rollback["removed_summary"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(rollback["last_good"]["status"], "not_available")
            events = [
                (event_type, json.loads(payload_json))
                for event_type, payload_json in fetch_rows(
                    db_path,
                    "select event_type, payload_json from events where event_type='worker_executed' order by event_id",
                )
            ]
            self.assertEqual([event[1]["attempt"] for event in events], [1, 2])
            self.assertEqual(events[1][1]["retry_of"], hint_id)
            self.assertEqual(events[1][1]["rollback_evidence"]["path"], payload["attempts"][1]["rollback_evidence"]["path"])

    def test_retry_worker_annotates_measured_unsafe_reduction_metrics_for_parent_merge(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            call_count = 0

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                if call_count == 1:
                    write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                else:
                    write_worker_summary(
                        summary_path,
                        request["run_id"],
                        status="passed",
                        failed=0,
                        semantic_pass=1,
                        workflow_metrics=measured_unsafe_worker_metrics(request["run_id"]),
                    )
                return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {call_count}\n", stderr="")

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )
            self.assertEqual(first["exit_code"], 1)
            hint_id = fetch_rows(db_path, "select hint_id from repair_hints")[0][0]

            retry = harness.retry_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(retry["exit_code"], 0)
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            self.assertEqual(summary_validator.validate_summary(summary_path, repo_root=REPO_ROOT)["status"], "passed")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["workflow_metrics"]["sha256"], harness.sha256_file(metrics_path))
            self.assertEqual(metrics["unsafe_reduction"]["status"], "measured")
            self.assertEqual(metrics["unsafe_reduction"]["baseline_total_unsafe"], 3)
            self.assertEqual(metrics["unsafe_reduction"]["current_total_unsafe"], 1)
            self.assertEqual(metrics["unsafe_reduction"]["reduced_by"], 2)
            self.assertEqual(metrics["avg_repair_rounds"], 1.0)
            self.assertEqual(metrics["auto_recovery_rate"], 1.0)
            unit = metrics["per_unit_statuses"][0]
            self.assertEqual(unit["repair_rounds"], 1)
            self.assertTrue(unit["auto_recovered"])
            repair_history = unit["repair_history"]
            repair_history_path = REPO_ROOT / repair_history["patch_events_path"]
            self.assertTrue(repair_history_path.exists())
            self.assertEqual(repair_history["patch_events_sha256"], harness.sha256_file(repair_history_path))
            self.assertIn("verified", repair_history["statuses"])
            self.assertEqual(repair_history["rollback_ids"], [retry["rollback_evidence"]["path"]])
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            self.assertEqual(payload["status"], "revalidated_passed")

    def test_retry_worker_cli_dispatches_and_returns_retry_exit_code(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "retry-worker",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
            "--worker-id",
            "worker-a",
            "--hint-id",
            "repair:run-test:worker-a:final_gate_failed",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()), patch.object(
            harness,
            "retry_worker",
            return_value={"exit_code": 7, "status": "retry-test"},
        ) as retry:
            self.assertEqual(harness.main(), 7)

        retry.assert_called_once()
        self.assertEqual(retry.call_args.kwargs["hint_id"], "repair:run-test:worker-a:final_gate_failed")

    def test_run_worker_rejects_missing_out_root(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            request_path = harness.assignment_file_path(db_path, "worker-a").with_name("worker-a-request.json")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            del request["out_root"]
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "worker out_root is required"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    repo_root=REPO_ROOT,
                )

    def test_run_worker_rejects_request_out_root_mismatch_with_ledger(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            request_path = harness.assignment_file_path(db_path, "worker-a").with_name("worker-a-request.json")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["out_root"] = repo_rel(out_root / "workers" / "worker-b")
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            def runner_should_not_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError("worker command should not run when request out_root mismatches ledger")

            with self.assertRaisesRegex(SystemExit, "worker request out_root .* does not match ledger"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    command_runner=runner_should_not_run,
                    repo_root=REPO_ROOT,
                )

    def test_rejects_absolute_or_escaping_paths(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            with self.assertRaises(SystemExit):
                harness.assign_slice(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    target_id="demo",
                    slice_id="escape",
                    source_repo_root=Path("external/demo"),
                    source_file="../src/demo.c",
                    function="add_one",
                    source_commit="abc123",
                    out_root=out_root / "workers" / "worker-a",
                    repo_root=REPO_ROOT,
                )

            with self.assertRaises(SystemExit):
                harness.record_worker_summary(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    summary_path=Path("C:/temp/summary.json"),
                    repo_root=REPO_ROOT,
                )

    def test_finalize_run_updates_run_record_with_summary(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            summary_path = out_root / "summary" / "competition-run-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "proof_class": "local-simulation",
                        "final_gate": {"status": "passed"},
                        "slices": {"attempted": 1, "semantic_pass": 1},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            result = harness.finalize_run(
                db_path=db_path,
                run_id="run-test",
                status="completed",
                summary_path=summary_path,
                final_gate_status="passed",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "finalized")
            self.assertEqual(result["run_id"], "run-test")
            run_rows = fetch_rows(
                db_path,
                "select run_id, status, final_gate_status, summary_path, summary_sha256, ended_at from runs",
            )
            self.assertEqual(len(run_rows), 1)
            run_row = run_rows[0]
            self.assertEqual(run_row[0], "run-test")
            self.assertEqual(run_row[1], "completed")
            self.assertEqual(run_row[2], "passed")
            self.assertIsNotNone(run_row[3])
            self.assertIsNotNone(run_row[4])
            self.assertIsNotNone(run_row[5])


def fetch_rows(db_path: Path, query: str, params: tuple = ()) -> list[tuple]:
    connection = sqlite3.connect(db_path)
    try:
        return list(connection.execute(query, params))
    finally:
        connection.close()


def write_worker_summary(
    summary_path: Path,
    run_id: str,
    *,
    status: str,
    failed: int,
    semantic_pass: int,
    workflow_metrics: dict | None = None,
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "proof_class": "local-simulation",
        "profile_id": "huawei-competition-ubuntu-24.04",
        "profile_sha256": "0" * 64,
        "clang_source": "missing",
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": 0,
        "translator_version": "test",
        "slices": {
            "attempted": 1,
            "typed_ir_generated": 1 if semantic_pass else 0,
            "compiled": 1 if semantic_pass else 0,
            "semantic_pass": semantic_pass,
            "refused": 0,
            "blocked": 0,
            "failed": failed,
        },
        "unsafe_budget": {
            "status": "passed",
            "total_first_party_non_test_unsafe": 0,
            "ratio": 0,
        },
        "artifact_roots": [
            "target/competition-out/evidence",
            "target/competition-out/summary",
            "target/competition-out/logs",
        ],
        "final_gate": {
            "status": status,
            "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
        },
    }
    if workflow_metrics is not None:
        metrics_path = summary_path.parent / "workflow-metrics.json"
        metrics_path.write_text(json.dumps(workflow_metrics, sort_keys=True) + "\n", encoding="utf-8")
        summary["workflow_metrics"] = {
            "path": "workflow-metrics.json",
            "sha256": harness.sha256_file(metrics_path),
        }
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")


def measured_unsafe_worker_metrics(run_id: str) -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "proof_class": "local-simulation",
        "units_total": 1,
        "units_converged": 1,
        "units_baseline_only": 0,
        "unsafe_reduction": {
            "status": "measured",
            "baseline_total_unsafe": 3,
            "current_total_unsafe": 1,
            "reduced_by": 2,
            "ratio": 1 / 3,
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
        "always_compiles": True,
        "always_equivalent": True,
        "fail_closed_count": 0,
        "root_cause_counts": {},
        "wall_clock_seconds": 0,
        "llm_calls": 0,
        "per_unit_statuses": [
            {
                "unit_id": "demo/demo-add-one",
                "source": "opencode-worker",
                "status": "converged",
                "compiled": True,
                "semantic_pass": True,
                "refused": False,
                "blocked": False,
                "failed": False,
            }
        ],
    }


def verified_unsafe_baseline_ref_for_tests() -> dict:
    path = (
        REPO_ROOT
        / "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/"
        "l3-real-fdb-calc-crc32-c2rust-verified-unsafe-baseline.json"
    )
    return {
        "path": repo_rel(path),
        "sha256": harness.sha256_file(path),
        "status": "passed",
        "semantic_pass": True,
        "semantic_claim_source": "verified_unsafe_baseline_gates",
        "generated_draft_semantic_pass": False,
    }


def before_after_worker_metrics(
    out_root: Path,
    run_id: str,
    *,
    baseline_verification: dict | None = None,
) -> dict:
    evidence_dir = out_root / "evidence" / "before-after"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "baseline": evidence_dir / "baseline-unsafe.rs",
        "final": evidence_dir / "final-safe.rs",
        "oracle_evidence": evidence_dir / "oracle-diff.json",
        "accepted_patch": evidence_dir / "accepted.patch",
        "patch_log": evidence_dir / "step-log.jsonl",
        "unsafe_scan_evidence": evidence_dir / "unsafe-scan.json",
    }
    for name, path in artifacts.items():
        path.write_text(f"{name}\n", encoding="utf-8")
    schema_diff_path = evidence_dir / "schema-diff.json"
    schema_diff_path.write_text("schema_diff\n", encoding="utf-8")
    before_after = {
        "schema_version": 1,
        "status": "bound",
        **{
            name: {
                "path": f"evidence/before-after/{path.name}",
                "sha256": harness.sha256_file(path),
            }
            for name, path in artifacts.items()
        },
        "unsafe_reduction": {
            "status": "measured",
            "baseline_total_unsafe": 3,
            "current_total_unsafe": 0,
            "reduced_by": 3,
            "ratio": 0.0,
        },
        "claim_boundary": {
            "function": "store_add_one",
            "non_goals": ["whole-program translation"],
        },
        "semantic_evidence": {
            "schema_diff": {
                "path": f"evidence/before-after/{schema_diff_path.name}",
                "sha256": harness.sha256_file(schema_diff_path),
            },
        },
    }
    if baseline_verification is not None:
        before_after["baseline_verification"] = baseline_verification
    summary_unit = {
        "unit_id": "demo/store-add-one",
        "status": "bound",
        "unsafe_reduction": before_after["unsafe_reduction"],
    }
    if baseline_verification is not None:
        summary_unit["baseline_verification"] = baseline_verification
    return {
        "schema_version": 1,
        "run_id": run_id,
        "proof_class": "local-simulation",
        "units_total": 1,
        "units_converged": 1,
        "units_baseline_only": 0,
        "unsafe_reduction": before_after["unsafe_reduction"],
        "translation_before_after": {
            "status": "bound",
            "unit_count": 1,
            "measured_unsafe_unit_count": 1,
            "accepted_patch_unit_count": 1,
            "units": [summary_unit],
        },
        "avg_repair_rounds": 0.0,
        "auto_recovery_rate": 0.0,
        "human_interventions": 0,
        "always_compiles": True,
        "always_equivalent": True,
        "fail_closed_count": 0,
        "root_cause_counts": {},
        "wall_clock_seconds": 0,
        "llm_calls": 0,
        "per_unit_statuses": [
            {
                "unit_id": "demo/store-add-one",
                "source": "opencode-worker",
                "status": "converged",
                "compiled": True,
                "semantic_pass": True,
                "refused": False,
                "blocked": False,
                "failed": False,
                "translation_before_after": before_after,
            }
        ],
    }


def write_slice_spec(path: Path, target_id: str, slice_id: str, function_name: str, source_commit: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "target_id": target_id,
                "slice_id": slice_id,
                "function_name": function_name,
                "source_commit": source_commit,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_passing_opencode_preflight_report(path: Path, *, run_id: str = "preflight-run", opencode_variant: str = "max") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    base_root = path.parent.parent if path.parent.name == "harness" else path.parent
    harness_dir = base_root / "harness"
    logs_dir = base_root / "logs"
    harness_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    marker_path = harness_dir / "opencode-preflight-marker.json"
    contract_path = harness_dir / "opencode-preflight-contract.json"
    session_path = logs_dir / "opencode-preflight-session-evidence.json"
    marker_command = [
        "python3",
        "-B",
        "validation/tools/opencode_agent_harness.py",
        "write-preflight-marker",
        "--marker",
        repo_rel(marker_path),
        "--run-id",
        run_id,
    ]
    marker_command_line = harness.shell_command_line(marker_command)
    write_json(
        marker_path,
        {
            "schema_version": 1,
            "report_kind": "opencode-preflight-marker",
            "run_id": run_id,
            "status": "written",
        },
    )
    model_stdout = "GLM-5.1\n"
    model_stderr = ""
    model_stdout_path = logs_dir / "opencode-models.stdout.log"
    model_stderr_path = logs_dir / "opencode-models.stderr.log"
    model_stdout_path.write_text(model_stdout, encoding="utf-8")
    model_stderr_path.write_text(model_stderr, encoding="utf-8")
    runtime_env = harness.opencode_runtime_env_contract(
        base_root=base_root,
        scope="preflight",
        repo_root=REPO_ROOT,
    )
    launch_policy = {
        "opencode_command": "opencode",
        "opencode_model": "GLM-5.1",
        "opencode_agent": "c2rust-migrator",
        "opencode_variant": opencode_variant,
        "opencode_skip_permissions": False,
    }
    preflight_argv = [
        "opencode",
        "run",
        "--dir",
        ".",
        "--format",
        "json",
        "--variant",
        opencode_variant,
        "--model",
        "GLM-5.1",
        "--agent",
        "c2rust-migrator",
        "Execute test preflight marker.",
    ]
    preflight_command_line = harness.shell_command_line(preflight_argv)
    write_json(
        contract_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "runner_kind": "opencode-preflight",
            "expected_marker_path": repo_rel(marker_path),
            "worker_command": marker_command,
            "worker_command_line": marker_command_line,
            "worker_command_sha256": harness.sha256_text(marker_command_line),
            "opencode_argv": preflight_argv,
            "opencode_command_line": preflight_command_line,
            "launch_policy": launch_policy,
            "launch_policy_sha256": harness.opencode_launch_policy_sha256(launch_policy),
            "prompt": preflight_argv[-1],
        },
    )
    write_json(
        session_path,
        {
            "schema_version": 1,
            "process_returncode": 0,
            "parsed": True,
            "format": "jsonl",
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
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "status": "passed",
                "exit_code": 0,
                "process_returncode": 0,
                "argv": preflight_argv,
                "opencode_run_launched": True,
                "marker_path": repo_rel(marker_path),
                "marker_exists": True,
                "marker": {
                    "path": repo_rel(marker_path),
                    "sha256": harness.sha256_file(marker_path),
                },
                "handoff_contract": {
                    "path": repo_rel(contract_path),
                    "sha256": harness.sha256_file(contract_path),
                },
                "opencode_session_evidence": {
                    "path": repo_rel(session_path),
                    "sha256": harness.sha256_file(session_path),
                },
                "contract_verification": {
                    "status": "executed",
                    "expected_worker_command_line": marker_command_line,
                    "expected_summary_path": repo_rel(marker_path),
                    "expected_worker_command_sha256": harness.sha256_text(marker_command_line),
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
                "launch_policy": launch_policy,
                "launch_policy_sha256": harness.sha256_text(json.dumps(launch_policy, sort_keys=True)),
                "opencode_runtime_env": runtime_env,
                "opencode_model_availability": {
                    "schema_version": 1,
                    "status": "available",
                    "failure_reason": "",
                    "opencode_command": "opencode",
                    "required_model": "GLM-5.1",
                    "argv": ["opencode", "models"],
                    "process_returncode": 0,
                    "model_listed": True,
                    "stdout_sha256": harness.sha256_text(model_stdout),
                    "stderr_sha256": harness.sha256_text(model_stderr),
                    "logs": {
                        "stdout": repo_rel(model_stdout_path),
                        "stderr": repo_rel(model_stderr_path),
                    },
                },
                "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def repo_rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def write_valid_preflight_marker(marker_path: Path, *, run_id: str) -> None:
    harness.write_opencode_preflight_marker(
        marker_path=Path(repo_rel(marker_path)),
        run_id=run_id,
        repo_root=REPO_ROOT,
    )


def temp_repo_dir():
    target = REPO_ROOT / "target"
    target.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="opencode-harness-test-", dir=target)


if __name__ == "__main__":
    unittest.main()
