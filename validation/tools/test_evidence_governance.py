import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import evidence_governance


class EvidenceGovernanceTests(unittest.TestCase):
    def test_portability_report_flags_claim_anchor_paths_and_missing_profile_hash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            evidence_dir = root / "validation/evidence/flashdb/auto-translation/example"
            evidence_dir.mkdir(parents=True)
            self._write_json(
                evidence_dir / "l3-example-evidence-manifest.json",
                {
                    "evidence": {
                        "rust_report": {
                            "path": "C:\\Users\\Administrator\\tmp\\rust-report.json",
                            "sha256": "rust-report-sha",
                            "status": "passed",
                        },
                        "clang_lowering_report": {
                            "path": "validation/evidence/flashdb/auto-translation/example/l3-example-clang-lowering-report.json",
                            "sha256": "clang-report-sha",
                            "status": "recorded",
                        },
                    },
                    "competition_environment": {
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "path": "config/competition-env/environment.json",
                    },
                },
            )
            self._write_json(
                evidence_dir / "l3-example-clang-lowering-report.json",
                {
                    "durable_evidence": {
                        "clang_path": "C:\\Program Files\\LLVM\\bin\\clang.exe",
                        "competition_environment": {
                            "profile_id": "huawei-competition-ubuntu-24.04",
                            "path": "config/competition-env/environment.json",
                            "sha256": "profile-sha",
                        },
                    },
                    "lowering_report": {
                        "arguments": [
                            "-IC:/Users/Administrator/Documents/c-to-rust/sources/FlashDB/inc",
                            "C:\\Users\\Administrator\\Documents\\c-to-rust\\sources\\FlashDB\\src\\fdb_utils.c",
                        ],
                        "source_file": "C:/Users/Administrator/Documents/c-to-rust/sources/FlashDB/src/fdb_utils.c",
                    },
                },
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            self.assertEqual(report["status"], "failed")
            self.assertIn("evidence_portability", report["failed_gates"])
            self.assertEqual(report["portability"]["claim_anchor_issue_count"], 1)
            self.assertEqual(report["portability"]["profile_hash_issue_count"], 1)
            self.assertGreaterEqual(report["portability"]["diagnostic_host_metadata_count"], 2)
            self.assertEqual(
                report["portability"]["issues"][0]["code"],
                "absolute_claim_anchor_path",
            )
            self.assertEqual(
                report["portability"]["issues"][0]["json_path"],
                "$.evidence.rust_report.path",
            )
            self.assertEqual(
                report["portability"]["profile_hash_issues"][0]["json_path"],
                "$.competition_environment",
            )

    def test_inventory_report_records_cost_and_retention_classes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "validation/evidence/flashdb/auto-translation/real-slice/l3-real-slice-summary.json",
                {"status": "passed", "duration_ms": 12},
            )
            self._write(
                root / "validation/evidence/flashdb/auto-translation/real-slice/translator-command.stdout.log",
                "translator output\n",
            )
            self._write_json(
                root / "validation/evidence/l1-failure-classification.json",
                {"status": "historical", "duration_ms": 5},
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            self.assertEqual(report["inventory"]["file_count"], 3)
            self.assertGreater(report["inventory"]["total_bytes"], 0)
            self.assertIn("committed_release", report["inventory"]["retention_classes"])
            self.assertIn("diagnostic_only", report["inventory"]["retention_classes"])
            self.assertIn("historical_archive", report["inventory"]["retention_classes"])
            pipelines = {
                pipeline["pipeline_id"]: pipeline for pipeline in report["inventory"]["pipelines"]
            }
            self.assertIn("validation/evidence/flashdb/auto-translation/real-slice", pipelines)
            real_slice = pipelines["validation/evidence/flashdb/auto-translation/real-slice"]
            self.assertEqual(real_slice["target_id"], "flashdb")
            self.assertEqual(real_slice["slice_id"], "real-slice")
            self.assertEqual(real_slice["artifact_count"], 2)
            self.assertGreater(real_slice["total_bytes"], 0)
            self.assertEqual(real_slice["runtime_ms"], 12)
            self.assertEqual(real_slice["retention_class"], "committed_release")
            self.assertEqual(real_slice["compression_policy"], "do_not_compress_claim_anchors")
            self.assertEqual(real_slice["prune_policy"], "do_not_prune_without_manifest_update")
            for policy_name in ["compression_policy", "prune_policy"]:
                self.assertIn(policy_name, report["inventory"]["retention_policy"])

    def test_inventory_report_counts_legacy_compatibility_candidates_separately(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root
                / "validation/evidence/demo/auto-translation/legacy-fallback/l3-legacy-fallback-route-decision.json",
                {
                    "status": "recorded",
                    "candidate_generation": {
                        "selected_candidate_id": None,
                        "candidate_set": [
                            {
                                "candidate_id": "compat:legacy-string-translator",
                                "kind": "legacy-string-translator",
                                "status": "generated",
                                "role": "compatibility_rust_draft",
                                "semantic_pass": False,
                                "correctness_role": "compatibility_only",
                                "compatibility_only": True,
                            },
                            {
                                "candidate_id": "typed-ir:clang-lowered",
                                "kind": "typed-ir",
                                "status": "missing",
                                "role": "typed_ir_candidate_signal",
                                "semantic_pass": False,
                            },
                        ],
                    },
                },
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            metrics = report["inventory"]["candidate_generation"]
            self.assertEqual(metrics["candidate_record_count"], 2)
            self.assertEqual(metrics["by_kind"]["legacy-string-translator"]["candidate_count"], 1)
            self.assertEqual(metrics["by_kind"]["legacy-string-translator"]["compatibility_only_count"], 1)
            self.assertEqual(metrics["by_role"]["compatibility_rust_draft"], 1)
            self.assertEqual(metrics["selected_candidate_count"], 0)

    def test_full_regression_inventory_is_ci_smoke_with_report_artifacts_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            run_dir = root / "target/full-regression/run-1"
            self._write_json(
                run_dir / "summary.json",
                {
                    "status": "passed",
                    "duration_ms": 17,
                    "evidence_root": "F:/agent/crustpaper/0625ctr/target/full-regression/run-1",
                    "working_directory": "F:/agent/crustpaper/0625ctr",
                },
            )
            self._write(
                run_dir / "events.jsonl",
                json.dumps(
                    {
                        "event": "step",
                        "duration_ms": 5,
                        "log": "F:/agent/crustpaper/0625ctr/target/full-regression/run-1/step.log",
                    }
                )
                + "\n",
            )
            self._write(run_dir / "round.log", "full regression smoke output\n")

            report = evidence_governance.build_report(root, evidence_root=Path("target/full-regression"))

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["portability"]["claim_anchor_issue_count"], 0)
            self.assertGreaterEqual(report["portability"]["diagnostic_host_metadata_count"], 3)
            self.assertEqual(report["inventory"]["retention_classes"]["ci_smoke"]["file_count"], 3)
            self.assertEqual(report["inventory"]["runtime"]["observation_count"], 2)
            self.assertEqual(report["inventory"]["runtime"]["total_duration_ms"], 22)
            pipelines = {
                pipeline["pipeline_id"]: pipeline for pipeline in report["inventory"]["pipelines"]
            }
            self.assertIn("target/full-regression/run-1", pipelines)
            pipeline = pipelines["target/full-regression/run-1"]
            self.assertEqual(pipeline["retention_class"], "ci_smoke")
            self.assertEqual(pipeline["artifact_count"], 3)
            self.assertEqual(pipeline["runtime_ms"], 17)
            self.assertEqual(pipeline["prune_policy"], "may_prune_after_ci_retention_window")
            self.assertIn("target/full-regression/run-1/summary.json", pipeline["report_artifacts"])
            self.assertIn("target/full-regression/run-1/events.jsonl", pipeline["report_artifacts"])

    def test_ci_policy_tier_reports_machine_readable_compliance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "target/full-regression/run-1/summary.json",
                {"status": "passed", "duration_ms": 17},
            )
            self._write(root / "target/full-regression/run-1/events.jsonl", '{"event":"step"}\n')

            report = evidence_governance.build_report(
                root,
                evidence_root=Path("target/full-regression"),
                policy_tier="ci",
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["policy_compliance"]["policy_tier"], "ci")
            self.assertEqual(report["policy_compliance"]["status"], "passed")
            self.assertEqual(report["policy_compliance"]["failed_gates"], [])
            gate_names = {gate["name"] for gate in report["policy_compliance"]["gates"]}
            self.assertIn("portability", gate_names)
            self.assertIn("retention_metadata", gate_names)

    def test_release_policy_tier_blocks_diagnostic_host_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "validation/evidence/l1-native-summary.json",
                {
                    "status": "historical",
                    "worker_result_sources": {
                        "network-event": {
                            "path": "C:\\Users\\Administrator\\Documents\\c-to-rust-l1-work\\results.json",
                        }
                    },
                },
            )

            report = evidence_governance.build_report(
                root,
                evidence_root=Path("validation/evidence"),
                policy_tier="release",
            )

            self.assertEqual(report["policy_compliance"]["policy_tier"], "release")
            self.assertEqual(report["policy_compliance"]["status"], "failed")
            self.assertIn("diagnostic_host_metadata", report["policy_compliance"]["failed_gates"])

    def test_translator_artifact_paths_are_claim_anchor_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "validation/evidence/demo/auto-translation/example/l3-example-auto-translation-manifest.json",
                {
                    "translator": {
                        "artifact_paths": [
                            "F:/agent/crustpaper/0625ctr/validation/evidence/demo/auto-translation/example/draft.rs"
                        ]
                    }
                },
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            self.assertEqual(report["portability"]["claim_anchor_issue_count"], 1)
            self.assertEqual(
                report["portability"]["issues"][0]["json_path"],
                "$.translator.artifact_paths[0]",
            )

    def test_source_boundary_files_are_claim_anchors_for_accepted_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "validation/evidence/flashdb/l3-real-fdb-calc-crc32-c-oracle.json",
                {
                    "source_boundary": {
                        "files": [
                            "C:/Users/Administrator/Documents/c-to-rust/sources/FlashDB/src/fdb_utils.c"
                        ]
                    }
                },
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            self.assertEqual(report["portability"]["claim_anchor_issue_count"], 1)
            self.assertEqual(
                report["portability"]["issues"][0]["json_path"],
                "$.source_boundary.files[0]",
            )

    def test_historical_l1_worker_result_sources_are_diagnostic_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "validation/evidence/l1-native-summary.json",
                {
                    "status": "historical",
                    "worker_result_sources": {
                        "network-event": {
                            "path": "C:\\Users\\Administrator\\Documents\\c-to-rust-l1-work\\network-event\\results.json",
                        }
                    },
                },
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["portability"]["claim_anchor_issue_count"], 0)
            self.assertEqual(report["portability"]["diagnostic_host_metadata_count"], 1)
            self.assertEqual(
                report["portability"]["diagnostic_host_metadata"][0]["json_path"],
                "$.worker_result_sources.network-event.path",
            )

    def test_skipped_c2rust_reference_tree_is_diagnostic_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "validation/evidence/demo/auto-translation/example/l3-example-c2rust-baseline-manifest.json",
                {
                    "status": "skipped",
                    "correctness_role": "candidate_context_only",
                    "reference_tree": {
                        "path": "F:\\agent\\c2rust-master",
                        "cargo_toml": "F:\\agent\\c2rust-master\\Cargo.toml",
                        "status": "present",
                    },
                },
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["portability"]["claim_anchor_issue_count"], 0)
            self.assertEqual(report["portability"]["diagnostic_host_metadata_count"], 2)

    def test_c2rust_selected_command_path_is_diagnostic_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence-governance-test-") as tmp:
            root = Path(tmp)
            self._write_json(
                root / "validation/evidence/flashdb/auto-translation/example/l3-example-c2rust-baseline-manifest.json",
                {
                    "status": "generated",
                    "correctness_role": "candidate_context_only",
                    "selected_command": {
                        "name": "c2rust-transpile",
                        "path": "/mnt/f/agent/c2rust-master/target/release/c2rust-transpile",
                        "source": "env:C2RUST_COMMAND",
                    },
                },
            )

            report = evidence_governance.build_report(root, evidence_root=Path("validation/evidence"))

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["portability"]["claim_anchor_issue_count"], 0)
            self.assertEqual(report["portability"]["diagnostic_host_metadata_count"], 1)
            self.assertEqual(
                report["portability"]["diagnostic_host_metadata"][0]["json_path"],
                "$.selected_command.path",
            )

    def test_core_ci_runs_evidence_governance_tests(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")

        self.assertIn("python3 -B -m unittest validation.tools.test_evidence_governance", workflow)

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_json(self, path: Path, payload: dict) -> None:
        self._write(path, json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
