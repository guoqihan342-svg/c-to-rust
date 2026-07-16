from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_test_inventory import (
    collect_project_test_inventory,
)


MODULE = (
    "validation.tools._project_migration_harness.project_test_inventory."
)


class ProjectTestInventoryDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-test-dispatch-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.output = self.root / "artifacts"
        self.build.mkdir()
        self.output.mkdir()
        self.discovery = {
            "build_system_facts": {"systems": ["make"]},
            "compile_database": {"path": "build/compile_commands.json"},
        }

    def test_make_system_selects_make_collector_and_deriver(self) -> None:
        observation = {"artifact_kind": "make-dry-run-v1-observation"}
        expected = {"status": "ready", "adapter": "make-dry-run-v1"}
        with (
            mock.patch(
                MODULE + "collect_make_test_dry_run",
                return_value={"status": "collected", "observation": observation},
            ) as make_collector,
            mock.patch(
                MODULE + "inventory_from_make_observation", return_value=expected,
            ) as make_deriver,
            mock.patch(MODULE + "collect_ctest_json") as ctest_collector,
        ):
            actual = collect_project_test_inventory(
                self.root, self.discovery, {}, output=self.output,
            )

        self.assertEqual(expected, actual)
        make_collector.assert_called_once()
        collector_root, collector_build = make_collector.call_args.args
        self.assertTrue(Path(collector_root).samefile(self.root))
        self.assertTrue(Path(collector_build).samefile(self.build))
        make_deriver.assert_called_once()
        ctest_collector.assert_not_called()
        source = make_deriver.call_args.kwargs["source_observation"]
        self.assertEqual("plan/project-test-make-observation.json", source["path"])

    def test_make_collection_failure_preserves_generic_blocker(self) -> None:
        with mock.patch(
            MODULE + "collect_make_test_dry_run",
            return_value={"status": "blocked", "blocker": {"code": "no-test-target"}},
        ):
            inventory = collect_project_test_inventory(
                self.root, self.discovery, {}, output=self.output,
            )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual("no-test-target", inventory["blockers"][0]["code"])


if __name__ == "__main__":
    unittest.main()
