import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import unsafe_budget


class UnsafeBudgetTests(unittest.TestCase):
    def test_core_ci_runs_repo_unsafe_budget_gate(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet", text)
        self.assertIn("python3 -B -m unittest validation.tools.test_auto_migrate", text)
        self.assertIn("python3 -B -m unittest validation.tools.test_unsafe_budget", text)
        self.assertIn("python3 -B validation/tools/unsafe_budget.py --max-ratio 0.10", text)
        self.assertIn('"validation/unsafe-budget-ledger.json"', text)
        self.assertIn("git diff --check", text)

    def test_current_repository_unsafe_budget_passes_with_default_ledger(self) -> None:
        report = unsafe_budget.build_report(Path("."), ledger_path=Path("validation/unsafe-budget-ledger.json"))

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["ledger"]["status"], "loaded")
        self.assertEqual(report["first_party_non_test_unsafe_count"], 4)
        self.assertEqual(report["registered_unsafe_count"], 4)
        self.assertEqual(report["unregistered_unsafe_count"], 0)
        self.assertEqual(report["categories"]["raw_pointer"], 4)
        self.assertGreaterEqual(report["scanned_files"], 3)
        self.assertEqual(
            [scope["path"] for scope in report["scopes"]],
            [
                "crates/c2r-translator/src",
                "flashDB_rust/src",
                "validation/l2_slices/src",
            ],
        )

    def test_current_repository_ledger_declares_review_contract(self) -> None:
        ledger = json.loads(Path("validation/unsafe-budget-ledger.json").read_text(encoding="utf-8"))

        contract = ledger["repo_level_policy"]
        required_fields = set(contract["required_fields"])
        for field in {
            "file",
            "span",
            "category",
            "reason",
            "replacement_or_alternative",
            "validation_evidence",
            "source_evidence",
            "review_status",
        }:
            self.assertIn(field, required_fields)
        self.assertEqual(contract["compatibility"]["registered_findings_identity"], ["path", "category"])
        self.assertEqual(contract["compatibility"]["file_field_alias"], "path")
        self.assertIn("extern_c", contract["category_contract"]["allowed_values"])
        self.assertIn("repr_c", contract["category_contract"]["allowed_values"])
        self.assertIn("raw_pointer", contract["category_contract"]["allowed_values"])
        self.assertIn("needs_triage", contract["review_status_contract"]["allowed_values"])
        self.assertIn("validated", contract["review_status_contract"]["terminal_review_states"])

    def test_scans_configured_first_party_non_test_scopes_and_ignores_tests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unsafe-budget-test-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/src/lib.rs", "pub fn safe() {}\n")
            self._write(root / "crates/c2r-translator/tests/ignored.rs", "unsafe { ignored(); }\n")
            self._write(root / "flashDB_rust/src/ffi.rs", "#[repr(C)]\npub struct Header { pub value: u32 }\n")
            self._write(
                root / "validation/l2_slices/src/lib.rs",
                'pub unsafe fn bridge() {}\nextern "C" { fn c_call(); }\n',
            )
            self._write(root / "validation/l2_slices/tests/ignored.rs", "pub unsafe fn ignored() {}\n")

            ledger_path = root / "validation/unsafe-budget-ledger.json"
            self._write_json(
                ledger_path,
                {
                    "schema_version": 1,
                    "registered_findings": [
                        {
                            "path": "flashDB_rust/src/ffi.rs",
                            "category": "repr_c",
                            "reason": "test registration",
                            "validation_gate": "unit-test",
                        },
                        {
                            "path": "validation/l2_slices/src/lib.rs",
                            "category": "unsafe_function",
                            "reason": "test registration",
                            "validation_gate": "unit-test",
                        },
                        {
                            "path": "validation/l2_slices/src/lib.rs",
                            "category": "extern_c",
                            "reason": "test registration",
                            "validation_gate": "unit-test",
                        },
                    ],
                },
            )

            report = unsafe_budget.build_report(root, ledger_path=ledger_path, max_ratio=1.0)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(
                [scope["path"] for scope in report["scopes"]],
                [
                    "crates/c2r-translator/src",
                    "flashDB_rust/src",
                    "validation/l2_slices/src",
                ],
            )
            self.assertEqual(report["scanned_files"], 3)
            self.assertEqual(report["first_party_non_test_unsafe_count"], 3)
            self.assertEqual(report["registered_unsafe_count"], 3)
            self.assertEqual(report["unregistered_unsafe_count"], 0)
            self.assertEqual(report["categories"]["repr_c"], 1)
            self.assertEqual(report["categories"]["unsafe_function"], 1)
            self.assertEqual(report["categories"]["extern_c"], 1)
            self.assertFalse(any("tests/ignored.rs" in item["path"] for item in report["findings"]))

    def test_fails_when_findings_are_unregistered_or_over_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unsafe-budget-test-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/src/lib.rs", "pub fn safe() {}\n")
            self._write(root / "flashDB_rust/src/lib.rs", "pub fn call() { unsafe { do_work(); } }\n")
            self._write(root / "validation/l2_slices/src/lib.rs", "pub fn safe() {}\n")

            unregistered = unsafe_budget.build_report(root, max_ratio=1.0)
            self.assertEqual(unregistered["status"], "failed")
            self.assertEqual(unregistered["unregistered_unsafe_count"], 1)
            self.assertIn("unregistered_unsafe", unregistered["failed_gates"])

            ledger_path = root / "validation/unsafe-budget-ledger.json"
            self._write_json(
                ledger_path,
                {
                    "schema_version": 1,
                    "registered_findings": [
                        {
                            "path": "flashDB_rust/src/lib.rs",
                            "category": "unsafe_block",
                            "reason": "test registration",
                            "validation_gate": "unit-test",
                        }
                    ],
                },
            )

            over_budget = unsafe_budget.build_report(root, ledger_path=ledger_path, max_ratio=0.0)
            self.assertEqual(over_budget["status"], "failed")
            self.assertEqual(over_budget["registered_unsafe_count"], 1)
            self.assertIn("unsafe_ratio", over_budget["failed_gates"])

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_json(self, path: Path, payload: dict) -> None:
        self._write(path, json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
