import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validation.tools import c2rust_migrator


REPO_ROOT = Path(__file__).resolve().parents[2]


def flashdb_translation_before_after_ref() -> dict:
    profile_path = REPO_ROOT / "config" / "competition-env" / "planned-batches" / "flashdb-fdb-utils-before-after.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return dict(profile["attempt_evidence_policy"]["translation_before_after"])


def flashdb_verified_unsafe_baseline_ref() -> dict:
    profile_path = REPO_ROOT / "config" / "competition-env" / "planned-batches" / "flashdb-fdb-utils-before-after.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return dict(profile["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"])


def flashdb_translation_before_after_payload() -> dict:
    ref = flashdb_translation_before_after_ref()
    return json.loads((REPO_ROOT / ref["path"]).read_text(encoding="utf-8"))


class C2RustMigratorTest(unittest.TestCase):
    def test_baseline_repair_gate_writes_failed_summary_from_bound_flashdb_evidence(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="c2rust-migrator-test-", dir=target_dir) as tmp:
            out_root = Path(tmp) / "worker-a"
            request = {
                "slice_specs": ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"],
                "target_id": "flashdb",
                "slice_id": "real-fdb-calc-crc32",
                "source_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
                "require_source_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
                "proof_class": "local-simulation",
                "out_root": out_root.relative_to(REPO_ROOT).as_posix(),
                "run_id": "run-test-worker-a",
                "harness_attempt_number": 1,
                "harness_repair_trace": {
                    "mode": "baseline_repair_gate",
                    "translation_before_after": flashdb_translation_before_after_ref(),
                    "baseline_attempt": {
                        "attempt_number": 1,
                        "root_cause_key": "unsafe_baseline_requires_repair",
                        "verified_unsafe_baseline": flashdb_verified_unsafe_baseline_ref(),
                    },
                    "accepted_attempt": {
                        "min_attempt_number": 2,
                        "require_hint_id": True,
                    },
                },
            }

            result = c2rust_migrator.maybe_write_harness_repair_trace_summary(request)

            self.assertIsNotNone(result)
            self.assertEqual(result["exit_code"], 0)
            summary_path = out_root / "summary" / "competition-run-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertEqual(summary["slices"]["semantic_pass"], 0)
            metrics_path = out_root / "summary" / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(metrics["root_cause_counts"], {"unsafe_baseline_requires_repair": 1})
            unit = metrics["per_unit_statuses"][0]
            self.assertEqual(unit["root_cause_key"], "unsafe_baseline_requires_repair")
            self.assertEqual(unit["translation_before_after"]["unsafe_reduction"]["baseline_total_unsafe"], 2)
            self.assertEqual(unit["translation_before_after"]["unsafe_reduction"]["current_total_unsafe"], 0)

    def test_baseline_repair_gate_rejects_failed_verified_unsafe_baseline_ref(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="c2rust-migrator-test-", dir=target_dir) as tmp:
            tmp_path = Path(tmp)
            verified_path = tmp_path / "failed-verified-baseline.json"
            verified_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "semantic_pass": False,
                        "semantic_claim_source": "verified_unsafe_baseline_gates",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            verified_ref = {
                "path": verified_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": c2rust_migrator.sha256_file(verified_path),
                "status": "failed",
                "semantic_pass": False,
                "semantic_claim_source": "verified_unsafe_baseline_gates",
            }
            before_after_artifacts = {}
            for name in ["baseline", "final", "oracle_evidence", "accepted_patch", "patch_log"]:
                artifact_path = tmp_path / f"{name}.txt"
                artifact_path.write_text(f"{name}\n", encoding="utf-8")
                before_after_artifacts[name] = {
                    "path": artifact_path.relative_to(REPO_ROOT).as_posix(),
                    "sha256": c2rust_migrator.sha256_file(artifact_path),
                }
            before_after_path = tmp_path / "translation-before-after.json"
            before_after = {
                "schema_version": 1,
                "status": "bound",
                "target_id": "flashdb",
                "slice_id": "real-fdb-calc-crc32",
                **before_after_artifacts,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                    "ratio": 0.0,
                },
            }
            before_after["baseline_verification"] = dict(verified_ref)
            before_after_path.write_text(json.dumps(before_after, sort_keys=True), encoding="utf-8")
            request = {
                "slice_specs": ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"],
                "target_id": "flashdb",
                "slice_id": "real-fdb-calc-crc32",
                "source_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
                "require_source_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
                "proof_class": "local-simulation",
                "out_root": (tmp_path / "worker-a").relative_to(REPO_ROOT).as_posix(),
                "run_id": "run-test-worker-a",
                "harness_attempt_number": 1,
                "harness_repair_trace": {
                    "mode": "baseline_repair_gate",
                    "translation_before_after": {
                        "path": before_after_path.relative_to(REPO_ROOT).as_posix(),
                        "sha256": c2rust_migrator.sha256_file(before_after_path),
                    },
                    "baseline_attempt": {
                        "attempt_number": 1,
                        "root_cause_key": "unsafe_baseline_requires_repair",
                        "verified_unsafe_baseline": verified_ref,
                    },
                    "accepted_attempt": {
                        "min_attempt_number": 2,
                        "require_hint_id": True,
                    },
                },
            }

            with self.assertRaisesRegex(SystemExit, "verified_unsafe_baseline status must be passed"):
                c2rust_migrator.maybe_write_harness_repair_trace_summary(request)

    def test_baseline_repair_gate_acceptance_attempt_requires_hint_id(self) -> None:
        request = {
            "harness_attempt_number": 2,
            "harness_repair_trace": {
                "mode": "baseline_repair_gate",
                "translation_before_after": flashdb_translation_before_after_ref(),
                "accepted_attempt": {
                    "min_attempt_number": 2,
                    "require_hint_id": True,
                },
            },
        }

        with self.assertRaisesRegex(SystemExit, "requires harness_repair_hint_id"):
            c2rust_migrator.maybe_write_harness_repair_trace_summary(request)

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

        self.assertEqual(argv[0:3], [sys.executable, "-B", "validation/tools/run_competition.py"])
        self.assertNotEqual(argv[0], "python3")
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
