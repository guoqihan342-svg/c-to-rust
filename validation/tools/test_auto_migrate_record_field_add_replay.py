from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.record_field_add_test_support import (
    build_field_add_spec,
    load_auto_migrate_module,
    renamed_rust_draft,
)


class AutoMigrateRecordFieldAddReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_auto_migrate_module()
        self.spec, _ = build_field_add_spec()
        self.spec["fixture_hash"] = "synthetic-renamed-field-add-fixture"

    def test_fully_renamed_wrapping_add_oracle_and_rust_replay(self) -> None:
        fixture_binding = self.module.oracle_fixture_binding(self.spec)
        contract = self._parse(self.spec)
        self.assertEqual(contract["state_update"]["operation"], "wrapping_add")
        oracle_source = self.module.oracle_fixture_execution_source(self.spec, fixture_binding)
        self.assertIn("expected_ordinary_wrapping_state", oracle_source["statements"])
        self.assertNotIn("scripted_external", oracle_source["statements"])

        with tempfile.TemporaryDirectory(prefix="auto-migrate-field-add-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "merge-quota-field.json"
            spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
            oracle = self.module.generate_oracle_harness_draft(self.spec, evidence_dir, False)
            self.assertEqual(oracle["compile_execution"]["status"], "compile_succeeded_not_oracle")
            self.assertEqual(
                oracle["compile_execution"]["harness_execution"]["status"],
                "exited_zero_not_oracle",
            )

            draft_path = evidence_dir / "l3-merge-quota-field-rust-draft.rs"
            draft_path.write_text(renamed_rust_draft(), encoding="utf-8")
            (evidence_dir / "l3-merge-quota-field-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "translation_summary": {
                            "translation_rule_ids": ["clang-lowered-typed-ir"],
                            "call_expressions": [],
                        }
                    }
                ),
                encoding="utf-8",
            )
            replay = self.module.generate_rust_replay_test_draft(
                self.spec, evidence_dir, spec_path
            )
            rust_check, _ = self.module.run_rust_check(evidence_dir, False, self.spec)
            self.assertEqual(rust_check["status"], "passed")
            self.assertEqual(rust_check["rust_check_harness_only_bindings"]["bindings"], [])
            replay = self.module.run_generated_rust_replay(
                self.spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")
            self.assertEqual(
                replay["fixture_state_model"],
                {
                    "kind": "record_u32_field_wrapping_add_state",
                    "scope": "fixture_only",
                    "operation": "wrapping_add",
                },
            )
            self.assertNotIn("fixture_external_stub", replay)

    def test_state_update_and_type_drift_fail_closed(self) -> None:
        missing = copy.deepcopy(self.spec)
        missing["replay_contract"].pop("state_update")
        with self.assertRaisesRegex(ValueError, "contract shape drifted"):
            self._parse(missing)

        operation = copy.deepcopy(self.spec)
        operation["replay_contract"]["state_update"]["operation"] = "checked_add"
        with self.assertRaisesRegex(ValueError, "operation must be wrapping_add"):
            self._parse(operation)

        signed = copy.deepcopy(self.spec)
        signed["replay_contract"]["rhs"]["rust_type"] = "i32"
        with self.assertRaisesRegex(ValueError, "rhs rust_type must be u32"):
            self._parse(signed)

        width = copy.deepcopy(self.spec)
        width["replay_contract"]["state_output"]["rust_type"] = "u64"
        with self.assertRaisesRegex(ValueError, "state rust_type must be u32"):
            self._parse(width)

    def test_root_noalias_path_mode_and_expected_drift_fail_closed(self) -> None:
        same_root = copy.deepcopy(self.spec)
        same_root["replay_contract"]["rhs"]["parameter"] = "reservoir"
        same_root["replay_contract"]["rhs"]["field_path"] = ["fill"]
        with self.assertRaisesRegex(ValueError, "source and target roots must be distinct"):
            self._parse(same_root)

        noalias = copy.deepcopy(self.spec)
        noalias["replay_contract"]["noalias_required"] = []
        noalias["c_boundary"]["pointer_contract"]["noalias_required"] = []
        with self.assertRaisesRegex(ValueError, "complete mutable root pair"):
            self._parse(noalias)

        complex_path = copy.deepcopy(self.spec)
        complex_path["replay_contract"]["rhs"]["field_path"] = ["nested", "quantum"]
        with self.assertRaisesRegex(ValueError, "one direct field"):
            self._parse(complex_path)

        mode = copy.deepcopy(self.spec)
        mode["replay_contract"]["rhs"]["mode"] = "record_ref"
        with self.assertRaisesRegex(ValueError, "rhs mode is unsupported"):
            self._parse(mode)

        expected = copy.deepcopy(self.spec)
        expected["fixture_contract"]["cases"][0]["expected_outputs"]["combined_fill"] += 1
        with self.assertRaisesRegex(ValueError, "expected outputs drifted"):
            self._parse(expected)

    def test_expected_output_object_order_does_not_define_semantics(self) -> None:
        renamed = copy.deepcopy(self.spec)
        renamed["replay_contract"]["return"]["fixture_field"] = "z_return"
        renamed["replay_contract"]["state_output"]["fixture_field"] = "a_state"
        renamed["fixture_contract"]["behavior_fields"] = ["z_return", "a_state"]
        renamed["fixture_contract"]["observable_outputs"] = ["z_return", "a_state"]
        for case in renamed["fixture_contract"]["cases"]:
            old = case["expected_outputs"]
            case["expected_outputs"] = {
                "z_return": old["accepted"],
                "a_state": old["combined_fill"],
            }

        contract = self._parse(renamed)

        self.assertEqual(contract["return"]["fixture_field"], "z_return")
        self.assertEqual(contract["state_output"]["fixture_field"], "a_state")

    def _parse(self, spec: dict[str, object]) -> dict[str, object]:
        return self.module.record_u32_field_wrapping_add_state_replay_contract(
            spec, self.module.oracle_fixture_binding(spec)
        )


if __name__ == "__main__":
    unittest.main()
