import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.validate_test_translation_coverage import validate_test_translation_coverage


class ValidateTestTranslationCoverageTests(unittest.TestCase):
    def test_rejects_missing_main_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coverage-test-") as tmp:
            path = self._write_evidence(Path(tmp), main_paths=[])

            with self.assertRaises(SystemExit) as raised:
                validate_test_translation_coverage([path])

            self.assertIn("main_paths", str(raised.exception))

    def test_rejects_missing_negative_cases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coverage-test-") as tmp:
            path = self._write_evidence(Path(tmp), negative_cases=[])

            with self.assertRaises(SystemExit) as raised:
                validate_test_translation_coverage([path])

            self.assertIn("negative_cases", str(raised.exception))

    def test_rejects_missing_evidence_link_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coverage-test-") as tmp:
            path = self._write_evidence(
                Path(tmp),
                evidence_links={
                    "negative_diff": {
                        "path": "missing-negative-diff.json",
                        "status": "passed",
                    }
                },
            )

            with self.assertRaises(SystemExit) as raised:
                validate_test_translation_coverage([path])

            self.assertIn("missing evidence link", str(raised.exception))

    def test_rejects_negative_diff_link_without_path_when_used_as_negative_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coverage-test-") as tmp:
            path = self._write_evidence(
                Path(tmp),
                include_negative_mapping=False,
                evidence_links={"negative_diff": {"status": "passed"}},
            )

            with self.assertRaises(SystemExit) as raised:
                validate_test_translation_coverage([path])

            self.assertIn("negative_diff", str(raised.exception))
            self.assertIn("path", str(raised.exception))

    def test_accepts_recorded_test_translation_coverage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coverage-test-") as tmp:
            path = self._write_evidence(Path(tmp))

            report = validate_test_translation_coverage([path])

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["evidence_count"], 1)
            self.assertEqual(report["evidence"][0]["slice_id"], "demo")

    def _write_evidence(
        self,
        root: Path,
        *,
        main_paths: list[str] | None = None,
        negative_cases: list[str] | None = None,
        evidence_links: dict | None = None,
        include_negative_mapping: bool = True,
    ) -> Path:
        mappings = [
            {
                "source": "fixture",
                "rust_test": "test_main",
                "coverage_kind": "main_path",
                "status": "mapped",
            }
        ]
        if include_negative_mapping:
            mappings.append(
                {
                    "source": "negative",
                    "rust_test": "test_negative",
                    "coverage_kind": "negative_case",
                    "status": "mapped",
                }
            )
        payload = {
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "demo",
            "status": "recorded",
            "coverage": {
                "main_paths": ["main"] if main_paths is None else main_paths,
                "error_paths": [],
                "negative_cases": ["negative"] if negative_cases is None else negative_cases,
            },
            "translation_mappings": mappings,
            "evidence_links": evidence_links or {},
        }
        path = root / "demo-test-translation.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
