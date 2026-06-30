import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from validation.tools import opencode_agent_harness as harness


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

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
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
        self.assertIn("Do not inspect an existing summary before running the command.", prompt)
        self.assertIn("Delete the expected summary file if it already exists, then execute the command exactly once.", prompt)
        self.assertIn("Do not run substitute diagnostics instead of the command.", prompt)
        self.assertIn("scripts/c2rust-migrator.py", prompt)

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
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
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
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def repo_rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def temp_repo_dir():
    target = REPO_ROOT / "target"
    target.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="opencode-harness-test-", dir=target)


if __name__ == "__main__":
    unittest.main()
