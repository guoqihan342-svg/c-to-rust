import hashlib
import json
from pathlib import Path, PurePosixPath
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "validation/evidence/flashdb/harness/l3-flashdb-explicit-workers-harness-run.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path_text: str) -> Path:
    parts = PurePosixPath(path_text).parts
    if ".." in parts or PurePosixPath(path_text).is_absolute():
        raise AssertionError(f"unsafe manifest path: {path_text}")
    return REPO_ROOT / Path(*parts)


def refs_from(value):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            yield value
        for child in value.values():
            yield from refs_from(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs_from(child)


class FlashDBExplicitWorkersManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_records_multi_worker_claim_boundary_and_commands(self):
        manifest = self.manifest
        self.assertEqual(manifest["manifest_kind"], "flashdb-explicit-workers-harness-run")
        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(manifest["run_id"], "harness-flashdb-explicit-workers-20260701")
        self.assertEqual(manifest["proof_class"], "local-simulation")
        self.assertEqual(manifest["summary"]["worker_count"], 2)
        self.assertEqual(manifest["summary"]["semantic_pass"], 2)
        self.assertEqual(manifest["summary"]["planning_mode"], "explicit_workers")
        self.assertEqual(manifest["summary"]["parallelism"]["result_order"], "planner_order")
        self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(manifest["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertIn("run-batch-profile", manifest["reproduction"]["run_batch_profile_command"])
        self.assertIn("evaluate --profile", manifest["reproduction"]["evaluate_profile_command"])
        evaluate_report = manifest["evaluate_profile_artifacts"]["artifacts"]["evaluate_report"]
        self.assertEqual(
            evaluate_report["path"],
            "target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701/harness/evaluate-report.json",
        )

    def test_tracked_artifact_hashes_match(self):
        tracked_roots = [
            self.manifest["profile"],
            self.manifest["environment_profile"],
            self.manifest["source"],
            self.manifest["workers"],
        ]
        refs = [ref for root in tracked_roots for ref in refs_from(root)]
        self.assertGreaterEqual(len(refs), 5)
        for ref in refs:
            path = repo_path(ref["path"])
            self.assertTrue(path.exists(), ref["path"])
            self.assertEqual(sha256(path), ref["sha256"], ref["path"])

    def test_target_artifact_hashes_match_when_reproduced_locally(self):
        target_root = self.manifest["target_run_root"]
        self.assertEqual(target_root["status"], "recorded_not_tracked")
        self.assertTrue(target_root["path"].startswith("target/"))
        refs = [
            *refs_from(self.manifest["target_run_artifacts"]),
            *refs_from(self.manifest["evaluate_profile_artifacts"]),
        ]
        self.assertGreaterEqual(len(refs), 10)
        existing_refs = 0
        for ref in refs:
            path = repo_path(ref["path"])
            if not path.exists():
                continue
            existing_refs += 1
            self.assertEqual(sha256(path), ref["sha256"], ref["path"])
        evaluate_report_path = repo_path(
            self.manifest["evaluate_profile_artifacts"]["artifacts"]["evaluate_report"]["path"]
        )
        if evaluate_report_path.exists():
            evaluate_report = json.loads(evaluate_report_path.read_text(encoding="utf-8"))
            self.assertEqual(evaluate_report["report_kind"], "evaluate-report")
            self.assertEqual(evaluate_report["entrypoint"], "evaluate --profile")
            self.assertIn("not a new semantic gate", evaluate_report["claim_boundary"])
            self.assertFalse(evaluate_report["acceptance_boundary"]["generated_draft_semantic_pass"])
        if repo_path(target_root["path"]).exists():
            self.assertGreater(existing_refs, 0)


if __name__ == "__main__":
    unittest.main()
