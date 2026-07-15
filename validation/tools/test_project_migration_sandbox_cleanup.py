from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from collections.abc import Iterator

from validation.tools._project_migration_harness.project_verification import (
    run_cargo_generation_gates,
    run_cargo_project_gates,
)
from validation.tools._project_migration_harness.cargo_fact_commands import (
    CARGO_METADATA_ARGS,
)
from validation.tools._project_migration_harness.integration_generation import (
    recover_current_generation,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxDiscovery,
)
from validation.tools.project_migration_sandbox_test_support import (
    BoundBackend,
    managed_project,
    passing_probe_receipt,
)


class ProjectMigrationSandboxCleanupTests(unittest.TestCase):
    def test_success_requires_and_records_execution_root_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-cleanup-") as temporary:
            root = Path(temporary)
            project, cargo = managed_project(root)
            runtime = root / "runtime"
            backend = BoundBackend()

            with self._sandbox(backend, cargo):
                result = run_cargo_project_gates(
                    project, runtime_root=runtime, timeout_seconds=60,
                )

            self.assertEqual("passed", result["status"])
            self.assertTrue(result["sandbox"]["cleanup_verified"])
            self.assertEqual(2, len(backend.calls))
            self.assertEqual([], list(runtime.glob("cargo-sandbox-*")))
            self.assertNotIn("topology", result["proof_boundary"])

    def test_cleanup_failure_blocks_an_otherwise_passing_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-cleanup-fail-") as temporary:
            root = Path(temporary)
            project, cargo = managed_project(root)
            runtime = root / "runtime"
            backend = BoundBackend()

            with (
                self._sandbox(backend, cargo),
                mock.patch(
                    "validation.tools._project_migration_harness."
                    "project_verification._cleanup_execution_root",
                    return_value=False,
                ),
            ):
                result = run_cargo_project_gates(
                    project, runtime_root=runtime, timeout_seconds=60,
                )

            self.assertEqual("blocked", result["status"])
            self.assertFalse(result["sandbox"]["cleanup_verified"])
            self.assertIn(
                "sandbox_cleanup_failed",
                {item["code"] for item in result["diagnostics"]},
            )

    def test_fact_capture_runs_fixed_metadata_before_compile_and_test(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-cargo-facts-") as temporary:
            root = Path(temporary)
            project, cargo = managed_project(root)
            generation = recover_current_generation(project)
            self.assertIsNotNone(generation)
            backend = BoundBackend()
            with self._sandbox(backend, cargo):
                result = run_cargo_generation_gates(
                    generation,
                    runtime_root=root / "runtime",
                    timeout_seconds=60,
                    capture_raw_output=True,
                    capture_cargo_facts=True,
                )
        self.assertEqual("passed", result["status"])
        self.assertEqual(
            [
                list(CARGO_METADATA_ARGS),
                ["check", "--all-targets", "--all-features", "--offline",
                 "--locked", "--message-format=json"],
                ["test", "--all-targets", "--all-features", "--offline",
                 "--locked", "--message-format=json"],
            ],
            [item["cargo_args"] for item in backend.calls],
        )
        self.assertEqual(
            ["cargo", *CARGO_METADATA_ARGS],
            result["fact_probes"]["cargo-metadata"]["command"],
        )
        self.assertIn("topology", result["proof_boundary"])

    def test_fact_capture_without_raw_output_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "facts require raw"):
            run_cargo_generation_gates(
                Path("does-not-need-to-exist"),
                runtime_root=Path("does-not-need-to-exist"),
                capture_cargo_facts=True,
            )

    def test_timeout_is_an_environment_block_not_a_compile_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-timeout-") as temporary:
            root = Path(temporary)
            project, cargo = managed_project(root)
            backend = BoundBackend()
            with (
                self._sandbox(backend, cargo),
                mock.patch.object(
                    backend, "execute",
                    side_effect=subprocess.TimeoutExpired(["cargo", "check"], 60),
                ),
            ):
                result = run_cargo_project_gates(
                    project, runtime_root=root / "runtime", timeout_seconds=60,
                )
        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["cargo_executed"])
        self.assertIn(
            "cargo_timeout", {item["code"] for item in result["diagnostics"]},
        )

    def test_native_trace_without_linker_blocks_before_any_cargo(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-native-preflight-") as temporary:
            root = Path(temporary)
            project, cargo = managed_project(root)
            generation = recover_current_generation(project)
            self.assertIsNotNone(generation)
            runtime = root / "runtime"
            backend = BoundBackend()

            with self._sandbox(backend, cargo):
                result = run_cargo_generation_gates(
                    generation,
                    runtime_root=runtime,
                    timeout_seconds=60,
                    capture_raw_output=True,
                    capture_native_link_trace=True,
                )

            self.assertEqual("blocked", result["status"])
            self.assertFalse(result["cargo_executed"])
            self.assertEqual([], result["checks"])
            self.assertEqual([], backend.calls)
            self.assertEqual([], list(runtime.glob("cargo-sandbox-*")))
            self.assertEqual(
                "sandbox_native_linker_unavailable",
                result["sandbox"]["reason_code"],
            )
            self.assertEqual(
                ["sandbox_native_linker_unavailable"],
                [item["code"] for item in result["diagnostics"]],
            )

    @staticmethod
    @contextmanager
    def _sandbox(backend: BoundBackend, cargo: Path) -> Iterator[None]:
        with (
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_verification._cargo_binary",
                return_value=cargo,
            ),
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_verification.discover_sandbox_backend",
                return_value=SandboxDiscovery(
                    backend, None, passing_probe_receipt(backend.contract),
                ),
            ),
        ):
            yield


if __name__ == "__main__":
    unittest.main()
