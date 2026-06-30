import json
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


class JudgeEntrypointsValidatorTests(unittest.TestCase):
    def test_default_flashdb_judge_entrypoints_passes(self) -> None:
        result = validator.validate_config(validator.DEFAULT_CONFIG, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entrypoint_count"], 2)
        self.assertFalse(result["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(result["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(
            [entry["id"] for entry in result["entrypoints"]],
            ["before_after_judge_demo", "multi_worker_evaluate_profile"],
        )
        for entry in result["entrypoints"]:
            self.assertEqual(entry["status"], "passed")
            self.assertEqual(entry["profile"]["status"], "present")
            self.assertEqual(entry["tracked_manifest"]["status"], "present")

    def test_require_local_artifacts_checks_expected_artifact_presence(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [config["entrypoints"][0]]
        config["entrypoints"][0]["expected_artifacts"] = {
            "validator": "validation/tools/validate_judge_entrypoints.py"
        }
        path = write_temp_config(config)

        result = validator.validate_config(path, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        artifacts = result["entrypoints"][0]["expected_artifacts"]
        self.assertEqual(artifacts["validator"]["status"], "present")
        self.assertIn("sha256", artifacts["validator"])

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

    def test_core_validation_ci_runs_judge_entrypoints_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("validation.tools.test_validate_judge_entrypoints", workflow)


if __name__ == "__main__":
    unittest.main()
