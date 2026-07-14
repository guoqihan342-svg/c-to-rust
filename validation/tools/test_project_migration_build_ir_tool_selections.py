from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.build_ir_tool_selections import (
    bound_standard_tool_requests,
)
from validation.tools._project_migration_harness.build_ir_toolchains import (
    merge_tool_requests,
)
from validation.tools._project_migration_harness.discovery import discover_project


class ProjectMigrationBuildIRToolSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="tool-selection-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative: str, value: str | bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
        return path

    def database(self, arguments: list[str]) -> Path:
        return self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root / "build"),
            "file": str(self.root / "src/unit.c"),
            "arguments": arguments,
            "output": "unit.o",
        }]))

    def project(self, link_text: str, arguments: list[str]) -> dict:
        self.write("CMakeLists.txt", "project(generic C)\n")
        self.write("src/unit.c", "int unit(void) { return 0; }\n")
        self.write("build/unit.o", b"object")
        self.write("build/program", b"program")
        self.write("build/CMakeFiles/program.dir/link.txt", link_text)
        database = self.database(arguments)
        return discover_project(self.root, compile_database=database)

    def test_reopens_absolute_compile_wrapper_and_link_driver_tokens(self) -> None:
        compiler = "C:/host-tools/clang"
        wrapper = "C:/host-tools/ccache"
        discovery = self.project(
            f"{compiler} unit.o -o program\n",
            [wrapper, compiler, "-c", str(self.root / "src/unit.c"),
             "-o", "unit.o"],
        )

        self.assertEqual("ready", discovery["status"], discovery)
        self.assertNotIn("C:/host-tools", json.dumps(discovery))
        requests = merge_tool_requests(bound_standard_tool_requests(
            self.root, discovery, discovery["generated_build_closure"],
        ))
        self.assertEqual([
            {"token": wrapper, "roles": ["compiler-wrapper"]},
            {"token": compiler, "roles": [
                "compiler-driver", "linker-driver",
            ]},
        ], requests)

    def test_reopens_absolute_archive_and_ranlib_tokens(self) -> None:
        compiler = "C:/host-tools/clang"
        self.write("CMakeLists.txt", "add_library(generic STATIC src/unit.c)\n")
        self.write("src/unit.c", "int unit(void) { return 0; }\n")
        self.write("build/unit.o", b"object")
        self.write("build/libgeneric.a", b"archive")
        self.write(
            "build/CMakeFiles/generic.dir/link.txt",
            "C:/host-tools/ar qc libgeneric.a unit.o\n"
            "C:/host-tools/ranlib libgeneric.a\n",
        )
        database = self.database([
            compiler, "-c", str(self.root / "src/unit.c"), "-o", "unit.o",
        ])
        discovery = discover_project(self.root, compile_database=database)

        requests = merge_tool_requests(bound_standard_tool_requests(
            self.root, discovery, discovery["generated_build_closure"],
        ))
        self.assertEqual([
            {"token": "C:/host-tools/ar", "roles": ["archiver"]},
            {"token": compiler, "roles": ["compiler-driver"]},
            {"token": "C:/host-tools/ranlib", "roles": ["ranlib"]},
        ], requests)

    def test_command_local_environment_fails_closed(self) -> None:
        discovery = self.project(
            "clang unit.o -o program\n",
            ["env", "PATH=C:/other", "clang", "-c",
             str(self.root / "src/unit.c"), "-o", "unit.o"],
        )

        with self.assertRaisesRegex(ValueError, "command_environment_unsupported"):
            bound_standard_tool_requests(
                self.root, discovery, discovery["generated_build_closure"],
            )


if __name__ == "__main__":
    unittest.main()
