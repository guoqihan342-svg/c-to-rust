import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from validation.tools import opencode_agent_harness as harness
from validation.tools import validate_competition_run_summary as summary_validator


REPO_ROOT = Path(__file__).resolve().parents[2]


class OpenCodeAgentHarnessTest(unittest.TestCase):
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
            self.assertEqual(merge_plan["argv"][0], sys.executable)
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
            self.assertEqual(payload["retry_command"][1:4], ["validation/tools/opencode_agent_harness.py", "retry-worker", "--db"])
            self.assertEqual(payload["revalidate_gate"], "competition-run-summary.final_gate.status == passed")

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

            preflight_report = write_passing_opencode_preflight_report(out_root / "harness" / "opencode-preflight-report.json")
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

            preflight_report = write_passing_opencode_preflight_report(out_root / "harness" / "opencode-preflight-report.json")
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
            self.assertEqual(contract["request_path"], repo_rel(out_root / "harness" / "assignments" / "worker-a-request.json"))
            self.assertEqual(
                contract["expected_summary_path"],
                repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
            )
            self.assertEqual(contract["worker_command"][1:4], ["scripts/c2rust-migrator.py", "--phase", "migrate"])
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

            preflight_report = write_passing_opencode_preflight_report(out_root / "harness" / "opencode-preflight-report.json")
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

            preflight_report = write_passing_opencode_preflight_report(out_root / "harness" / "opencode-preflight-report.json")
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

            preflight_report = write_passing_opencode_preflight_report(out_root / "harness" / "opencode-preflight-report.json")
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

    def test_opencode_contract_records_tools_before_first_shell_command(self) -> None:
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

        self.assertEqual(verification["status"], "executed")
        self.assertEqual(verification["first_tool_name"], "read")
        self.assertEqual(verification["first_shell_tool_name"], "bash")
        self.assertEqual(verification["tools_before_first_shell"], ["read"])
        self.assertEqual(verification["contract_failure_reason"], "")

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
                        "run_id": "preflight-run",
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
                        "run_id": "preflight-run",
                        "status": "passed",
                        "exit_code": 0,
                        "marker_exists": True,
                        "contract_verification": {"status": "executed"},
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
            preflight_report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "preflight-run",
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
                harness.run_plan(
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
            repair_history_path = summary_path.parent / repair_history["patch_events_path"]
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


def write_passing_opencode_preflight_report(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "preflight-run",
                "status": "passed",
                "exit_code": 0,
                "marker_exists": True,
                "contract_verification": {"status": "executed"},
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
