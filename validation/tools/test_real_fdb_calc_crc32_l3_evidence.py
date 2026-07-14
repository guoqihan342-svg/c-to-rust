import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from validation.tools import auto_migrate
from validation.tools import validate_competition_run_summary as summary_validator


REPO_ROOT = Path(__file__).resolve().parents[2]


class RealFdbCalcCrc32L3EvidenceTests(unittest.TestCase):
    def test_c2rust_safety_candidate_is_hash_bound_to_real_baseline_manifest(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-calc-crc32"
        )
        manifest_path = evidence_dir / "l3-real-fdb-calc-crc32-c2rust-baseline-manifest.json"
        manifest = self._load(manifest_path)

        candidate = auto_migrate.c2rust_crc32_safety_candidate_from_manifest(
            manifest,
            manifest_path=manifest_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(candidate["candidate_source"], "c2rust-function-level-baseline")
        self.assertFalse(candidate["semantic_pass"])
        self.assertEqual(candidate["baseline_manifest"]["sha256"], auto_migrate.sha256(manifest_path))
        self.assertEqual(candidate["baseline_output"], manifest["output"] | {"verified_sha256": True})
        self.assertEqual(candidate["unsafe_reduction"]["baseline_total_unsafe"], 2)
        self.assertEqual(candidate["unsafe_reduction"]["current_total_unsafe"], 0)
        self.assertEqual(candidate["unsafe_reduction"]["reduced_by"], 2)
        self.assertEqual(
            candidate["repair_round"]["input_baseline"]["sha256"],
            manifest["output"]["sha256"],
        )
        self.assertEqual(
            candidate["repair_round"]["transformed_baseline_sha256"],
            candidate["transformed"]["rust_sha256"],
        )

    def test_c2rust_safety_candidate_rejects_baseline_output_sha_drift(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-calc-crc32"
        )
        manifest_path = evidence_dir / "l3-real-fdb-calc-crc32-c2rust-baseline-manifest.json"
        manifest = self._load(manifest_path)
        manifest["output"] = {**manifest["output"], "sha256": "0" * 64}

        with self.assertRaisesRegex(ValueError, "baseline output sha256 mismatch"):
            auto_migrate.c2rust_crc32_safety_candidate_from_manifest(
                manifest,
                manifest_path=manifest_path,
                repo_root=REPO_ROOT,
            )

    def test_c2rust_safety_evidence_runs_independent_replay_and_keeps_coverage_zero(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-calc-crc32"
        )
        manifest_path = evidence_dir / "l3-real-fdb-calc-crc32-c2rust-baseline-manifest.json"
        manifest = self._load(manifest_path)

        with tempfile.TemporaryDirectory(prefix="crc32-c2rust-safety-evidence-", dir=REPO_ROOT / "target") as tmp:
            report = auto_migrate.emit_c2rust_crc32_safety_evidence(
                manifest,
                manifest_path=manifest_path,
                repo_root=REPO_ROOT,
                out_dir=Path(tmp),
            )

            self.assertEqual(report["status"], "passed")
            self.assertTrue(report["semantic_pass"])
            self.assertFalse(report["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(report["claim_boundary"]["translation_coverage_numerator"], 0)
            self.assertEqual(report["replay"]["case_count"], 2)
            self.assertEqual(
                [case["return_code"] for case in report["replay"]["cases"]],
                [0, 3421780262],
            )
            self.assertEqual(report["schema_diff"]["status"], "passed")
            self.assertTrue(report["negative_diff"]["mutation_detected"])
            self.assertEqual(report["unsafe_reduction"]["status"], "measured")
            self.assertEqual(report["unsafe_reduction"]["reduced_by"], 2)
            for artifact in report["artifacts"].values():
                artifact_path = REPO_ROOT / artifact["path"]
                self.assertTrue(artifact_path.is_file())
                self.assertEqual(artifact["sha256"], auto_migrate.sha256(artifact_path))
            verification_path = REPO_ROOT / report["verification"]["path"]
            self.assertEqual(report["verification"]["sha256"], auto_migrate.sha256(verification_path))

    def test_summary_validator_deep_checks_c2rust_safety_verification_body(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-calc-crc32"
        )
        before_after = self._load(evidence_dir / "l3-real-fdb-calc-crc32-translation-before-after.json")
        summary_path = REPO_ROOT / "target" / "c2rust-safety-validator" / "summary" / "summary.json"
        summary_validator.validate_translation_before_after_unit(
            before_after,
            unit={},
            index=0,
            summary_path=summary_path,
            repo_root=REPO_ROOT,
        )

        with tempfile.TemporaryDirectory(prefix="crc32-c2rust-safety-tamper-", dir=REPO_ROOT / "target") as tmp:
            tampered_path = Path(tmp) / "c2rust-safety-verification.json"
            tampered = self._load(REPO_ROOT / before_after["oracle_evidence"]["path"])
            tampered["schema_diff"] = {**tampered["schema_diff"], "status": "failed"}
            tampered_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            tampered_before_after = json.loads(json.dumps(before_after))
            tampered_ref = {
                "path": tampered_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": auto_migrate.sha256(tampered_path),
            }
            tampered_before_after["oracle_evidence"] = tampered_ref
            with self.assertRaisesRegex(SystemExit, "schema_diff must pass"):
                summary_validator.validate_translation_before_after_unit(
                    tampered_before_after,
                    unit={},
                    index=0,
                    summary_path=summary_path,
                    repo_root=REPO_ROOT,
                )

            tampered = self._load(REPO_ROOT / before_after["oracle_evidence"]["path"])
            tampered["c_oracle_execution"]["execution"]["returncode"] = 1
            tampered_path.write_text(
                json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            tampered_before_after["oracle_evidence"] = {
                "path": tampered_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": auto_migrate.sha256(tampered_path),
            }
            with self.assertRaisesRegex(SystemExit, "successful marker-complete run"):
                summary_validator.validate_translation_before_after_unit(
                    tampered_before_after,
                    unit={},
                    index=0,
                    summary_path=summary_path,
                    repo_root=REPO_ROOT,
                )

    def test_emit_reports_records_real_fdb_calc_crc32_replay_and_diff_gates(self) -> None:
        result = subprocess.run(
            [
                "cargo",
                "run",
                "--manifest-path",
                "validation/l2_slices/Cargo.toml",
                "--bin",
                "emit_reports",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

        evidence_dir = REPO_ROOT / "validation" / "evidence" / "flashdb"
        slice_spec = self._load(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json")
        prefix = "l3-real-fdb-calc-crc32"
        c_oracle = self._load(evidence_dir / f"{prefix}-c-oracle.json")
        rust_report = self._load(evidence_dir / f"{prefix}-rust-report.json")
        diff = self._load(evidence_dir / f"{prefix}-diff.json")
        negative_diff = self._load(evidence_dir / f"{prefix}-negative-diff.json")

        self.assertEqual(c_oracle["target_id"], "flashdb")
        self.assertEqual(c_oracle["slice_id"], "real-fdb-calc-crc32")
        self.assertEqual(c_oracle["status"], "passed")
        self.assertTrue(c_oracle["semantic_pass"])
        self.assertEqual(c_oracle["toolchain_status"], "C_ORACLE_GENERATED")
        self.assertEqual(c_oracle["source_commit"], slice_spec["source_commit"])
        self.assertEqual(rust_report["source_commit"], slice_spec["source_commit"])
        self.assertEqual(diff["source_commit"], slice_spec["source_commit"])
        self.assertEqual(negative_diff["source_commit"], slice_spec["source_commit"])
        self.assertEqual(c_oracle["case_count"], 2)
        self.assertEqual(
            c_oracle["generator"],
            "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_calc_crc32",
        )
        self.assertEqual(
            c_oracle["command"],
            "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
        )
        self.assertEqual(
            c_oracle["source_boundary"]["files"],
            ["src/fdb_utils.c"],
        )
        self.assertEqual(
            rust_report["source_boundary"]["files"],
            ["src/fdb_utils.c"],
        )
        self.assertEqual(
            [case["return_code"] for case in c_oracle["cases"]],
            [0, 3421780262],
        )
        provenance = c_oracle["provenance"]
        self.assertEqual(
            provenance["fixture_sha256"],
            self._sha256(REPO_ROOT / c_oracle["fixture"]),
        )
        self.assertEqual(
            provenance["source_file_hashes"]["src/fdb_utils.c"],
            slice_spec["source"]["source_file_hashes"]["src/fdb_utils.c"],
        )
        self.assertEqual(
            provenance["source_span_sha256"],
            "523e88f41d20405f6aed4fbd62e1ddc2c7127473864d9ca80d2aca4874549007",
        )
        self.assertEqual(provenance["global_dependencies"][0]["name"], "crc32_table")
        self.assertEqual(
            provenance["global_dependencies"][0]["sha256"],
            "df869743cd92f9edf5d4f0f058ffd6b73e67af6dbcfc070baef8fc4a6919ca41",
        )
        self.assertEqual(
            provenance["harness_draft_ref"]["path"],
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c-oracle-harness-draft.c",
        )
        self.assertEqual(
            provenance["harness_draft_ref"]["sha256"],
            self._sha256(REPO_ROOT / provenance["harness_draft_ref"]["path"]),
        )
        self.assertIn(
            provenance["compile_execution"]["toolchain_adapter"],
            {"not_executed", "local", "wsl", "native"},
        )
        self.assertIn(
            provenance["compile_execution"]["status"],
            {
                "skipped_by_flag",
                "compile_succeeded_not_oracle",
                "compile_failed_not_oracle",
                "compiler_missing_not_oracle",
            },
        )
        self.assertFalse(provenance["compile_execution"]["semantic_pass"])
        self.assertNotEqual(provenance["compile_execution"]["toolchain_status_after_attempt"], "C_ORACLE_GENERATED")
        self.assertEqual(
            provenance["evidence_refs"]["c_oracle_status"],
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c-oracle-status.json",
        )
        self.assertNotIn("c_oracle_sha256", provenance)

        self.assertEqual(rust_report["target_id"], "flashdb")
        self.assertEqual(rust_report["slice_id"], "real-fdb-calc-crc32")
        self.assertEqual(rust_report["status"], "passed")
        self.assertEqual(rust_report["case_count"], 2)
        self.assertEqual(
            rust_report["rust_module_path"],
            "validation/l2_slices/src/fdb_calc_crc32.rs",
        )
        self.assertEqual(
            [case["return_code"] for case in rust_report["cases"]],
            [0, 3421780262],
        )

        self.assertEqual(diff["status"], "passed")
        self.assertEqual(diff["case_count"], 2)
        self.assertEqual(diff["compared_fields"], ["return_code"])
        self.assertIsNone(diff["first_mismatch"])

        self.assertEqual(negative_diff["status"], "expected_failed")
        self.assertTrue(negative_diff["expected_failure"])
        self.assertTrue(negative_diff["mutation_detected"])
        self.assertEqual(negative_diff["first_mismatch"]["field"], "return_code")

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
