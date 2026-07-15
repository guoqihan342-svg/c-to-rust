from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import unittest

from validation.tools._project_migration_harness.rust_source_pre_cfg_process import (
    bind_rust_source_parser_binary,
    run_rust_source_parser,
)
from validation.tools._project_migration_harness.rust_source_pre_cfg_schema import (
    parse_rust_source_pre_cfg_witness,
)


class RustSourcePreCfgProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.target_dir = (
            cls.root / "target/test-host" / platform.system().lower()
        )
        result = subprocess.run(
            [
                "cargo", "build", "--quiet", "--manifest-path",
                "crates/c2r-translator/Cargo.toml", "--bin",
                "c2r_rust_source_witness",
            ],
            cwd=cls.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "CARGO_TARGET_DIR": str(cls.target_dir)},
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
        executable = "c2r_rust_source_witness.exe" if os.name == "nt" else (
            "c2r_rust_source_witness"
        )
        cls.binary = cls.target_dir / "debug" / executable

    def test_real_binary_binding_and_bounded_stdin_process(self) -> None:
        source = b"pub fn value(input: u32) -> u32 { input }\n"
        binding = bind_rust_source_parser_binary(self.root, self.binary)
        result = run_rust_source_parser(
            tool_root=self.root, parser_binary=self.binary, source=source,
        )
        witness = parse_rust_source_pre_cfg_witness(result.stdout, source)

        self.assertEqual("c2r_rust_source_witness", binding["name"])
        self.assertTrue(result.started)
        self.assertEqual(0, result.returncode)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.output_limit_exceeded)
        self.assertEqual(b"", result.stderr)
        self.assertEqual("ready", witness["status"])

    def test_binary_must_be_inside_tool_root_with_the_fixed_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside_tool_root"):
            bind_rust_source_parser_binary(
                self.root / "validation", self.binary,
            )
        with self.assertRaisesRegex(ValueError, "binary_invalid"):
            bind_rust_source_parser_binary(
                self.root, self.root / "crates/c2r-translator/Cargo.toml",
            )


if __name__ == "__main__":
    unittest.main()
