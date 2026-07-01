import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_CHECKLIST = (
    REPO_ROOT
    / "config"
    / "competition-env"
    / "review-checklists"
    / "flashdb-harness-internal-review.json"
)


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
            "--review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json",
            "python -B -m validation.tools.opencode_agent_harness run-batch-profile",
            "target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json",
            "repair_summary",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-baseline-unsafe.rs",
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-baseline-unsafe.rs",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-final-safe.rs",
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-final-safe.rs",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-accepted-safety.patch",
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-accepted-safety.patch",
            "python -B validation/tools/milestone_release_report.py",
            "--review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json",
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
            "--review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json",
            "python -B -m validation.tools.opencode_agent_harness run-batch-profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
            "target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json",
            "target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json",
            "repair_summary",
            "python -B validation/tools/milestone_release_report.py",
            "--review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json",
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
        review_checklist_rel = "config/competition-env/review-checklists/flashdb-harness-internal-review.json"
        milestone_review_checklist_rel = "target/judge-demo-unit/summary/milestone-review-checklist.json"
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
                self.assertIn("--review-checklist", argv)
                self.assertEqual(argv[argv.index("--review-checklist") + 1], milestone_review_checklist_rel)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                before_after_path = out_root / "summary" / "before-after-exhibit.json"
                batch_path = out_root / "harness" / "batch-profile-report.json"
                before_after = json.loads(before_after_path.read_text(encoding="utf-8"))
                batch = json.loads(batch_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    before_after["inputs"]["competition_summary"]["sha256"],
                    judge_demo_sha256(summary_path),
                )
                self.assertEqual(
                    batch["before_after_exhibit_report"]["sha256"],
                    judge_demo_sha256(before_after_path),
                )
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
                            "review_gate": {
                                "status": "passed",
                                "review_count": 1,
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
            review_checklist_paths=[REVIEW_CHECKLIST],
            command_runner=fake_runner,
            repo_root=REPO_ROOT,
        )

        report_path = out_root / "summary" / "judge-demo-report.json"
        judge_index_path = out_root / "harness" / "judge-evidence-index.json"
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report_path.exists())
        self.assertTrue(judge_index_path.exists())
        persisted = json.loads(report_path.read_text(encoding="utf-8"))
        judge_index = json.loads(judge_index_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["report_kind"], "judge-demo-run-report")
        self.assertEqual(persisted["sidecar_reports"]["judge_evidence_index"]["path"], "target/judge-demo-unit/harness/judge-evidence-index.json")
        self.assertEqual(persisted["artifacts"]["judge_demo_report"]["path"], "target/judge-demo-unit/summary/judge-demo-report.json")
        self.assertEqual(persisted["artifacts"]["judge_demo_report"]["status"], "present")
        self.assertRegex(persisted["artifacts"]["competition_summary"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(persisted["artifacts"]["workflow_metrics"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(persisted["artifacts"]["before_after_exhibit"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(persisted["artifacts"]["milestone_release_report"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(persisted["artifacts"]["milestone_review_checklist"]["path"], milestone_review_checklist_rel)
        self.assertEqual(
            persisted["artifacts"]["milestone_review_checklist"]["sha256"],
            judge_demo_sha256(REVIEW_CHECKLIST),
        )
        self.assertEqual(persisted["artifacts"]["review_checklists"][0]["path"], review_checklist_rel)
        self.assertEqual(persisted["artifacts"]["review_checklists"][0]["sha256"], judge_demo_sha256(REVIEW_CHECKLIST))
        self.assertEqual(persisted["metrics"]["final_gate"], "passed")
        self.assertEqual(persisted["metrics"]["semantic_pass"], 1)
        self.assertEqual(persisted["metrics"]["unsafe_reduction"]["reduced_by"], 2)
        self.assertEqual(persisted["metrics"]["translation_before_after"]["status"], "bound")
        self.assertEqual(persisted["metrics"]["translation_coverage_numerator"], 0)
        self.assertEqual(persisted["metrics"]["review_gate"]["status"], "passed")
        self.assertEqual(set(persisted["metrics"]["stage_contracts"]), {"planner", "worker", "verifier", "repairer", "reporter"})
        self.assertEqual(persisted["harness_architecture"]["entrypoint"], "judge_demo")
        self.assertEqual(
            persisted["harness_architecture"]["pipeline"],
            ["run-batch-profile", "validate-summary", "milestone-release-report", "judge-demo-report"],
        )
        self.assertEqual(
            persisted["harness_architecture"]["command_stages"],
            ["run_batch_profile", "validate_summary", "milestone_release_report"],
        )
        self.assertEqual(persisted["core_translation_quality"]["final_gate_status"], "passed")
        self.assertEqual(persisted["core_translation_quality"]["semantic_pass_count"], 1)
        self.assertEqual(persisted["core_translation_quality"]["unsafe_reduction"]["reduced_by"], 2)
        self.assertEqual(persisted["core_translation_quality"]["translation_before_after"]["status"], "bound")
        self.assertEqual(persisted["core_translation_quality"]["translation_coverage_numerator"], 0)
        self.assertEqual(persisted["core_translation_quality"]["repair_summary"], persisted["repair_summary"])
        self.assertEqual(persisted["core_translation_quality"]["before_after_units"][0]["unit_id"], "flashdb/real-fdb-calc-crc32")
        self.assertEqual(persisted["core_translation_quality"]["before_after_units"][0]["unsafe_reduction"]["reduced_by"], 2)
        self.assertEqual(persisted["harness_architecture"]["delegated_harness"]["entrypoint"], "run-batch-profile")
        self.assertEqual(
            persisted["core_translation_quality"]["delegated_core_translation_quality"]["unsafe_reduction"]["reduced_by"],
            2,
        )
        self.assertEqual(persisted["repair_summary"]["status"], "verified")
        self.assertEqual(persisted["repair_summary"]["repair_round_cap"], 5)
        self.assertEqual(persisted["repair_summary"]["observed_repair_unit_count"], 1)
        self.assertEqual(persisted["repair_summary"]["auto_recovered_unit_count"], 1)
        self.assertEqual(persisted["repair_summary"]["rollback_evidence_count"], 1)
        self.assertEqual(persisted["repair_summary"]["histories"][0]["unit_id"], "flashdb/real-fdb-calc-crc32")
        self.assertEqual(
            persisted["repair_summary"]["histories"][0]["repair_history"]["patch_events_path"],
            "retry-repair-history-judge-demo-unit.jsonl",
        )
        self.assertEqual([command["stage"] for command in persisted["commands"]], [
            "run_batch_profile",
            "validate_summary",
            "milestone_release_report",
        ])
        self.assertEqual(persisted["commands"][0]["argv"][0], "python")
        self.assertIn("translator-generated semantic pass", persisted["claim_boundary"]["must_not_claim"][1])
        self.assertEqual(judge_index["report_kind"], "judge-evidence-index")
        self.assertEqual(judge_index["entrypoint"], "judge_demo")
        self.assertFalse(judge_index["claim_boundary"]["index_is_semantic_gate"])
        self.assertEqual(judge_index["claim_boundary"]["semantic_claim_source"], "accepted_evidence_binding")
        self.assertFalse(judge_index["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(judge_index["claim_boundary"]["translation_coverage_numerator"], 0)
        refs = judge_index["evidence_artifact_refs"]
        self.assertNotIn("judge_evidence_index", refs)
        self.assertNotIn("before_after_exhibit_report", refs)
        self.assertEqual(refs["judge_demo_report"]["path"], "target/judge-demo-unit/summary/judge-demo-report.json")
        self.assertEqual(refs["judge_demo_report"]["sha256"], judge_demo_sha256(report_path))
        self.assertEqual(refs["before_after_exhibit"]["path"], "target/judge-demo-unit/summary/before-after-exhibit.json")
        self.assertEqual(refs["milestone_release_report"]["path"], "target/judge-demo-unit/summary/milestone-release-report.json")
        self.assertEqual(refs["milestone_review_checklist"]["path"], milestone_review_checklist_rel)
        self.assertEqual(refs["milestone_review_checklist"]["sha256"], judge_demo_sha256(REVIEW_CHECKLIST))
        self.assertEqual(refs["internal_review_checklist"]["path"], review_checklist_rel)
        self.assertEqual(refs["internal_review_checklist"]["sha256"], judge_demo_sha256(REVIEW_CHECKLIST))
        self.assertEqual(refs["competition_run_summary"]["path"], "target/judge-demo-unit/summary/competition-run-summary.json")
        self.assertEqual(refs["workflow_metrics"]["path"], "target/judge-demo-unit/summary/workflow-metrics.json")
        self.assertEqual(
            judge_index["reproduction_commands"]["judge_demo"],
            "python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id judge-demo-unit --out-root target/judge-demo-unit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json",
        )
        self.assertIn(
            "--review-checklist target/judge-demo-unit/summary/milestone-review-checklist.json",
            judge_index["reproduction_commands"]["milestone_release_report"],
        )

    def test_repair_summary_falls_back_to_workflow_metrics(self) -> None:
        from validation.tools import judge_demo

        workflow_metrics = {
            "human_interventions": 2,
            "avg_repair_rounds": 2.0,
            "auto_recovery_rate": 0.5,
            "root_cause_counts": {"rustc:E0609": 1, "oracle:diff": 1},
            "per_unit_statuses": [
                {
                    "unit_id": "flashdb/unit-a",
                    "source": "opencode-worker",
                    "status": "failed",
                    "repair_rounds": 3,
                    "auto_recovered": False,
                    "root_cause_key": "rustc:E0609",
                    "repair_history": {
                        "verified": False,
                        "rollback_ids": ["target/judge-demo-unit/workers/unit-a/rollback-before-retry.json"],
                    },
                },
                {
                    "unit_id": "flashdb/unit-b",
                    "source": "opencode-worker",
                    "status": "passed",
                    "repair_rounds": 1,
                    "auto_recovered": True,
                    "root_cause_key": "oracle:diff",
                    "repair_history": {
                        "verified": True,
                        "rollback_ids": [],
                    },
                },
            ],
        }

        summary = judge_demo.build_repair_summary(
            workflow_metrics=workflow_metrics,
            before_after_exhibit={},
        )

        self.assertEqual(summary["status"], "verified")
        self.assertEqual(summary["observed_repair_unit_count"], 2)
        self.assertEqual(summary["auto_recovered_unit_count"], 1)
        self.assertEqual(summary["rollback_evidence_count"], 1)
        self.assertEqual(summary["human_interventions"], 2)
        self.assertEqual(summary["root_cause_counts"], {"rustc:E0609": 1, "oracle:diff": 1})
        self.assertEqual(summary["histories"][0]["unit_id"], "flashdb/unit-a")
        self.assertEqual(summary["histories"][0]["repair_rounds"], 3)

    def test_judge_demo_accepts_bound_before_after_exhibit_without_translator_final_gate(self) -> None:
        from validation.tools import judge_demo

        out_root = REPO_ROOT / "target" / "judge-demo-final-gate-failed-unit"
        profile_path = REPO_ROOT / "config" / "competition-env" / "planned-batches" / "flashdb-fdb-utils-before-after.json"
        if out_root.exists():
            import shutil

            shutil.rmtree(out_root)
        write_judge_demo_fixture_outputs(out_root)
        summary_path = out_root / "summary" / "competition-run-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["final_gate"] = {"status": "failed", "validator": "validate_auto_translation_evidence.py --require-semantic-pass"}
        summary["semantic_pass"] = 0
        summary["slices"]["semantic_pass"] = 0
        summary["slices"]["failed"] = 1
        summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
        milestone_path = out_root / "summary" / "milestone-release-report.json"
        milestone_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "report_kind": "milestone-release-metrics",
                    "status": "internal_preview",
                    "metrics": {"translation_coverage_numerator": 0},
                    "review_gate": {"status": "passed", "review_count": 1},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        report = judge_demo.build_report(
            profile_path=profile_path,
            run_id="judge-demo-final-gate-failed-unit",
            out_root=out_root,
            summary_path=summary_path,
            batch_profile_report_path=out_root / "harness" / "batch-profile-report.json",
            milestone_report_path=milestone_path,
            review_checklist_paths=[],
            milestone_review_checklist_paths=[],
            commands=[
                {"stage": "run_batch_profile", "exit_code": 1},
                {"stage": "validate_summary", "exit_code": 0},
                {"stage": "milestone_release_report", "exit_code": 1},
            ],
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["harness_architecture"]["command_status"], "passed_with_accepted_evidence_gate")
        self.assertEqual(report["core_translation_quality"]["final_gate_status"], "failed")
        self.assertEqual(report["core_translation_quality"]["judge_demo_gate"]["status"], "passed")
        self.assertEqual(report["core_translation_quality"]["judge_demo_gate"]["source"], "before_after_exhibit")
        self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
        self.assertEqual(report["metrics"]["review_gate"]["status"], "passed")


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
        "avg_repair_rounds": 1.0,
        "auto_recovery_rate": 1.0,
        "human_interventions": 0,
        "always_compiles": True,
        "always_equivalent": True,
        "fail_closed_count": 0,
        "root_cause_counts": {"rustc:E0308": 1},
        "wall_clock_seconds": 1,
        "llm_calls": 0,
        "per_unit_statuses": [
            {
                "unit_id": "flashdb/real-fdb-calc-crc32",
                "source": "accepted-evidence-authoritative",
                "status": "passed",
                "repair_rounds": 1,
                "auto_recovered": True,
                "root_cause_key": "rustc:E0308",
                "repair_history": {
                    "patch_events_path": "retry-repair-history-judge-demo-unit.jsonl",
                    "patch_events_sha256": "",
                    "statuses": ["failed", "verified"],
                    "rollback_ids": ["target/judge-demo-unit/workers/rollback-before-retry.json"],
                    "verified": True,
                },
            }
        ],
    }
    workflow_path = summary_dir / "workflow-metrics.json"
    repair_history_path = summary_dir / "retry-repair-history-judge-demo-unit.jsonl"
    repair_history_path.write_text(
        json.dumps(
            {
                "attempt": 1,
                "status": "failed",
                "root_cause_key": "rustc:E0308",
                "rollback_evidence": {"path": "target/judge-demo-unit/workers/rollback-before-retry.json"},
            },
            sort_keys=True,
        )
        + "\n"
        + json.dumps({"attempt": 2, "status": "verified"}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    workflow_metrics["per_unit_statuses"][0]["repair_history"]["patch_events_sha256"] = judge_demo_sha256(
        repair_history_path
    )
    workflow_path.write_text(json.dumps(workflow_metrics, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "schema_version": 1,
        "status": "passed",
        "proof_class": "local-simulation",
        "semantic_pass": 0,
        "failed": 0,
        "blocked": 0,
        "slices": {"semantic_pass": 1},
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
            "repairer": {
                "status": "verified",
                "repair_round_cap": 5,
                "observed_repair_unit_count": 1,
                "avg_repair_rounds": 1.0,
                "auto_recovery_rate": 1.0,
                "root_cause_counts": {"rustc:E0308": 1},
                "histories": [
                    {
                        "unit_id": "flashdb/real-fdb-calc-crc32",
                        "source": "accepted-evidence-authoritative",
                        "status": "passed",
                        "repair_rounds": 1,
                        "auto_recovered": True,
                        "verified": True,
                        "repair_history": workflow_metrics["per_unit_statuses"][0]["repair_history"],
                        "root_cause_key": "rustc:E0308",
                    }
                ],
            },
            "reporter": {"status": "passed"},
        },
        "units": [
            {
                "unit_id": "flashdb/real-fdb-calc-crc32",
                "status": "bound",
                "baseline": {"path": "validation/evidence/flashdb/before-after/baseline-unsafe.rs", "sha256": "0" * 64},
                "final": {"path": "validation/evidence/flashdb/before-after/final-safe.rs", "sha256": "0" * 64},
                "oracle_evidence": {"path": "validation/evidence/flashdb/before-after/oracle-diff.json", "sha256": "0" * 64},
                "accepted_patch": {"path": "validation/evidence/flashdb/before-after/accepted.patch", "sha256": "0" * 64},
                "patch_log": {"path": "validation/evidence/flashdb/before-after/step-log.jsonl", "sha256": "0" * 64},
                "unsafe_reduction": workflow_metrics["unsafe_reduction"],
                "repair_history": workflow_metrics["per_unit_statuses"][0]["repair_history"],
            }
        ],
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
        "judge_summary": {
            "harness_architecture": {
                "entrypoint": "run-batch-profile",
                "graph_runtime": "opencode-harness-langgraph-inspired",
            },
            "core_translation_quality": {
                "final_gate_status": "passed",
                "unsafe_reduction": workflow_metrics["unsafe_reduction"],
                "translation_before_after": workflow_metrics["translation_before_after"],
            },
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
