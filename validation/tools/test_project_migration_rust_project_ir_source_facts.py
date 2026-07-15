from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.rust_project_ir_source_facts import (
    SOURCE_INTERFACE_SECTIONS,
    derive_bound_candidate_source_facts,
    derive_candidate_source_facts,
)


class RustProjectIRSourceFactTests(unittest.TestCase):
    def test_public_function_signature_is_recomputable_and_abi_preserving(self) -> None:
        facts = derive_bound_candidate_source_facts(
            'pub unsafe extern "C" fn value(input: *const u8) -> usize { 0 }\n',
            ["value"],
        )

        self.assertEqual("ready", facts["status"])
        self.assertEqual([], facts["unresolved_sections"])
        self.assertEqual([{
            "symbol": "value",
            "kind": "function",
            "signature": 'pub unsafe extern "C" fn value ( input : * const u8 ) -> usize',
        }], facts["public_items"])

    def test_comments_and_strings_cannot_forge_target_roles(self) -> None:
        facts = derive_candidate_source_facts(
            '// fn main() {}\n'
            'fn helper() { let _text = "#[test] fn forged() {}"; }\n'
        )

        self.assertEqual(0, facts["binary_entry_count"])
        self.assertEqual(0, facts["test_entry_count"])
        self.assertEqual("ready", facts["status"])

    def test_language_entry_and_test_attribute_are_detected_without_names(self) -> None:
        binary = derive_candidate_source_facts("fn main() {}\n")
        tests = derive_candidate_source_facts(
            "#[test]\nfn arbitrary_case_name() { assert_eq!(2 + 2, 4); }\n"
        )

        self.assertEqual(1, binary["binary_entry_count"])
        self.assertEqual(0, binary["test_entry_count"])
        self.assertEqual(0, tests["binary_entry_count"])
        self.assertEqual(1, tests["test_entry_count"])

    def test_unsupported_interface_families_remain_unresolved(self) -> None:
        facts = derive_candidate_source_facts(
            "#[cfg(unix)]\n"
            "pub struct Shared { value: i32 }\n"
            "static mut STATE: i32 = 0;\n"
            "mod nested { pub fn value() {} }\n"
        )

        self.assertEqual("partial", facts["status"])
        self.assertTrue({
            "cfg-feature-extraction", "global-ownership",
            "initialization-destruction", "nested-module-multi-target",
            "shared-type-layout",
        } <= set(facts["unresolved_sections"]))

    def test_metadata_mismatch_and_malformed_source_fail_closed(self) -> None:
        mismatched = derive_bound_candidate_source_facts(
            "pub fn actual() {}\n", ["different"],
        )
        malformed = derive_candidate_source_facts("pub fn broken( {\n")

        self.assertIn("public-signature", mismatched["unresolved_sections"])
        self.assertEqual(
            SOURCE_INTERFACE_SECTIONS, set(malformed["unresolved_sections"]),
        )

    def test_restricted_visibility_cannot_impersonate_public_interface(self) -> None:
        facts = derive_bound_candidate_source_facts(
            "pub(crate) fn local_value() -> i32 { 1 }\n", ["local_value"],
        )

        self.assertEqual("partial", facts["status"])
        self.assertIn("public-signature", facts["unresolved_sections"])


if __name__ == "__main__":
    unittest.main()
