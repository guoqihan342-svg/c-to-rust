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
        ledger = report["capability_delta_ledger"]
        self.assertGreaterEqual(ledger["ledger_count"], 1)
        self.assertGreaterEqual(
            ledger["by_construct"]["external_direct_callee_context"]["refused"],
            1,
        )
        self.assertGreaterEqual(
            ledger["by_construct"]["typed_ir_candidate_generated"]["candidate"],
            1,
        )
        self.assertGreaterEqual(
            ledger["by_construct"]["typed_ir_zero_token_deterministic"]["candidate"],
            1,
        )
        self.assertGreaterEqual(ledger["blocked_callee_count"], 1)
        self.assertEqual(ledger["translator_generated_semantic_pass_count"], 28)
        self.assertEqual(ledger["semantic_pass_count"], 28)
        self.assertGreaterEqual(ledger["accepted_evidence_semantic_pass_count"], 1)
        self.assertIn("not semantic acceptance evidence", ledger["claim_boundary"])

    def test_current_repository_matrix_binds_traversed_len_to_exact_named_slice(self) -> None:
        matrix = json.loads(
            Path("validation/translator-coverage-matrix.json").read_text(encoding="utf-8")
        )
        capability = next(
            item for item in matrix["capabilities"] if item["id"] == "record-field-subset"
        )
        evidence_paths = {
            evidence["path"]
            for dimension in capability["dimension_status"].values()
            for evidence in dimension.get("evidence", [])
        }

        self.assertIn(
            "crates/c2r-translator/tests/bounded_translation/chunk_25.rs",
            evidence_paths,
        )
        self.assertIn(
            "validation/evidence/flashdb/l3-real-fdb-kv-iterate-traversed-len-c-oracle.json",
            evidence_paths,
        )
        self.assertIn(
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-iterate-traversed-len/l3-real-fdb-kv-iterate-traversed-len-final-verification.json",
            evidence_paths,
        )
        scope_note = capability["dimension_status"]["c_rust_diff"]["scope_note"]
        self.assertIn("exact line-1892", scope_note)
        self.assertIn("do not generalize", scope_note)

    def test_current_repository_matrix_binds_kv_reset_to_exact_named_slice(self) -> None:
        matrix = json.loads(
            Path("validation/translator-coverage-matrix.json").read_text(encoding="utf-8")
        )
        capability = next(
            item for item in matrix["capabilities"] if item["id"] == "record-field-subset"
        )
        evidence_paths = {
            evidence["path"]
            for dimension in capability["dimension_status"].values()
            for evidence in dimension.get("evidence", [])
        }

        required_paths = {
            "crates/c2r-translator/tests/bounded_translation/chunk_26.rs",
            "crates/c2r-translator/tests/bounded_translation/chunk_26_split_parts/part_01.rs",
            "crates/c2r-translator/tests/bounded_translation/chunk_26_split_parts/part_02.rs",
            "crates/c2r-translator/tests/bounded_translation/chunk_26_split_parts/part_03.rs",
            "validation/evidence/flashdb/l3-real-fdb-kv-iterate-kv-reset-c-oracle.json",
            "validation/evidence/flashdb/l3-real-fdb-kv-iterate-kv-reset-rust-report.json",
            "validation/evidence/flashdb/l3-real-fdb-kv-iterate-kv-reset-diff.json",
            "validation/evidence/flashdb/l3-real-fdb-kv-iterate-kv-reset-negative-diff.json",
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-iterate-kv-reset/l3-real-fdb-kv-iterate-kv-reset-generated-draft-unsafe-ledger.json",
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-iterate-kv-reset/l3-real-fdb-kv-iterate-kv-reset-route-decision.json",
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-iterate-kv-reset/l3-real-fdb-kv-iterate-kv-reset-validation-profile.json",
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-iterate-kv-reset/l3-real-fdb-kv-iterate-kv-reset-capability-delta.json",
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-iterate-kv-reset/l3-real-fdb-kv-iterate-kv-reset-final-verification.json",
        }
        self.assertTrue(required_paths.issubset(evidence_paths))
        scope_note = capability["dimension_status"]["c_rust_diff"]["scope_note"]
        self.assertIn("exact named slice bound to fdb_kvdb.c:1891", scope_note)
        self.assertIn("fdb_kvdb.c:1871 is not automatically covered", scope_note)
        self.assertIn("complete fdb_kv_iterate function", scope_note)
        self.assertIn("FlashDB project", scope_note)

    def test_capability_delta_ledger_keeps_refusal_separate_from_semantic_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="translator-coverage-matrix-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/tests/bounded_translation.rs", "// tests\n")
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-capability-delta.json",
                {
                    "schema_version": 1,
                    "status": "recorded",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "route_level": "L4",
                    "route_status": "refused",
                    "boundary": "unit test capability ledger; not semantic acceptance evidence",
                    "capability_delta": [
                        {
                            "delta_id": "cap-refused-external-callee",
                            "kind": "refusal_classification",
                            "construct_id": "external_direct_callee_context",
                            "real_c_slice": "refused",
                            "generated_candidate_status": "refused",
                            "semantic_pass": False,
                            "blocked_callees": ["helper"],
                            "evidence_refs": [
                                "validation/evidence/demo/auto-translation/refused/l3-refused-auto-translation-plan.json"
                            ],
                            "negative_coverage": [{"kind": "regression"}],
                        }
                    ],
                    "governance_delta": [
                        {
                            "delta_id": "gov-refused-external-callee",
                            "construct_id": "external_direct_callee_context",
                            "kind": "evidence_contract",
                            "evidence_refs": [
                                "validation/evidence/demo/auto-translation/refused/l3-refused-auto-translation-plan.json"
                            ],
                            "bound_to": "unit test",
                        }
                    ],
                    "verification_commands": ["python -B -m unittest demo"],
                },
            )
            path = root / "matrix.json"
            path.write_text(
                json.dumps(self._minimal_matrix([self._capability(capability_id="scalar-add")])),
                encoding="utf-8",
            )

            report = translator_coverage_matrix.build_report(root, matrix_path=path)

            ledger = report["capability_delta_ledger"]
            self.assertEqual(ledger["ledger_count"], 1)
            self.assertEqual(ledger["delta_count"], 1)
            self.assertEqual(ledger["semantic_pass_count"], 0)
            self.assertEqual(ledger["generated_candidate_status"]["refused"], 1)
            self.assertEqual(ledger["route_levels"]["L4"], 1)
            self.assertEqual(ledger["route_statuses"]["refused"], 1)
            self.assertEqual(ledger["blocked_callee_count"], 1)
            self.assertEqual(ledger["by_construct"]["external_direct_callee_context"]["refused"], 1)

    def test_capability_delta_ledger_counts_accepted_evidence_semantic_pass_without_translation_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="translator-coverage-matrix-") as tmp:
            root = Path(tmp)
            self._write(root / "crates/c2r-translator/tests/bounded_translation.rs", "// tests\n")
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-capability-delta.json",
                self._refused_capability_ledger(),
            )
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-final-verification.json",
                {
                    "schema_version": 1,
                    "status": "passed",
                    "semantic_pass": True,
                    "accepted_evidence_authoritative": True,
                    "generated_draft_semantic_pass": False,
                },
            )
            path = root / "matrix.json"
            path.write_text(
                json.dumps(self._minimal_matrix([self._capability(capability_id="scalar-add")])),
                encoding="utf-8",
            )

            report = translator_coverage_matrix.build_report(root, matrix_path=path)

            ledger_report = report["capability_delta_ledger"]
            self.assertEqual(ledger_report["translator_generated_semantic_pass_count"], 0)
            self.assertEqual(ledger_report["semantic_pass_count"], 0)
            self.assertEqual(ledger_report["accepted_evidence_semantic_pass_count"], 1)
            self.assertEqual(ledger_report["generated_candidate_status"]["refused"], 1)

    def test_rejects_invalid_capability_delta_ledger_contract(self) -> None:
        cases = [
            (
                "missing-boundary",
                {"boundary": None},
                "boundary",
            ),
            (
                "empty-capability-delta",
                {"capability_delta": []},
                "capability_delta is empty",
            ),
            (
                "missing-slice-id",
                {"slice_id": None},
                "slice_id",
            ),
            (
                "missing-governance-binding",
                {"governance_delta": [{"construct_id": None}]},
                "governance_delta item must reference",
            ),
            (
                "missing-governance-evidence",
                {"governance_delta": [{"evidence_refs": []}]},
                "governance_delta evidence_refs",
            ),
            (
                "missing-negative-coverage",
                {"capability_delta": [{"negative_coverage": []}]},
                "negative_coverage",
            ),
            (
                "missing-evidence-refs",
                {"capability_delta": [{"evidence_refs": []}]},
                "evidence_refs",
            ),
            (
                "l4-refused-semantic-pass",
                {"capability_delta": [{"semantic_pass": True}]},
                "L4/refused semantic_pass=true requires generated_draft_acceptance.status=passed",
            ),
        ]
        for name, override, expected in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory(prefix="translator-coverage-matrix-") as tmp:
                    root = Path(tmp)
                    self._write(root / "crates/c2r-translator/tests/bounded_translation.rs", "// tests\n")
                    ledger = self._refused_capability_ledger()
                    for key, value in override.items():
                        if key == "capability_delta" and value and isinstance(value[0], dict):
                            ledger["capability_delta"][0].update(value[0])
                        elif key == "governance_delta" and value and isinstance(value[0], dict):
                            ledger["governance_delta"][0].update(value[0])
                        else:
                            ledger[key] = value
                    self._write_json(
                        root / "validation/evidence/demo/auto-translation/refused/l3-refused-capability-delta.json",
                        ledger,
                    )
                    path = root / "matrix.json"
                    path.write_text(
                        json.dumps(self._minimal_matrix([self._capability(capability_id="scalar-add")])),
                        encoding="utf-8",
                    )

                    with self.assertRaises(SystemExit) as raised:
                        translator_coverage_matrix.build_report(root, matrix_path=path)

                    self.assertIn(expected, str(raised.exception))

    def test_current_repository_matrix_links_existing_evidence_and_tests(self) -> None:
        report = translator_coverage_matrix.build_report(Path("."))

        for capability in report["capabilities"]:
            self.assertTrue(capability["positive_cases"], capability["id"])
            self.assertTrue(capability["negative_cases"], capability["id"])
            self.assertFalse(capability["missing_links"], capability["id"])

    def test_legacy_fallback_telemetry_is_provenance_coverage_not_semantic_claim(self) -> None:
        report = translator_coverage_matrix.build_report(Path("."))
        legacy = next(
            capability
            for capability in report["capabilities"]
            if capability["id"] == "legacy-fallback-telemetry"
        )

        self.assertEqual(legacy["status"], "covered")
        self.assertEqual(legacy["dimension_status"]["runtime_emitted_rust"]["status"], "not_applicable")
        self.assertEqual(legacy["dimension_status"]["c_rust_diff"]["status"], "not_applicable")
        self.assertEqual(legacy["dimension_status"]["legacy_fallback"]["status"], "covered")
        self.assertEqual(legacy["dimension_status"]["route_evidence"]["status"], "covered")

    def test_core_ci_runs_translator_coverage_matrix_gate(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("python3 -B -m unittest validation.tools.test_translator_coverage_matrix", text)
        self.assertIn("python3 -B validation/tools/translator_coverage_matrix.py", text)

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

    def _refused_capability_ledger(self) -> dict:
        return {
            "schema_version": 1,
            "status": "recorded",
            "target_id": "demo",
            "slice_id": "refused",
            "route_level": "L4",
            "route_status": "refused",
            "boundary": "unit test capability ledger; not semantic acceptance evidence",
            "capability_delta": [
                {
                    "delta_id": "cap-refused-external-callee",
                    "kind": "refusal_classification",
                    "construct_id": "external_direct_callee_context",
                    "real_c_slice": "refused",
                    "generated_candidate_status": "refused",
                    "semantic_pass": False,
                    "blocked_callees": ["helper"],
                    "evidence_refs": [
                        "validation/evidence/demo/auto-translation/refused/l3-refused-auto-translation-plan.json"
                    ],
                    "negative_coverage": [{"kind": "regression"}],
                }
            ],
            "governance_delta": [
                {
                    "delta_id": "gov-refused-external-callee",
                    "construct_id": "external_direct_callee_context",
                    "kind": "evidence_contract",
                    "evidence_refs": [
                        "validation/evidence/demo/auto-translation/refused/l3-refused-auto-translation-plan.json"
                    ],
                    "bound_to": "unit test",
                }
            ],
            "verification_commands": ["python -B -m unittest demo"],
        }

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_json(self, path: Path, payload: dict) -> None:
        self._write(path, json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
