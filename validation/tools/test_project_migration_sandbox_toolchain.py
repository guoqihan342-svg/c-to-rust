from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_verification import (
    _cargo_binary,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_linux import (
    BubblewrapBackend,
    discover_sandbox_backend,
)
from validation.tools._project_migration_harness.sandbox_toolchain import (
    resolve_toolchain,
    toolchain_sha256,
)
from validation.tools.project_migration_sandbox_test_support import (
    executable,
    toolchain,
    triples,
)


class ProjectMigrationSandboxToolchainTests(unittest.TestCase):
    def test_rustup_cargo_proxy_is_preserved_for_toolchain_resolution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-rustup-proxy-") as temporary:
            rustup = Path(temporary) / "rustup"
            rustup.write_bytes(b"test rustup proxy")
            with mock.patch(
                "validation.tools._project_migration_harness.project_verification.shutil.which",
                return_value=str(rustup),
            ):
                self.assertEqual(rustup.resolve(), _cargo_binary("cargo"))

    def test_rustup_drift_is_bound_to_real_tools_and_pinned(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-rustup-drift-") as temporary:
            root = Path(temporary)
            project = root / "project"
            runtime = root / "runtime"
            project.mkdir()
            runtime.mkdir()
            proxy_content = b"stable rustup proxy"
            proxies = {
                name: executable(root / name, proxy_content)
                for name in ("cargo", "rustc", "rustdoc", "rustup")
            }
            rustup = proxies["rustup"]
            launcher = executable(root / "bwrap", b"bubblewrap")
            toolchains = {
                version: toolchain(root / f"toolchain-{version}", version)
                for version in ("a", "b")
            }
            active = {"version": "a"}

            def rustup_which(
                argv: list[str], **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                self.assertTrue(Path(argv[0]).samefile(rustup))
                self.assertEqual("which", argv[1])
                self.assertEqual("", kwargs["env"]["PATH"])
                path = toolchains[active["version"]][argv[-1]]
                return subprocess.CompletedProcess(argv, 0, f"{path}\n", "")

            with mock.patch(
                "validation.tools._project_migration_harness."
                "sandbox_toolchain.shutil.which",
                side_effect=lambda name: str(proxies[name]),
            ):
                first = resolve_toolchain(proxies["cargo"], project, runner=rustup_which)
                active["version"] = "b"
                second = resolve_toolchain(proxies["cargo"], project, runner=rustup_which)

            shim_hash = hashlib.sha256(rustup.read_bytes()).hexdigest()
            shim_only = canonical_sha256({
                name: shim_hash for name in ("cargo", "rustc", "rustdoc")
            })
            self.assertEqual(
                toolchain_sha256(first.paths(), first.root), first.sha256
            )
            self.assertNotEqual(shim_only, first.sha256)
            self.assertNotEqual(first.sha256, second.sha256)

            contract = SandboxContract(
                backend="bubblewrap-v1",
                launcher_sha256="4" * 64,
                toolchain_sha256=first.sha256,
                cpu_seconds=60,
            )
            observed: list[list[str]] = []

            def executor(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                observed.append(argv)
                (runtime / "check-command-started").write_text(
                    f"{contract.sha256}\n{canonical_sha256(['cargo', 'check'])}\n",
                    encoding="ascii",
                )
                return subprocess.CompletedProcess(argv, 0)

            backend = BubblewrapBackend(
                launcher, first.paths(), contract, executor=executor,
                requested_cargo=proxies["cargo"], toolchain_root=first.root,
            )
            result = backend.execute(
                proxies["cargo"], ["check"], project_root=project,
                runtime_root=runtime, timeout_seconds=60,
            )

            argv = observed[0]
            self.assertTrue(result.command_started)
            self.assertIn(["--ro-bind", str(first.root), "/toolchain"], triples(argv))
            self.assertNotIn(str(second.root), argv)
            self.assertFalse(any(str(path) in argv for path in proxies.values()))
            self.assertIn("--unshare-all", argv)
            self.assertNotIn("--share-net", argv)
            self.assertIn("/toolchain/bin/cargo", argv)

            first.rustc.write_bytes(b"drifted rustc")
            with self.assertRaisesRegex(ValueError, "content drifted"):
                backend.execute(
                    proxies["cargo"], ["check"], project_root=project,
                    runtime_root=runtime, timeout_seconds=60,
                )
            self.assertEqual(1, len(observed))

            first.rustc.write_bytes(b"a-rustc")
            first.rustc.chmod(0o755)
            library = first.root / "lib" / "libstd.rlib"
            library.write_bytes(b"drifted library")
            with self.assertRaisesRegex(ValueError, "content drifted"):
                backend.execute(
                    proxies["cargo"], ["check"], project_root=project,
                    runtime_root=runtime, timeout_seconds=60,
                )
            self.assertEqual(1, len(observed))

    def test_unreliable_rustup_resolution_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-rustup-reject-") as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            rustup = executable(root / "rustup", b"rustup proxy")
            first = toolchain(root / "first", "first")
            second = toolchain(root / "second", "second")

            def mixed_runner(
                argv: list[str], **_: object,
            ) -> subprocess.CompletedProcess[str]:
                tools = second if argv[-1] == "rustdoc" else first
                return subprocess.CompletedProcess(argv, 0, f"{tools[argv[-1]]}\n", "")

            with mock.patch(
                "validation.tools._project_migration_harness."
                "sandbox_toolchain.shutil.which",
                return_value=str(rustup),
            ):
                with self.assertRaisesRegex(ValueError, "one toolchain"):
                    resolve_toolchain(rustup, project, runner=mixed_runner)

            launcher = executable(root / "bwrap", b"bubblewrap")
            with (
                mock.patch(
                    "validation.tools._project_migration_harness.sandbox_linux.platform.system",
                    return_value="Linux",
                ),
                mock.patch(
                    "validation.tools._project_migration_harness.sandbox_linux.shutil.which",
                    return_value=str(launcher),
                ),
                mock.patch(
                    "validation.tools._project_migration_harness."
                    "sandbox_linux._validate_launcher",
                ),
                mock.patch(
                    "validation.tools._project_migration_harness."
                    "sandbox_linux.resolve_toolchain",
                    side_effect=ValueError("ambiguous rustup toolchain"),
                ),
            ):
                discovery = discover_sandbox_backend(rustup, project)
            self.assertIsNone(discovery.backend)
            self.assertEqual("sandbox_toolchain_untrusted", discovery.reason_code)


if __name__ == "__main__":
    unittest.main()
