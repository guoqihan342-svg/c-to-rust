from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

from validation.tools._project_migration_harness.discovery import discover_project


SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RepositoryBuildDiscoveryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_database(
        self, relative: str, entries: list[object]
    ) -> Path:
        return self.write(
            relative,
            json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        )

    @staticmethod
    def arguments_entry(
        source: str,
        arguments: list[str],
        *,
        output: str | None = None,
    ) -> dict[str, object]:
        entry: dict[str, object] = {
            "directory": ".",
            "file": source,
            "arguments": arguments,
        }
        if output is not None:
            entry["output"] = output
        return entry

    def test_missing_database_fails_closed_but_reports_build_markers(self) -> None:
        self.write("CMakeLists.txt", "cmake_minimum_required(VERSION 3.20)\n")
        self.write("sub/Makefile", "all:\n\t@true\n")
        self.write("vendor/meson.build", "project('sample', 'c')\n")

        result = discover_project(self.root)

        self.assertEqual(1, result["schema_version"])
        self.assertEqual("blocked", result["status"])
        self.assertEqual("missing", result["compile_database"]["status"])
        self.assertEqual(["compile_database_not_found"], result["blockers"])
        facts = result["build_system_facts"]
        self.assertEqual("detected", facts["status"])
        self.assertEqual(["cmake", "make", "meson"], facts["systems"])
        self.assertEqual(
            ["CMakeLists.txt", "sub/Makefile", "vendor/meson.build"],
            [item["path"] for item in facts["markers"]],
        )
        self.assertFalse(facts["build_commands_executed"])
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertFalse(result["claim_boundary"]["translation_units_complete"])

    def test_discovery_orders_candidates_and_requires_explicit_override(self) -> None:
        source = self.write("src/unit.c", "int unit(void) { return 1; }\n")
        entry = self.arguments_entry(
            "src/unit.c", ["clang", "-c", "src/unit.c"]
        )
        root_database = self.write_database("compile_commands.json", [entry])
        build_database = self.write_database("build-debug/compile_commands.json", [entry])
        self.write_database("out-tree/nested/compile_commands.json", [entry])

        ambiguous = discover_project(self.root)

        self.assertEqual("blocked", ambiguous["status"])
        self.assertEqual("ambiguous", ambiguous["compile_database"]["status"])
        candidate_paths = [
            item["path"] for item in ambiguous["compile_database"]["candidates"]
        ]
        self.assertEqual(sorted(candidate_paths), candidate_paths)
        self.assertEqual(
            [
                "build-debug/compile_commands.json",
                "compile_commands.json",
                "out-tree/nested/compile_commands.json",
            ],
            candidate_paths,
        )
        self.assertEqual(["multiple_compile_databases"], ambiguous["blockers"])

        explicit = discover_project(self.root, compile_database=build_database)

        self.assertEqual("ready", explicit["status"])
        self.assertEqual("explicit", explicit["compile_database"]["selection"])
        self.assertEqual("build-debug/compile_commands.json", explicit["compile_database"]["path"])
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            explicit["translation_units"][0]["source"]["sha256"],
        )
        self.assertTrue(root_database.is_file())

    def test_arguments_commands_and_nested_response_files_preserve_variants(self) -> None:
        source = self.write("src/widget.c", "int widget(void) { return 7; }\n")
        self.write("src/widget.cpp", "int widget_cpp() { return 8; }\n")
        (self.root / "include").mkdir()
        flags = self.write(
            "build/flags.rsp",
            "-Iinclude -DLEVEL=1 @build/more.rsp\n",
        )
        nested = self.write("build/more.rsp", "-std=c11 -O2\n")
        entries: list[object] = [
            self.arguments_entry(
                "src/widget.c",
                [
                    "ccache",
                    "clang",
                    "@build/flags.rsp",
                    "-c",
                    "src/widget.c",
                    "-o",
                    "build/widget-debug.o",
                ],
                output="build/widget-debug.o",
            ),
            {
                "directory": ".",
                "file": "src/widget.c",
                "command": (
                    "clang -Iinclude -DLEVEL=2 -std=c17 -O3 -c "
                    "src/widget.c -o build/widget-release.o"
                ),
                "output": "build/widget-release.o",
            },
            self.arguments_entry(
                "src/widget.cpp",
                ["clang++", "-c", "src/widget.cpp"],
            ),
        ]
        database = self.write_database("build/compile_commands.json", entries)

        result = discover_project(self.root, compile_database=database)

        self.assertEqual("ready", result["status"])
        self.assertEqual([], result["blockers"])
        self.assertEqual(2, len(result["translation_units"]))
        by_entry = {item["entry"]["index"]: item for item in result["translation_units"]}
        debug = by_entry[0]
        release = by_entry[1]
        self.assertEqual("clang", debug["compiler"])
        self.assertEqual(["ccache"], debug["compiler_wrappers"])
        self.assertEqual("c", debug["language"])
        self.assertEqual(
            [{"kind": "user", "path": "include", "scope": "repository"}],
            debug["includes"],
        )
        self.assertEqual([{"name": "LEVEL", "value": "1"}], debug["defines"])
        self.assertEqual(["-std=c11", "-O2"], debug["semantic_flags"])
        self.assertEqual("build/widget-debug.o", debug["output"])
        self.assertEqual(
            ["build/flags.rsp", "build/more.rsp"],
            [item["path"] for item in debug["response_files"]],
        )
        response_hashes = {
            item["path"]: item["sha256"] for item in debug["response_files"]
        }
        self.assertEqual(hashlib.sha256(flags.read_bytes()).hexdigest(), response_hashes["build/flags.rsp"])
        self.assertEqual(hashlib.sha256(nested.read_bytes()).hexdigest(), response_hashes["build/more.rsp"])
        self.assertEqual([{"name": "LEVEL", "value": "2"}], release["defines"])
        self.assertEqual(["-std=c17", "-O3"], release["semantic_flags"])
        self.assertEqual("build/widget-release.o", release["output"])
        for unit in (debug, release):
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), unit["source"]["sha256"])
            self.assertRegex(unit["entry_sha256"], SHA256)
            self.assertRegex(unit["expanded_argv_sha256"], SHA256)
            self.assertRegex(unit["variant_id"], SHA256)
            self.assertEqual(unit["variant_id"], unit["unit_id"])
            self.assertEqual(2, unit["variant_count"])
        self.assertEqual({0, 1}, {debug["variant_index"], release["variant_index"]})
        self.assertEqual(
            ["non_c_translation_unit"],
            [item["reason"] for item in result["rejected_entries"]],
        )

    def test_exact_duplicate_variant_is_recorded_without_blocking(self) -> None:
        self.write("same.c", "int same(void) { return 0; }\n")
        entry = self.arguments_entry(
            "same.c",
            ["clang", "-DVALUE=1", "-c", "same.c", "-o", "same.o"],
            output="same.o",
        )
        database = self.write_database("compile_commands.json", [entry, entry])

        result = discover_project(self.root, compile_database=database)

        self.assertEqual("ready", result["status"])
        self.assertEqual(1, len(result["translation_units"]))
        self.assertEqual("exact_duplicate_variant", result["rejected_entries"][0]["reason"])
        self.assertEqual(0, result["rejected_entries"][0]["duplicate_of"])
        self.assertFalse(result["rejected_entries"][0]["blocking"])

    def test_unmaterialized_source_reports_repository_relative_path(self) -> None:
        database = self.write_database("build/compile_commands.json", [
            self.arguments_entry(
                "build/generated.c",
                ["clang", "-c", "build/generated.c", "-o", "build/generated.o"],
                output="build/generated.o",
            ),
        ])

        result = discover_project(self.root, compile_database=database)

        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            ["no_c_translation_units", "source_not_regular"], result["blockers"],
        )
        rejected = result["rejected_entries"][0]
        self.assertEqual("build/generated.c", rejected["source"])
        self.assertTrue(rejected["blocking"])

    def test_same_output_with_distinct_commands_rejects_all_ambiguous_variants(self) -> None:
        self.write("ambiguous.c", "int ambiguous(void) { return 0; }\n")
        entries = [
            self.arguments_entry(
                "ambiguous.c",
                ["clang", f"-DMODE={mode}", "-c", "ambiguous.c", "-o", "ambiguous.o"],
                output="ambiguous.o",
            )
            for mode in (1, 2)
        ]
        database = self.write_database("compile_commands.json", entries)

        result = discover_project(self.root, compile_database=database)

        self.assertEqual("blocked", result["status"])
        self.assertEqual([], result["translation_units"])
        self.assertEqual(["ambiguous_translation_unit_variants"], result["blockers"])
        self.assertEqual(
            ["ambiguous_variant_output", "ambiguous_variant_output"],
            [item["reason"] for item in result["rejected_entries"]],
        )
        self.assertTrue(all(item["blocking"] for item in result["rejected_entries"]))

    def test_language_selection_accepts_only_c_translation_units(self) -> None:
        self.write("forced.h", "int forced(void);\n")
        self.write("plain.c", "int plain(void) { return 1; }\n")
        self.write("wrong.c", "int wrong(void) { return 2; }\n")
        self.write("preprocessed.i", "int prepared(void) { return 3; }\n")
        entries = [
            self.arguments_entry("forced.h", ["clang", "-x", "c", "-c", "forced.h"]),
            self.arguments_entry("plain.c", ["g++", "-c", "plain.c"]),
            self.arguments_entry("wrong.c", ["clang", "-x", "c++", "-c", "wrong.c"]),
            self.arguments_entry("preprocessed.i", ["clang", "-c", "preprocessed.i"]),
        ]
        database = self.write_database("compile_commands.json", entries)

        result = discover_project(self.root, compile_database=database)

        self.assertEqual("ready", result["status"])
        self.assertEqual(
            {"forced.h": "c", "preprocessed.i": "c-cpp-output"},
            {item["source"]["path"]: item["language"] for item in result["translation_units"]},
        )
        self.assertEqual(
            ["non_c_translation_unit", "non_c_translation_unit"],
            [item["reason"] for item in result["rejected_entries"]],
        )

if __name__ == "__main__":
    unittest.main()
