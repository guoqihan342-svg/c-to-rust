from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from validation.tools._project_migration_harness.artifacts import (
    content_sha256, write_json_artifact,
)
from validation.tools._project_migration_harness.project_test_inventory import (
    collect_project_test_inventory,
)
from validation.tools._project_migration_harness.project_test_inventory_adapter import (
    select_project_test_adapter,
)
from validation.tools._project_migration_harness.project_test_inventory_meson import (
    collect_meson_test_introspection,
)
from validation.tools._project_migration_harness.project_test_inventory_meson_parse import (
    inventory_from_meson_observation,
)
from validation.tools._project_migration_harness.project_test_inventory_validation import (
    reopen_manifest_project_test_inventory,
)
from validation.tools.project_migration_project_test_inventory_meson_test_support import (
    MesonInventoryTestCase,
)


COLLECTOR_MODULE = (
    "validation.tools._project_migration_harness.project_test_inventory_meson"
)
DISPATCH_MODULE = (
    "validation.tools._project_migration_harness.project_test_inventory."
)
VALIDATION_MODULE = (
    "validation.tools._project_migration_harness.project_test_inventory_validation."
)


class MesonProjectTestDispatchTests(MesonInventoryTestCase):
    def test_collector_uses_fixed_read_only_no_network_introspection(self) -> None:
        meson, bwrap = self.fake_tools()

        def execute(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            kwargs["stdout"].write(json.dumps(self.tests).encode("utf-8"))
            return subprocess.CompletedProcess(argv, 0)

        with (
            mock.patch(f"{COLLECTOR_MODULE}.sys.platform", "linux"),
            mock.patch(
                f"{COLLECTOR_MODULE}.shutil.which",
                side_effect=[str(meson), str(bwrap)],
            ),
            mock.patch(
                f"{COLLECTOR_MODULE}.subprocess.run", side_effect=execute,
            ) as runner,
        ):
            collected = collect_meson_test_introspection(
                self.root, self.build, self.database,
            )

        self.assertEqual("collected", collected["status"], collected)
        observation = collected["observation"]
        self.assertFalse(observation["tests_executed"])
        self.assertEqual(
            ["meson", "introspect", "--tests", "build"],
            observation["command"],
        )
        argv = runner.call_args.args[0]
        boundary = argv.index("--")
        self.assertEqual(
            ["/toolchain/bin/meson", "introspect", "--tests", "/workspace/build"],
            argv[boundary + 1:],
        )
        self.assertIn("--unshare-all", argv)
        self.assertIn("--ro-bind", argv)
        self.assertNotIn("--share-net", argv)
        self.assertIs(subprocess.DEVNULL, runner.call_args.kwargs["stdin"])
        self.assertFalse(runner.call_args.kwargs["shell"])
        self.assertTrue(callable(runner.call_args.kwargs["preexec_fn"]))

    def test_collector_blocks_malformed_and_oversized_output(self) -> None:
        meson, bwrap = self.fake_tools()

        def run_with(raw: bytes):
            def execute(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
                kwargs["stdout"].write(raw)
                return subprocess.CompletedProcess(argv, 0)
            with (
                mock.patch(f"{COLLECTOR_MODULE}.sys.platform", "linux"),
                mock.patch(
                    f"{COLLECTOR_MODULE}.shutil.which",
                    side_effect=[str(meson), str(bwrap)],
                ),
                mock.patch(
                    f"{COLLECTOR_MODULE}.subprocess.run", side_effect=execute,
                ),
            ):
                return collect_meson_test_introspection(
                    self.root, self.build, self.database,
                )

        malformed = run_with(b"{not-json")
        self.assertEqual(
            "project_test_meson_json_invalid", malformed["blocker"]["code"],
        )
        with mock.patch(f"{COLLECTOR_MODULE}.MAX_MESON_TEST_OUTPUT_BYTES", 8):
            oversized = run_with(b"123456789")
        self.assertEqual(
            "project_test_meson_output_limit_exceeded",
            oversized["blocker"]["code"],
        )

    def test_single_meson_dispatches_collector_and_deriver(self) -> None:
        observation = self.observation(self.tests)
        expected = {"status": "ready", "adapter": "meson-introspect-tests-v1"}
        with (
            mock.patch(
                DISPATCH_MODULE + "collect_meson_test_introspection",
                return_value={"status": "collected", "observation": observation},
            ) as collector,
            mock.patch(
                DISPATCH_MODULE + "inventory_from_meson_observation",
                return_value=expected,
            ) as derive,
        ):
            actual = collect_project_test_inventory(
                self.root, self.discovery, self.build_ir, output=self.root / "artifacts",
            )

        self.assertEqual(expected, actual)
        self.assertTrue(collector.call_args.args[1].samefile(self.build))
        self.assertTrue(collector.call_args.args[2].samefile(self.database))
        self.assertEqual(
            "plan/project-test-meson-observation.json",
            derive.call_args.kwargs["source_observation"]["path"],
        )

    def test_mixed_system_selection_requires_unique_bound_evidence(self) -> None:
        self.discovery["build_system_facts"]["systems"] = ["make", "meson"]
        selected = select_project_test_adapter(
            self.root, self.discovery, self.build_ir,
        )
        self.assertEqual("meson-introspect-tests-v1", selected["adapter"])

        changed = copy.deepcopy(self.build_ir)
        changed["translation_units"] = [{
            "output": {"path": "build/CMakeFiles/suite.dir/unit.c.o"},
        }]
        self.discovery["build_system_facts"]["systems"] = ["cmake", "meson"]
        ambiguous = select_project_test_adapter(
            self.root, self.discovery, changed,
        )
        self.assertEqual(
            "project_test_adapter_ambiguous", ambiguous["blocker"]["code"],
        )

    def test_discovery_marker_drift_blocks_selection(self) -> None:
        self.manifest.write_text("project('changed', 'c')\n", encoding="ascii")
        selected = select_project_test_adapter(
            self.root, self.discovery, self.build_ir,
        )
        self.assertEqual(
            "project_test_adapter_evidence_invalid",
            selected["blocker"]["code"],
        )

    def test_compile_database_drift_blocks_selection(self) -> None:
        self.database.write_text("[]", encoding="ascii")
        selected = select_project_test_adapter(
            self.root, self.discovery, self.build_ir,
        )
        self.assertEqual(
            "project_test_adapter_evidence_invalid",
            selected["blocker"]["code"],
        )

    def test_completion_recollects_every_bound_field_and_blocks_drift(self) -> None:
        observation = self.observation(self.tests)
        inventory = inventory_from_meson_observation(
            self.root, self.build_ir, observation,
            source_observation=write_json_artifact(
                self.root / "artifacts", "plan/meson-observation.json", observation,
            ),
        )
        artifacts = self.root / "artifacts"
        inventory_ref = write_json_artifact(
            artifacts, "plan/project-tests.json", inventory,
        )
        build_ref = write_json_artifact(artifacts, "plan/build-ir.json", {})
        manifest = {
            "build_ir": {"status": "bound", "artifact": build_ref},
            "project_test_inventory": {
                "status": "bound", "artifact": inventory_ref,
            },
        }
        with (
            mock.patch(
                VALIDATION_MODULE + "_reopen_manifest_build_ir",
                return_value=self.build_ir,
            ),
            mock.patch(
                VALIDATION_MODULE + "collect_meson_test_introspection",
                return_value={"status": "collected", "observation": observation},
            ) as collector,
        ):
            reopened = reopen_manifest_project_test_inventory(
                repo_root=self.root, artifact_root=artifacts,
                migration_manifest=manifest,
            )
        self.assertEqual(inventory, reopened)
        self.assertTrue(collector.call_args.args[2].samefile(self.database))

        drifted = copy.deepcopy(observation)
        drifted["tool"]["sha256"] = "f" * 64
        drifted["observation_sha256"] = content_sha256({
            key: value for key, value in drifted.items()
            if key != "observation_sha256"
        })
        with (
            mock.patch(
                VALIDATION_MODULE + "_reopen_manifest_build_ir",
                return_value=self.build_ir,
            ),
            mock.patch(
                VALIDATION_MODULE + "collect_meson_test_introspection",
                return_value={"status": "collected", "observation": drifted},
            ),
        ):
            with self.assertRaisesRegex(
                ValueError, "project_test_inventory_observation_drifted",
            ):
                reopen_manifest_project_test_inventory(
                    repo_root=self.root, artifact_root=artifacts,
                    migration_manifest=manifest,
                )

    def fake_tools(self) -> tuple[Path, Path]:
        tools = self.root.parent / "tools"
        tools.mkdir(exist_ok=True)
        meson, bwrap = tools / "meson", tools / "bwrap"
        meson.write_bytes(b"meson-tool")
        bwrap.write_bytes(b"bubblewrap-tool")
        return meson, bwrap


if __name__ == "__main__":
    unittest.main()
