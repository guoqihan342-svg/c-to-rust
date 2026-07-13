from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.closure_paths import (
    bind_repository_artifact,
)
from validation.tools._project_migration_harness.ninja_link_facts import (
    discover_ninja_link_commands,
)


class ProjectMigrationNinjaScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_build_header_variables_expand_at_parse_position(self) -> None:
        report = self._report(
            """cc = gcc
outdir = one
rule link
  command = $cc $in -o $out
build $outdir/first: link first.o
outdir = two
build $outdir/second: link second.o
"""
        )

        self.assertEqual("ready", report["status"])
        self.assertEqual(
            [
                ["gcc", "first.o", "-o", "one/first"],
                ["gcc", "second.o", "-o", "two/second"],
            ],
            [item["argv"] for item in report["commands"]],
        )

    def test_subninja_rule_shadow_does_not_escape_child_scope(self) -> None:
        (self.root / "child.ninja").write_text(
            """rule link
  command = gcc $in -o $out
build child: link child.o
""",
            encoding="utf-8",
        )
        report = self._report(
            """rule link
  command = clang $in -o $out
subninja child.ninja
build parent: link parent.o
"""
        )

        self.assertEqual("ready", report["status"])
        self.assertEqual(
            [
                ["gcc", "child.o", "-o", "child"],
                ["clang", "parent.o", "-o", "parent"],
            ],
            [item["argv"] for item in report["commands"]],
        )

    def test_subninja_inherits_later_parent_variable_value(self) -> None:
        (self.root / "child.ninja").write_text(
            "build child: link child.o\n", encoding="utf-8",
        )
        report = self._report(
            """cc = gcc
rule link
  command = $cc $in -o $out
subninja child.ninja
cc = clang
"""
        )

        self.assertEqual("ready", report["status"])
        self.assertEqual(
            [["clang", "child.o", "-o", "child"]],
            [item["argv"] for item in report["commands"]],
        )

    def _report(self, source: str) -> dict:
        ninja = self.root / "build.ninja"
        ninja.write_text(source, encoding="utf-8")
        fact = bind_repository_artifact(self.root, ninja, kind="file")
        return discover_ninja_link_commands(self.root, fact)


if __name__ == "__main__":
    unittest.main()
