import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from validation.tools import milestone_release_notes


class MilestoneReleaseNotesTests(unittest.TestCase):
    def test_release_notes_render_publication_manifest_without_semantic_expansion(self) -> None:
        notes = milestone_release_notes.build_release_notes(self._bundle())

        self.assertIn("# FlashDB Harness MVP Release Notes", notes)
        self.assertIn("Status: `passed`", notes)
        self.assertIn("Repository commit: `1234567890abcdef1234567890abcdef12345678`", notes)
        self.assertIn("Proof class rollup: `local-simulation`", notes)
        self.assertIn("Translation coverage numerator: `0`", notes)
        self.assertIn("Semantic gate: `false`", notes)
        self.assertIn("## Judge Packet Index", notes)
        self.assertIn(
            "| Judge config | config/competition-env/judge-entrypoints/flashdb-harness.json | 000000000000 | present |",
            notes,
        )
        self.assertIn(
            "| Competition config archive | config/competition-env/bundle-manifest.json | 111111111111 | present |",
            notes,
        )
        self.assertIn(
            "| Judge run report | target/competition-out/summary/judge-entrypoints-run-report.json | 222222222222 | present |",
            notes,
        )
        self.assertIn(
            "| Readiness report | target/competition-out/summary/judge-entrypoints-readiness.json | 333333333333 | present |",
            notes,
        )
        self.assertIn(
            "| Judge milestone bundle | target/competition-out/summary/judge-milestone-bundle.json | self | self |",
            notes,
        )
        self.assertIn("| Auto-recovered units | 1 |", notes)
        self.assertIn("| raw C2Rust | not_verified_here | no | 0 |", notes)
        self.assertIn("python -B -m validation.tools.run_judge_entrypoints", notes)
        self.assertIn("accepted_evidence_is_not_translator_generated_coverage", notes)
        self.assertIn("whole-project FlashDB migration", notes)

    def test_release_notes_reject_expanded_semantic_claims(self) -> None:
        cases = [
            ("claim_boundary.semantic_gate", lambda payload: payload["claim_boundary"].__setitem__("semantic_gate", True)),
            (
                "claim_boundary.translation_coverage_numerator",
                lambda payload: payload["claim_boundary"].__setitem__("translation_coverage_numerator", 1),
            ),
            (
                "quantitative_evaluation.semantic_gate",
                lambda payload: payload["quantitative_evaluation"].__setitem__("semantic_gate", True),
            ),
            (
                "quantitative_evaluation.translation_coverage_numerator",
                lambda payload: payload["quantitative_evaluation"].__setitem__("translation_coverage_numerator", 1),
            ),
            (
                "quantitative_evaluation.outcome_counts.translator_generated_semantic_pass_count",
                lambda payload: payload["quantitative_evaluation"]["outcome_counts"].__setitem__(
                    "translator_generated_semantic_pass_count",
                    1,
                ),
            ),
            (
                "quantitative_evaluation.outcome_counts.generated_draft_semantic_pass",
                lambda payload: payload["quantitative_evaluation"]["outcome_counts"].__setitem__(
                    "generated_draft_semantic_pass",
                    True,
                ),
            ),
            (
                "quantitative_evaluation.outcome_counts.translation_coverage_numerator",
                lambda payload: payload["quantitative_evaluation"]["outcome_counts"].__setitem__(
                    "translation_coverage_numerator",
                    1,
                ),
            ),
            (
                "publication_manifest.claim_boundary.publication_manifest_is_semantic_gate",
                lambda payload: payload["publication_manifest"]["claim_boundary"].__setitem__(
                    "publication_manifest_is_semantic_gate",
                    True,
                ),
            ),
            (
                "baseline_comparison.raw_c2rust.semantic_acceptance_claimed",
                lambda payload: payload["quantitative_evaluation"]["baseline_comparison"]["raw_c2rust"].__setitem__(
                    "semantic_acceptance_claimed",
                    True,
                ),
            ),
            (
                "opencode_runtime.chat_output_is_evidence_false",
                lambda payload: payload["opencode_runtime"].__setitem__("chat_output_is_evidence_false", False),
            ),
            (
                "opencode_evidence_policy.chat_output_is_evidence_false",
                lambda payload: payload["opencode_evidence_policy"].__setitem__("chat_output_is_evidence_false", False),
            ),
            (
                "opencode_evidence_policy.semantic_gate_false",
                lambda payload: payload["opencode_evidence_policy"].__setitem__("semantic_gate_false", False),
            ),
            (
                "opencode_evidence_policy.semantic_gate",
                lambda payload: payload["opencode_evidence_policy"].__setitem__("semantic_gate", True),
            ),
        ]

        for expected_error, mutate in cases:
            with self.subTest(expected_error=expected_error):
                payload = self._bundle()
                mutate(payload)
                with self.assertRaises(SystemExit) as raised:
                    milestone_release_notes.build_release_notes(payload)
                self.assertIn(expected_error, str(raised.exception))

    def test_main_writes_release_notes_markdown(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-notes-") as tmp:
            root = Path(tmp)
            bundle_path = root / "judge-milestone-bundle.json"
            notes_path = root / "milestone-release-notes.md"
            bundle_path.write_text(json.dumps(self._bundle()), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = milestone_release_notes.main(
                    [
                        "--bundle",
                        str(bundle_path),
                        "--out",
                        str(notes_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            text = notes_path.read_text(encoding="utf-8")
            self.assertIn("# FlashDB Harness MVP Release Notes", text)
            self.assertIn("Bundle: `target/competition-out/summary/judge-milestone-bundle.json`", text)

    def test_core_ci_runs_release_notes_gate(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("python -m unittest validation.tools.test_milestone_release_notes", text)

    def _bundle(self) -> dict:
        return {
            "schema_version": 1,
            "report_kind": "judge-milestone-bundle",
            "status": "passed",
            "summary": {
                "headline": "FlashDB harness MVP local-simulation milestone",
            },
            "claim_boundary": {
                "semantic_gate": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "bundle_is_semantic_gate": False,
            },
            "proof_classes": {
                "rollup": {
                    "trusted_proof_classes": ["local-simulation"],
                    "has_competition_exact": False,
                }
            },
            "publishability": {
                "status": "internal_preview",
                "scope": "full",
                "external_milestone": False,
            },
            "core_translation_quality": {
                "translation_coverage_numerator": 0,
                "accepted_evidence_semantic_pass_count": 2,
                "generated_draft_semantic_pass": False,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                },
            },
            "harness_architecture_summary": {
                "rollup": {
                    "source_count": 4,
                    "worker_count": 2,
                    "repair_round_cap": 5,
                    "graph_runtimes": ["langgraph-style"],
                    "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                }
            },
            "workflow_metrics": {
                "rollup": {
                    "units_total": 5,
                    "units_converged": 4,
                    "human_interventions": 0,
                    "repair_activity": {
                        "observed_source_count": 1,
                        "repair_history_unit_count": 1,
                        "auto_recovered_unit_count": 1,
                        "avg_repair_rounds": 1.0,
                        "auto_recovery_rate": 0.2,
                    },
                }
            },
            "quantitative_evaluation": {
                "report_kind": "quantitative-evaluation-scorecard",
                "evaluation_scope": "bounded-mvp",
                "semantic_gate": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "project_slice_counts": {
                    "workflow_units_total": 5,
                    "workflow_units_converged": 4,
                    "before_after_bound_unit_count": 1,
                },
                "outcome_counts": {
                    "accepted_evidence_semantic_pass_count": 2,
                    "translator_generated_semantic_pass_count": 0,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                    "blocked_repair_count": 1,
                    "human_interventions": 0,
                    "auto_recovered_unit_count": 1,
                },
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                    "scope": "partial",
                },
                "repair_activity": {
                    "observed_source_count": 1,
                    "repair_history_unit_count": 1,
                    "auto_recovered_unit_count": 1,
                    "avg_repair_rounds": 1.0,
                    "auto_recovery_rate": 0.2,
                    "human_interventions": 0,
                },
                "baseline_comparison": {
                    "raw_c2rust": {
                        "status": "not_verified_here",
                        "evidence_role": "candidate_context_only",
                        "semantic_acceptance_claimed": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                    "c2rust_repair": {
                        "status": "not_exercised",
                        "evidence_role": "candidate_source",
                        "semantic_acceptance_claimed": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                    "typed_ir_route": {
                        "status": "candidate_or_accepted_evidence_bound",
                        "evidence_role": "candidate_source",
                        "semantic_acceptance_claimed": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                    "opencode_llm_worker": {
                        "status": "command_contract_executed",
                        "evidence_role": "patch_candidate_source",
                        "semantic_acceptance_claimed": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                        "chat_output_is_evidence": False,
                    },
                    "handwritten_reference": {
                        "status": "accepted_evidence_reference",
                        "evidence_role": "reference_only",
                        "semantic_acceptance_claimed": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                        "counts_as_translator_generated_coverage": False,
                    },
                },
                "claim_boundary": {
                    "semantic_gate": False,
                    "scorecard_is_semantic_gate": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
            },
            "publication_manifest": {
                "report_kind": "publication-manifest",
                "publication_scope": "full",
                "repo_commit": {
                    "status": "present",
                    "commit": "1234567890abcdef1234567890abcdef12345678",
                },
                "target_source_pin": {
                    "target_id": "flashdb",
                    "repository": "https://gitcode.com/xwxf/FlashDB.git",
                    "branch": "competition",
                    "canonical_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
                },
                "judge_config": {
                    "path": "config/competition-env/judge-entrypoints/flashdb-harness.json",
                    "sha256": "0" * 64,
                    "status": "present",
                },
                "competition_config_archive": {
                    "status": "present",
                    "bundle_manifest": {
                        "path": "config/competition-env/bundle-manifest.json",
                        "sha256": "1" * 64,
                        "status": "present",
                    },
                },
                "judge_entrypoints_run_report": {
                    "path": "target/competition-out/summary/judge-entrypoints-run-report.json",
                    "sha256": "2" * 64,
                    "status": "present",
                },
                "readiness_report": {
                    "path": "target/competition-out/summary/judge-entrypoints-readiness.json",
                    "sha256": "3" * 64,
                    "status": "present",
                },
                "judge_milestone_bundle": {
                    "path": "target/competition-out/summary/judge-milestone-bundle.json",
                    "status": "self",
                },
                "supported_subset": {
                    "claims": [
                        "harness planner/worker/verifier/repairer/reporter contract",
                        "FlashDB before/after safety exhibit",
                    ],
                },
                "known_non_goals": [
                    "whole-project FlashDB migration",
                    "production-ready translation quality",
                ],
                "claim_boundary": {
                    "semantic_gate": False,
                    "publication_manifest_is_semantic_gate": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
            },
            "opencode_runtime": {
                "enabled_entrypoint_count": 1,
                "all_contracts_executed": True,
                "chat_output_is_evidence_false": True,
                "semantic_gate_false": True,
            },
            "opencode_evidence_policy": {
                "enabled": True,
                "boundary_fields_explicit": True,
                "chat_output_is_evidence_false": True,
                "semantic_gate_false": True,
                "semantic_gate": False,
            },
            "known_gaps": [
                {
                    "gap_id": "local_simulation_not_competition_exact",
                    "status": "open",
                    "boundary": "local simulation only",
                }
            ],
            "must_not_claim": [
                "accepted_evidence_is_not_translator_generated_coverage",
                "whole_project_flashdb_translation",
            ],
            "reproduction_commands": {
                "run_judge_entrypoints": "python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out/summary/judge-entrypoints-run-report.json",
                "validate_judge_entrypoints": "python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --require-local-artifacts",
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "command": "python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
                    }
                ],
            },
        }


if __name__ == "__main__":
    unittest.main()
