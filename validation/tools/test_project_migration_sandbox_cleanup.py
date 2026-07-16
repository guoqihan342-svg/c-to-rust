from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
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
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.cargo_fact_commands import (
    CARGO_BUILD_ARGS, CARGO_METADATA_ARGS,
)
from validation.tools._project_migration_harness.integration_generation import (
    recover_current_generation,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxDiscovery,
)
from validation.tools._project_migration_harness.sandbox_native_linker_contract import (
    NativeLinkerContract,
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

    def test_structure_capture_runs_real_build_before_check_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-cargo-structure-") as temporary:
            root = Path(temporary)
            project, cargo = managed_project(root)
            generation = recover_current_generation(project)
            self.assertIsNotNone(generation)
            backend = _ProductBackend()
            runtime = root / "runtime"
            with self._sandbox(backend, cargo):
                result = run_cargo_generation_gates(
                    generation, runtime_root=runtime, timeout_seconds=60,
                    capture_raw_output=True, capture_cargo_facts=True,
                    capture_cargo_structure=True,
                )

        self.assertEqual("passed", result["status"])
        self.assertEqual(
            [list(CARGO_METADATA_ARGS), list(CARGO_BUILD_ARGS),
             ["check", "--all-targets", "--all-features", "--offline",
              "--locked", "--message-format=json"],
             ["test", "--all-targets", "--all-features", "--offline",
              "--locked", "--message-format=json"]],
            [item["cargo_args"] for item in backend.calls],
        )
        self.assertEqual(
            b"linked-product", result["_captured_rust_products"][0]["data"],
        )
        self.assertEqual([], list(runtime.glob("cargo-sandbox-*")))

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


class _ProductBackend(BoundBackend):
    def __init__(self):
        super().__init__()
        binding = {
            "driver": {"basename": "cc", "family": "gnu-compiler",
                       "sha256": "4" * 64},
            "linker": {"basename": "ld", "family": "linker",
                       "sha256": "5" * 64},
            "target_triple": "x86_64-unknown-linux-gnu",
        }
        self.contract = replace(self.contract, native_linker=NativeLinkerContract(
            driver_basename="cc", driver_sha256="4" * 64,
            linker_basename="ld", linker_sha256="5" * 64,
            target_triple="x86_64-unknown-linux-gnu",
            binding_sha256=content_sha256(binding),
        ))

    def execute(self, cargo_binary, cargo_args, **kwargs):
        result = super().execute(cargo_binary, cargo_args, **kwargs)
        if cargo_args[0] != "build":
            return result
        product = kwargs["runtime_root"] / "target" / "debug" / "app"
        product.parent.mkdir(parents=True, exist_ok=True)
        product.write_bytes(b"linked-product")
        product.with_suffix(".d").write_bytes(
            b"/runtime/target/debug/app: /workspace/pkg/src/main.rs\n\n",
        )
        artifact = {
            "reason": "compiler-artifact",
            "package_id": "path+file:///workspace/pkg#pkg@0.0.0",
            "manifest_path": "/workspace/pkg/Cargo.toml",
            "target": {
                "kind": ["bin"], "crate_types": ["bin"], "name": "app",
                "src_path": "/workspace/pkg/src/main.rs", "edition": "2021",
                "doc": True, "doctest": True, "test": True,
            },
            "profile": {
                "opt_level": "0", "debuginfo": 2,
                "debug_assertions": True, "overflow_checks": True,
                "test": False,
            },
            "features": [], "filenames": ["/runtime/target/debug/app"],
            "executable": "/runtime/target/debug/app", "fresh": False,
        }
        stdout = "\n".join((
            json.dumps(artifact, sort_keys=True, separators=(",", ":")),
            '{"reason":"build-finished","success":true}', "",
        ))
        completed = subprocess.CompletedProcess(
            result.completed.args, 0, stdout, "",
        )
        return replace(result, completed=completed)


if __name__ == "__main__":
    unittest.main()
