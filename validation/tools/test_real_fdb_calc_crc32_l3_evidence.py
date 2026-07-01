import json
import hashlib
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class RealFdbCalcCrc32L3EvidenceTests(unittest.TestCase):
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
            "207e1af49b7ee5cb26d31e66a0d8334bb3566b85bc727844be3c52fdbcf577cc",
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
        self.assertIn(provenance["compile_execution"]["toolchain_adapter"], {"not_executed", "wsl", "native"})
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
