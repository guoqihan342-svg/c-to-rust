import io
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
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
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )

            handoff_contract = {"path": "target/opencode/handoff-contract.json", "sha256": "a" * 64}
            session_evidence = {"path": "target/opencode/session-evidence.json", "sha256": "b" * 64}
            contract_verification = {"status": "executed", "matched_command": "python -B scripts/c2rust-migrator.py"}
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
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )

            def fake_preflight_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(
                    json.dumps({"schema_version": 1, "run_id": "run-profile-opencode-auto"}, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": contract["worker_command_line"]}, "status": "completed"},
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

            expected_preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
                "run_id": "run-profile-opencode-auto",
                "contract_status": "executed",
                "launch_policy": {
                    "opencode_command": "opencode",
                    "opencode_model": None,
                    "opencode_agent": None,
                    "opencode_variant": "max",
                    "opencode_skip_permissions": False,
                },
                "launch_policy_sha256": harness.sha256_text(
                    json.dumps(
                        {
                            "opencode_agent": None,
                            "opencode_command": "opencode",
                            "opencode_model": None,
                            "opencode_skip_permissions": False,
                            "opencode_variant": "max",
                        },
                        sort_keys=True,
                    )
                ),
                "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
            }
            self.assertEqual(result["mode"], "opencode")
            self.assertEqual(result["opencode_preflight_report"], expected_preflight_binding)
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["opencode_preflight_report"], Path(repo_rel(preflight_report)))
            run_plan = result["run_plan"]
            self.assertEqual(run_plan["opencode_preflight_report"], expected_preflight_binding)
            self.assertEqual(
                run_plan["graph"]["opencode_worker"]["preflight_report"]["path"],
                repo_rel(preflight_report),
            )
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["entrypoints"]["opencode_preflight_report"], repo_rel(preflight_report))
            self.assertEqual(agent_index["reports"]["opencode_preflight_report"], expected_preflight_binding)

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
            self.assertEqual(exhibit["units"][0]["unsafe_reduction"]["reduced_by"], 3)
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
                            "baseline_attempt": {"attempt_number": 1},
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
                        write_worker_summary(
                            summary_path,
                            request["run_id"],
                            status="passed",
                            failed=0,
                            semantic_pass=1,
                            workflow_metrics=before_after_worker_metrics(out_root, request["run_id"]),
                        )
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
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

            self.assertEqual(result["status"], "completed")
            self.assertEqual(worker_attempts, 2)
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
            self.assertEqual(unit["repair_history"], repair_history)
            summary_metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_metrics["translation_before_after"]["status"], "bound")
            self.assertEqual(summary_metrics["root_cause_counts"], {"final_gate_failed": 1})
            self.assertEqual(summary_metrics["per_unit_statuses"][0]["root_cause_key"], "final_gate_failed")
            self.assertEqual(summary_metrics["per_unit_statuses"][0]["repair_history"], repair_history)
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(agent_index["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(context_pack["entrypoints"]["before_after_exhibit_report"], exhibit_ref["path"])
            self.assertEqual(context_pack["report_artifacts"]["before_after_exhibit_report"], exhibit_ref)
            self.assertEqual(agent_index["reports"]["before_after_exhibit_report"], exhibit_ref)

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
            "gpt-5",
            "--opencode-agent",
            "build",
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
        self.assertEqual(kwargs["opencode_model"], "gpt-5")
        self.assertEqual(kwargs["opencode_agent"], "build")
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
        self.assertEqual(evaluate_profile_report.call_args.kwargs["batch_result"], {"status": "completed", "exit_code": 0})
        self.assertEqual(
            evaluate_profile_report.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"),
        )

    def test_write_evaluate_profile_report_updates_context_index_and_ledger(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-evaluate-profile",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
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

            context_pack = json.loads(context_pack_path.read_text(encoding="utf-8"))
            self.assertEqual(context_pack["entrypoints"]["primary_report"], repo_rel(report_path))
            self.assertEqual(context_pack["entrypoints"]["evaluate_report"], repo_rel(report_path))
            self.assertEqual(context_pack["entrypoints"]["batch_profile_report"], repo_rel(batch_report_path))
            self.assertEqual(context_pack["entrypoints"]["judge_evidence_index"], repo_rel(index_path))
            self.assert_context_management_contract(context_pack["context_management_contract"])
            agent_index = json.loads(agent_index_path.read_text(encoding="utf-8"))
            self.assertEqual(agent_index["reports"]["evaluate_report"]["path"], repo_rel(report_path))
            self.assertEqual(agent_index["reports"]["batch_profile_report"]["path"], repo_rel(batch_report_path))
            self.assertEqual(agent_index["reports"]["judge_evidence_index"]["path"], repo_rel(index_path))
            self.assertNotIn("sha256", agent_index["reports"]["judge_evidence_index"])
            self.assert_agent_coordination_contract(agent_index["agent_coordination_contract"], expected_worker_count=0)
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
                "select kind, repo_rel_path, semantic_role from artifacts where kind in ('evaluate-report', 'context-pack', 'agent-index', 'judge-evidence-index') order by kind",
            )
            self.assertEqual(
                artifact_rows,
                [
                    ("agent-index", repo_rel(agent_index_path), "agent-index"),
                    ("context-pack", repo_rel(context_pack_path), "agent-context-pack"),
                    ("evaluate-report", repo_rel(report_path), "evaluate-report"),
                    ("judge-evidence-index", repo_rel(index_path), "judge-evidence-index"),
                ],
            )
            event_rows = fetch_rows(
                db_path,
                "select event_type from events where event_type in ('evaluate_profile_context_refs_updated', 'evaluate_profile_executed', 'judge_evidence_index_written') order by event_type",
            )
            self.assertEqual(
                event_rows,
                [
                    ("evaluate_profile_context_refs_updated",),
                    ("evaluate_profile_executed",),
                    ("judge_evidence_index_written",),
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
            "gpt-5.4",
            "--opencode-agent",
            "c2rust-worker",
            "--opencode-variant",
            "max",
            "--opencode-skip-permissions",
            "--execute-merge",
            "--auto-retry",
            "--max-workers",
            "3",
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
        self.assertEqual(runner.call_args.kwargs["opencode_model"], "gpt-5.4")
        self.assertEqual(runner.call_args.kwargs["opencode_agent"], "c2rust-worker")
        self.assertTrue(runner.call_args.kwargs["opencode_skip_permissions"])
        self.assertTrue(runner.call_args.kwargs["execute_merge"])
        self.assertTrue(runner.call_args.kwargs["auto_retry"])
        self.assertEqual(runner.call_args.kwargs["max_workers"], 3)

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
            self.assertEqual(merge_plan["argv"][:3], ["python", "-B", "validation/tools/run_competition.py"])
            self.assertIn("--worker-summary", merge_plan["argv"])
            self.assertIn("--run-id", merge_plan["argv"])
            run_id_idx = merge_plan["argv"].index("--run-id")
            self.assertEqual(merge_plan["argv"][run_id_idx + 1], "run-test")
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertEqual(artifact_rows, [("competition-run-summary", repo_rel(summary_path), "run-summary")])

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
            self.assertEqual(report["mode"], "deterministic")
            self.assertEqual(report["runner_kind"], "repo-local-c2rust-migrator")
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, status from artifacts")
            self.assertEqual(
                artifact_rows,
                [
                    (
                        "competition-run-summary",
                        repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                        "passed",
                    )
                ],
            )
            event_rows = fetch_rows(db_path, "select event_type from events order by event_id")
            self.assertIn(("worker_executed",), event_rows)

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
            self.assertEqual(
                payload["retry_command"][:5],
                ["python", "-B", "validation/tools/opencode_agent_harness.py", "retry-worker", "--db"],
            )
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
            self.assertEqual(
                contract["worker_command"][:5],
                ["python", "-B", "scripts/c2rust-migrator.py", "--phase", "migrate"],
            )
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
            expected_command = subprocess.list2cmdline(
                [
                    sys.executable,
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
            opencode_agent=None,
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
            opencode_agent=None,
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
        expected_command = subprocess.list2cmdline(worker_command)
        wrong_command = "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": wrong_command}}},
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
        self.assertTrue(verification["worker_command_seen"])
        self.assertEqual(verification["first_shell_command"], wrong_command)
        self.assertFalse(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["first_tool_name"], "bash")
        self.assertEqual(verification["tools_before_first_shell"], [])
        self.assertEqual(verification["contract_failure_reason"], "first_shell_command_mismatch_worker_command_seen_later")

    def test_opencode_contract_rejects_any_tool_before_first_shell_command(self) -> None:
        worker_command = [
            sys.executable,
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/harness/assignments/worker-a-request.json",
        ]
        expected_command = subprocess.list2cmdline(worker_command)
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
                    opencode_agent=None,
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

    def test_opencode_preflight_requires_exact_first_shell_command_and_marker(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(
                    json.dumps({"schema_version": 1, "run_id": "preflight-run"}, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"]},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                opencode_model="gpt-5.4",
                opencode_agent="c2rust-worker",
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
                "opencode_model": "gpt-5.4",
                "opencode_agent": "c2rust-worker",
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            }
            self.assertEqual(report["launch_policy"], expected_policy)
            self.assertRegex(report["launch_policy_sha256"], r"^[0-9a-f]{64}$")
            contract = json.loads((out_root / "harness" / "opencode-preflight-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["launch_policy"], expected_policy)

    def test_opencode_preflight_rejects_marker_when_first_shell_command_differs(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(
                    json.dumps({"schema_version": 1, "run_id": "preflight-run"}, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
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

            with self.assertRaisesRegex(SystemExit, "opencode preflight launch policy mismatch"):
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
                with self.assertRaisesRegex(SystemExit, "opencode preflight launch policy mismatch"):
                    harness.run_plan(
                        db_path=db_path,
                        run_id="run-test",
                        plan_path=Path(str(plan["plan_path"])),
                        out_root=out_root,
                        proof_class="local-simulation",
                        mode="opencode",
                        opencode_preflight_report=preflight_report,
                        opencode_model="gpt-5.4",
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
                        "launch_policy": {
                            "opencode_command": "opencode",
                            "opencode_model": None,
                            "opencode_agent": None,
                            "opencode_variant": "max",
                            "opencode_skip_permissions": False,
                        },
                        "launch_policy_sha256": harness.sha256_text(
                            json.dumps(
                                {
                                    "opencode_agent": None,
                                    "opencode_command": "opencode",
                                    "opencode_model": None,
                                    "opencode_skip_permissions": False,
                                    "opencode_variant": "max",
                                },
                                sort_keys=True,
                            )
                        ),
                        "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
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
                            "state": {"input": {"command": contract["worker_command_line"]}, "status": "completed"},
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
            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            launch_policy = {
                "opencode_command": "opencode",
                "opencode_model": None,
                "opencode_agent": None,
                "opencode_variant": "max",
                "opencode_skip_permissions": False,
            }
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
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            handoff_contract = {"path": "target/opencode/handoff-contract.json", "sha256": "a" * 64}
            session_evidence = {"path": "target/opencode/session-evidence.json", "sha256": "b" * 64}
            contract_verification = {"status": "executed", "matched_command": "python -B scripts/c2rust-migrator.py"}
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


def before_after_worker_metrics(out_root: Path, run_id: str) -> dict:
    evidence_dir = out_root / "evidence" / "before-after"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "baseline": evidence_dir / "baseline-unsafe.rs",
        "final": evidence_dir / "final-safe.rs",
        "oracle_evidence": evidence_dir / "oracle-diff.json",
        "accepted_patch": evidence_dir / "accepted.patch",
        "patch_log": evidence_dir / "step-log.jsonl",
    }
    for name, path in artifacts.items():
        path.write_text(f"{name}\n", encoding="utf-8")
    before_after = {
        "schema_version": 1,
        "status": "bound",
        **{
            name: {
                "path": f"evidence/before-after/{path.name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
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
    }
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
            "units": [
                {
                    "unit_id": "demo/store-add-one",
                    "status": "bound",
                    "unsafe_reduction": before_after["unsafe_reduction"],
                }
            ],
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


def write_passing_opencode_preflight_report(path: Path, *, run_id: str = "preflight-run") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    launch_policy = {
        "opencode_command": "opencode",
        "opencode_model": None,
        "opencode_agent": None,
        "opencode_variant": "max",
        "opencode_skip_permissions": False,
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "status": "passed",
                "exit_code": 0,
                "marker_exists": True,
                "contract_verification": {"status": "executed"},
                "launch_policy": launch_policy,
                "launch_policy_sha256": harness.sha256_text(json.dumps(launch_policy, sort_keys=True)),
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


def temp_repo_dir():
    target = REPO_ROOT / "target"
    target.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="opencode-harness-test-", dir=target)


if __name__ == "__main__":
    unittest.main()
