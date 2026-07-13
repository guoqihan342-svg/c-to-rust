from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
)
from validation.tools._project_migration_harness.sandbox_linux_probe import (
    bubblewrap_version,
    run_bubblewrap_probe,
)
from validation.tools._project_migration_harness.sandbox_probe import (
    SandboxProbeReceipt,
    validate_probe_receipt,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    ENVIRONMENT_ALLOWLIST,
)


HOST_NAMESPACES = {
    "mnt": "mnt:[1]", "net": "net:[1]",
    "pid": "pid:[1]", "user": "user:[1]",
}


def contract() -> SandboxContract:
    return SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256="1" * 64,
        toolchain_sha256="2" * 64,
    )


def _failed_cleanup(root: Path) -> bool:
    shutil.rmtree(root)
    return False


class ProbeExecutor:
    def __init__(self, *, extra_route: bool = False) -> None:
        self.extra_route = extra_route
        self.calls = 0

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls += 1
        runtime = Path(kwargs["cwd"])
        namespaces = "".join(
            f"{name}={value}-guest\n"
            for name, value in sorted(HOST_NAMESPACES.items())
        )
        environment = "".join(
            f"{name}=bounded\n" for name in ENVIRONMENT_ALLOWLIST
        ) + "PWD=/workspace\n"
        status = "".join(
            f"{name}:\t0000000000000000\n"
            for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        )
        limits = "\n".join((
            "Max cpu time              300                  300                  seconds",
            "Max file size             536870912            536870912            bytes",
            "Max address space         4294967296           4294967296           bytes",
            "Max processes             128                  128                  processes",
            "Max open files            256                  256                  files",
        )) + "\n"
        routes = "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
        if self.extra_route:
            routes += "eth0 00000000 0100007F 0003 0 0 0 00000000\n"
        for name, value in {
            "namespaces": namespaces,
            "environment": environment,
            "status": status,
            "limits": limits,
            "routes": routes,
        }.items():
            (runtime / name).write_text(value, encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)


class ProjectMigrationSandboxLinuxProbeTests(unittest.TestCase):
    def test_host_owned_probe_produces_a_bound_receipt_and_cleans_up(self) -> None:
        selected = contract()
        executor = ProbeExecutor()
        with tempfile.TemporaryDirectory(prefix="linux-probe-project-") as temporary:
            project = Path(temporary)
            with mock.patch(
                "validation.tools._project_migration_harness."
                "sandbox_linux_probe._host_namespaces",
                return_value=HOST_NAMESPACES,
            ):
                receipt = run_bubblewrap_probe(
                    contract=selected, backend_version="0.11.0",
                    project_root=project,
                    argv_builder=lambda _runtime, command: ["bwrap", *command],
                    executor=executor, preexec_fn=lambda: None,
                )

        self.assertIsInstance(receipt, SandboxProbeReceipt)
        self.assertEqual(1, executor.calls)
        validate_probe_receipt(receipt, selected, selected.requirements)

    def test_probe_rejects_a_network_route(self) -> None:
        selected = contract()
        with tempfile.TemporaryDirectory(prefix="linux-probe-route-") as temporary:
            with (
                mock.patch(
                    "validation.tools._project_migration_harness."
                    "sandbox_linux_probe._host_namespaces",
                    return_value=HOST_NAMESPACES,
                ),
                self.assertRaisesRegex(ValueError, "execution failed"),
            ):
                run_bubblewrap_probe(
                    contract=selected, backend_version="0.11.0",
                    project_root=Path(temporary),
                    argv_builder=lambda _runtime, command: ["bwrap", *command],
                    executor=ProbeExecutor(extra_route=True),
                    preexec_fn=lambda: None,
                )

    def test_cleanup_failure_invalidates_the_probe(self) -> None:
        selected = contract()
        with tempfile.TemporaryDirectory(prefix="linux-probe-cleanup-") as temporary:
            with (
                mock.patch(
                    "validation.tools._project_migration_harness."
                    "sandbox_linux_probe._host_namespaces",
                    return_value=HOST_NAMESPACES,
                ),
                mock.patch(
                    "validation.tools._project_migration_harness."
                    "sandbox_linux_probe._cleanup", side_effect=_failed_cleanup,
                ),
                self.assertRaisesRegex(ValueError, "did not satisfy"),
            ):
                run_bubblewrap_probe(
                    contract=selected, backend_version="0.11.0",
                    project_root=Path(temporary),
                    argv_builder=lambda _runtime, command: ["bwrap", *command],
                    executor=ProbeExecutor(), preexec_fn=lambda: None,
                )

    def test_backend_version_output_is_strict(self) -> None:
        def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, "bubblewrap 0.11.0\n", "")

        self.assertEqual("0.11.0", bubblewrap_version(Path("/usr/bin/bwrap"), runner=runner))

        def forged(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, "bubblewrap bad version\n", "")

        with self.assertRaisesRegex(ValueError, "version is untrusted"):
            bubblewrap_version(Path("/usr/bin/bwrap"), runner=forged)


if __name__ == "__main__":
    unittest.main()
