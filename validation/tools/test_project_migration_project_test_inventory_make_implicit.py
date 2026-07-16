from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.project_test_inventory_make_static import (
    collect_static_make_test_recipes,
)
from validation.tools._project_migration_harness.project_test_target_proposal import (
    load_project_test_target_proposal,
)
from validation.tools.test_project_migration_make_support import (
    make_test_target_proposal,
)


class StaticMakeImplicitPrerequisiteTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="static-make-implicit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        (self.build / "suite-bin").write_bytes(b"native-suite")
        self.proposal = load_project_test_target_proposal(
            make_test_target_proposal(self.root, "verify-core"),
        )

    def test_suffix_builtin_and_archive_chains_fail_closed(self) -> None:
        source = self.build / "suite-bin.c"
        source.write_text("int main(void) { return 0; }\n", encoding="ascii")
        cases = (
            ".c:\n\tcc $< -o $@\n"
            "verify-core: suite-bin\n\t./suite-bin --strict\n",
            "verify-core: suite-bin\n\t./suite-bin --strict\n",
        )
        for content in cases:
            with self.subTest(explicit_suffix_rule=content.startswith(".c:")):
                self._assert_blocked(content)
        source.unlink()
        for relative in ("RCS/suite-bin.c,v", "SCCS/s.suite-bin.c"):
            with self.subTest(archive_source=relative):
                archive = self.build / relative
                archive.parent.mkdir(exist_ok=True)
                archive.write_text("archived C source\n", encoding="ascii")
                self._assert_blocked(
                    "verify-core: suite-bin\n\t./suite-bin --strict\n",
                )
                archive.unlink()

    def _assert_blocked(self, makefile: str) -> None:
        (self.build / "Makefile").write_text(makefile, encoding="ascii")
        collected = collect_static_make_test_recipes(
            self.root, self.build, target_proposal=self.proposal,
        )
        self.assertEqual("blocked", collected["status"])
        self.assertTrue(
            collected["blocker"]["code"].startswith(
                "project_test_make_prerequisite_"
            ),
        )


if __name__ == "__main__":
    unittest.main()
