import json
import tempfile
import unittest
from pathlib import Path

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
    bundle = write_text_artifact(root / "summary" / "judge-milestone-bundle.json", "{}\n")
    notes = write_text_artifact(root / "summary" / "milestone-release-notes.md", "# notes\n")
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
        "publication_manifest": {
            "publication_scope": "all-entrypoints",
            "claim_boundary": {
                "semantic_gate": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
        },
        "known_gaps": [],
        "must_not_claim": ["public_release_packet_is_not_semantic_gate"],
        "reproduction_commands": {
            "run_judge_entrypoints": "python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out/summary/judge-entrypoints-run-report.json"
        },
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
