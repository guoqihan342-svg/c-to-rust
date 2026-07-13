from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness import build_facts
from validation.tools._project_migration_harness import discovery_database
from validation.tools._project_migration_harness.discovery import discover_project


class ProjectMigrationDiscoverySecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-discovery-security-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def database(self, entries: list[dict[str, object]]) -> Path:
        return self.write("compile_commands.json", json.dumps(entries) + "\n")

    def test_repository_root_link_is_rejected_before_resolution(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="project-discovery-link-"))
        self.addCleanup(parent.rmdir)
        linked = parent / "linked-root"
        try:
            os.symlink(self.root, linked, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {error}")
        self.addCleanup(linked.unlink)

        result = discover_project(linked)

        self.assertEqual("blocked", result["status"])
        self.assertEqual(["repository_root_linked"], result["blockers"])

    def test_compile_database_bytes_must_match_selected_binding(self) -> None:
        self.write("unit.c", "int unit(void) { return 0; }\n")
        database = self.database([self.entry("unit.c", ["clang", "-c", "unit.c"])])
        original = discovery_database.file_binding
        changed = False

        def bind_then_replace(repo_root: Path, path: Path, **kwargs: object) -> dict:
            nonlocal changed
            binding = original(repo_root, path, **kwargs)
            if Path(path).resolve() == database.resolve() and not changed:
                database.write_text("[]\n", encoding="utf-8")
                changed = True
            return binding

        with mock.patch.object(discovery_database, "file_binding", side_effect=bind_then_replace):
            result = discover_project(self.root, compile_database=database)

        self.assertIn("compile_database_binding_changed", result["blockers"])
        self.assertEqual([], result["translation_units"])

    def test_non_compilers_incomplete_commands_and_shell_text_are_blocked(self) -> None:
        self.write("unit.c", "int unit(void) { return 0; }\n")
        entries = [
            self.entry("unit.c", ["python", "unit.c"]),
            self.entry("unit.c", ["clang", "unit.c"]),
            self.entry("unit.c", ["clang", "-c", "other.c"]),
            {"directory": ".", "file": "unit.c", "command": "clang -c unit.c; echo bad"},
        ]

        result = discover_project(self.root, compile_database=self.database(entries))

        reasons = {item["reason"] for item in result["rejected_entries"]}
        self.assertTrue(
            {
                "compiler_unsupported",
                "compile_only_flag_missing",
                "source_argument_missing",
                "command_shell_syntax_unsupported",
            }
            <= reasons
        )
        self.assertIn("no_c_translation_units", result["blockers"])

    def test_external_paths_and_sensitive_defines_are_redacted(self) -> None:
        self.write("unit.c", "int unit(void) { return 0; }\n")
        outside = self.root.parent / "private-sdk"
        compiler = self.root.parent / "toolchain" / "clang.exe"
        entry = self.entry(
            "unit.c",
            [
                str(compiler),
                "-I",
                str(outside),
                "-DAPI_TOKEN=do-not-publish",
                "-DPUBLIC_MODE=1",
                "--sysroot",
                str(outside),
                "-c",
                "unit.c",
                "-o",
                "unit.o",
            ],
            output="unit.o",
        )

        result = discover_project(self.root, compile_database=self.database([entry]))

        self.assertEqual("ready", result["status"])
        unit = result["translation_units"][0]
        self.assertEqual("clang", unit["compiler"])
        self.assertEqual(1, unit["redacted_define_count"])
        self.assertEqual([{"name": "PUBLIC_MODE", "value": "1"}], unit["defines"])
        self.assertEqual("<external-path>", unit["includes"][0]["path"])
        self.assertEqual(["--sysroot", "<external-path>"], unit["semantic_flags"])
        serialized = json.dumps(result)
        self.assertNotIn("do-not-publish", serialized)
        self.assertNotIn(str(outside), serialized)
        self.assertNotIn(str(compiler), serialized)

    def test_outputs_are_derived_or_bound_and_mismatches_fail_closed(self) -> None:
        for name in ("good", "mismatch", "outside"):
            self.write(f"{name}.c", f"int {name}(void) {{ return 0; }}\n")
        external_output = self.root.parent / "outside.o"
        entries = [
            self.entry("good.c", ["clang", "-c", "good.c"]),
            self.entry(
                "mismatch.c",
                ["clang", "-c", "mismatch.c", "-o", "actual.o"],
                output="declared.o",
            ),
            self.entry(
                "outside.c",
                ["clang", "-c", "outside.c", "-o", str(external_output)],
            ),
        ]

        result = discover_project(self.root, compile_database=self.database(entries))

        self.assertEqual("good.o", result["translation_units"][0]["output"])
        reasons = {item["reason"] for item in result["rejected_entries"]}
        self.assertIn("compile_output_binding_mismatch", reasons)
        self.assertIn("compile_output_outside_repository", reasons)

    def test_cmake_declared_output_may_be_database_directory_relative(self) -> None:
        self.write("src/unit.c", "int unit(void) { return 0; }\n")
        (self.root / "build/subdir").mkdir(parents=True)
        database = self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root / "build/subdir"),
            "file": str(self.root / "src/unit.c"),
            "arguments": [
                "clang", "-c", str(self.root / "src/unit.c"),
                "-o", "CMakeFiles/unit.dir/unit.c.o",
            ],
            "output": "subdir/CMakeFiles/unit.dir/unit.c.o",
        }]))

        result = discover_project(self.root, compile_database=database)

        self.assertEqual("ready", result["status"], result)
        self.assertEqual(
            "build/subdir/CMakeFiles/unit.dir/unit.c.o",
            result["translation_units"][0]["output"],
        )

    def test_build_fact_scan_limit_blocks_incomplete_discovery(self) -> None:
        self.write("unit.c", "int unit(void) { return 0; }\n")
        self.write("nested/CMakeLists.txt", "project(limit C)\n")
        database = self.database([self.entry("unit.c", ["clang", "-c", "unit.c"])])

        with mock.patch.object(build_facts, "MAX_BUILD_DIRECTORIES", 1):
            result = discover_project(self.root, compile_database=database)

        self.assertEqual("blocked", result["status"])
        self.assertIn("build_fact_directory_limit_exceeded", result["blockers"])

    def test_source_and_response_files_must_remain_inside_repository(self) -> None:
        outside_source = self.root.parent / f"{self.root.name}-outside.c"
        outside_response = self.root.parent / f"{self.root.name}-outside.rsp"
        outside_source.write_text("int outside(void);\n", encoding="utf-8")
        outside_response.write_text("-DOUTSIDE=1\n", encoding="utf-8")
        self.addCleanup(outside_source.unlink, missing_ok=True)
        self.addCleanup(outside_response.unlink, missing_ok=True)
        self.write("inside.c", "int inside(void) { return 0; }\n")
        entries = [
            self.entry(
                f"../{outside_source.name}",
                ["clang", "-c", f"../{outside_source.name}"],
            ),
            self.entry(
                "inside.c",
                ["clang", f"@../{outside_response.name}", "-c", "inside.c"],
            ),
        ]
        result = discover_project(self.root, compile_database=self.database(entries))
        reasons = {item["reason"] for item in result["rejected_entries"]}
        self.assertEqual(
            {"source_path_outside_repository", "response_file_path_outside_source_root"},
            reasons,
        )

    def test_invalid_json_command_external_database_and_unit_cap_fail_closed(self) -> None:
        invalid = self.write("build/compile_commands.json", "{not-json}\n")
        self.assertEqual(
            ["compile_database_invalid_json"],
            discover_project(self.root, compile_database=invalid)["blockers"],
        )
        self.write("broken.c", "int broken(void);\n")
        broken = self.database([
            {"directory": ".", "file": "broken.c", "command": "clang 'unterminated"}
        ])
        self.assertIn(
            "command_parse_invalid",
            discover_project(self.root, compile_database=broken)["blockers"],
        )
        external_root = Path(tempfile.mkdtemp(prefix="external-database-"))
        self.addCleanup(external_root.rmdir)
        external = external_root / "compile_commands.json"
        external.write_text("[]\n", encoding="utf-8")
        self.addCleanup(external.unlink, missing_ok=True)
        result = discover_project(self.root, compile_database=external)
        self.assertEqual("invalid", result["compile_database"]["status"])

        for name in ("one", "two"):
            self.write(f"{name}.c", f"int {name}(void) {{ return 0; }}\n")
        capped = self.database([
            self.entry(f"{name}.c", ["clang", "-c", f"{name}.c"])
            for name in ("one", "two")
        ])
        limited = discover_project(self.root, compile_database=capped, max_units=1)
        self.assertEqual(["translation_unit_limit_exceeded"], limited["blockers"])
        self.assertEqual(
            ["max_units_invalid"],
            discover_project(self.root, compile_database=capped, max_units=0)["blockers"],
        )

    @staticmethod
    def entry(
        source: str, arguments: list[str], *, output: str | None = None
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "directory": ".",
            "file": source,
            "arguments": arguments,
        }
        if output is not None:
            result["output"] = output
        return result


if __name__ == "__main__":
    unittest.main()
