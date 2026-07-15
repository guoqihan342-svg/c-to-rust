from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from validation.tools._project_migration_harness.sandbox_bubblewrap_argv import (
    build_bubblewrap_argv,
    redacted_bubblewrap_argv,
    resource_limiter,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
)
from validation.tools._project_migration_harness.sandbox_environment import (
    bubblewrap_environment_args,
    canonical_environment_items,
    cargo_guest_environment,
)
from validation.tools._project_migration_harness.sandbox_linux import (
    BubblewrapBackend,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    strict_sandbox_requirements,
)
from validation.tools._project_migration_harness.sandbox_toolchain import (
    toolchain_sha256,
)
from validation.tools.project_migration_sandbox_test_support import (
    executable,
    toolchain,
    triples,
)


class ProjectMigrationSandboxBubblewrapArgvTests(unittest.TestCase):
    def test_direct_host_tool_uses_fixed_isolation_without_a_shell(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-bwrap-argv-") as temporary:
            root = Path(temporary).resolve()
            launcher = root / "bwrap"
            workspace = root / "workspace"
            runtime = root / "runtime"
            host_tool = root / "tools" / "clang"
            environment = canonical_environment_items(cargo_guest_environment())
            command = ("/toolchain/bin/clang", "--version")

            argv = build_bubblewrap_argv(
                launcher=launcher, workspace=workspace, runtime=runtime,
                tool_bindings=((host_tool, "/toolchain/bin/clang"),),
                environment=environment, guest_command=command,
            )

            self.assertEqual([
                str(launcher), "--die-with-parent", "--new-session",
                "--unshare-all", "--cap-drop", "ALL", "--clearenv",
            ], argv[:7])
            self.assertNotIn("--share-net", argv)
            self.assertIn(["--cap-drop", "ALL"], _pairs(argv))
            self.assertIn("--clearenv", argv)
            self.assertIn(["--proc", "/proc"], _pairs(argv))
            self.assertIn(["--dev", "/dev"], _pairs(argv))
            self.assertIn(["--tmpfs", "/tmp"], _pairs(argv))
            self.assertIn(["--dir", "/home"], _pairs(argv))
            self.assertIn(["--dir", "/home/sandbox"], _pairs(argv))
            self.assertIn(
                ["--ro-bind", str(workspace), "/workspace"], triples(argv),
            )
            self.assertIn(["--bind", str(runtime), "/runtime"], triples(argv))
            self.assertNotIn(
                ["--bind", str(workspace), "/workspace"], triples(argv),
            )
            self.assertNotIn(
                ["--ro-bind", str(runtime), "/runtime"], triples(argv),
            )
            self.assertIn(
                ["--ro-bind", str(host_tool), "/toolchain/bin/clang"],
                triples(argv),
            )
            environment_start = argv.index("--setenv")
            self.assertEqual(
                bubblewrap_environment_args(environment),
                argv[environment_start:argv.index("--chdir")],
            )
            self.assertEqual(
                ["--chdir", "/workspace", "--", *command],
                argv[-(len(command) + 3):],
            )
            self.assertNotIn("/bin/sh", argv)
            self.assertNotIn("sandbox-launch", argv)
            _assert_system_read_only_bindings(self, argv)

    def test_redaction_removes_every_host_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-bwrap-redact-") as temporary:
            root = Path(temporary).resolve()
            argv = build_bubblewrap_argv(
                launcher=root / "bwrap", workspace=root / "workspace",
                runtime=root / "runtime",
                tool_bindings=((root / "clang", "/toolchain/bin/clang"),),
                environment=canonical_environment_items(cargo_guest_environment()),
                guest_command=("/toolchain/bin/clang", "--version"),
            )

            redacted = redacted_bubblewrap_argv(argv)

            self.assertFalse(any(str(root) in value for value in redacted))
            self.assertGreaterEqual(redacted.count("<host-or-guest-path>"), 4)
            self.assertIn("/workspace", redacted)
            self.assertIn("/runtime", redacted)

    def test_cargo_argv_is_identical_to_the_legacy_builder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sandbox-cargo-argv-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            runtime = root / "runtime"
            workspace.mkdir()
            runtime.mkdir()
            launcher = executable(root / "bwrap", b"bubblewrap")
            tools = toolchain(root / "toolchain", "stable")
            environment = canonical_environment_items(cargo_guest_environment())
            cargo_args = ("check", "--locked")
            marker_name = "sandbox-marker.started"
            command_sha256 = "4" * 64

            for selected_root in (None, root / "toolchain"):
                with self.subTest(toolchain_root=selected_root):
                    contract = SandboxContract(
                        backend="bubblewrap-v1",
                        launcher_sha256=hashlib.sha256(
                            launcher.read_bytes(),
                        ).hexdigest(),
                        toolchain_sha256=toolchain_sha256(tools, selected_root),
                        requirements=strict_sandbox_requirements(),
                    )
                    backend = BubblewrapBackend(
                        launcher, tools, contract, requested_cargo=tools["cargo"],
                        toolchain_root=selected_root,
                    )

                    actual = backend._argv(
                        workspace, runtime, cargo_args, marker_name,
                        command_sha256, environment,
                    )
                    expected = _legacy_cargo_argv(
                        launcher=launcher, workspace=workspace, runtime=runtime,
                        tools=tools, toolchain_root=selected_root,
                        environment=environment, cargo_args=cargo_args,
                        marker_name=marker_name, contract_sha256=contract.sha256,
                        command_sha256=command_sha256,
                    )

                    self.assertEqual(expected, actual)

    def test_resource_limiter_preserves_all_contract_limits(self) -> None:
        requirements = strict_sandbox_requirements(
            cpu_seconds=11, address_space_bytes=12, file_size_bytes=13,
            process_count=14, open_files=15,
        )
        contract = SandboxContract(
            backend="bubblewrap-v1", launcher_sha256="1" * 64,
            toolchain_sha256="2" * 64, requirements=requirements,
        )
        calls: list[tuple[int, tuple[int, int]]] = []
        resource = SimpleNamespace(
            RLIMIT_CPU=1, RLIMIT_AS=2, RLIMIT_FSIZE=3,
            RLIMIT_NPROC=4, RLIMIT_NOFILE=5,
            setrlimit=lambda kind, value: calls.append((kind, value)),
        )

        with mock.patch.dict(sys.modules, {"resource": resource}):
            resource_limiter(contract)()

        self.assertEqual([
            (1, (11, 11)), (2, (12, 12)), (3, (13, 13)),
            (4, (14, 14)), (5, (15, 15)),
        ], calls)


def _legacy_cargo_argv(
    *, launcher: Path, workspace: Path, runtime: Path,
    tools: dict[str, Path], toolchain_root: Path | None,
    environment: tuple[tuple[str, str], ...], cargo_args: tuple[str, ...],
    marker_name: str, contract_sha256: str, command_sha256: str,
) -> list[str]:
    argv = [
        str(launcher), "--die-with-parent", "--new-session",
        "--unshare-all", "--cap-drop", "ALL", "--clearenv",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/workspace", "--dir", "/runtime",
        "--dir", "/toolchain", "--dir", "/toolchain/bin",
        "--dir", "/home", "--dir", "/home/sandbox", "--dir", "/etc",
    ]
    for system_path in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(system_path).exists():
            argv.extend(("--ro-bind", system_path, system_path))
    for host_path, guest_path in _legacy_system_files():
        argv.extend(("--ro-bind", host_path, guest_path))
    argv.extend((
        "--ro-bind", str(workspace), "/workspace",
        "--bind", str(runtime), "/runtime",
    ))
    if toolchain_root is None:
        for name, path in sorted(tools.items()):
            argv.extend(("--ro-bind", str(path), f"/toolchain/bin/{name}"))
    else:
        argv.extend(("--ro-bind", str(toolchain_root), "/toolchain"))
    argv.extend(bubblewrap_environment_args(environment))
    argv.extend((
        "--chdir", "/workspace", "--", "/bin/sh", "-c",
        "umask 077; printf '%s\\n%s\\n' \"$1\" \"$2\" > \"$3\" || exit 125; "
        "shift 3; exec \"$@\"",
        "sandbox-launch", contract_sha256, command_sha256,
        f"/runtime/{marker_name}", "/toolchain/bin/cargo", *cargo_args,
    ))
    return argv


def _legacy_system_files() -> list[tuple[str, str]]:
    result = []
    for value in ("/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/passwd", "/etc/group"):
        if Path(value).is_file():
            result.append((value, value))
    if Path("/etc/ld.so.conf.d").is_dir():
        result.append(("/etc/ld.so.conf.d", "/etc/ld.so.conf.d"))
    return result


def _assert_system_read_only_bindings(
    case: unittest.TestCase, argv: list[str],
) -> None:
    for system_path in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(system_path).exists():
            case.assertIn(
                ["--ro-bind", system_path, system_path], triples(argv),
            )
    for host_path, guest_path in _legacy_system_files():
        case.assertIn(["--ro-bind", host_path, guest_path], triples(argv))


def _pairs(values: list[str]) -> list[list[str]]:
    return [values[index:index + 2] for index in range(len(values) - 1)]


if __name__ == "__main__":
    unittest.main()
