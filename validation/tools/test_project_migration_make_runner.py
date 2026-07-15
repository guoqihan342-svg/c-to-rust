from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, content_sha256,
)
from validation.tools._project_migration_harness.make_dry_run_host_evidence import (
    MAKE_REQUIRED_CAPABILITIES,
)
from validation.tools._project_migration_harness.make_dry_run_runner import (
    MakeDryRunExecution,
    MakeDryRunPreflight,
    create_make_dry_run_plan,
    run_make_dry_run,
)


class ControlledMakeBackend:
    def __init__(
        self, preflight: MakeDryRunPreflight, execution: MakeDryRunExecution,
    ) -> None:
        self.preflight_value = preflight
        self.execution_value = execution
        self.preflight_calls = 0
        self.execute_calls = 0
        self.make_args: list[str] | None = None

    def preflight(self, plan, *, project_root, runtime_root):
        self.preflight_calls += 1
        return self.preflight_value

    def execute(
        self, make_binary, make_args, *, project_root, runtime_root,
        plan, preflight,
    ):
        self.execute_calls += 1
        self.make_args = list(make_args)
        return self.execution_value


class MakeDryRunRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.makefile = self.ref("Makefile", b"all:\n")
        self.source = self.ref("src/unit.c", b"int unit(void);\n")
        self.toolchain = self.ref("evidence/toolchain.json", b"toolchain\n")
        self.plan = create_make_dry_run_plan(
            makefile_ref=self.makefile,
            input_refs=[self.source],
            toolchain_ref=self.toolchain,
            targets=["all"],
            timeout_seconds=30,
        )

    @staticmethod
    def ref(path: str, data: bytes) -> dict[str, object]:
        return {
            "path": path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }

    def preflight(self, *, missing: str | None = None) -> MakeDryRunPreflight:
        return MakeDryRunPreflight(
            backend="controlled-test-backend",
            backend_version="test-1",
            plan_sha256=self.plan["plan_sha256"],
            toolchain_sha256=self.toolchain["sha256"],
            launcher_sha256="1" * 64,
            make_sha256="2" * 64,
            probe_observation_sha256="3" * 64,
            capability_results=tuple(
                (name, name != missing) for name in MAKE_REQUIRED_CAPABILITIES
            ),
            cleanup_ready=True,
        )

    def sandbox_ref(self, preflight: MakeDryRunPreflight) -> dict[str, object]:
        payload = preflight.payload()
        data = canonical_json_bytes(payload)
        return {
            "path": "evidence/sandbox.json",
            "sha256": content_sha256(payload),
            "size_bytes": len(data),
        }

    def execution(
        self, *, stdout: bytes = b"clang -c src/unit.c -o build/unit.o\n",
        timed_out: bool = False, cleanup: bool = True, returncode: int = 0,
    ) -> MakeDryRunExecution:
        return MakeDryRunExecution(
            stdout=stdout,
            stderr=b"",
            returncode=returncode,
            timed_out=timed_out,
            command_started=True,
            cleanup_verified=cleanup,
            plan_sha256=self.plan["plan_sha256"],
            command_sha256=content_sha256(self.plan["command"]),
        )

    def run_runner(self, backend, sandbox_ref):
        return run_make_dry_run(
            self.plan,
            project_root=Path("."),
            runtime_root=Path("target/runtime"),
            make_binary=Path("make"),
            toolchain_ref=self.toolchain,
            sandbox_ref=sandbox_ref,
            backend=backend,
        )

    def test_fixed_argv_runs_only_after_bound_preflight(self) -> None:
        preflight = self.preflight()
        backend = ControlledMakeBackend(preflight, self.execution())
        with mock.patch("subprocess.run", side_effect=AssertionError("direct process")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("direct process")):
            outcome = self.run_runner(backend, self.sandbox_ref(preflight))

        self.assertEqual("ready", outcome.status)
        self.assertEqual(1, backend.execute_calls)
        self.assertEqual(self.plan["command"][1:], backend.make_args)
        self.assertEqual(
            ["make", "-B", "-n", "-j1", "--no-print-directory",
             "-f", "Makefile", "--", "all"],
            self.plan["command"],
        )
        self.assertFalse(outcome.payload()["semantic_gate"])
        self.assertEqual(0, outcome.payload()["translation_coverage_numerator"])

    def test_missing_backend_and_capability_fail_before_make(self) -> None:
        missing = self.run_runner(None, self.ref("evidence/sandbox.json", b"missing"))
        self.assertEqual("make_host_backend_unavailable", missing.blocker)
        self.assertFalse(missing.make_started)

        preflight = self.preflight(missing="network-isolation")
        backend = ControlledMakeBackend(preflight, self.execution())
        blocked = self.run_runner(
            backend, self.ref("evidence/sandbox.json", b"invalid"),
        )
        self.assertEqual("make_host_capability_unavailable", blocked.blocker)
        self.assertEqual(0, backend.execute_calls)
        self.assertFalse(blocked.make_started)

    def test_timeout_output_flood_and_cleanup_are_blocked(self) -> None:
        cases = (
            ("timeout", self.execution(timed_out=True), "make_timeout"),
            (
                "flood",
                self.execution(stdout=b"x" * (self.plan["max_stdout_bytes"] + 1)),
                "make_output_flood",
            ),
            ("cleanup", self.execution(cleanup=False), "make_exit_cleanup_unverified"),
        )
        for name, execution, blocker in cases:
            with self.subTest(name=name):
                preflight = self.preflight()
                backend = ControlledMakeBackend(preflight, execution)
                outcome = self.run_runner(backend, self.sandbox_ref(preflight))
                self.assertEqual("blocked", outcome.status)
                self.assertEqual(blocker, outcome.blocker)
                self.assertEqual(1, backend.execute_calls)
                self.assertTrue(outcome.make_started)


if __name__ == "__main__":
    unittest.main()
