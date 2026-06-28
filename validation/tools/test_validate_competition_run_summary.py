import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_competition_run_summary.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_competition_run_summary_under_test", VALIDATOR)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load validate_competition_run_summary module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_summary() -> dict:
    return {
        "schema_version": 1,
        "run_id": "run-2026-06-28T120000Z",
        "proof_class": "wsl-local-simulation",
        "profile_id": "huawei-competition-ubuntu-24.04",
        "profile_sha256": "a" * 64,
        "clang_source": "vendored",
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": 17,
        "translator_version": "0.1.0",
        "slices": {
            "attempted": 2,
            "typed_ir_generated": 1,
            "compiled": 1,
            "semantic_pass": 1,
            "refused": 1,
            "blocked": 0,
            "failed": 0,
        },
        "unsafe_budget": {
            "status": "passed",
            "total_first_party_non_test_unsafe": 0,
            "ratio": 0.0,
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
    }


class ValidateCompetitionRunSummaryTests(unittest.TestCase):
    def test_core_ci_runs_competition_run_summary_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "core-translator-validation-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("validation.tools.test_validate_competition_run_summary", workflow)

    def test_accepts_valid_competition_run_summary(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            summary_path.write_text(json.dumps(valid_summary()), encoding="utf-8")

            result = module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["proof_class"], "wsl-local-simulation")

    def test_accepts_valid_competition_run_summary_with_worker_statuses(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 2,
            "summaries": [
                {
                    "path": "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
                    "status": "passed",
                    "proof_class": "local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                },
                {
                    "path": "target/competition-out/workers/worker-b/summary/competition-run-summary.json",
                    "status": "failed",
                    "proof_class": "local-simulation",
                    "attempted": 2,
                    "semantic_pass": 1,
                    "failed": 1,
                    "slices": {
                        "attempted": 2,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 1,
                    },
                },
            ],
        }
        summary["final_gate"]["status"] = "failed"
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            result = module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")

    def test_rejects_unknown_proof_class(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["proof_class"] = "local"
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("proof_class", str(raised.exception))

    def test_rejects_worker_summary_count_mismatch(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 2,
            "summaries": [
                {
                    "path": "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
                    "status": "passed",
                    "proof_class": "local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("workers.count", str(raised.exception))

    def test_rejects_absolute_artifact_root(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["artifact_roots"][0] = "F:/agent/crustpaper/0625ctr/target/competition-out/evidence"
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("artifact_roots", str(raised.exception))

    def test_rejects_passed_final_gate_without_semantic_pass(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["slices"]["semantic_pass"] = 0
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("semantic_pass", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
