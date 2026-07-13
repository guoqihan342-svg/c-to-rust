from __future__ import annotations

from contextlib import ExitStack
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
from validation.tools._project_migration_harness.sandbox_requirements import (
    cargo_verification_plan, strict_sandbox_requirements,
)
from validation.tools._project_migration_harness.sandbox_probe import (
    make_probe_receipt,
)
from validation.tools._project_migration_harness.sandbox_toolchain import (
    ResolvedToolchain, resolve_toolchain,
    toolchain_sha256,
)
from validation.tools.project_migration_sandbox_test_support import (
    executable,
    passing_probe_receipt,
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
                launcher_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
                toolchain_sha256=first.sha256,
                requirements=strict_sandbox_requirements(cpu_seconds=60),
            )
            observed: list[list[str]] = []

            def executor(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                observed.append(argv)
                command_sha256 = canonical_sha256(["cargo", "check"])
                (runtime / f"sandbox-{command_sha256}.started").write_text(
                    f"{contract.sha256}\n{command_sha256}\n",
                    encoding="ascii",
                )
                return subprocess.CompletedProcess(argv, 0)

            backend = BubblewrapBackend(
                launcher, first.paths(), contract, executor=executor,
                requested_cargo=proxies["cargo"], toolchain_root=first.root,
            )
            plan = cargo_verification_plan(
                "cargo-check", ("cargo", "check"), "5" * 64,
                timeout_seconds=60, requirements=contract.requirements,
            )
            probe = passing_probe_receipt(contract)
            result = backend.execute(
                proxies["cargo"], ["check"], project_root=project,
                runtime_root=runtime, verification_plan=plan,
                probe_receipt=probe,
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
                    runtime_root=runtime, verification_plan=plan,
                    probe_receipt=probe,
                )
            self.assertEqual(1, len(observed))

            first.rustc.write_bytes(b"a-rustc")
            first.rustc.chmod(0o755)
            library = first.root / "lib" / "libstd.rlib"
            library.write_bytes(b"drifted library")
            with self.assertRaisesRegex(ValueError, "content drifted"):
                backend.execute(
                    proxies["cargo"], ["check"], project_root=project,
                    runtime_root=runtime, verification_plan=plan,
                    probe_receipt=probe,
                )
            self.assertEqual(1, len(observed))

            library.write_bytes(b"a-library")
            launcher.write_bytes(b"drifted bubblewrap")
            with self.assertRaisesRegex(ValueError, "launcher content drifted"):
                backend.execute(
                    proxies["cargo"], ["check"], project_root=project,
                    runtime_root=runtime, verification_plan=plan,
                    probe_receipt=probe,
                )
            self.assertEqual(1, len(observed))

            launcher.write_bytes(b"bubblewrap")
            launcher.chmod(0o755)
            wrong_version = make_probe_receipt(
                contract=contract, backend_version="different",
                capability_results={
                    name: True for name in contract.requirements.capabilities
                },
                raw_observation={"fixture": "wrong-version"},
                cleanup_verified=True,
            )
            with self.assertRaisesRegex(ValueError, "backend version drifted"):
                backend.execute(
                    proxies["cargo"], ["check"], project_root=project,
                    runtime_root=runtime, verification_plan=plan,
                    probe_receipt=wrong_version,
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

    def test_discovery_requires_a_successful_capability_probe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-probe-discovery-") as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            launcher = executable(root / "bwrap", b"bubblewrap")
            tools = toolchain(root / "toolchain", "stable")
            selected = ResolvedToolchain(
                cargo=tools["cargo"], rustc=tools["rustc"],
                rustdoc=tools["rustdoc"], root=tools["cargo"].parent.parent,
                sha256=toolchain_sha256(
                    tools, tools["cargo"].parent.parent,
                ),
            )

            def discover(probe_effect: object):
                with ExitStack() as stack:
                    stack.enter_context(mock.patch(
                        "validation.tools._project_migration_harness."
                        "sandbox_linux.platform.system", return_value="Linux",
                    ))
                    stack.enter_context(mock.patch(
                        "validation.tools._project_migration_harness."
                        "sandbox_linux.shutil.which", return_value=str(launcher),
                    ))
                    stack.enter_context(mock.patch(
                        "validation.tools._project_migration_harness."
                        "sandbox_linux._validate_launcher",
                    ))
                    stack.enter_context(mock.patch(
                        "validation.tools._project_migration_harness."
                        "sandbox_linux.resolve_toolchain", return_value=selected,
                    ))
                    stack.enter_context(mock.patch(
                        "validation.tools._project_migration_harness."
                        "sandbox_linux.bubblewrap_version", return_value="0.11.0",
                    ))
                    probe = stack.enter_context(mock.patch.object(
                        BubblewrapBackend, "probe", autospec=True,
                        side_effect=probe_effect,
                    ))
                    result = discover_sandbox_backend(tools["cargo"], project)
                    return result, probe.call_count

            discovered, probe_count = discover(
                lambda backend, _project: passing_probe_receipt(backend.contract),
            )
            self.assertIsNotNone(discovered.backend)
            self.assertIsNotNone(discovered.probe_receipt)
            self.assertEqual(1, probe_count)

            rejected, _ = discover(ValueError("probe failed"))
            self.assertIsNone(rejected.backend)
            self.assertEqual(
                "sandbox_capability_probe_failed", rejected.reason_code,
            )


if __name__ == "__main__":
    unittest.main()
