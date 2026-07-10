from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.record_constant_state_test_support import (
    build_constant_state_spec,
    load_auto_migrate_module,
    renamed_rust_draft,
)


class AutoMigrateRecordConstantStateReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_auto_migrate_module()
        self.spec, _ = build_constant_state_spec()
        self.spec["fixture_hash"] = "synthetic-renamed-constant-state-fixture"

    def test_renamed_nested_constant_state_oracle_and_rust_replay(self) -> None:
        fixture_binding = self.module.oracle_fixture_binding(self.spec)
        contract = self._parse(self.spec)
        self.assertEqual(contract["state_output"]["field_path"], ["route", "marker"])
        self.assertEqual(contract["state_update"]["value"], 0)
        oracle_source = self.module.oracle_fixture_execution_source(self.spec, fixture_binding)
        self.assertIn("actual_ordinary_parcel.route.marker", oracle_source["statements"])
        self.assertNotIn("scripted_external", oracle_source["statements"])

        with tempfile.TemporaryDirectory(prefix="auto-migrate-constant-state-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "clear-nested-marker.json"
            spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
            oracle = self.module.generate_oracle_harness_draft(self.spec, evidence_dir, False)
            self.assertEqual(oracle["compile_execution"]["status"], "compile_succeeded_not_oracle")
            self.assertEqual(
                oracle["compile_execution"]["harness_execution"]["status"],
                "exited_zero_not_oracle",
            )
            draft_path = evidence_dir / "l3-clear-nested-marker-rust-draft.rs"
            draft_path.write_text(renamed_rust_draft(), encoding="utf-8")
            (evidence_dir / "l3-clear-nested-marker-auto-translation-plan.json").write_text(
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
                    "kind": "record_u32_field_constant_state",
                    "scope": "fixture_only",
                    "operation": "constant_assign",
                    "value": 0,
                },
            )
            self.assertNotIn("fixture_external_stub", replay)

    def test_contract_path_constant_pointer_and_noalias_drift_fail_closed(self) -> None:
        shallow = copy.deepcopy(self.spec)
        shallow["replay_contract"]["state_output"]["field_path"] = ["label"]
        with self.assertRaisesRegex(ValueError, "field_path must be nested"):
            self._parse(shallow)

        constant = copy.deepcopy(self.spec)
        constant["replay_contract"]["state_update"]["value"] = 1
        with self.assertRaisesRegex(ValueError, "constant 0"):
            self._parse(constant)

        pointer = copy.deepcopy(self.spec)
        pointer["c_boundary"]["pointer_contract"]["aliasing_proven"] = False
        with self.assertRaisesRegex(ValueError, "proven pointer metadata"):
            self._parse(pointer)

        noalias = copy.deepcopy(self.spec)
        noalias["replay_contract"]["noalias_required"] = [["parcel", "parcel"]]
        with self.assertRaisesRegex(ValueError, "distinct names"):
            self._parse(noalias)

        uninitialized = copy.deepcopy(self.spec)
        uninitialized["replay_contract"]["state_output"]["field_path"] = ["route", "missing"]
        with self.assertRaisesRegex(ValueError, "not initialized"):
            self._parse(uninitialized)

    def test_expected_outputs_are_recomputed_from_declared_constants(self) -> None:
        drifted = copy.deepcopy(self.spec)
        drifted["fixture_contract"]["cases"][0]["expected_outputs"]["cleared_marker"] = 9
        with self.assertRaisesRegex(ValueError, "expected outputs drifted"):
            self._parse(drifted)

    def _parse(self, spec: dict[str, object]) -> dict[str, object]:
        return self.module.record_u32_field_constant_state_replay_contract(
            spec, self.module.oracle_fixture_binding(spec)
        )


if __name__ == "__main__":
    unittest.main()
