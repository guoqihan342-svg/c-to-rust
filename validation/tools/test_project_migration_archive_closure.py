from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.archive_closure import (
    parse_archive_command,
)
from validation.tools._project_migration_harness.discovery import discover_project


class ProjectMigrationArchiveClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="archive-closure-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()

    def write(self, relative: str, data: str | bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def project(self, kind: str, *, ranlib_target: str = "libsample.a") -> Path:
        self.write("CMakeLists.txt", "add_library(sample STATIC src/unit.c)\n")
        self.write("src/unit.c", "int unit(void) { return 1; }\n")
        self.write("build/unit.o", b"object")
        self.write("build/libsample.a", b"archive")
        if ranlib_target != "libsample.a":
            self.write(f"build/{ranlib_target}", b"other-archive")
        if kind == "link-txt":
            self.write(
                "build/CMakeFiles/sample.dir/link.txt",
                "C:/toolchains/ar qc libsample.a unit.o\n"
                f"C:/toolchains/ranlib {ranlib_target}\n",
            )
        elif kind == "ninja":
            self.write(
                "build/CMakeFiles/rules.ninja",
                "rule C_STATIC_LIBRARY_LINKER\n"
                "  command = rm -f $TARGET_FILE && ar qc $TARGET_FILE $in "
                "&& ranlib $TARGET_FILE\n",
            )
            self.write(
                "build/build.ninja",
                "include CMakeFiles/rules.ninja\n"
                "build libsample.a: C_STATIC_LIBRARY_LINKER unit.o\n"
                "  TARGET_FILE = libsample.a\n",
            )
        else:
            raise ValueError("unknown archive test kind")
        return self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root),
            "file": "src/unit.c",
            "arguments": [
                "clang", "-c", "src/unit.c", "-o", "build/unit.o",
            ],
            "output": "build/unit.o",
        }]))

    def parse_archive(
        self, argv: list[str],
    ) -> tuple[dict | None, list[dict]]:
        return parse_archive_command(
            self.root,
            self.root / "build",
            {"path": "build/archive-command.txt"},
            argv,
        )

    def assert_archive_rejected(self, argv: list[str], kind: str) -> None:
        target, blockers = self.parse_archive(argv)
        self.assertIsNone(target)
        self.assertEqual({kind}, {item["kind"] for item in blockers})

    def test_msvc_lib_requires_exactly_one_non_empty_out(self) -> None:
        cases = (
            ("missing", ["lib.exe", "unit.obj"],
             "archive_target_output_missing"),
            ("empty", ["lib.exe", "/OUT:", "unit.obj"],
             "archive_target_output_missing"),
            ("duplicate", [
                "lib.exe", "/OUT:sample.lib", "/OUT:other.lib", "unit.obj",
            ], "archive_target_output_duplicate"),
        )
        for name, argv, blocker in cases:
            with self.subTest(name=name):
                self.assert_archive_rejected(argv, blocker)

    def test_msvc_lib_rejects_semantic_and_unknown_options(self) -> None:
        for option in (
            "/DEF:exports.def", "/MACHINE:X64", "/UNKNOWN", "-UNKNOWN",
        ):
            with self.subTest(option=option):
                self.assert_archive_rejected(
                    ["lib.exe", "/OUT:sample.lib", option, "unit.obj"],
                    "archive_option_unsupported",
                )

    def test_gnu_ar_accepts_only_modeled_create_operations(self) -> None:
        self.write("build/unit.o", b"object")
        self.write("build/libsample.a", b"archive")
        for token, operation in (
            ("qc", "qc"), ("cq", "cq"), ("rc", "rc"), ("cr", "cr"),
            ("rcs", "rcs"), ("-rcs", "rcs"), ("rcsD", "rcsD"),
        ):
            with self.subTest(token=token):
                target, blockers = self.parse_archive(
                    ["ar", token, "libsample.a", "unit.o"]
                )
                self.assertEqual([], blockers)
                self.assertIsNotNone(target)
                assert target is not None
                self.assertEqual(operation, target["archive_operation"])

    def test_gnu_ar_rejects_operand_consuming_and_unmodeled_modifiers(self) -> None:
        cases = (
            ("a-anchor", ["ar", "ra", "anchor.o", "libsample.a", "unit.o"]),
            ("b-anchor", ["ar", "rb", "anchor.o", "libsample.a", "unit.o"]),
            ("i-anchor", ["ar", "ri", "anchor.o", "libsample.a", "unit.o"]),
            ("N-count", ["ar", "rN", "1", "libsample.a", "unit.o"]),
            ("T-thin", ["ar", "rcsT", "libsample.a", "unit.o"]),
            ("thin-long", ["ar", "--thin", "rc", "libsample.a", "unit.o"]),
            ("unmodeled", ["ar", "ru", "libsample.a", "unit.o"]),
        )
        for name, argv in cases:
            with self.subTest(name=name):
                self.assert_archive_rejected(
                    argv, "archive_operation_unsupported"
                )

    def test_cmake_archive_and_ranlib_are_one_bound_target(self) -> None:
        closure = discover_project(
            self.root, compile_database=self.project("link-txt")
        )["generated_build_closure"]

        self.assertEqual("ready", closure["status"], closure)
        target = closure["target_link_closure"]["targets"][0]
        self.assertEqual("build/libsample.a", target["output"]["path"])
        self.assertEqual(["build/unit.o"], [item["path"] for item in target["inputs"]])
        self.assertEqual("qc", target["archive_operation"])
        self.assertEqual(["ranlib"], target["ranlib_drivers"])

    def test_ninja_archive_rule_is_lowered_without_execution(self) -> None:
        closure = discover_project(
            self.root, compile_database=self.project("ninja")
        )["generated_build_closure"]

        self.assertEqual("ready", closure["status"], closure)
        target = closure["target_link_closure"]["targets"][0]
        self.assertEqual("ar", target["driver"])
        self.assertEqual(["ranlib"], target["ranlib_drivers"])
        self.assertEqual("build/libsample.a", target["output"]["path"])
        self.assertFalse(closure["claim_boundary"]["commands_executed"])

    def test_ranlib_must_bind_the_same_archive(self) -> None:
        closure = discover_project(
            self.root,
            compile_database=self.project("link-txt", ranlib_target="other.a"),
        )["generated_build_closure"]

        self.assertEqual("blocked", closure["status"])
        self.assertIn(
            "ranlib_target_mismatch",
            {item["kind"] for item in closure["blockers"]},
        )

    def test_cmake_subdirectory_link_script_uses_subdirectory_cwd(self) -> None:
        self.write("CMakeLists.txt", "add_subdirectory(lib)\n")
        self.write("src/unit.c", "int unit(void) { return 1; }\n")
        self.write("build/lib/CMakeFiles/sample.dir/unit.o", b"object")
        self.write("build/lib/libsample.a", b"archive")
        self.write(
            "build/lib/CMakeFiles/sample.dir/link.txt",
            "ar qc libsample.a CMakeFiles/sample.dir/unit.o\n"
            "ranlib libsample.a\n",
        )
        database = self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root / "build/lib"),
            "file": str(self.root / "src/unit.c"),
            "arguments": [
                "clang", "-c", str(self.root / "src/unit.c"),
                "-o", "CMakeFiles/sample.dir/unit.o",
            ],
            "output": "lib/CMakeFiles/sample.dir/unit.o",
        }]))

        closure = discover_project(
            self.root, compile_database=database
        )["generated_build_closure"]

        self.assertEqual("ready", closure["status"], closure)
        target = closure["target_link_closure"]["targets"][0]
        self.assertEqual("build/lib/libsample.a", target["output"]["path"])


if __name__ == "__main__":
    unittest.main()
