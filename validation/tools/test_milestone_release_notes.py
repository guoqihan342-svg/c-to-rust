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
        self.assertIn("Readiness: `internal_preview`", notes)
        self.assertIn("## Readiness Blockers", notes)
        self.assertIn("- none", notes)
        self.assertIn("## Publication Readiness Contract", notes)
        self.assertIn("| Status | internal_preview |", notes)
        self.assertIn("| Required agent tool | opencode |", notes)
        self.assertIn("| Required agent | c2rust-migrator |", notes)
        self.assertIn("| Required model | GLM-5.1 |", notes)
        self.assertIn("| OpenCode GLM preflight status | passed |", notes)
        self.assertIn("| OpenCode GLM publishable | true |", notes)
        self.assertIn("| Competition-exact publishable | false |", notes)
        self.assertIn("| External milestone claim ready | false |", notes)
        self.assertIn("| Semantic gate | false |", notes)
        self.assertIn("| Translation coverage numerator | 0 |", notes)
        self.assertIn("## Competition Host Readiness", notes)
        self.assertIn("| Status | blocked |", notes)
        self.assertIn("| Required agent | c2rust-migrator |", notes)
        self.assertIn("| Required model | GLM-5.1 |", notes)
        self.assertIn("| Required proof class | competition-exact |", notes)
        self.assertIn("| Actual highest proof class | local-simulation |", notes)
        self.assertIn("| Competition exact host verified | false |", notes)
        self.assertIn("| Missing requirements | all_entrypoints_competition_exact, competition_exact_host_verified, external_milestone_claim_ready |", notes)
        self.assertIn("Repository commit: `1234567890abcdef1234567890abcdef12345678`", notes)
        self.assertIn("Proof class rollup: `local-simulation`", notes)
        self.assertIn("Translation coverage numerator: `0`", notes)
        self.assertIn("Semantic gate: `false`", notes)
        self.assertIn("## OpenCode GLM Preflight", notes)
        self.assertIn("| Required model | GLM-5.1 |", notes)
        self.assertIn("| OpenCode command | opencode |", notes)
        self.assertIn("| OpenCode agent | c2rust-migrator |", notes)
        self.assertIn("| OpenCode variant | max |", notes)
        self.assertIn("| Model listed by `opencode models` | true |", notes)
        self.assertIn("| Preflight contract | executed |", notes)
        self.assertIn("| OpenCode run launched | true |", notes)
        self.assertIn("| Translation coverage numerator | 0 |", notes)
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
        self.assertIn("## Competition Config Archive", notes)
        self.assertIn("| Config files | 21 |", notes)
        self.assertIn("| External refs | 1 |", notes)
        self.assertNotIn(".codex/skills/c2rust-migration/SKILL.md", notes)
        self.assertIn(
            "| opencode-agent-runbook | .opencode/agents/c2rust-migrator.md | bbbbbbbbbbbb | present |",
            notes,
        )
        self.assertIn("## Release Tag Readiness", notes)
        self.assertIn("| Status | not_tagged |", notes)
        self.assertIn("| Tag name | none |", notes)
        self.assertIn("| Tag target commit | none |", notes)
        self.assertIn("| Tag matches repo commit | false |", notes)
        self.assertIn("| Remote release notes | not_published |", notes)
        self.assertIn("| External review record | not_recorded |", notes)
        self.assertIn("| External milestone claim ready | false |", notes)
        self.assertIn("| Semantic gate | false |", notes)
        self.assertIn("| Translation coverage numerator | 0 |", notes)
        self.assertIn("## Self-Heal Classification", notes)
        self.assertIn("| Blocked repairs | 1 |", notes)
        self.assertIn("| Human action required | 1 |", notes)
        self.assertIn("| Blocked reasons | `external_callee`: 1 |", notes)
        self.assertIn("| IR feature gaps | `external_direct_callee_context`: 1 |", notes)
        self.assertIn("| Routes | `typed_ir`: 1 |", notes)
        self.assertIn("| Next actions | `bind_external_callee_semantics`: 1 |", notes)
        self.assertIn("| Sample next-action limit | 5 |", notes)
        self.assertIn("| Semantic gate | false |", notes)
        self.assertIn("## Evidence Cost and Retention", notes)
        self.assertIn("| Source count | 1 |", notes)
        self.assertIn("| Artifact count | 3 |", notes)
        self.assertIn("| Total bytes | 120 |", notes)
        self.assertIn("| Pipeline count | 2 |", notes)
        self.assertIn("| Runtime observations | 2 |", notes)
        self.assertIn("| Runtime total ms | 45 |", notes)
        self.assertIn("| Runtime max ms | 40 |", notes)
        self.assertIn("| Retention classes | `ci_smoke`: 1 files / 40 bytes, `committed_release`: 2 files / 80 bytes |", notes)
        self.assertIn("| All sources passed | true |", notes)
        self.assertIn("| Policy compliant | true |", notes)
        self.assertIn("| Policy tiers | `ci`: 1 |", notes)
        self.assertIn("| Policy failed gates | none |", notes)
        self.assertIn("| Portability issues | 0 |", notes)
        self.assertIn("| Diagnostic host metadata | 0 |", notes)
        self.assertIn("## Progress Delta Ledger", notes)
        self.assertIn("| Capability delta count | 2 |", notes)
        self.assertIn("| Governance delta count | 3 |", notes)
        self.assertIn("| Workflow units converged | 4 / 5 |", notes)
        self.assertIn("| Observed repair units | 1 |", notes)
        self.assertIn("| Auto-recovered units | 1 |", notes)
        self.assertIn("| Rollback evidence count | 2 |", notes)
        self.assertIn("| Before/after repair sources | 1 |", notes)
        self.assertIn("| Repair delta sources | 1 |", notes)
        self.assertIn("| raw C2Rust | not_verified_here | no | 0 |", notes)
        self.assertIn("python3 -B -m validation.tools.run_judge_entrypoints", notes)
        self.assertNotIn("python -B -m validation.tools.run_judge_entrypoints", notes)
        self.assertIn("accepted_evidence_is_not_translator_generated_coverage", notes)
        self.assertIn("whole-project FlashDB migration", notes)

    def test_release_notes_render_blockers_for_blocked_bundle(self) -> None:
        payload = self._bundle()
        blocker = "validated_artifact_sha256_mismatch:before_after_judge_demo:judge_evidence_index"
        payload["status"] = "blocked"
        payload["blockers"] = [blocker]
        payload["publishability"]["status"] = "blocked"
        payload["publishability"]["scope"] = "blocked"
        payload["publishability"]["publication_scope"] = "blocked"
        payload["publishability"]["external_milestone_claim_ready"] = False
        payload["publishability"]["external_milestone"] = False
        payload["publishability"]["blocker_count"] = 1
        payload["publishability"]["blockers"] = [blocker]

        notes = milestone_release_notes.build_release_notes(payload)

        self.assertIn("Status: `blocked`", notes)
        self.assertIn("## Readiness Blockers", notes)
        self.assertIn(f"- `{blocker}`", notes)

    def test_release_notes_publish_bundle_rebuild_command(self) -> None:
        notes = milestone_release_notes.build_release_notes(self._bundle())

        self.assertIn("python3 -B -m validation.tools.judge_milestone_bundle", notes)
        self.assertNotIn("python -B -m validation.tools.judge_milestone_bundle", notes)
        self.assertIn("- `build_bundle`:", notes)

    def test_release_notes_reject_external_ready_when_host_readiness_blocked(self) -> None:
        payload = self._bundle()
        payload["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("competition_host_readiness.status must be ready", str(raised.exception))

    def test_release_notes_allow_competition_exact_preflight_when_host_ready(self) -> None:
        payload = self._bundle()
        payload["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )
        payload["competition_host_readiness"].update(
            {
                "status": "ready",
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "external_milestone_claim_ready": True,
                "missing_requirements": [],
                "blocker_count": 0,
            }
        )
        payload["opencode_runtime"]["preflight_proof_summary"]["proof_class"] = "competition-exact"

        notes = milestone_release_notes.build_release_notes(payload)

        self.assertIn("Readiness: `external_release_ready`", notes)
        self.assertIn("| Required proof class | competition-exact |", notes)

    def test_release_notes_reject_competition_exact_preflight_when_host_blocked(self) -> None:
        payload = self._bundle()
        payload["opencode_runtime"]["preflight_proof_summary"]["proof_class"] = "competition-exact"

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("proof_class must not claim competition-exact without host attestation", str(raised.exception))

    def test_release_notes_reject_passed_bundle_with_blockers(self) -> None:
        payload = self._bundle()
        payload["blockers"] = ["validated_artifact_sha256_mismatch:before_after_judge_demo:judge_evidence_index"]

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("blockers must be empty when status is passed", str(raised.exception))

    def test_release_notes_reject_unknown_publishability_status(self) -> None:
        payload = self._bundle()
        payload["publishability"]["status"] = "unknown"

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("publishability.status", str(raised.exception))

    def test_release_notes_reject_missing_release_tag_readiness(self) -> None:
        payload = self._bundle()
        payload["publication_manifest"].pop("release_tag_readiness", None)

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("release_tag_readiness", str(raised.exception))

    def test_release_notes_reject_missing_competition_host_readiness(self) -> None:
        payload = self._bundle()
        payload.pop("competition_host_readiness", None)

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("competition_host_readiness", str(raised.exception))

    def test_release_notes_reject_missing_evidence_cost_retention(self) -> None:
        payload = self._bundle()
        payload.pop("evidence_cost_retention")

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("evidence_cost_retention must be an object", str(raised.exception))

    def test_release_notes_reject_invalid_evidence_cost_retention_kind(self) -> None:
        payload = self._bundle()
        payload["evidence_cost_retention"]["report_kind"] = "evidence-cost-summary"

        with self.assertRaises(SystemExit) as raised:
            milestone_release_notes.build_release_notes(payload)

        self.assertIn("evidence_cost_retention.report_kind", str(raised.exception))

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
                "quantitative_evaluation.self_heal_classification.semantic_gate",
                lambda payload: payload["quantitative_evaluation"]["self_heal_classification"].__setitem__(
                    "semantic_gate",
                    True,
                ),
            ),
            (
                "quantitative_evaluation.self_heal_classification.translation_coverage_numerator",
                lambda payload: payload["quantitative_evaluation"]["self_heal_classification"].__setitem__(
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
                "opencode_runtime.preflight_proof_summary.status",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"].__setitem__("status", "absent"),
            ),
            (
                "opencode_runtime.preflight_proof_summary.opencode_command",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"].__setitem__(
                    "opencode_command",
                    "codex",
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.opencode_agent",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"].__setitem__(
                    "opencode_agent",
                    "general",
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.opencode_model",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"].__setitem__(
                    "opencode_model",
                    "gpt-5.1",
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.opencode_variant",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"].__setitem__(
                    "opencode_variant",
                    "small",
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.model_listed",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"].__setitem__(
                    "model_listed",
                    False,
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.preflight_report.path",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"]["preflight_report"].pop(
                    "path",
                    None,
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.preflight_report.sha256",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"]["preflight_report"].__setitem__(
                    "sha256",
                    "not-a-sha",
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.model_probe_logs.stdout.path",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"]["model_probe_logs"]["stdout"].pop(
                    "path",
                    None,
                ),
            ),
            (
                "opencode_runtime.preflight_proof_summary.semantic_gate",
                lambda payload: payload["opencode_runtime"]["preflight_proof_summary"].__setitem__(
                    "semantic_gate",
                    True,
                ),
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

        self.assertIn("python3 -B -m unittest validation.tools.test_milestone_release_notes", text)

    def _bundle(self) -> dict:
        return {
            "schema_version": 1,
            "report_kind": "judge-milestone-bundle",
            "status": "passed",
            "blockers": [],
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
                "publication_scope": "internal_preview_full",
                "external_milestone_claim_ready": False,
                "external_milestone": False,
                "blocker_count": 0,
                "blockers": [],
                "all_entrypoints_run_publishable": True,
                "focused_run": False,
                "competition_exact_publishable": False,
                "required_agent_tool": "opencode",
                "required_agent": "c2rust-migrator",
                "required_model": "GLM-5.1",
                "opencode_glm51_required": True,
                "opencode_glm51_preflight_status": "passed",
                "opencode_glm51_publishable": True,
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
                "target_artifacts_regenerable": True,
            },
            "competition_host_readiness": {
                "report_kind": "competition-host-readiness",
                "status": "blocked",
                "required_agent_tool": "opencode",
                "required_agent": "c2rust-migrator",
                "required_model": "GLM-5.1",
                "required_variant": "max",
                "required_proof_class": "competition-exact",
                "actual_highest_proof_class": "local-simulation",
                "all_entrypoints_run_publishable": True,
                "all_entrypoints_competition_exact": False,
                "competition_exact_host_verified": False,
                "opencode_glm51_preflight_status": "passed",
                "opencode_glm51_publishable": True,
                "external_milestone_claim_ready": False,
                "missing_requirements": [
                    "all_entrypoints_competition_exact",
                    "competition_exact_host_verified",
                    "external_milestone_claim_ready",
                ],
                "blocker_count": 3,
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
                "boundary": "Competition host readiness is an H9 launch contract, not semantic acceptance.",
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
            "evidence_cost_retention": {
                "report_kind": "evidence-cost-retention-rollup",
                "sources": [
                    {
                        "source": "fixture-evidence-governance",
                        "status": "passed",
                        "artifact_count": 3,
                        "total_bytes": 120,
                        "pipeline_count": 2,
                        "runtime_observation_count": 2,
                        "runtime_total_duration_ms": 45,
                        "runtime_max_duration_ms": 40,
                        "retention_classes": {
                            "committed_release": {"file_count": 2, "total_bytes": 80},
                            "ci_smoke": {"file_count": 1, "total_bytes": 40},
                        },
                        "policy_compliance": {
                            "policy_tier": "ci",
                            "status": "passed",
                            "failed_gates": [],
                        },
                        "claim_anchor_issue_count": 0,
                        "profile_hash_issue_count": 0,
                        "diagnostic_host_metadata_count": 0,
                    }
                ],
                "rollup": {
                    "source_count": 1,
                    "artifact_count": 3,
                    "total_bytes": 120,
                    "pipeline_count": 2,
                    "runtime_ms": {
                        "observation_count": 2,
                        "total": 45,
                        "max": 40,
                    },
                    "retention_classes": {
                        "committed_release": {"file_count": 2, "total_bytes": 80},
                        "ci_smoke": {"file_count": 1, "total_bytes": 40},
                    },
                    "all_sources_passed": True,
                    "policy_compliance": {
                        "all_sources_policy_passed": True,
                        "tier_counts": {"ci": 1},
                        "failed_gate_counts": {},
                    },
                    "portability_issue_count": 0,
                    "diagnostic_host_metadata_count": 0,
                },
                "boundary": "Evidence cost and retention metrics are review-only and not semantic acceptance.",
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
                "self_heal_classification": {
                    "report_kind": "self-heal-classification",
                    "source": "blocked_repairs_rollup",
                    "status": "observed",
                    "blocked_repair_count": 1,
                    "human_action_required_count": 1,
                    "status_counts": {"observed": 1},
                    "blocked_reason_counts": {"external_callee": 1},
                    "ir_feature_gap_kinds": {"external_direct_callee_context": 1},
                    "forbidden_change_counts": {"missing_l1_evidence": 1},
                    "source_span_kind_counts": {"c_source": 1},
                    "route_counts": {"typed_ir": 1},
                    "next_action_counts": {"bind_external_callee_semantics": 1},
                    "smallest_next_test_kind_counts": {"callee_contract_replay": 1},
                    "next_action_count": 1,
                    "sample_next_action_limit": 5,
                    "sample_next_actions": [
                        {
                            "route": "typed_ir",
                            "status": "blocked",
                            "next_action": "bind_external_callee_semantics",
                        }
                    ],
                    "semantic_gate": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                    "boundary": "Self-heal classification is judge-facing repair context only.",
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
            "progress_delta_ledger": {
                "report_kind": "progress-delta-ledger",
                "semantic_gate": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "capability_delta": {
                    "ledger_count": 2,
                    "delta_count": 2,
                    "translator_generated_semantic_pass_count": 0,
                    "accepted_evidence_semantic_pass_count": 2,
                },
                "governance_delta": {
                    "delta_count": 3,
                    "verification_command_count": 4,
                    "route_decision_artifacts": 2,
                    "slice_gate_contexts": 2,
                },
                "workflow_delta": {
                    "workflow_source_count": 2,
                    "workflow_units_total": 5,
                    "workflow_units_converged": 4,
                    "repair_history_unit_count": 1,
                    "observed_repair_unit_count": 1,
                    "auto_recovered_unit_count": 1,
                    "rollback_evidence_count": 2,
                    "before_after_repair_source_count": 1,
                    "repair_delta_source_count": 1,
                    "human_interventions": 0,
                },
                "boundary": "Progress deltas are review metrics only.",
            },
            "publication_manifest": {
                "report_kind": "publication-manifest",
                "publication_scope": "internal_preview_full",
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
                    "root": "config/competition-env",
                    "file_count": 21,
                    "bundle_manifest": {
                        "path": "config/competition-env/bundle-manifest.json",
                        "sha256": "1" * 64,
                        "status": "present",
                    },
                    "external_ref_count": 1,
                    "external_refs": {
                        ".opencode/agents/c2rust-migrator.md": {
                            "path": ".opencode/agents/c2rust-migrator.md",
                            "sha256": "b" * 64,
                            "status": "present",
                            "role": "opencode-agent-runbook",
                        },
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
                "release_tag_readiness": {
                    "report_kind": "release-tag-readiness",
                    "status": "not_tagged",
                    "tag_name": None,
                    "tag_target_commit": None,
                    "repo_commit": "1234567890abcdef1234567890abcdef12345678",
                    "tag_matches_repo_commit": False,
                    "remote_release_notes_status": "not_published",
                    "external_review_record_status": "not_recorded",
                    "external_milestone_claim_ready": False,
                    "semantic_gate": False,
                    "translation_coverage_numerator": 0,
                    "boundary": "Tag and release records are publication readiness evidence only.",
                },
                "claim_boundary": {
                    "semantic_gate": False,
                    "publication_manifest_is_semantic_gate": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
            },
            "opencode_runtime": {
                "report_kind": "opencode-runtime-rollup",
                "enabled_entrypoint_count": 1,
                "worker_count": 2,
                "all_contracts_executed": True,
                "chat_output_is_evidence_false": True,
                "semantic_gate_false": True,
                "preflight_proof_summary": {
                    "status": "passed",
                    "required_when_opencode_runtime_enabled": True,
                    "preflight_report": {
                        "path": "target/competition-out/opencode/harness/opencode-preflight-report.json",
                        "sha256": "4" * 64,
                        "status": "present",
                    },
                    "run_id": "flashdb-opencode-explicit-workers",
                    "opencode_command": "opencode",
                    "opencode_agent": "c2rust-migrator",
                    "opencode_model": "GLM-5.1",
                    "opencode_variant": "max",
                    "required_model": "GLM-5.1",
                    "model_availability_status": "available",
                    "model_listed": True,
                    "model_probe_argv": ["opencode", "models"],
                    "process_returncode": 0,
                    "model_probe_logs": {
                        "stdout": {
                            "path": "target/competition-out/opencode/logs/opencode-models.stdout.log",
                            "sha256": "5" * 64,
                            "status": "present",
                        },
                        "stderr": {
                            "path": "target/competition-out/opencode/logs/opencode-models.stderr.log",
                            "sha256": "6" * 64,
                            "status": "present",
                        },
                    },
                    "contract_status": "executed",
                    "marker_exists": True,
                    "opencode_run_launched": True,
                    "opencode_run_argv_bound": True,
                    "proof_class": "local-simulation",
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                    "translation_coverage_numerator": 0,
                    "boundary": "OpenCode preflight is runtime proof only.",
                },
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
                "run_judge_entrypoints": "python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out/summary/judge-entrypoints-run-report.json",
                "build_bundle": "python3 -B -m validation.tools.judge_milestone_bundle --config config/competition-env/judge-entrypoints/flashdb-harness.json --run-report target/competition-out/summary/judge-entrypoints-run-report.json --output target/competition-out/summary/judge-milestone-bundle.json",
                "validate_judge_entrypoints": "python3 -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --require-local-artifacts",
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "command": "python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
                    }
                ],
            },
        }


if __name__ == "__main__":
    unittest.main()
