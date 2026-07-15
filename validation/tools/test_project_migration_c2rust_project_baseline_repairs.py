from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline_repair import (
    add_deref_nullptr_allow,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_variadics import (
    modernize_c2rust_variadics,
)


class C2RustProjectBaselineRepairTests(unittest.TestCase):
    def test_generated_lint_allows_are_complete_and_idempotent(self) -> None:
        repaired = add_deref_nullptr_allow("pub fn probe(size: usize) {}\n")
        self.assertTrue(repaired.startswith(
            "#![allow(deref_nullptr)]\n"
            "#![allow(unused_variables)]\n"
            "#![allow(unreachable_code)]\n"
            "#![allow(unused_must_use)]\n"
        ))
        self.assertEqual(repaired, add_deref_nullptr_allow(repaired))

    def test_generated_lint_allows_preserve_bom_and_shebang(self) -> None:
        bom = add_deref_nullptr_allow("\ufeffpub fn probe() {}\n")
        script = add_deref_nullptr_allow("#!/usr/bin/env rustx\npub fn probe() {}\n")
        self.assertTrue(bom.startswith("\ufeff#![allow(deref_nullptr)]"))
        self.assertTrue(script.startswith(
            "#!/usr/bin/env rustx\n#![allow(deref_nullptr)]"
        ))

    def test_old_c2rust_variadic_api_is_modernized_structurally(self) -> None:
        source = """\
unsafe fn forward(mut current: ::core::ffi::VaList) {
    sink(current.as_va_list());
}
unsafe extern "C" fn variadic(mut c2rust_args: ...) {
    let mut copied: ::core::ffi::VaListImpl;
    copied = c2rust_args.clone();
    sink(copied.as_va_list());
    custom.as_va_list();
    let marker = "::core::ffi::VaListImpl copied.as_va_list()";
    // copied.as_va_list()
}
"""
        repaired = modernize_c2rust_variadics(source)
        self.assertEqual(1, repaired.va_list_type_rewrite_count)
        self.assertEqual(2, repaired.va_list_adapter_rewrite_count)
        self.assertIn("let mut copied: ::core::ffi::VaList;", repaired.source)
        self.assertIn("sink(current);", repaired.source)
        self.assertIn("sink(copied);", repaired.source)
        self.assertIn("custom.as_va_list();", repaired.source)
        self.assertIn(
            '"::core::ffi::VaListImpl copied.as_va_list()"', repaired.source,
        )
        self.assertIn("// copied.as_va_list()", repaired.source)

        second = modernize_c2rust_variadics(repaired.source)
        self.assertEqual(repaired.source, second.source)
        self.assertEqual(0, second.va_list_type_rewrite_count)
        self.assertEqual(0, second.va_list_adapter_rewrite_count)

    def test_custom_variadic_adapter_without_core_type_is_unchanged(self) -> None:
        source = "struct VaListImpl;\nfn probe() { custom.as_va_list(); }\n"
        repaired = modernize_c2rust_variadics(source)
        self.assertEqual(source, repaired.source)


if __name__ == "__main__":
    unittest.main()
