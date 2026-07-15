from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.closure_paths import (
    bind_repository_artifact,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)


class GeneratedClosureSymlinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="generated-link-closure-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()

    def write(self, relative: str, data: str | bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
        return path

    def symlink_or_skip(
        self, link: Path, target: str | Path, *, target_is_directory: bool = False,
    ) -> None:
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links unavailable: {error}")

    def project(self) -> Path:
        self.write("CMakeLists.txt", "add_executable(sample src/unit.c)\n")
        self.write("src/unit.c", "int unit(void) { return 1; }\n")
        self.write("build/generated/config.h", "#define VALUE 1\n")
        self.write("build/unit.o", b"object-v1")
        self.write("build/program.bin", b"target-v1")
        self.write(
            "build/CMakeFiles/generated.dir/link.txt",
            "clang unit.o -o program.bin -lm\n",
        )
        return self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root),
            "file": "src/unit.c",
            "arguments": [
                "clang", "-Ibuild/generated", "-c", "src/unit.c",
                "-o", "build/unit.o",
            ],
            "output": "build/unit.o",
        }]))

    def test_internal_directory_symlink_is_bound_without_alias_traversal(self) -> None:
        database = self.project()
        target = self.write(
            "build/generated/shared/value.h", "#define SHARED_VALUE 7\n"
        )
        self.symlink_or_skip(
            self.root / "build/generated/shared-alias",
            "shared",
            target_is_directory=True,
        )

        closure = discover_project(
            self.root, compile_database=database
        )["generated_build_closure"]

        self.assertEqual("ready", closure["status"], closure)
        include = closure["generated_include_roots"][0]
        self.assertEqual(4, include["entry_count"])
        self.assertEqual(
            (self.root / "build/generated/config.h").stat().st_size
            + target.stat().st_size,
            include["size_bytes"],
        )
        target.write_text("#define SHARED_VALUE 8\n", encoding="utf-8")
        verification = verify_generated_build_closure(self.root, closure)
        self.assertIn(
            {"kind": "artifact_sha256_drift", "path": "build/generated"},
            verification["blockers"],
        )

    def test_digest_binds_link_path_text_and_resolved_target(self) -> None:
        generated = self.root / "build/generated"
        first_target = self.write("build/generated/first.h", "same\n")
        self.write("build/generated/second.h", "same\n")
        link = generated / "alias.h"
        self.symlink_or_skip(link, "first.h")
        first = self._binding()

        link.unlink()
        self.symlink_or_skip(link, "./first.h")
        changed_text = self._binding()
        self.assertNotEqual(first["sha256"], changed_text["sha256"])

        link.unlink()
        self.symlink_or_skip(link, "second.h")
        changed_target = self._binding()
        self.assertNotEqual(changed_text["sha256"], changed_target["sha256"])

        link.unlink()
        self.symlink_or_skip(generated / "renamed.h", first_target.name)
        self.assertNotEqual(changed_target["sha256"], self._binding()["sha256"])

    def _binding(self) -> dict:
        return bind_repository_artifact(
            self.root, "build/generated", kind="directory"
        )


if __name__ == "__main__":
    unittest.main()
