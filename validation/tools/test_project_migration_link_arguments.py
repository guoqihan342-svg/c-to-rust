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


if __name__ == "__main__":
    unittest.main()
