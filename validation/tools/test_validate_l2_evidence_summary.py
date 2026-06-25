import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.validate_l2_evidence_summary import validate_l2_evidence


class ValidateL2EvidenceSummaryTests(unittest.TestCase):
    def test_rejects_accepted_slice_without_negative_diff(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(root, "sqlite-varint", include_negative=False)

            with self.assertRaises(SystemExit) as raised:
                validate_l2_evidence(root)

            self.assertIn("negative diff", str(raised.exception))
            self.assertIn("sqlite-varint", str(raised.exception))

    def test_rejects_accepted_slice_without_test_translation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(root, "sqlite-varint", include_test_translation=False)

            with self.assertRaises(SystemExit) as raised:
                validate_l2_evidence(root)

            self.assertIn("test translation", str(raised.exception))
            self.assertIn("sqlite-varint", str(raised.exception))

    def test_rejects_failed_summary_negative_diff_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(root, "sqlite-varint", negative_status="failed")

            with self.assertRaises(SystemExit) as raised:
                validate_l2_evidence(root)

            self.assertIn("negative_diff_check", str(raised.exception))

    def test_validates_l2_passed_slice_even_when_l3_status_is_pending(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(root, "sqlite-varint", l3_status="pending")

            report = validate_l2_evidence(root)

            self.assertEqual(report["slice_count"], 1)
            self.assertEqual(report["slices"][0]["slice_id"], "sqlite-varint")

    def test_rejects_failed_unsafe_scan_file_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(root, "sqlite-varint")
            self._write_json(root / "l2-slices" / "unsafe-scan.json", {"status": "failed", "unsafe_count": 0})

            with self.assertRaises(SystemExit) as raised:
                validate_l2_evidence(root)

            self.assertIn("unsafe scan", str(raised.exception))

    def test_rejects_negative_diff_report_path_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(root, "sqlite-varint", negative_report_path="wrong/path.json")

            with self.assertRaises(SystemExit) as raised:
                validate_l2_evidence(root)

            self.assertIn("negative diff report path", str(raised.exception))

    def test_accepts_complete_slice_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(root, "sqlite-varint")

            report = validate_l2_evidence(root)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["slice_count"], 1)
            self.assertEqual(report["slices"][0]["slice_id"], "sqlite-varint")
            self.assertEqual(report["slices"][0]["negative_diff"], "passed")

    def test_accepts_sum_i32_buffer_l3_demo_location(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l2-evidence-test-") as tmp:
            root = Path(tmp)
            self._write_complete_slice(
                root,
                "demo-sum-i32-buffer",
                negative_report_path="validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json",
            )
            demo = root / "demo"
            demo.mkdir(parents=True)
            self._write_json(demo / "l3-sum-i32-buffer-rust-report.json", {"status": "passed"})
            self._write_json(
                demo / "l3-sum-i32-buffer-diff.json",
                {"status": "passed", "first_mismatch": None},
            )
            self._write_json(
                demo / "l3-sum-i32-buffer-negative-diff.json",
                {"status": "passed", "detected": True, "first_mismatch": {"field": "sum"}},
            )
            self._write_json(
                demo / "l3-sum-i32-buffer-test-translation.json",
                {
                    "status": "recorded",
                    "coverage": {
                        "main_paths": ["empty input", "multi input"],
                        "error_paths": [],
                        "negative_cases": ["sum mutation rejected"],
                    },
                    "translation_mappings": [
                        {
                            "source": "oracle fixture",
                            "rust_test": "cargo test",
                            "coverage_kind": "main_path",
                            "status": "mapped",
                        },
                        {
                            "source": "negative diff",
                            "rust_test": "emit_reports",
                            "coverage_kind": "negative_case",
                            "status": "mapped",
                        },
                    ],
                    "evidence_links": {
                        "negative_diff": {
                            "path": "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json",
                            "status": "passed",
                        }
                    },
                },
            )

            report = validate_l2_evidence(root)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["slice_count"], 1)
            self.assertEqual(report["slices"][0]["slice_id"], "demo-sum-i32-buffer")
            self.assertEqual(report["slices"][0]["level"], "L3")

    def _write_complete_slice(
        self,
        root: Path,
        slice_id: str,
        *,
        include_negative: bool = True,
        include_test_translation: bool = True,
        negative_status: str = "passed",
        l3_status: str = "passed",
        negative_report_path: str | None = None,
    ) -> None:
        l2 = root / "l2-slices"
        l2.mkdir(parents=True)
        negative_report_path = negative_report_path or f"validation/evidence/l2-slices/{slice_id}-negative-diff.json"
        self._write_json(
            l2 / "l2-l3-summary.json",
            {
                "schema_version": 1,
                "status": "passed",
                "diff_check": {
                    "status": "passed",
                    "slices": [
                        {
                            "slice_id": slice_id,
                            "case_count": 3,
                            "l2_status": "passed",
                            "l3_status": l3_status,
                        }
                    ],
                },
                "safety_check": {
                    "status": "passed",
                    "unsafe_count": 0,
                },
                "unsafe_ledger_check": {
                    "audit_status": "passed",
                    "first_party_non_test_unsafe_count": 0,
                },
                "negative_diff_check": {
                    "status": negative_status,
                    "reports": [
                        {
                            "slice_id": slice_id,
                            "status": "passed",
                            "report": negative_report_path,
                        }
                    ]
                    if include_negative
                    else [],
                },
            },
        )
        self._write_json(l2 / f"{slice_id}-rust-report.json", {"status": "passed"})
        self._write_json(l2 / f"{slice_id}-diff.json", {"status": "passed", "first_mismatch": None})
        if include_negative:
            self._write_json(
                l2 / f"{slice_id}-negative-diff.json",
                {"status": "passed", "detected": True, "first_mismatch": {"field": "value"}},
            )
        self._write_json(l2 / "unsafe-scan.json", {"status": "passed", "unsafe_count": 0})
        self._write_json(
            l2 / "unsafe-ledger.json",
            {"audit_status": "passed", "first_party_non_test_unsafe_count": 0},
        )
        if include_test_translation:
            self._write_json(
                l2 / f"{slice_id}-test-translation.json",
                {
                    "status": "recorded",
                    "coverage": {
                        "main_paths": ["main"],
                        "error_paths": [],
                        "negative_cases": ["mutation rejected"],
                    },
                    "translation_mappings": [
                        {
                            "source": "oracle fixture",
                            "rust_test": "cargo test",
                            "coverage_kind": "main_path",
                            "status": "mapped",
                        },
                        {
                            "source": "negative diff",
                            "rust_test": "emit_reports",
                            "coverage_kind": "negative_case",
                            "status": "mapped",
                        },
                    ],
                    "evidence_links": {
                        "negative_diff": {
                            "path": f"validation/evidence/l2-slices/{slice_id}-negative-diff.json",
                            "status": "passed",
                        }
                    },
                },
            )

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
