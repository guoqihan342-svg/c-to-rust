from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.record_field_scalar_add_test_support import (
    build_field_scalar_add_spec,
    load_auto_migrate_module,
    renamed_rust_draft,
)


class AutoMigrateRecordFieldScalarAddReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_auto_migrate_module()
        self.spec, _ = build_field_scalar_add_spec()
        self.spec["fixture_hash"] = "synthetic-renamed-field-scalar-fixture"

    def test_renamed_by_value_field_scalar_oracle_and_rust_replay(self) -> None:
        fixture_binding = self.module.oracle_fixture_binding(self.spec)
        contract = self._parse(self.spec)
        self.assertEqual(contract["state_output"]["field_path"], ["slot", "total"])
        self.assertEqual(contract["state_update"]["record_field"]["field_path"], ["amount"])
        self.assertEqual(contract["state_update"]["scalar"]["fixture_field"], "increment_value")
        oracle_source = self.module.oracle_fixture_execution_source(self.spec, fixture_binding)
        self.assertIn("actual_ordinary_sample.amount + actual_ordinary_increment", oracle_source["statements"])
        self.assertNotRegex(oracle_source["statements"], r"sizeof|alignof|layout")

        with tempfile.TemporaryDirectory(prefix="auto-migrate-field-scalar-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "field-scalar.json"
            spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
            oracle = self.module.generate_oracle_harness_draft(self.spec, evidence_dir, False)
            self.assertEqual(oracle["compile_execution"]["status"], "compile_succeeded_not_oracle")
            self.assertEqual(
                oracle["compile_execution"]["harness_execution"]["status"],
                "exited_zero_not_oracle",
            )
            prefix = "l3-assign-field-scalar-sum"
            (evidence_dir / f"{prefix}-rust-draft.rs").write_text(
                renamed_rust_draft(), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"translation_summary": {
                    "translation_rule_ids": ["clang-lowered-typed-ir"], "call_expressions": []
                }}),
                encoding="utf-8",
            )
            replay = self.module.generate_rust_replay_test_draft(self.spec, evidence_dir, spec_path)
            rust_check, _ = self.module.run_rust_check(evidence_dir, False, self.spec)
            self.assertEqual(rust_check["status"], "passed")
            replay = self.module.run_generated_rust_replay(
                self.spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")
            self.assertEqual(replay["fixture_state_model"]["operation"], "wrapping_add")
            self.assertEqual(
                replay["fixture_state_model"]["scalar"]["fixture_field"], "increment_value"
            )
            self.assertNotIn("fixture_external_stub", replay)

    def test_entry_path_scalar_pointer_and_noalias_drift_fail_closed(self) -> None:
        mutable_source = copy.deepcopy(self.spec)
        source = mutable_source["replay_contract"]["entry_arguments"][1]
        source["pass_mode"] = "mutable_ref"
        source["c_type"] = "struct Sample *"
        with self.assertRaisesRegex(ValueError, "one mutable inout record"):
            self._parse(mutable_source)

        shallow = copy.deepcopy(self.spec)
        shallow["replay_contract"]["state_output"]["field_path"] = ["label"]
        with self.assertRaisesRegex(ValueError, "nested u32"):
            self._parse(shallow)

        nested_source = copy.deepcopy(self.spec)
        nested_source["replay_contract"]["state_update"]["record_field"]["field_path"] = ["nested", "amount"]
        with self.assertRaisesRegex(ValueError, "one direct initialized u32 field"):
            self._parse(nested_source)

        scalar = copy.deepcopy(self.spec)
        scalar["replay_contract"]["state_update"]["scalar"]["fixture_field"] = "other"
        with self.assertRaisesRegex(ValueError, "scalar binding drifted"):
            self._parse(scalar)

        pointer = copy.deepcopy(self.spec)
        pointer["c_boundary"]["pointer_contract"]["aliasing_proven"] = False
        with self.assertRaisesRegex(ValueError, "proven pointer metadata"):
            self._parse(pointer)

        noalias = copy.deepcopy(self.spec)
        noalias["replay_contract"]["noalias_required"] = [["harbor", "sample"]]
        noalias["c_boundary"]["pointer_contract"]["noalias_required"] = [["harbor", "sample"]]
        with self.assertRaisesRegex(ValueError, "empty noalias pairs"):
            self._parse(noalias)

    def test_expected_and_degenerate_mutation_fixtures_fail_closed(self) -> None:
        drifted = copy.deepcopy(self.spec)
        drifted["fixture_contract"]["cases"][0]["expected_outputs"]["updated_total"] += 1
        with self.assertRaisesRegex(ValueError, "expected outputs drifted"):
            self._parse(drifted)

        degenerate = copy.deepcopy(self.spec)
        case = degenerate["fixture_contract"]["cases"][0]
        case["inputs"]["increment_value"] = 0
        case["expected_outputs"]["updated_total"] = case["inputs"]["sample_amount"]
        with self.assertRaisesRegex(ValueError, "does not observe add-to-sub mutation"):
            self._parse(degenerate)

    def _parse(self, spec: dict[str, object]) -> dict[str, object]:
        return self.module.record_u32_field_scalar_wrapping_add_state_replay_contract(
            spec, self.module.oracle_fixture_binding(spec)
        )


if __name__ == "__main__":
    unittest.main()
