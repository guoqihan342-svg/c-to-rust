from __future__ import annotations

import copy
import unittest

from validation.tools.guarded_stats_sequence_test_support import (
    build_spec,
    load_auto_migrate_module,
)


class AutoMigrateGuardedStatsSequenceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_auto_migrate_module()

    def test_generates_short_circuit_guard_and_false_no_effect_replay(self) -> None:
        spec, _ = build_spec()
        binding = self.module.oracle_fixture_binding(spec)
        contract = (
            self.module.record_owner_interior_guarded_stats_sequence_state_replay_contract(
                spec, binding
            )
        )
        self.assertEqual(contract["guard"]["operator"], "short_circuit_and")
        self.assertEqual(
            [item["operation"] for item in contract["guard"]["predicates"]],
            ["equality", "equality"],
        )
        oracle = (
            self.module.c_oracle_record_owner_interior_guarded_stats_sequence_state_execution_source(
                spec, binding
            )
        )
        self.assertIn(" == CELL_READY && ", oracle["statements"])
        self.assertIn(" ? ", oracle["statements"])
        replay = (
            self.module.rust_replay_record_owner_interior_guarded_stats_sequence_state_cases_source(
                spec, binding
            )
        )
        self.assertIn(" == 7u32 && ", replay)
        self.assertIn("if expected_guard", replay)
        self.assertIn("verified: false", replay)

    def test_rejects_guard_shape_alias_overlap_and_fixture_drift(self) -> None:
        spec, _ = build_spec()
        mutations = []
        operator = copy.deepcopy(spec)
        operator["replay_contract"]["guard"]["operator"] = "bitwise_and"
        mutations.append((operator, "short_circuit_and"))
        one_predicate = copy.deepcopy(spec)
        one_predicate["replay_contract"]["guard"]["predicates"].pop()
        mutations.append((one_predicate, "exactly two ordered equality predicates"))
        overlap = copy.deepcopy(spec)
        overlap["replay_contract"]["guard"]["predicates"][0]["lhs"] = {
            "alias_field_path": ["alpha"],
            "owner_field_path": ["cell", "alpha"],
            "rust_type": "u32",
            "mode": "direct_field_value",
        }
        mutations.append((overlap, "distinct from update fields"))
        false_effect = copy.deepcopy(spec)
        false_effect["replay_contract"]["guard"]["false_path"]["state_effect"] = "update"
        mutations.append((false_effect, "no state effect"))
        for changed, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.module.record_owner_interior_guarded_stats_sequence_state_replay_contract(
                    changed
                )


if __name__ == "__main__":
    unittest.main()
