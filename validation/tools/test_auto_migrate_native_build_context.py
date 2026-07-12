from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validation.tools import auto_migrate


class AutoMigrateNativeBuildContextTests(unittest.TestCase):
    def context(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "mode": "linked_artifacts_v1",
            "closure_manifest": {"path": "closure/closure.json", "sha256": "a" * 64},
            "source_root": {"path": "vendor/core", "sha256": "b" * 64},
            "compile_database": {"path": "closure/compile_commands.json", "sha256": "c" * 64},
            "defines": ["FEATURE=1"],
            "source_include_dirs": [{"path": "vendor/core/include", "sha256": "d" * 64}],
            "generated_include_dirs": [{"path": "closure/include", "sha256": "e" * 64}],
            "include_paths": ["vendor/core/include", "closure/include"],
            "target_abi": {
                "triple": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "pointer_width": 64,
            },
            "toolchain": {"cc": "test-cc"},
            "build_config": {
                "generator": "Ninja",
                "build_type": "Release",
                "build_target": "core",
                "configure_defines": [],
            },
            "symbol_bindings": [],
        }

    def spec(self) -> dict[str, object]:
        source_hash = "f" * 64
        return {
            "target_id": "renamable-target",
            "slice_id": "renamable-slice",
            "source_commit": "1234567",
            "function_name": "transform",
            "c_source": "int EXPORT_NAME(transform)(int value) { return value + FEATURE; }",
            "fixture_hash": "fixture-hash",
            "source": {
                "source_root": "vendor/core",
                "source_file_hashes": {
                    "src/unit.c": source_hash,
                    "fixtures/cases.json": "1" * 64,
                },
            },
            "c_boundary": {
                "files": [
                    {"path": "src/unit.c", "role": "source", "sha256": source_hash},
                    {"path": "fixtures/cases.json", "role": "fixture"},
                ],
                "signatures": [
                    {
                        "function": "transform",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int", "direction": "input"}],
                        "c_source": "int EXPORT_NAME(transform)(int value) { return value + FEATURE; }",
                        "source_span": {
                            "file": "src/unit.c",
                            "line_start": 7,
                            "line_end": 7,
                            "byte_start": 80,
                            "byte_end": 148,
                            "sha256": "2" * 64,
                        },
                    }
                ],
            },
            "build_profile": {
                "include_paths": ["legacy/include"],
                "defines": ["LEGACY=1"],
                "target": {
                    "triple_or_abi": "x86_64-unknown-linux-gnu",
                    "endianness": "little",
                    "int_width": 32,
                    "long_width": 64,
                    "pointer_width": 64,
                },
                "compiler_command_source": "legacy-command",
            },
        }

    def test_verified_closure_rebases_real_source_and_overrides_legacy_compile_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="translator-native-context-") as tmp:
            out = Path(tmp)
            with patch(
                "validation.tools.native_build_context.resolve_native_build_context",
                return_value=self.context(),
            ):
                path = auto_migrate.write_translator_spec(self.spec(), out / "spec.json", out)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_root"], ".")
            self.assertEqual(payload["source_file"], "vendor/core/src/unit.c")
            self.assertEqual(payload["function_source_span"]["file"], "vendor/core/src/unit.c")
            self.assertEqual(
                payload["source_file_hashes"],
                {
                    "vendor/core/src/unit.c": "f" * 64,
                    "fixtures/cases.json": "1" * 64,
                },
            )
            self.assertEqual(payload["compile_commands"], self.context()["compile_database"])
            self.assertEqual(
                payload["build_profile"]["include_paths"],
                ["vendor/core/include", "closure/include"],
            )
            self.assertEqual(payload["build_profile"]["defines"], ["FEATURE=1"])
            self.assertEqual(
                payload["build_profile"]["compiler_command_source"],
                "closure/compile_commands.json",
            )
            self.assertEqual(payload["c_boundary"]["signatures"][0]["source_span"]["file"], "vendor/core/src/unit.c")
            serialized = json.dumps(payload["native_build_context"], sort_keys=True)
            self.assertNotIn("argv", serialized)
            self.assertNotIn("working_directory", serialized)
            self.assertNotIn("renamable-target", serialized)

    def test_conflicting_closure_abi_fails_closed(self) -> None:
        context = self.context()
        context["target_abi"] = {
            "triple": "aarch64-unknown-linux-gnu",
            "endianness": "little",
            "pointer_width": 64,
        }
        with tempfile.TemporaryDirectory(prefix="translator-native-context-") as tmp:
            with patch(
                "validation.tools.native_build_context.resolve_native_build_context",
                return_value=context,
            ):
                with self.assertRaisesRegex(SystemExit, "conflicts at triple_or_abi"):
                    auto_migrate.write_translator_spec(
                        self.spec(),
                        Path(tmp) / "spec.json",
                        Path(tmp),
                    )


if __name__ == "__main__":
    unittest.main()
