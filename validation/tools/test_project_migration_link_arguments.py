from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.discovery import discover_project


class ProjectMigrationLinkArgumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="link-arguments-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative: str, data: str | bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def link_closure(self, argument: str) -> dict:
        source = self.write("src/main.c", "int main(void) { return 0; }\n")
        self.write("build/main.o", b"object")
        self.write("build/app", b"executable")
        self.write(
            "build/CMakeFiles/app.dir/link.txt",
            f"clang main.o {argument} -o app\n",
        )
        database = self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root / "build"),
            "file": str(source),
            "arguments": ["clang", "-c", str(source), "-o", "main.o"],
            "output": "main.o",
        }]))
        return discover_project(
            self.root, compile_database=database,
        )["generated_build_closure"]

    def test_safe_driver_flags_and_repository_rpath_are_normalized(self) -> None:
        compiler_token = "C:/toolchains/cc"
        source = self.write("src/main.c", "int main(void) { return 0; }\n")
        obj = self.write("build/CMakeFiles/app.dir/main.c.o", b"object")
        self.write("build/bin/app", b"executable")
        (self.root / "build/lib").mkdir(parents=True)
        rpath = (self.root / "build/lib").as_posix()
        self.write(
            "build/CMakeFiles/app.dir/link.txt",
            f"{compiler_token} -Wall -O3 -fPIC -DNDEBUG "
            f"-Wl,-rpath,{rpath}: CMakeFiles/app.dir/main.c.o -o bin/app\n",
        )
        database = self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root / "build"),
            "file": str(source),
            "arguments": [
                "C:/toolchains/ccache", compiler_token, "-c", str(source),
                "-o", "CMakeFiles/app.dir/main.c.o",
            ],
            "output": "CMakeFiles/app.dir/main.c.o",
        }]))

        closure = discover_project(
            self.root, compile_database=database
        )["generated_build_closure"]

        self.assertEqual("ready", closure["status"], closure)
        discovery = discover_project(self.root, compile_database=database)
        unit = discovery["translation_units"][0]
        self.assertEqual("cc", unit["compiler"])
        self.assertEqual(["ccache"], unit["compiler_wrappers"])
        self.assertNotIn(compiler_token, json.dumps(discovery))
        self.assertNotIn("C:/toolchains/ccache", json.dumps(discovery))
        target = closure["target_link_closure"]["targets"][0]
        self.assertEqual("cc", target["driver"])
        self.assertEqual("build/bin/app", target["output"]["path"])
        self.assertEqual(["build/CMakeFiles/app.dir/main.c.o"], [
            item["path"] for item in target["inputs"]
        ])
        self.assertIn(
            "-Wl,-rpath,<repository>/build/lib:",
            target["ordered_system_link_args"],
        )
        self.assertNotIn(str(self.root), json.dumps(closure))
        self.assertTrue(obj.is_file())

    def test_library_selectors_accept_only_portable_names(self) -> None:
        for argument in ("-lz", "-l:libalpha.so.1", "/DEFAULTLIB:alpha.lib"):
            with self.subTest(argument=argument):
                closure = self.link_closure(argument)
                self.assertEqual("ready", closure["status"], closure)
                target = closure["target_link_closure"]["targets"][0]
                self.assertIn(argument, target["ordered_system_link_args"])

    def test_library_like_options_cannot_smuggle_external_paths(self) -> None:
        for argument in (
            "-load=/outside/object/unit.o",
            "-l/outside/private/libalpha.a",
            "/DEFAULTLIB:/outside/object/unit.obj",
            "-lC:/outside/private/alpha.lib",
            "-plugin@/outside/private/plugin.so",
            "-Wl,@/outside/private/link.rsp",
            "-Wl,-T/outside/private/script.ld",
        ):
            with self.subTest(argument=argument):
                closure = self.link_closure(argument)
                self.assertEqual("blocked", closure["status"])
                self.assertNotIn(argument, json.dumps(closure))
                self.assertTrue({
                    "external_link_argument", "link_argument_unsupported",
                } & {item["kind"] for item in closure["blockers"]})


if __name__ == "__main__":
    unittest.main()
