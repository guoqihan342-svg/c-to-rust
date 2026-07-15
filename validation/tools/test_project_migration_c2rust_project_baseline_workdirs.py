from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline_workdirs import (
    translated_source_working_directories,
)


class C2RustProjectBaselineWorkdirTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="c2rust-project-workdirs-",
        )
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.repo = self.repo.resolve(strict=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_common_source_ancestor_can_trim_repository_prefix(self) -> None:
        source = self._source("third_party/engine/tests/unit.c")
        build = self.repo / "target/native-build/engine-tests"
        build.mkdir(parents=True)

        result = translated_source_working_directories(
            self.repo, (self._entry(source, build),),
        )

        self.assertEqual(
            "target/native-build/engine-tests",
            result["src/tests/unit.rs"],
        )
        self.assertEqual(
            "target/native-build/engine-tests",
            result["src/third_party/engine/tests/unit.rs"],
        )

    def test_trimmed_source_suffix_collision_does_not_guess_workdir(self) -> None:
        entries = tuple(
            self._entry(self._source(f"{prefix}/tests/runner.c"), self.repo)
            for prefix in ("vendor/first", "vendor/second")
        )

        result = translated_source_working_directories(self.repo, entries)

        self.assertNotIn("src/tests/runner.rs", result)
        self.assertEqual(".", result["src/vendor/first/tests/runner.rs"])
        self.assertEqual(".", result["src/vendor/second/tests/runner.rs"])

    def _source(self, relative: str) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("int main(void) { return 0; }\n", encoding="utf-8")
        return path

    @staticmethod
    def _entry(source: Path, directory: Path) -> dict[str, str]:
        return {"file": str(source), "directory": str(directory)}


if __name__ == "__main__":
    unittest.main()
