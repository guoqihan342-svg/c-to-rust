from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_test_inventory import (
    collect_project_test_inventory,
)
from validation.tools._project_migration_harness.make_build_ir_adapter import (
    MAKE_INPUT_KIND,
)
from validation.tools._project_migration_harness.make_build_ir_projection import (
    MAKE_RAW_ROLE,
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

    def test_mixed_system_selects_ctest_from_bound_compile_evidence(self) -> None:
        build_ir = self.bind_compile_database([
            "cc", "-c", "unit.c", "-o", "CMakeFiles/suite.dir/unit.c.o",
        ])
        self.discovery["build_system_facts"]["systems"] = ["cmake", "make"]
        expected = {"status": "ready", "adapter": "ctest-json-v1"}
        with (
            mock.patch(
                MODULE + "collect_ctest_json",
                return_value={
                    "status": "collected",
                    "observation": {"artifact_kind": "ctest-json-v1-observation"},
                },
            ) as ctest_collector,
            mock.patch(
                MODULE + "inventory_from_ctest_observation", return_value=expected,
            ),
            mock.patch(MODULE + "collect_make_test_dry_run") as make_collector,
        ):
            actual = collect_project_test_inventory(
                self.root, self.discovery, build_ir, output=self.output,
            )

        self.assertEqual(expected, actual)
        ctest_collector.assert_called_once()
        make_collector.assert_not_called()

    def test_mixed_system_selects_make_from_bound_compile_evidence(self) -> None:
        build_ir = self.bind_compile_database([
            "cc", "-c", "unit.c", "-MF", ".deps/unit.Tpo", "-o", "unit.o",
        ])
        self.discovery["build_system_facts"]["systems"] = ["cmake", "make"]
        expected = {"status": "ready", "adapter": "make-dry-run-v1"}
        with (
            mock.patch(
                MODULE + "collect_make_test_dry_run",
                return_value={
                    "status": "collected",
                    "observation": {"artifact_kind": "make-dry-run-v1-observation"},
                },
            ) as make_collector,
            mock.patch(
                MODULE + "inventory_from_make_observation", return_value=expected,
            ),
            mock.patch(MODULE + "collect_ctest_json") as ctest_collector,
        ):
            actual = collect_project_test_inventory(
                self.root, self.discovery, build_ir, output=self.output,
            )

        self.assertEqual(expected, actual)
        make_collector.assert_called_once()
        ctest_collector.assert_not_called()

    def test_mixed_system_without_unique_evidence_fails_closed(self) -> None:
        cases = (
            (["cc", "-c", "unit.c", "-o", "unit.o"],
             "project_test_adapter_unbound"),
            (["cc", "-c", "unit.c", "-MF", ".deps/unit.Po", "-o",
              "CMakeFiles/suite.dir/unit.o"], "project_test_adapter_ambiguous"),
        )
        for arguments, code in cases:
            with self.subTest(code=code):
                build_ir = self.bind_compile_database(arguments)
                self.discovery["build_system_facts"]["systems"] = ["cmake", "make"]
                with (
                    mock.patch(MODULE + "collect_make_test_dry_run") as make,
                    mock.patch(MODULE + "collect_ctest_json") as ctest,
                ):
                    result = collect_project_test_inventory(
                        self.root, self.discovery, build_ir, output=self.output,
                    )
                self.assertEqual(code, result["blockers"][0]["code"])
                make.assert_not_called()
                ctest.assert_not_called()

    def test_mixed_system_rejects_unbound_build_ir_metadata(self) -> None:
        build_ir = self.bind_compile_database([
            "cc", "-c", "unit.c", "-o", "CMakeFiles/suite.dir/unit.o",
        ])
        build_ir["build_metadata"][0]["sha256"] = "0" * 64
        self.discovery["build_system_facts"]["systems"] = ["cmake", "make"]

        result = collect_project_test_inventory(
            self.root, self.discovery, build_ir, output=self.output,
        )

        self.assertEqual(
            "project_test_adapter_evidence_invalid",
            result["blockers"][0]["code"],
        )

    def test_mixed_system_accepts_unique_make_build_ir_provenance(self) -> None:
        makefile = self.root / "Makefile"
        makefile.write_text("test:\n\t./suite\n", encoding="ascii")
        self.discovery.update({
            "input_kind": MAKE_INPUT_KIND,
            "compile_database": {"status": "not-selected"},
        })
        self.discovery["build_system_facts"]["systems"] = ["cmake", "make"]
        build_ir = {
            "raw_fact_refs": [{"role": MAKE_RAW_ROLE}],
            "translation_units": [{
                "provenance": {"raw_fact_role": MAKE_RAW_ROLE},
            }],
            "targets": [],
            "build_metadata": [{"path": "Makefile"}],
        }
        expected = {"status": "ready", "adapter": "make-dry-run-v1"}
        with (
            mock.patch(
                MODULE + "collect_make_test_dry_run",
                return_value={
                    "status": "collected",
                    "observation": {"artifact_kind": "make-dry-run-v1-observation"},
                },
            ) as make_collector,
            mock.patch(
                MODULE + "inventory_from_make_observation", return_value=expected,
            ),
            mock.patch(MODULE + "collect_ctest_json") as ctest_collector,
        ):
            actual = collect_project_test_inventory(
                self.root, self.discovery, build_ir, output=self.output,
            )

        self.assertEqual(expected, actual)
        self.assertTrue(make_collector.call_args.args[1].samefile(self.root))
        ctest_collector.assert_not_called()

    def bind_compile_database(self, arguments: list[str]) -> dict:
        path = self.build / "compile_commands.json"
        data = json.dumps([{
            "directory": "build", "file": "unit.c", "arguments": arguments,
        }], sort_keys=True).encode("utf-8")
        path.write_bytes(data)
        binding = {
            "path": "build/compile_commands.json",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }
        self.discovery["compile_database"].update({"status": "bound", **binding})
        return {"build_metadata": [{
            **binding, "kind": "file", "materialized": True,
        }]}


if __name__ == "__main__":
    unittest.main()
