from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import tempfile
from collections.abc import Iterator
import unittest
from unittest import mock

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract, contract_from_payload,
)
from validation.tools._project_migration_harness.sandbox_native_linker import (
    NativeLinkerToolchain,
    resolve_native_linker_toolchain,
    validate_native_linker_toolchain,
)
from validation.tools._project_migration_harness.sandbox_native_linker_contract import (
    native_linker_contract,
)


MODULE = (
    "validation.tools._project_migration_harness.sandbox_native_linker"
)


class ProjectMigrationSandboxNativeLinkerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sandbox-native-linker-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.bin_dir = self.root / "system-bin"
        self.bin_dir.mkdir()
        self.driver = self._executable("gcc", b"driver-v1")
        self.linker = self._executable("ld", b"linker-v1")

    def test_relative_linker_binding_is_path_free_and_deterministic(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        executor = self._executor(calls=calls)
        first = self._resolve(executor)
        second = self._resolve(executor)

        self.assertIsInstance(first, NativeLinkerToolchain)
        self.assertEqual(first, second)
        self.assertEqual("/usr/bin/cc", first.driver_invocation_path.as_posix())
        self.assertEqual(self.driver, first.driver_resolved_path)
        self.assertEqual(self.driver, first.resolved_driver_path)
        self.assertEqual(self.linker, first.linker_resolved_path)
        self.assertEqual(self.linker, first.resolved_linker_path)
        self.assertEqual("x86_64-pc-linux-gnu", first.target_triple)
        payload = first.payload()
        self.assertEqual(content_sha256(payload), first.binding_sha256)
        self.assertEqual(
            {"basename": "gcc", "family": "gnu-compiler",
             "sha256": first.driver_sha256},
            payload["driver"],
        )
        self.assertEqual(
            {"basename": "ld", "family": "linker",
             "sha256": first.linker_sha256},
            payload["linker"],
        )
        encoded = json.dumps(payload, sort_keys=True)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn(self.root.as_posix(), encoded)
        self.assertNotIn("/usr/bin", encoded)
        sandbox_contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256="1" * 64,
            toolchain_sha256="2" * 64,
            native_linker=native_linker_contract(first),
        )
        self.assertEqual(
            sandbox_contract,
            contract_from_payload(sandbox_contract.payload()),
        )
        self.assertEqual(3, sandbox_contract.payload()["schema_version"])

        self.assertEqual(
            [["/usr/bin/cc", "-print-prog-name=ld"],
             ["/usr/bin/cc", "-dumpmachine"]],
            [item[0] for item in calls[:2]],
        )
        expected = {
            "shell": False,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": {"LC_ALL": "C", "LANG": "C"},
            "timeout": 2,
            "check": False,
            "text": False,
        }
        self.assertEqual(expected, calls[0][1])

    def test_absolute_linker_report_uses_the_trusted_resolver(self) -> None:
        executor = self._executor(linker_stdout=b"/usr/bin/ld\n")

        def trusted(candidate: Path) -> Path:
            if candidate.as_posix() == "/usr/bin/ld" or candidate == self.linker:
                return self.linker
            raise AssertionError(f"unexpected trusted path: {candidate}")

        with mock.patch(
            f"{MODULE}._resolve_trusted_executable", side_effect=trusted,
        ) as resolver:
            binding = self._resolve(executor)
        self.assertEqual(self.linker, binding.linker_resolved_path)
        self.assertTrue(any(
            call.args[0].as_posix() == "/usr/bin/ld"
            for call in resolver.call_args_list
        ))

    def test_timeout_and_nonzero_probe_fail_closed(self) -> None:
        def timeout(argv: list[str], **_: object) -> None:
            raise subprocess.TimeoutExpired(argv, 2)

        with self.assertRaisesRegex(ValueError, "timed_out"):
            self._resolve(timeout)
        with self.assertRaisesRegex(ValueError, "nonzero"):
            self._resolve(self._executor(linker_returncode=7))

    def test_probe_streams_require_strict_bounded_utf8(self) -> None:
        cases = (
            self._executor(linker_stdout=b"\xff"),
            self._executor(target_stderr=b"\xff"),
            self._executor(linker_stdout=b"x" * (64 * 1024 + 1)),
            self._executor(target_stderr=b"x" * (64 * 1024 + 1)),
        )
        for index, executor in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "output"):
                    self._resolve(executor)

    def test_reported_linker_path_cannot_escape_fixed_system_trees(self) -> None:
        for value in ("../ld", "..", "/tmp/ld", "C:\\host\\ld"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "path|trusted"):
                    self._resolve(
                        self._executor(linker_stdout=f"{value}\n".encode("utf-8"))
                    )

    def test_linker_must_be_a_regular_executable(self) -> None:
        directory = self.bin_dir / "directory-linker"
        directory.mkdir()
        with self.assertRaisesRegex(ValueError, "executable"):
            self._resolve(self._executor(linker_stdout=b"directory-linker\n"))

        blocked = self._executable("blocked-linker", b"not executable")
        blocked.chmod(0o644)
        real_access = os.access

        def access(path: os.PathLike[str] | str, mode: int) -> bool:
            if Path(path).resolve() == blocked:
                return False
            return real_access(path, mode)

        with mock.patch(f"{MODULE}.os.access", side_effect=access):
            with self.assertRaisesRegex(ValueError, "executable"):
                self._resolve(
                    self._executor(linker_stdout=b"blocked-linker\n")
                )

    def test_driver_and_linker_content_drift_fail_reopen(self) -> None:
        binding = self._resolve(self._executor())
        self.driver.write_bytes(b"driver-v2")
        self.driver.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "driver_content_drifted"):
            self._validate(binding)

        self.driver.write_bytes(b"driver-v1")
        self.driver.chmod(0o755)
        self.linker.write_bytes(b"linker-v2")
        self.linker.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "linker_content_drifted"):
            self._validate(binding)

    def test_target_format_and_complete_payload_hash_are_enforced(self) -> None:
        invalid = (
            "x86_64", "x86_64 linux gnu", "x86_64--linux-gnu",
            "x86_64-linux-gnu/escape", "-x86_64-linux-gnu",
        )
        for target in invalid:
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "target_triple"):
                    self._resolve(self._executor(
                        target_stdout=f"{target}\n".encode("utf-8"),
                    ))

        binding = self._resolve(self._executor())
        changed = replace(
            binding, target_triple="aarch64-unknown-linux-gnu",
        )
        with self.assertRaisesRegex(ValueError, "binding_sha256_drifted"):
            self._validate(changed)
        with self.assertRaisesRegex(ValueError, "binding_sha256_drifted"):
            self._validate(replace(binding, binding_sha256="0" * 64))

    def test_non_linux_host_is_rejected_before_resolution(self) -> None:
        with mock.patch(f"{MODULE}.platform.system", return_value="Windows"):
            with self.assertRaisesRegex(ValueError, "linux_required"):
                resolve_native_linker_toolchain(self._executor())

    def _executable(self, name: str, content: bytes) -> Path:
        path = self.bin_dir / name
        path.write_bytes(content)
        path.chmod(0o755)
        return path.resolve()

    def _resolve(self, executor: object) -> NativeLinkerToolchain:
        with self._linux_host():
            return resolve_native_linker_toolchain(executor)  # type: ignore[arg-type]

    def _validate(self, binding: NativeLinkerToolchain) -> None:
        with self._linux_host():
            validate_native_linker_toolchain(binding)

    @contextmanager
    def _linux_host(self) -> Iterator[None]:
        with (
            mock.patch(f"{MODULE}.platform.system", return_value="Linux"),
            mock.patch(
                f"{MODULE}._resolve_fixed_driver", return_value=self.driver,
            ),
            mock.patch(
                f"{MODULE}._TRUSTED_SYSTEM_TREES", (self.bin_dir,),
            ),
        ):
            yield

    @staticmethod
    def _executor(
        *, linker_stdout: bytes = b"ld\n",
        target_stdout: bytes = b"x86_64-pc-linux-gnu\n",
        linker_stderr: bytes = b"", target_stderr: bytes = b"",
        linker_returncode: int = 0, target_returncode: int = 0,
        calls: list[tuple[list[str], dict[str, object]]] | None = None,
    ):
        def execute(
            argv: list[str], **kwargs: object,
        ) -> subprocess.CompletedProcess[bytes]:
            if calls is not None:
                calls.append((list(argv), dict(kwargs)))
            if argv[-1] == "-print-prog-name=ld":
                return subprocess.CompletedProcess(
                    argv, linker_returncode, linker_stdout, linker_stderr,
                )
            if argv[-1] == "-dumpmachine":
                return subprocess.CompletedProcess(
                    argv, target_returncode, target_stdout, target_stderr,
                )
            raise AssertionError(f"unexpected argv: {argv}")

        return execute


if __name__ == "__main__":
    unittest.main()
