import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


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
                compiler_command_source="compile_commands.json",
                include_paths=["include", "src/include"],
                defines=["DEMO=1", "USE_FAST"],
                out_root=out_root / "workers" / "worker-a",
                lease_ttl_seconds=900,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(assignment["worker_id"], "worker-a")
            self.assertEqual(assignment["run_id"], "run-test")
            self.assertEqual(assignment["slice"]["slice_id"], "demo-add-one")
            self.assertEqual(assignment["out_root"], repo_rel(out_root / "workers" / "worker-a"))
            self.assertTrue((out_root / "harness" / "assignments" / "worker-a.json").exists())
            request_path = out_root / "harness" / "assignments" / "worker-a-request.json"
            self.assertTrue(request_path.exists())
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["source_repo_root"], "external/demo")
            self.assertEqual(request["source_file"], "src/demo.c")
            self.assertEqual(request["out_root"], repo_rel(out_root / "workers" / "worker-a"))
            self.assertEqual(request["compiler_command_source"], "compile_commands.json")
            self.assertEqual(request["include_paths"], ["include", "src/include"])
            self.assertEqual(request["defines"], ["DEMO=1", "USE_FAST"])
            task_rows = fetch_rows(db_path, "select worker_name, role, status from agents")
            self.assertEqual(task_rows, [("worker-a", "slice-worker", "assigned")])
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

    def test_record_worker_summary_indexes_artifact_and_merge_plan(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
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
            self.assertIn("--worker-summary", merge_plan["argv"])
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertEqual(artifact_rows, [("competition-run-summary", repo_rel(summary_path), "run-summary")])

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


def fetch_rows(db_path: Path, query: str) -> list[tuple]:
    connection = sqlite3.connect(db_path)
    try:
        return list(connection.execute(query))
    finally:
        connection.close()


def repo_rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def temp_repo_dir():
    target = REPO_ROOT / "target"
    target.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="opencode-harness-test-", dir=target)


if __name__ == "__main__":
    unittest.main()
