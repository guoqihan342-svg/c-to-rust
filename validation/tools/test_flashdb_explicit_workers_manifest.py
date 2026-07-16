import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
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
        judge_evidence_index = manifest["evaluate_profile_artifacts"]["artifacts"]["judge_evidence_index"]
        self.assertEqual(
            judge_evidence_index["path"],
            "target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701/harness/judge-evidence-index.json",
        )

    def test_tracked_artifact_hashes_match(self):
        tracked_roots = [
            self.manifest["profile"],
            self.manifest["environment_profile"],
            self.manifest["workers"],
        ]
        refs = [ref for root in tracked_roots for ref in refs_from(root)]
        self.assertGreaterEqual(len(refs), 4)
        for ref in refs:
            path = repo_path(ref["path"])
            self.assertTrue(path.exists(), ref["path"])
            self.assertEqual(sha256(path), ref["sha256"], ref["path"])

    def test_source_hash_binds_each_worker_git_blob(self):
        source = self.manifest["source"]
        profile = json.loads(repo_path(self.manifest["profile"]["path"]).read_text(encoding="utf-8"))
        workers = profile["workers"]
        source_repo_root = repo_path(workers[0]["source_repo_root"])
        source_file = workers[0]["source_file"]
        source_commits = list(dict.fromkeys(worker["source_commit"] for worker in workers))

        self.assertEqual(source["hash_basis"], "git_blob_at_source_commit")
        self.assertEqual(source["source_commits"], source_commits)
        self.assertEqual(
            source["path"],
            f"{workers[0]['source_repo_root']}/{source_file}",
        )
        for worker in workers:
            self.assertEqual(worker["source_repo_root"], workers[0]["source_repo_root"])
            self.assertEqual(worker["source_file"], source_file)
            self.assertEqual(worker["require_source_commit"], worker["source_commit"])

        checkout_commit = subprocess.run(
            ["git", "-C", str(source_repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(source["checkout_commit"], checkout_commit)
        source_diff = subprocess.run(
            ["git", "-C", str(source_repo_root), "diff", "--quiet", "--", source_file],
            check=False,
        )
        self.assertEqual(source_diff.returncode, 0, "FlashDB tracked source must be clean")

        for source_commit in source_commits:
            with self.subTest(source_commit=source_commit):
                completed = subprocess.run(
                    ["git", "-C", str(source_repo_root), "show", f"{source_commit}:{source_file}"],
                    check=False,
                    capture_output=True,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stderr.decode("utf-8", errors="replace"),
                )
                self.assertEqual(hashlib.sha256(completed.stdout).hexdigest(), source["sha256"])

    def test_target_artifact_hashes_match_when_reproduced_locally(self):
        target_root = self.manifest["target_run_root"]
        self.assertEqual(target_root["status"], "recorded_not_tracked")
        self.assertTrue(target_root["path"].startswith("target/"))
        refs = [
            *refs_from(self.manifest["target_run_artifacts"]),
            *refs_from(self.manifest["evaluate_profile_artifacts"]),
        ]
        self.assertGreaterEqual(len(refs), 11)
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
            contracts = evaluate_report["judge_summary"]["harness_architecture"]["architecture_contracts"]
            self.assertFalse(contracts["context_management"]["chat_output_is_evidence"])
            self.assertFalse(contracts["context_management"]["semantic_gate"])
            self.assertEqual(
                [stage["stage"] for stage in contracts["context_management"]["pipeline"]],
                ["plan", "translate", "verify", "repair"],
            )
            self.assertFalse(contracts["agent_coordination"]["chat_output_is_evidence"])
            self.assertFalse(contracts["agent_coordination"]["semantic_gate"])
        judge_index_path = repo_path(
            self.manifest["evaluate_profile_artifacts"]["artifacts"]["judge_evidence_index"]["path"]
        )
        if judge_index_path.exists():
            judge_index = json.loads(judge_index_path.read_text(encoding="utf-8"))
            self.assertEqual(judge_index["report_kind"], "judge-evidence-index")
            self.assertEqual(judge_index["entrypoint"], "evaluate --profile")
            self.assertFalse(judge_index["claim_boundary"]["index_is_semantic_gate"])
            self.assertFalse(judge_index["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(judge_index["claim_boundary"]["translation_coverage_numerator"], 0)
            self.assertIn("does not add a semantic acceptance gate", judge_index["claim_boundary"]["boundary"])
            contracts = judge_index["harness_architecture"]["architecture_contracts"]
            self.assertEqual(set(contracts["agent_coordination"]["roles"]), {"planner", "worker", "repairer", "verifier", "reporter"})
            self.assertFalse(contracts["context_management"]["chat_output_is_evidence"])
            self.assertFalse(contracts["agent_coordination"]["chat_output_is_evidence"])
            self.assertEqual(
                judge_index["evidence_artifact_refs"]["evaluate_report"]["path"],
                self.manifest["evaluate_profile_artifacts"]["artifacts"]["evaluate_report"]["path"],
            )
            self.assertEqual(
                judge_index["evidence_artifact_refs"]["competition_run_summary"]["path"],
                self.manifest["evaluate_profile_artifacts"]["artifacts"]["competition_summary"]["path"],
            )
            self.assertNotIn("judge_evidence_index", judge_index["evidence_artifact_refs"])
            self.assertNotIn("context_management_contract", judge_index["evidence_artifact_refs"])
            self.assertNotIn("agent_coordination_contract", judge_index["evidence_artifact_refs"])
        if repo_path(target_root["path"]).exists():
            self.assertGreater(existing_refs, 0)


if __name__ == "__main__":
    unittest.main()
