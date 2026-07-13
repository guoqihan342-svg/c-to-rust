from __future__ import annotations

import hashlib
import unittest

from validation.tools._project_migration_harness.rust_candidate_facts import (
    derive_rust_metadata,
)
from validation.tools._project_migration_harness.rust_ffi_facts import (
    derive_boundary_manifest,
)


class ProjectMigrationRustFactsTests(unittest.TestCase):
    def test_lifetimes_do_not_hide_public_or_unsafe_facts(self) -> None:
        source = (
            "// unsafe pub fn comment_only() {}\n"
            "const TEXT: &str = \"unsafe pub fn string_only() {}\";\n"
            "const RAW: &str = r###\"unsafe pub fn raw_only() {}\"###;\n"
            "pub fn borrow<'a>(value: &'a str) -> &'a str { value }\n"
            "pub unsafe extern \"C\" fn exported() { unsafe { core::ptr::read(0 as *const u8); } }\n"
        )

        facts = derive_rust_metadata(source)

        self.assertEqual(["borrow", "exported"], facts["public_symbols"])
        self.assertEqual([], facts["required_symbols"])
        self.assertEqual(2, facts["unsafe_count"])

    def test_boundary_manifest_derives_extern_block_and_exports(self) -> None:
        source = (
            "unsafe extern \"C\" {\n"
            "    safe fn external_read(value: i32) -> i32;\n"
            "    static mut EXTERNAL_FLAG: i32;\n"
            "}\n"
            "#[unsafe(no_mangle)]\n"
            "pub extern \"C\" fn exported_write(value: i32) -> i32 { value }\n"
        )
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()

        manifest = derive_boundary_manifest(source, digest)

        self.assertEqual(
            ["EXTERNAL_FLAG", "exported_write", "external_read"],
            manifest["extern_c_symbols"],
        )
        self.assertEqual(["exported_write"], manifest["exported_symbols"])
        self.assertEqual(
            ["EXTERNAL_FLAG", "external_read"], manifest["imported_symbols"],
        )
        self.assertEqual(
            {"rust_symbol": "exported_write", "link_name": "exported_write", "abi": "C"},
            manifest["exported_links"][0],
        )
        self.assertEqual(digest, manifest["candidate_sha256"])

    def test_boundary_manifest_preserves_native_import_and_export_names(self) -> None:
        source = (
            "extern \"C\" {\n"
            "    #[link_name = r#\"native_read\"#]\n"
            "    fn rust_read(value: i32) -> i32;\n"
            "}\n"
            "#[export_name = \"native\\x5fwrite\"]\n"
            "pub extern \"C\" fn rust_write(value: i32) -> i32 { value }\n"
        )
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()

        manifest = derive_boundary_manifest(source, digest)

        self.assertEqual([{
            "rust_symbol": "rust_read", "link_name": "native_read", "abi": "C",
        }], manifest["imported_links"])
        self.assertEqual([{
            "rust_symbol": "rust_write", "link_name": "native_write", "abi": "C",
        }], manifest["exported_links"])

    def test_boundary_without_detectable_c_abi_is_rejected(self) -> None:
        source = "pub fn ordinary() {}\n"
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "C ABI boundary"):
            derive_boundary_manifest(source, digest)


if __name__ == "__main__":
    unittest.main()
