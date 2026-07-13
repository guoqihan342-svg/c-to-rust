from pathlib import Path
import unittest


MAX_MODULE_LINES = 300


class ProjectMigrationSourceLayoutTests(unittest.TestCase):
    def test_a19_python_modules_stay_bounded_by_responsibility(self) -> None:
        root = Path(__file__).resolve().parents[2]
        tools = root / "validation" / "tools"
        project_package = tools / "_project_migration_harness"
        paths = [
            *project_package.glob("*.py"),
            *tools.glob("test_project_migration_*.py"),
            *tools.glob("project_migration_*_test_support.py"),
            tools / "project_migration_harness.py",
            tools / "project_migration_held_out.py",
        ]
        provider = tools / "_ai_candidate_harness_parts"
        paths.extend(
            provider / name
            for name in (
                "provider_process.py",
                "provider_readiness.py",
                "provider_readiness_response_files.py",
                "provider_runtime.py",
                "provider_session.py",
            )
        )

        offenders = {}
        for path in sorted(set(paths)):
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > MAX_MODULE_LINES:
                offenders[path.relative_to(root).as_posix()] = line_count

        self.assertEqual({}, offenders)


if __name__ == "__main__":
    unittest.main()
