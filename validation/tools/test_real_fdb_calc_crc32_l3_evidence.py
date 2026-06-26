import json
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
        prefix = "l3-real-fdb-calc-crc32"
        rust_report = self._load(evidence_dir / f"{prefix}-rust-report.json")
        diff = self._load(evidence_dir / f"{prefix}-diff.json")
        negative_diff = self._load(evidence_dir / f"{prefix}-negative-diff.json")

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


if __name__ == "__main__":
    unittest.main()
