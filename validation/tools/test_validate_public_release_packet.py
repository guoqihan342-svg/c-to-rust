import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import milestone_release_notes
from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools import validate_public_release_packet as packet_validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def write_text_artifact(path: Path, text: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "path": repo_relative(path),
        "status": "present",
        "sha256": judge_validator.sha256_file(path),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def valid_packet(root: Path) -> dict:
    run_report = write_text_artifact(root / "summary" / "judge-entrypoints-run-report.json", "{}\n")
    readiness = write_text_artifact(root / "summary" / "judge-entrypoints-readiness.json", "{}\n")
    bundle_path = root / "summary" / "judge-milestone-bundle.json"
    bundle_self_ref = {
        "path": repo_relative(bundle_path),
        "status": "self",
    }
    publication_manifest = {
        "publication_scope": "all-entrypoints",
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "judge_milestone_bundle": bundle_self_ref,
        "supported_subset": {
            "claims": ["public packet validator fixture"],
        },
        "known_non_goals": ["semantic translation gate"],
        "claim_boundary": {
            "semantic_gate": False,
            "publication_manifest_is_semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }
    known_gaps = [{"gap_id": "competition-exact-not-run", "status": "open"}]
    bundle_must_not_claim = ["bundle_status_is_not_project_level_translation_success"]
    packet_must_not_claim = [*bundle_must_not_claim, "public_release_packet_is_not_semantic_gate"]
    reproduction_commands = {
        "run_judge_entrypoints": "python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out/summary/judge-entrypoints-run-report.json"
    }
    bundle_payload = {
        "schema_version": 1,
        "report_kind": "judge-milestone-bundle",
        "status": "passed",
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "bundle_is_semantic_gate": False,
        },
        "publishability": {
            "status": "internal_preview",
        },
        "proof_classes": {
            "rollup": {
                "trusted_proof_classes": ["local-simulation"],
                "has_competition_exact": False,
            }
        },
        "harness_architecture_summary": {
            "rollup": {
                "source_count": 1,
                "worker_count": 1,
                "repair_round_cap": 5,
                "roles": ["planner", "worker", "verifier", "repairer", "reporter"],
            }
        },
        "workflow_metrics": {
            "rollup": {
                "repair_activity": {
                    "repair_history_unit_count": 1,
                    "auto_recovered_unit_count": 1,
                }
            }
        },
        "quantitative_evaluation": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "project_slice_counts": {
                "workflow_units_total": 1,
                "workflow_units_converged": 1,
                "before_after_bound_unit_count": 1,
            },
            "outcome_counts": {
                "accepted_evidence_semantic_pass_count": 1,
                "translator_generated_semantic_pass_count": 0,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "blocked_repair_count": 0,
                "human_interventions": 0,
            },
            "baseline_comparison": {},
            "claim_boundary": {
                "semantic_gate": False,
                "scorecard_is_semantic_gate": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
        },
        "opencode_runtime": {
            "chat_output_is_evidence_false": True,
            "semantic_gate_false": True,
        },
        "opencode_evidence_policy": {
            "boundary_fields_explicit": True,
            "chat_output_is_evidence_false": True,
            "semantic_gate_false": True,
            "semantic_gate": False,
        },
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "publication_manifest": publication_manifest,
        "known_gaps": known_gaps,
        "must_not_claim": bundle_must_not_claim,
        "reproduction_commands": reproduction_commands,
    }
    write_json(bundle_path, bundle_payload)
    notes = write_text_artifact(
        root / "summary" / "milestone-release-notes.md",
        milestone_release_notes.build_release_notes(bundle_payload),
    )
    bundle = {
        "path": repo_relative(bundle_path),
        "status": "present",
        "sha256": judge_validator.sha256_file(bundle_path),
    }
    return {
        "schema_version": 1,
        "report_kind": "public-release-packet",
        "status": "passed",
        "summary": {
            "entrypoint_count": 4,
            "publication_scope": "all-entrypoints",
            "readiness": {"status": "passed"},
            "proof_class_rollup": {"local-simulation": 4},
        },
        "claim_boundary": {
            "semantic_gate": False,
            "packet_is_semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "boundary": "packet index only",
        },
        "judge_entrypoints_run_report": run_report,
        "readiness_report": readiness,
        "judge_milestone_bundle": bundle,
        "milestone_release_notes": notes,
        "competition_config_archive": {
            "status": "present",
            "claim_boundary": {
                "semantic_gate": False,
                "archive_is_semantic_gate": False,
            },
        },
        "publication_manifest": publication_manifest,
        "known_gaps": known_gaps,
        "must_not_claim": packet_must_not_claim,
        "reproduction_commands": reproduction_commands,
    }


class PublicReleasePacketValidatorTests(unittest.TestCase):
    def test_validate_packet_binds_hashes_and_claim_boundary(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        write_json(packet_path, valid_packet(temp_dir))

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["packet"]["path"], repo_relative(packet_path))
        self.assertEqual(result["artifact_refs"]["checked_count"], 4)
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertEqual(result["claim_boundary"]["translation_coverage_numerator"], 0)

    def test_validate_packet_rejects_artifact_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["judge_milestone_bundle"]["sha256"] = "0" * 64
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("sha256 mismatch" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_rejects_publication_manifest_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-bundle-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publication_manifest"] = {
            **packet["publication_manifest"],
            "publication_scope": "focused-run",
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publication_manifest must match judge_milestone_bundle.publication_manifest" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_run_report_ref_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-run-ref-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        alternate_report = write_text_artifact(
            temp_dir / "summary" / "alternate-judge-entrypoints-run-report.json",
            '{"status":"passed","source":"alternate"}\n',
        )
        packet["judge_entrypoints_run_report"] = alternate_report
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_entrypoints_run_report must match judge_milestone_bundle.judge_entrypoints_run_report" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_release_notes_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-notes-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        stale_notes = write_text_artifact(
            temp_dir / "summary" / "stale-milestone-release-notes.md",
            "# stale notes\n\nThese notes were not rendered from the bound milestone bundle.\n",
        )
        packet["milestone_release_notes"] = stale_notes
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("milestone_release_notes must match judge_milestone_bundle rendered release notes" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_semantic_gate_overclaim(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-overclaim-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["claim_boundary"]["semantic_gate"] = True
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("claim_boundary.semantic_gate must be false" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_local_absolute_path_leak(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-path-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["reproduction_commands"]["run_judge_entrypoints"] = "C:\\Python314\\python.exe -m validation.tools.run_judge_entrypoints"
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("forbidden local absolute path" in error for error in result["errors"]), result["errors"])

    def test_core_validation_ci_runs_public_packet_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("validation.tools.test_validate_public_release_packet", workflow)


if __name__ == "__main__":
    unittest.main()
