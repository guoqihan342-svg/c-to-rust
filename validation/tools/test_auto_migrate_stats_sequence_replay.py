from __future__ import annotations

import copy
import unittest

from validation.tools.stats_sequence_test_support import build_spec, load_auto_migrate_module


class AutoMigrateStatsSequenceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_auto_migrate_module()

    def test_generates_ordered_lp64_oracle_and_replay(self) -> None:
        spec, _ = build_spec()
        binding = self.module.oracle_fixture_binding(spec)
        contract = self.module.record_owner_interior_stats_sequence_state_replay_contract(
            spec, binding
        )
        self.assertEqual([item["operation"] for item in contract["updates"]], [
            "postfix_increment", "wrapping_add", "wrapping_add"
        ])
        oracle = self.module.c_oracle_record_owner_interior_stats_sequence_state_execution_source(
            spec, binding
        )
        self.assertIn("UINT32_C(1)", oracle["statements"])
        self.assertEqual(oracle["statements"].count("(size_t)"), 8)
        replay = self.module.rust_replay_record_owner_interior_stats_sequence_state_cases_source(
            spec, binding
        )
        self.assertIn("expected_state_2", replay)
        self.assertIn("usize::try_from", replay)

    def test_rejects_alias_distinctness_order_shape_and_abi_drift(self) -> None:
        spec, _ = build_spec()
        mutations = []
        raw_alias = copy.deepcopy(spec)
        raw_alias["replay_contract"]["alias"]["c_type"] = "struct Cell *"
        mutations.append((raw_alias, "pointer typedef"))
        duplicate_target = copy.deepcopy(spec)
        duplicate_target["replay_contract"]["updates"][2]["target"]["owner_field_path"] = ["bytes"]
        mutations.append((duplicate_target, "targets must be distinct"))
        duplicate_source = copy.deepcopy(spec)
        duplicate_source["replay_contract"]["updates"][2]["source"] = copy.deepcopy(
            duplicate_source["replay_contract"]["updates"][1]["source"]
        )
        mutations.append((duplicate_source, "sources must be distinct"))
        reordered = copy.deepcopy(spec)
        reordered["replay_contract"]["updates"][0], reordered["replay_contract"]["updates"][1] = (
            reordered["replay_contract"]["updates"][1],
            reordered["replay_contract"]["updates"][0],
        )
        mutations.append((reordered, "updates\[0\] shape drifted"))
        extra = copy.deepcopy(spec)
        extra["replay_contract"]["updates"].append(copy.deepcopy(extra["replay_contract"]["updates"][2]))
        mutations.append((extra, "exactly three ordered updates"))
        abi = copy.deepcopy(spec)
        abi["build_profile"]["target"]["size_t_width"] = 32
        abi["c_boundary"]["target_abi_contract"]["size_t_width"] = 32
        mutations.append((abi, "LP64"))
        for changed, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.module.record_owner_interior_stats_sequence_state_replay_contract(changed)


if __name__ == "__main__":
    unittest.main()
