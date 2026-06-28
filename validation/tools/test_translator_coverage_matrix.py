import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import translator_coverage_matrix


class TranslatorCoverageMatrixTests(unittest.TestCase):
    def test_rejects_capability_without_negative_fail_closed_reason(self) -> None:
        with tempfile.TemporaryDirectory(prefix="translator-coverage-matrix-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/tests/bounded_translation.rs", "// tests\n")
            matrix = self._minimal_matrix(
                [
                    self._capability(
                        capability_id="scalar-add",
                        negative_cases=[
                            {
                                "name": "typed_ir_rejects_bad_scalar_add",
                                "path": "crates/c2r-translator/tests/bounded_translation.rs",
                            }
                        ],
                    )
                ]
            )
            path = root / "matrix.json"
            path.write_text(json.dumps(matrix), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                translator_coverage_matrix.build_report(root, matrix_path=path)

            self.assertIn("fail_closed_reason", str(raised.exception))

    def test_rejects_missing_required_dimension(self) -> None:
        with tempfile.TemporaryDirectory(prefix="translator-coverage-matrix-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/tests/bounded_translation.rs", "// tests\n")
            capability = self._capability(capability_id="scalar-add")
            capability["dimension_status"].pop("route_evidence")
            path = root / "matrix.json"
            path.write_text(json.dumps(self._minimal_matrix([capability])), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                translator_coverage_matrix.build_report(root, matrix_path=path)

            self.assertIn("dimensions", str(raised.exception))

    def test_rejects_covered_dimension_evidence_without_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="translator-coverage-matrix-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/tests/bounded_translation.rs", "// tests\n")
            capability = self._capability(capability_id="scalar-add")
            capability["dimension_status"]["handwritten_ir"] = {
                "status": "covered",
                "evidence": [{"name": "unlinked"}],
            }
            path = root / "matrix.json"
            path.write_text(json.dumps(self._minimal_matrix([capability])), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                translator_coverage_matrix.build_report(root, matrix_path=path)

            self.assertIn("evidence item path is required", str(raised.exception))

    def test_rejects_missing_link_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="translator-coverage-matrix-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/tests/bounded_translation.rs", "// tests\n")
            capability = self._capability(capability_id="scalar-add")
            capability["positive_cases"][0]["path"] = "missing.rs"
            path = root / "matrix.json"
            path.write_text(json.dumps(self._minimal_matrix([capability])), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                translator_coverage_matrix.build_report(root, matrix_path=path)

            self.assertIn("missing matrix evidence links", str(raised.exception))

    def test_current_repository_matrix_records_required_dimensions(self) -> None:
        report = translator_coverage_matrix.build_report(Path("."))

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["matrix"]["path"], "validation/translator-coverage-matrix.json")
        self.assertGreaterEqual(report["capability_count"], 5)
        self.assertGreaterEqual(report["dimensions"]["clang_fixture_replay"]["covered"], 2)
        self.assertGreaterEqual(report["dimensions"]["handwritten_ir"]["covered"], 1)
        self.assertGreaterEqual(report["dimensions"]["runtime_emitted_rust"]["covered"], 1)
        self.assertGreaterEqual(report["dimensions"]["c_rust_diff"]["covered"], 1)
        self.assertGreaterEqual(report["dimensions"]["legacy_fallback"]["covered"], 1)
        self.assertGreaterEqual(report["dimensions"]["route_evidence"]["covered"], 1)
        self.assertIn("translator coverage matrix", report["claim_boundary"])

    def test_current_repository_matrix_links_existing_evidence_and_tests(self) -> None:
        report = translator_coverage_matrix.build_report(Path("."))

        for capability in report["capabilities"]:
            self.assertTrue(capability["positive_cases"], capability["id"])
            self.assertTrue(capability["negative_cases"], capability["id"])
            self.assertFalse(capability["missing_links"], capability["id"])

    def test_core_ci_runs_translator_coverage_matrix_gate(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("python -m unittest validation.tools.test_translator_coverage_matrix", text)
        self.assertIn("python validation/tools/translator_coverage_matrix.py", text)

    def _minimal_matrix(self, capabilities: list[dict]) -> dict:
        return {
            "schema_version": 1,
            "status": "recorded",
            "claim_boundary": "unit test matrix",
            "required_dimensions": translator_coverage_matrix.REQUIRED_DIMENSIONS,
            "capabilities": capabilities,
        }

    def _capability(
        self,
        *,
        capability_id: str,
        negative_cases: list[dict] | None = None,
    ) -> dict:
        return {
            "id": capability_id,
            "status": "covered",
            "ir_constructs": ["IrExpr::Binary"],
            "dimension_status": {
                dimension: {"status": "not_applicable", "reason": "unit test"}
                for dimension in translator_coverage_matrix.REQUIRED_DIMENSIONS
            },
            "positive_cases": [
                {
                    "name": "typed_ir_emits_scalar_add",
                    "path": "crates/c2r-translator/tests/bounded_translation.rs",
                }
            ],
            "negative_cases": negative_cases
            if negative_cases is not None
            else [
                {
                    "name": "typed_ir_rejects_bad_scalar_add",
                    "path": "crates/c2r-translator/tests/bounded_translation.rs",
                    "fail_closed_reason": "unit-test fail-closed reason",
                }
            ],
        }

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
