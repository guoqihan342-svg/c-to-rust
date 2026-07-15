from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import platform
import subprocess
import unittest

from validation.tools._project_migration_harness.rust_source_pre_cfg_schema import (
    parse_rust_source_pre_cfg_witness,
    validate_rust_source_pre_cfg_witness,
)


class RustSourcePreCfgSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.ready_source = b"""
#[cfg(feature = \"fast\")]
pub mod api {
    #[repr(C)]
    pub struct Pair { pub left: i32, pub right: i32 }
    pub static mut TOTAL: i32 = 0;
    pub extern \"C\" fn add(value: i32) -> i32 { value + 1 }
}
"""
        cls.blocked_source = b"""
#[cfg_attr(feature = \"derive\", derive(Clone))]
mod external;
#[vendor::rewrites_signature]
pub fn render() { println!(\"value\"); }
"""
        cls.ready_raw = cls._run_parser(cls.ready_source)
        cls.blocked_raw = cls._run_parser(cls.blocked_source)

    def test_real_syn_output_recomputes_source_and_fact_bindings(self) -> None:
        witness = parse_rust_source_pre_cfg_witness(
            self.ready_raw, self.ready_source,
        )

        self.assertEqual("ready", witness["status"])
        self.assertEqual("syn", witness["parser"]["implementation"])
        self.assertEqual(2, len(witness["modules"]))
        self.assertTrue(any(
            item["item_path"] == "crate::api::add"
            for item in witness["items"]
        ))
        self.assertFalse(witness["claim_boundary"]["post_cfg"])
        self.assertFalse(witness["claim_boundary"]["section_closure"])
        self.assertFalse(witness["claim_boundary"]["semantic_gate"])
        self.assertEqual(
            0, witness["claim_boundary"]["translation_coverage_numerator"],
        )

    def test_macro_attribute_cfg_attr_and_external_module_are_blocked(self) -> None:
        witness = parse_rust_source_pre_cfg_witness(
            self.blocked_raw, self.blocked_source,
        )
        codes = {item["code"] for item in witness["blockers"]}

        self.assertEqual("blocked", witness["status"])
        self.assertIn("rust_source_cfg_attr_unresolved", codes)
        self.assertIn("rust_source_external_module_unresolved", codes)
        self.assertIn("rust_source_unsupported_attribute", codes)
        self.assertIn("rust_source_macro_expansion_required", codes)

    def test_tampered_source_syntax_and_claim_boundary_fail_closed(self) -> None:
        witness = json.loads(self.ready_raw)
        changed = copy.deepcopy(witness)
        changed["source"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source_binding_invalid"):
            validate_rust_source_pre_cfg_witness(changed, self.ready_source)

        changed = copy.deepcopy(witness)
        changed["signatures"][0]["syntax_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "syntax_binding_invalid"):
            validate_rust_source_pre_cfg_witness(changed, self.ready_source)

        changed = copy.deepcopy(witness)
        changed["claim_boundary"]["section_closure"] = True
        with self.assertRaisesRegex(ValueError, "identity_invalid"):
            validate_rust_source_pre_cfg_witness(changed, self.ready_source)

    def test_missing_blocker_and_duplicate_json_key_fail_closed(self) -> None:
        witness = json.loads(self.blocked_raw)
        witness["blockers"] = [
            item for item in witness["blockers"]
            if item["code"] != "rust_source_cfg_attr_unresolved"
        ]
        with self.assertRaisesRegex(ValueError, "attribute_blocker_missing"):
            validate_rust_source_pre_cfg_witness(
                witness, self.blocked_source,
            )

        duplicate = self.ready_raw.replace(
            b'{"schema_version":1,',
            b'{"schema_version":1,"schema_version":1,',
            1,
        )
        with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
            parse_rust_source_pre_cfg_witness(
                duplicate, self.ready_source,
            )

    def test_different_source_bytes_cannot_reuse_a_witness(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_binding_invalid"):
            parse_rust_source_pre_cfg_witness(
                self.ready_raw, self.ready_source + b"\n",
            )

    @classmethod
    def _run_parser(cls, source: bytes) -> bytes:
        result = subprocess.run(
            [
                "cargo", "run", "--quiet", "--manifest-path",
                "crates/c2r-translator/Cargo.toml", "--bin",
                "c2r_rust_source_witness",
            ],
            cwd=cls.root,
            input=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "CARGO_TARGET_DIR": str(
                    cls.root / "target/test-host" / platform.system().lower()
                ),
            },
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout


if __name__ == "__main__":
    unittest.main()
