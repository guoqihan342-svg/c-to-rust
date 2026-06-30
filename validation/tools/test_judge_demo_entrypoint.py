import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class JudgeDemoEntrypointTest(unittest.TestCase):
    def test_public_docs_bind_before_after_demo_entrypoint(self) -> None:
        chinese_doc = REPO_ROOT / "docs/c2rust-migration-agent/judge-demo.md"
        english_doc = REPO_ROOT / "docs/c2rust-migration-agent/judge-demo.en.md"
        self.assertTrue(chinese_doc.exists(), "missing Chinese judge demo entrypoint")
        self.assertTrue(english_doc.exists(), "missing English judge demo mirror")

        chinese = chinese_doc.read_text(encoding="utf-8")
        english = english_doc.read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        docs_readme = (REPO_ROOT / "docs/c2rust-migration-agent/README.md").read_text(encoding="utf-8")
        roadmap_index = (REPO_ROOT / "docs/c2rust-migration-agent/index/roadmap.md").read_text(encoding="utf-8")
        future_vision = (REPO_ROOT / "docs/c2rust-migration-agent/future-vision-and-mvp.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(chinese.splitlines()[0], "英文镜像见 `judge-demo.en.md`。")
        self.assertIn("docs/c2rust-migration-agent/judge-demo.md", readme)
        self.assertIn("judge-demo.md", docs_readme)
        self.assertIn("target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json", readme)
        self.assertIn("translation_coverage_numerator", readme)

        required_fragments = [
            "config/competition-env/planned-batches/demo-store-add-one-before-after.json",
            "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
            "python -B -m validation.tools.judge_demo",
            "python -B -m validation.tools.opencode_agent_harness run-batch-profile",
            "target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-baseline-unsafe.rs",
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-baseline-unsafe.rs",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-final-safe.rs",
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-final-safe.rs",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-accepted-safety.patch",
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-accepted-safety.patch",
            "python -B validation/tools/milestone_release_report.py",
            "target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json",
            "real-fdb-calc-crc32",
            "C2Rust baseline output remains skipped",
            "translation_coverage_numerator",
            "generated_draft_semantic_pass=false",
        ]
        for fragment in required_fragments:
            self.assertIn(fragment, chinese)
            self.assertIn(fragment, english)

        public_index_fragments = [
            "python -B -m validation.tools.judge_demo",
            "python -B -m validation.tools.opencode_agent_harness run-batch-profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
            "target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json",
            "python -B validation/tools/milestone_release_report.py",
            "translation_coverage_numerator",
        ]
        for fragment in public_index_fragments:
            self.assertIn(fragment, roadmap_index)
            self.assertIn(fragment, future_vision)

        forbidden_host_paths = ("C:\\", "F:\\", "/mnt/c/")
        for fragment in forbidden_host_paths:
            self.assertNotIn(fragment, chinese)
            self.assertNotIn(fragment, english)

    def test_core_validation_ci_runs_judge_demo_entrypoint_contract(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")

        self.assertIn("validation.tools.test_judge_demo_entrypoint", workflow)

    def test_judge_demo_runner_writes_hash_bound_report(self) -> None:
        from validation.tools import judge_demo

        out_root = REPO_ROOT / "target" / "judge-demo-unit"
        profile_path = REPO_ROOT / "config" / "competition-env" / "planned-batches" / "flashdb-fdb-utils-before-after.json"
        if out_root.exists():
            import shutil

            shutil.rmtree(out_root)

        def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if "validation.tools.opencode_agent_harness" in argv:
                write_judge_demo_fixture_outputs(out_root)
                return subprocess.CompletedProcess(argv, 0, stdout="batch ok\n", stderr="")
            if any(str(part).endswith("validate_competition_run_summary.py") for part in argv):
                return subprocess.CompletedProcess(argv, 0, stdout='{"status":"passed"}\n', stderr="")
            if any(str(part).endswith("milestone_release_report.py") for part in argv):
                output_path = REPO_ROOT / argv[argv.index("--output") + 1]
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "report_kind": "milestone-release-metrics",
                            "status": "internal_preview",
                            "metrics": {
                                "translation_coverage_numerator": 0,
                            },
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, stdout="milestone ok\n", stderr="")
            raise AssertionError(f"unexpected argv: {argv}")

        report = judge_demo.run_judge_demo(
            profile_path=profile_path,
            run_id="judge-demo-unit",
            out_root=out_root,
            command_runner=fake_runner,
            repo_root=REPO_ROOT,
        )

        report_path = out_root / "summary" / "judge-demo-report.json"
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report_path.exists())
        persisted = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["report_kind"], "judge-demo-run-report")
        self.assertEqual(persisted["artifacts"]["judge_demo_report"]["path"], "target/judge-demo-unit/summary/judge-demo-report.json")
        self.assertEqual(persisted["artifacts"]["judge_demo_report"]["status"], "present")
        self.assertRegex(persisted["artifacts"]["competition_summary"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(persisted["artifacts"]["workflow_metrics"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(persisted["artifacts"]["before_after_exhibit"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(persisted["artifacts"]["milestone_release_report"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(persisted["metrics"]["final_gate"], "passed")
        self.assertEqual(persisted["metrics"]["semantic_pass"], 1)
        self.assertEqual(persisted["metrics"]["unsafe_reduction"]["reduced_by"], 2)
        self.assertEqual(persisted["metrics"]["translation_before_after"]["status"], "bound")
        self.assertEqual(persisted["metrics"]["translation_coverage_numerator"], 0)
        self.assertEqual(set(persisted["metrics"]["stage_contracts"]), {"planner", "worker", "verifier", "repairer", "reporter"})
        self.assertEqual([command["stage"] for command in persisted["commands"]], [
            "run_batch_profile",
            "validate_summary",
            "milestone_release_report",
        ])
        self.assertEqual(persisted["commands"][0]["argv"][0], "python")
        self.assertIn("translator-generated semantic pass", persisted["claim_boundary"]["must_not_claim"][1])


def write_judge_demo_fixture_outputs(out_root: Path) -> None:
    summary_dir = out_root / "summary"
    harness_dir = out_root / "harness"
    summary_dir.mkdir(parents=True, exist_ok=True)
    harness_dir.mkdir(parents=True, exist_ok=True)
    workflow_metrics = {
        "schema_version": 1,
        "run_id": "judge-demo-unit",
        "proof_class": "local-simulation",
        "units_total": 1,
        "units_converged": 1,
        "units_baseline_only": 0,
        "unsafe_reduction": {
            "status": "measured",
            "baseline_total_unsafe": 2,
            "current_total_unsafe": 0,
            "reduced_by": 2,
            "ratio": 0.0,
        },
        "translation_before_after": {
            "status": "bound",
            "unit_count": 1,
            "measured_unsafe_unit_count": 1,
            "accepted_patch_unit_count": 1,
            "units": [],
        },
        "avg_repair_rounds": 0.0,
        "auto_recovery_rate": 0.0,
        "human_interventions": 0,
        "always_compiles": True,
        "always_equivalent": True,
        "fail_closed_count": 0,
        "root_cause_counts": {},
        "wall_clock_seconds": 1,
        "llm_calls": 0,
        "per_unit_statuses": [],
    }
    workflow_path = summary_dir / "workflow-metrics.json"
    workflow_path.write_text(json.dumps(workflow_metrics, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "schema_version": 1,
        "status": "passed",
        "proof_class": "local-simulation",
        "semantic_pass": 1,
        "failed": 0,
        "blocked": 0,
        "final_gate": {"status": "passed"},
        "workflow_metrics": {
            "path": "workflow-metrics.json",
            "sha256": judge_demo_sha256(workflow_path),
        },
    }
    (summary_dir / "competition-run-summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before_after = {
        "schema_version": 1,
        "report_kind": "before-after-exhibit",
        "status": "passed",
        "stage_contracts": {
            "planner": {"status": "planned"},
            "worker": {"status": "passed"},
            "verifier": {"status": "passed"},
            "repairer": {"status": "not_exercised"},
            "reporter": {"status": "passed"},
        },
    }
    before_after_path = summary_dir / "before-after-exhibit.json"
    before_after_path.write_text(json.dumps(before_after, sort_keys=True) + "\n", encoding="utf-8")
    batch = {
        "schema_version": 1,
        "profile_id": "flashdb-fdb-utils-before-after",
        "proof_class": "local-simulation",
        "before_after_exhibit_report": {
            "path": "target/judge-demo-unit/summary/before-after-exhibit.json",
            "sha256": judge_demo_sha256(before_after_path),
            "status": "passed",
            "report_kind": "before-after-exhibit",
            "unit_count": 1,
            "measured_unsafe_unit_count": 1,
            "accepted_patch_unit_count": 1,
        },
    }
    (harness_dir / "batch-profile-report.json").write_text(
        json.dumps(batch, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def judge_demo_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
