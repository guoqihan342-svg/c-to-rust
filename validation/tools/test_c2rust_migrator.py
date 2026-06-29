import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validation.tools import c2rust_migrator


REPO_ROOT = Path(__file__).resolve().parents[2]


class C2RustMigratorTest(unittest.TestCase):
    def test_builds_run_competition_argv_from_direct_request(self) -> None:
        request = {
            "source_repo_root": "external/demo",
            "source_file": "src/demo.c",
            "function": "add_one",
            "target_id": "demo",
            "slice_id": "demo-add-one",
            "source_repository": "https://gitcode.com/xwxf/FlashDB.git",
            "source_branch": "competition",
            "source_commit": "abc123",
            "require_source_commit": "abc123",
            "compiler_command_source": "compile_commands.json",
            "include_paths": ["include", "src/include"],
            "defines": ["DEMO=1"],
            "proof_class": "local-simulation",
            "out_root": "target/competition-out/workers/worker-a",
            "run_id": "run-test-worker-a",
        }

        argv = c2rust_migrator.build_run_competition_argv(request)

        self.assertEqual(argv[0:2], ["python", "validation/tools/run_competition.py"])
        self.assertIn("--source-repo-root", argv)
        self.assertIn("external/demo", argv)
        self.assertIn("--source-repository", argv)
        self.assertIn("https://gitcode.com/xwxf/FlashDB.git", argv)
        self.assertIn("--source-branch", argv)
        self.assertIn("competition", argv)
        self.assertIn("--require-source-commit", argv)
        self.assertIn("--include-path", argv)
        self.assertIn("src/include", argv)
        self.assertIn("--define", argv)
        self.assertIn("DEMO=1", argv)
        self.assertEqual(argv[-4:], ["--proof-class", "local-simulation", "--run-id", "run-test-worker-a"])

    def test_builds_reuse_accepted_evidence_args_from_request(self) -> None:
        request = {
            "source_repo_root": "external/demo",
            "source_file": "src/demo.c",
            "function": "add_one",
            "target_id": "demo",
            "slice_id": "demo-add-one",
            "source_commit": "abc123",
            "proof_class": "local-simulation",
            "out_root": "target/competition-out/workers/worker-a",
            "reuse_accepted_evidence": True,
            "accepted_evidence_root": "validation/evidence",
        }

        argv = c2rust_migrator.build_run_competition_argv(request)

        self.assertIn("--reuse-accepted-evidence", argv)
        self.assertIn("--accepted-evidence-root", argv)
        self.assertIn("validation/evidence", argv)

    def test_builds_run_competition_argv_from_slice_spec_request(self) -> None:
        request = {
            "slice_specs": ["validation/slice-specs/demo-add-one.json"],
            "proof_class": "local-simulation",
            "out_root": "target/competition-out/workers/worker-a",
            "run_id": "run-test-worker-a",
            "reuse_accepted_evidence": True,
            "accepted_evidence_root": "validation/evidence",
        }

        argv = c2rust_migrator.build_run_competition_argv(request)

        self.assertIn("--slice-spec", argv)
        self.assertIn("validation/slice-specs/demo-add-one.json", argv)
        self.assertNotIn("--source-file", argv)
        self.assertIn("--reuse-accepted-evidence", argv)

    def test_slice_spec_request_rejects_mismatched_required_source_commit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-migrator-test-", dir=REPO_ROOT / "target") as tmp:
            spec_path = Path(tmp) / "slice.json"
            spec_path.write_text(json.dumps({"source_commit": "old-commit"}), encoding="utf-8")
            request = {
                "slice_specs": [spec_path.relative_to(REPO_ROOT).as_posix()],
                "require_source_commit": "new-commit",
                "proof_class": "local-simulation",
                "out_root": "target/competition-out/workers/worker-a",
            }

            with self.assertRaisesRegex(SystemExit, "source_commit mismatch"):
                c2rust_migrator.build_run_competition_argv(request)

    def test_builds_merge_argv_from_worker_summaries(self) -> None:
        request = {
            "worker_summaries": [
                "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
                "target/competition-out/workers/worker-b/summary/competition-run-summary.json",
            ],
            "proof_class": "local-simulation",
            "out_root": "target/competition-out",
        }

        argv = c2rust_migrator.build_run_competition_argv(request)

        self.assertEqual(argv.count("--worker-summary"), 2)
        self.assertNotIn("--source-file", argv)
        self.assertEqual(argv[-4:], ["--out-root", "target/competition-out", "--proof-class", "local-simulation"])

    def test_load_request_rejects_missing_required_direct_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-migrator-test-") as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text(json.dumps({"source_file": "src/demo.c"}), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                c2rust_migrator.build_run_competition_argv(c2rust_migrator.load_request(request_path))

        self.assertIn("missing required request fields", str(raised.exception))

    def test_script_entrypoint_runs_from_repo_root(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/c2rust-migrator.py", "--help"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--input", completed.stdout)


if __name__ == "__main__":
    unittest.main()
