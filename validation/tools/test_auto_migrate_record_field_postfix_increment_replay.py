from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.record_field_postfix_increment_test_support import (
    build_postfix_increment_spec,
    load_auto_migrate_module,
    renamed_rust_draft,
)


class AutoMigrateRecordFieldPostfixIncrementReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_auto_migrate_module()
        self.spec, _ = build_postfix_increment_spec()
        self.spec["fixture_hash"] = "synthetic-postfix-increment-fixture"

    def test_generic_oracle_rust_replay_and_state_model(self) -> None:
        binding = self.module.oracle_fixture_binding(self.spec)
        contract = self._parse(self.spec)
        self.assertEqual(contract["state_update"], {"operation": "wrapping_add", "increment": 1})
        source = self.module.oracle_fixture_execution_source(self.spec, binding)
        self.assertIn("actual_zero_counter.ticks + UINT32_C(1)", source["statements"])
        self.assertNotIn("increment_value", source["statements"])

        with tempfile.TemporaryDirectory(prefix="auto-migrate-postfix-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "postfix.json"
            spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
            oracle = self.module.generate_oracle_harness_draft(self.spec, evidence_dir, False)
            self.assertEqual(oracle["compile_execution"]["status"], "compile_succeeded_not_oracle")
            prefix = "l3-bump-counter"
            (evidence_dir / f"{prefix}-rust-draft.rs").write_text(
                renamed_rust_draft(), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"translation_summary": {
                    "translation_rule_ids": ["clang-lowered-typed-ir"],
                    "call_expressions": [],
                }}),
                encoding="utf-8",
            )
            replay = self.module.generate_rust_replay_test_draft(
                self.spec, evidence_dir, spec_path
            )
            rust_check, _ = self.module.run_rust_check(evidence_dir, False, self.spec)
            self.assertEqual(rust_check["status"], "passed")
            replay = self.module.run_generated_rust_replay(
                self.spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")
            self.assertEqual(
                replay["fixture_state_model"],
                {
                    "kind": "record_u32_field_postfix_increment_state",
                    "scope": "fixture_only",
                    "operation": "wrapping_add",
                    "increment": 1,
                },
            )
            self.assertNotIn("fixture_external_stub", replay)

    def test_shape_fixture_and_pointer_drift_fail_closed(self) -> None:
        scalar = copy.deepcopy(self.spec)
        scalar["replay_contract"]["entry_arguments"].append({
            "parameter": "amount", "c_type": "uint32_t", "rust_type": "u32",
            "pass_mode": "value", "direction": "input", "fixture_field": "amount",
        })
        with self.assertRaisesRegex(ValueError, "one entry argument"):
            self._parse(scalar)

        increment = copy.deepcopy(self.spec)
        increment["replay_contract"]["state_update"]["increment"] = 2
        with self.assertRaisesRegex(ValueError, "increment 1"):
            self._parse(increment)

        extra_input = copy.deepcopy(self.spec)
        extra_input["fixture_contract"]["cases"][0]["inputs"]["unrelated"] = 3
        with self.assertRaisesRegex(ValueError, "only the record initial field"):
            self._parse(extra_input)

        noalias = copy.deepcopy(self.spec)
        noalias["replay_contract"]["noalias_required"] = [["counter", "other"]]
        noalias["c_boundary"]["pointer_contract"]["noalias_required"] = [["counter", "other"]]
        with self.assertRaisesRegex(ValueError, "empty noalias pairs"):
            self._parse(noalias)

    def _parse(self, spec: dict[str, object]) -> dict[str, object]:
        return self.module.record_u32_field_postfix_increment_state_replay_contract(
            spec, self.module.oracle_fixture_binding(spec)
        )


if __name__ == "__main__":
    unittest.main()
