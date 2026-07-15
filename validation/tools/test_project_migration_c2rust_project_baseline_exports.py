from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline_exports import (
    privatize_duplicate_exports,
)


class C2RustProjectBaselineExportTests(unittest.TestCase):
    def test_duplicate_no_mangle_functions_and_statics_are_privatized(self) -> None:
        first = (
            "#[no_mangle]\npub static mut state: i32 = 0;\n"
            "#[no_mangle]\npub unsafe extern \"C\" fn shared() {}\n"
        )
        second = first + "#[no_mangle]\npub fn unique() {}\n"
        result = privatize_duplicate_exports({"z.rs": second, "a.rs": first})

        self.assertEqual(first, result.sources["a.rs"])
        self.assertNotIn("#[no_mangle]\npub static mut state", result.sources["z.rs"])
        self.assertNotIn("#[no_mangle]\npub unsafe", result.sources["z.rs"])
        self.assertIn("#[no_mangle]\npub fn unique", result.sources["z.rs"])
        self.assertEqual(("shared", "state"), result.privatized["z.rs"])

    def test_comments_and_literals_do_not_create_exports(self) -> None:
        source = 'const TEXT: &str = "#[no_mangle]"; // #[no_mangle]\n'
        result = privatize_duplicate_exports({"a.rs": source, "b.rs": source})
        self.assertEqual({}, result.privatized)
        self.assertEqual(source, result.sources["b.rs"])


if __name__ == "__main__":
    unittest.main()
