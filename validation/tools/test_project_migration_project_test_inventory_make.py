from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_inventory_make import (
    AUTOMAKE_CHECK_COMMAND, MAKE_COMMAND, collect_make_test_dry_run,
    inventory_from_make_observation,
)
from validation.tools._project_migration_harness.project_test_inventory_automake import (
    select_make_test_command,
)


class MakeProjectTestInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="make-test-inventory-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.binary = self.build / "suite-bin"
        self.binary.write_bytes(b"native-test-binary")
        self.fixture = self.root / "fixture.txt"
        self.fixture.write_text("fixture", encoding="ascii")
        self.source_ref = {
            "path": "plan/make-observation.json", "sha256": "d" * 64,
            "size_bytes": 10,
        }

    def test_direct_mapped_command_derives_ctest_shaped_record(self) -> None:
        inventory = self.inventory([
            "MODE=portable ./suite-bin ../fixture.txt --strict",
        ])

        self.assertEqual("ready", inventory["status"])
        self.assertEqual("make-dry-run-v1", inventory["adapter"])
        self.assertEqual(1, len(inventory["tests"]))
        test = inventory["tests"][0]
        self.assertEqual("link-target", test["source_target_id"])
        self.assertEqual([
            {"kind": "repo-path", "path": "fixture.txt"},
            {"kind": "literal", "value": "--strict"},
        ], test["arguments"])
        self.assertEqual("build", test["working_directory"])
        self.assertEqual({
            "MODE": {"kind": "literal", "value": "portable"},
        }, test["environment"])
        self.assertEqual(120, test["timeout_seconds"])
        self.assertEqual(
            inventory["inventory_sha256"],
            content_sha256({
                key: value for key, value in inventory.items()
                if key != "inventory_sha256"
            }),
        )

    def test_presentation_only_commands_are_ignored(self) -> None:
        inventory = self.inventory([
            "/bin/echo preparing", "echo \"\"", "/usr/bin/printf ready",
            "./suite-bin --strict",
        ])

        self.assertEqual("ready", inventory["status"], inventory)
        self.assertEqual(1, len(inventory["tests"]))
        self.assertEqual(3, inventory["tests"][0]["source_index"])

    def test_presentation_only_output_does_not_hide_empty_inventory(self) -> None:
        inventory = self.inventory(["echo preparing", "printf ready"])

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_inventory_empty", inventory["blockers"][0]["code"],
        )

    def test_duplicate_mapped_command_fails_closed(self) -> None:
        inventory = self.inventory(["./suite-bin --strict", "./suite-bin --strict"])

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual([], inventory["tests"])
        self.assertEqual(
            "project_test_make_command_duplicate", inventory["blockers"][0]["code"],
        )

    def test_unmapped_only_command_fails_closed(self) -> None:
        inventory = self.inventory(["./not-a-build-output --strict"])

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_make_command_unmapped",
            inventory["blockers"][0]["code"],
        )

    def test_runner_and_compile_commands_cannot_be_silently_skipped(self) -> None:
        commands = (
            "python3 run-tests.py",
            "./custom-runner --all",
            "./echo hidden-test",
            "cc -c test-driver.c -o test-driver.o",
        )
        for command in commands:
            with self.subTest(command=command):
                inventory = self.inventory([command, "./suite-bin --strict"])
                self.assertEqual("blocked", inventory["status"])
                self.assertEqual([], inventory["tests"])
                self.assertEqual(
                    "project_test_make_command_unmapped",
                    inventory["blockers"][0]["code"],
                )

    def test_shell_operators_and_substitution_fail_closed(self) -> None:
        cases = (
            "./suite-bin | /usr/bin/cat",
            "./suite-bin > result.txt",
            "./suite-bin && ./suite-bin",
            "./suite-bin $(/usr/bin/printf hidden)",
            "./suite-bin `printf hidden`",
        )
        for line in cases:
            with self.subTest(line=line):
                inventory = self.inventory([line])
                self.assertEqual("blocked", inventory["status"])
                self.assertEqual(
                    "project_test_make_shell_control_rejected",
                    inventory["blockers"][0]["code"],
                )

    def test_observation_hash_drift_fails_closed(self) -> None:
        observation = self.observation(["./suite-bin --strict"])
        observation["stdout"] += "./suite-bin --changed\n"

        inventory = inventory_from_make_observation(
            self.root, self.build_ir(), observation,
            source_observation=self.source_ref,
        )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_make_schema_invalid", inventory["blockers"][0]["code"],
        )

    def test_empty_dry_run_fails_closed(self) -> None:
        inventory = self.inventory([])

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_inventory_empty", inventory["blockers"][0]["code"],
        )

    def test_collector_uses_fixed_argv_without_shell(self) -> None:
        make, bwrap = self.root / "make", self.root / "bwrap"
        make.write_bytes(b"make-tool")
        bwrap.write_bytes(b"bubblewrap-tool")
        completed = subprocess.CompletedProcess(
            ["bwrap"], 0, stdout=b"./suite-bin\n", stderr=b"",
        )
        module = (
            "validation.tools._project_migration_harness."
            "project_test_inventory_make"
        )
        with (
            patch(f"{module}.sys.platform", "linux"),
            patch(f"{module}.shutil.which", side_effect=[str(make), str(bwrap)]),
            patch(f"{module}.subprocess.run", return_value=completed) as runner,
        ):
            collected = collect_make_test_dry_run(self.root, self.build)

        self.assertEqual("collected", collected["status"])
        self.assertEqual(MAKE_COMMAND, collected["observation"]["command"])
        argv = runner.call_args.args[0]
        boundary = argv.index("--")
        self.assertEqual(
            ("/toolchain/bin/make", *MAKE_COMMAND[1:]),
            tuple(argv[boundary + 1:]),
        )
        environment = {
            argv[index + 1]: argv[index + 2]
            for index, value in enumerate(argv[:boundary]) if value == "--setenv"
        }
        self.assertEqual(
            {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"}, set(environment),
        )
        self.assertFalse(runner.call_args.kwargs["shell"])
        self.assertTrue(callable(runner.call_args.kwargs["preexec_fn"]))

    def test_automake_declarations_select_check_and_bind_manifest(self) -> None:
        manifest = self.root / "Makefile.am"
        manifest.write_text(
            "# TESTS = ignored\ncheck_PROGRAMS = suite-bin\n"
            "TESTS = $(check_PROGRAMS)\n",
            encoding="ascii",
        )

        selected = select_make_test_command(self.root)

        self.assertEqual("selected", selected["status"])
        self.assertEqual(AUTOMAKE_CHECK_COMMAND, selected["command"])
        binding = selected["target_binding"]
        self.assertEqual("automake-content-v1", binding["kind"])
        self.assertEqual(
            ["TESTS", "check_PROGRAMS"], binding["manifests"][0]["variables"],
        )

    def test_collector_executes_automake_check_dry_run(self) -> None:
        (self.root / "Makefile.am").write_text("TESTS = suite-bin\n", encoding="ascii")
        make, bwrap = self.root / "make", self.root / "bwrap"
        make.write_bytes(b"make-tool")
        bwrap.write_bytes(b"bubblewrap-tool")
        module = (
            "validation.tools._project_migration_harness."
            "project_test_inventory_make"
        )
        with (
            patch(f"{module}.sys.platform", "linux"),
            patch(f"{module}.shutil.which", side_effect=[str(make), str(bwrap)]),
            patch(
                f"{module}.subprocess.run",
                return_value=subprocess.CompletedProcess(["bwrap"], 0),
            ) as runner,
        ):
            collected = collect_make_test_dry_run(self.root, self.build)
        argv = runner.call_args.args[0]
        self.assertEqual(AUTOMAKE_CHECK_COMMAND, collected["observation"]["command"])
        self.assertEqual(
            tuple(AUTOMAKE_CHECK_COMMAND),
            ("make", *tuple(argv[argv.index("--") + 2:])),
        )

    def test_automake_manifest_drift_invalidates_observation(self) -> None:
        manifest = self.root / "Makefile.am"
        manifest.write_text("TESTS = suite-bin\n", encoding="ascii")
        observation = self.observation(["./suite-bin --strict"])
        manifest.write_text("TESTS = other-bin\n", encoding="ascii")

        inventory = inventory_from_make_observation(
            self.root, self.build_ir(), observation,
            source_observation=self.source_ref,
        )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_make_schema_invalid", inventory["blockers"][0]["code"],
        )

    def inventory(self, lines: list[str]) -> dict:
        return inventory_from_make_observation(
            self.root, self.build_ir(), self.observation(lines),
            source_observation=self.source_ref,
        )

    def build_ir(self) -> dict:
        data = self.binary.read_bytes()
        return {
            "targets": [{
                "target_id": "link-target", "kind": "link",
                "outputs": [{
                    "path": "build/suite-bin", "kind": "file",
                    "materialized": True,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }],
            }],
        }

    def observation(self, lines: list[str]) -> dict:
        selected = select_make_test_command(self.root)
        self.assertEqual("selected", selected["status"], selected)
        stdout = "" if not lines else "\n".join(lines) + "\n"
        raw = stdout.encode("utf-8")
        value = {
            "schema_version": 1,
            "artifact_kind": "make-dry-run-v1-observation",
            "command": selected["command"],
            "target_binding": selected["target_binding"],
            "build_directory": "build",
            "tool": {"basename": "make", "sha256": "a" * 64, "size_bytes": 1},
            "sandbox_launcher": {
                "basename": "bwrap", "sha256": "b" * 64, "size_bytes": 1,
            },
            "timeout_seconds": 30,
            "returncode": 0,
            "stdout": stdout,
            "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "stdout_size_bytes": len(raw),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "stderr_size_bytes": 0,
            "semantic_gate": False,
        }
        value["observation_sha256"] = content_sha256(value)
        return value


if __name__ == "__main__":
    unittest.main()
