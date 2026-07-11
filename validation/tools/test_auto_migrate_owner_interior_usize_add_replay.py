from __future__ import annotations

import copy
import unittest

from validation.tools.owner_interior_usize_add_test_support import (
    build_spec,
    load_auto_migrate_module,
)


class AutoMigrateOwnerInteriorUsizeAddReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_auto_migrate_module()

    def test_generates_lp64_oracle_replay_and_explicit_state_model(self) -> None:
        spec, _ = build_spec()
        binding = self.module.oracle_fixture_binding(spec)
        contract = self._parse(spec, binding)
        self.assertEqual(contract["state_output"]["owner_field_path"], ["total"])
        oracle = self.module.c_oracle_record_owner_interior_u32_to_usize_wrapping_add_state_execution_source(
            spec, binding
        )
        self.assertIn("size_t expected_lp64_wrap_usize_state", oracle["statements"])
        self.assertEqual(
            oracle["fixture_state_model"],
            {
                "kind": "record_owner_interior_u32_to_usize_wrapping_add_state",
                "scope": "fixture_only",
                "operation": "wrapping_add",
                "projection_mode": "owner_interior_mutable",
                "pointer_root_count": 1,
                "conversion": "u32_to_usize",
                "source_bits": 32,
                "target_bits": 64,
            },
        )
        replay = self.module.rust_replay_record_owner_interior_u32_to_usize_wrapping_add_state_cases_source(
            spec, binding
        )
        self.assertIn("usize::try_from(actual_lp64_wrap_ledger.slot.amount)", replay)
        self.assertIn("assert_eq!(expected_state, 1usize", replay)

    def test_rejects_alias_root_abi_conversion_and_shape_drift(self) -> None:
        spec, _ = build_spec()
        mutations = []

        raw_pointer_alias = copy.deepcopy(spec)
        raw_pointer_alias["replay_contract"]["alias"]["c_type"] = "struct Slot *"
        mutations.append((raw_pointer_alias, "pointer typedef"))

        overlap = copy.deepcopy(spec)
        overlap["replay_contract"]["state_output"]["owner_field_path"] = ["slot"]
        mutations.append((overlap, "accumulator"))

        second_root = copy.deepcopy(spec)
        second_root["c_boundary"]["signatures"][0]["parameters"].append(
            {"name": "other", "c_type": "struct Ledger *", "direction": "input"}
        )
        mutations.append((second_root, "only the owner root"))

        noalias = copy.deepcopy(spec)
        noalias["replay_contract"]["noalias_required"] = [["ledger", "other"]]
        noalias["c_boundary"]["pointer_contract"]["noalias_required"] = [["ledger", "other"]]
        mutations.append((noalias, "empty noalias"))

        missing_abi = copy.deepcopy(spec)
        del missing_abi["build_profile"]["target"]
        mutations.append((missing_abi, "build_profile.target"))

        non_lp64 = copy.deepcopy(spec)
        non_lp64["build_profile"]["target"]["pointer_width"] = 32
        non_lp64["c_boundary"]["target_abi_contract"]["pointer_width"] = 32
        mutations.append((non_lp64, "LP64"))

        narrowing = copy.deepcopy(spec)
        narrowing["replay_contract"]["widening"]["target_bits"] = 16
        mutations.append((narrowing, "lossless u32_to_usize"))

        signed = copy.deepcopy(spec)
        signed["replay_contract"]["widening"]["signedness"] = "signed"
        mutations.append((signed, "lossless u32_to_usize"))

        extra = copy.deepcopy(spec)
        extra["replay_contract"]["rhs"]["extra"] = True
        mutations.append((extra, "rhs shape drifted"))

        for changed, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self._parse(changed)

    def _parse(self, spec, binding=None):
        return self.module.record_owner_interior_u32_to_usize_wrapping_add_state_replay_contract(
            spec, binding
        )


if __name__ == "__main__":
    unittest.main()
