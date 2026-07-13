from __future__ import annotations

import unittest

from validation.tools._ai_candidate_harness_parts.abi_dependencies import (
    classify_abi_dependencies,
)
from validation.tools._ai_candidate_harness_parts.exact_validation_contracts import (
    mask_noncode,
)


def dependencies(source: str) -> dict[str, int]:
    analysis = classify_abi_dependencies(mask_noncode(source))
    return {item["kind"]: item["count"] for item in analysis["dependencies"]}


class AiAbiDependencyPatternTests(unittest.TestCase):
    def test_target_dependency_families_are_classified_without_identity_rules(self) -> None:
        source = (
            "#[cfg(target_endian = \"little\")]\n"
            "pub fn renamed_width(value: core::ffi::c_int) -> usize {\n"
            "    let bytes = value.to_ne_bytes();\n"
            "    i32::from_ne_bytes(bytes) as usize\n"
            "}\n"
        )
        observed = dependencies(source)
        for kind in (
            "target_width_integer",
            "pointer_integer_cast",
            "target_cfg",
            "native_endian",
            "ffi_platform_type",
        ):
            self.assertIn(kind, observed)

    def test_all_declared_repr_layout_modifiers_are_counted(self) -> None:
        source = (
            "#[repr(transparent)] struct Transparent(i32);\n"
            "#[repr(packed)] struct Packed { value: i32 }\n"
            "#[repr(align(8))] struct Aligned(i32);\n"
            "#[repr(u16)] enum Code { Ok = 0 }\n"
        )
        self.assertEqual(dependencies(source)["repr_layout_modifier"], 4)

    def test_extern_crate_and_safe_non_null_type_do_not_become_layout_dependencies(self) -> None:
        source = (
            "extern crate core;\n"
            "pub struct Holder {\n"
            "    value: Option<core::ptr::NonNull<core::ffi::c_void>>,\n"
            "}\n"
        )
        observed = dependencies(source)
        self.assertNotIn("extern_abi", observed)
        self.assertNotIn("raw_pointer", observed)
        self.assertEqual(observed, {"ffi_platform_type": 1})


if __name__ == "__main__":
    unittest.main()
