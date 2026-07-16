from __future__ import annotations

from pathlib import Path
import subprocess
from collections.abc import Mapping
from typing import Any, Callable, Sequence

from .sandbox_bubblewrap_argv import (
    build_bubblewrap_argv,
    redacted_bubblewrap_argv as _redacted_argv,
    resource_limiter as _resource_limiter,
)
from .sandbox_contract import (
    SandboxContract,
    SandboxDiscovery,
    SandboxRunResult,
    canonical_sha256,
    validate_contract,
)
from .sandbox_environment import (
    canonical_environment_items,
    cargo_guest_environment,
)
from .sandbox_requirements import SandboxVerificationPlan
from .sandbox_linux_probe import run_bubblewrap_probe
from .sandbox_native_linker import (
    NativeLinkerToolchain, validate_native_linker_toolchain,
)
from .sandbox_native_linker_contract import native_linker_contract
from .sandbox_probe import SandboxProbeReceipt, validate_probe_receipt
from .sandbox_toolchain import (
    file_sha256,
    toolchain_sha256,
)


MAX_CAPTURE_BYTES = 1024 * 1024 + 1
Executor = Callable[..., subprocess.CompletedProcess[Any]]


class BubblewrapBackend:
    def __init__(
        self, launcher: Path, tools: dict[str, Path], contract: SandboxContract,
        *, executor: Executor | None = None, requested_cargo: Path | None = None,
        toolchain_root: Path | None = None, backend_version: str = "test-only",
        native_linker_toolchain: NativeLinkerToolchain | None = None,
    ) -> None:
        validate_contract(contract)
        self._launcher = launcher
        self._tools = {name: path.resolve(strict=True) for name, path in tools.items()}
        if toolchain_sha256(self._tools, toolchain_root) != contract.toolchain_sha256:
            raise ValueError("Sandbox toolchain does not match its contract")
        self._contract = contract
        self._executor = executor or subprocess.run
        self._requested_cargo = (requested_cargo or tools["cargo"]).resolve(strict=True)
        self._toolchain_root = (
            toolchain_root.resolve(strict=True) if toolchain_root is not None else None
        )
        self._backend_version = backend_version
        self._native_linker_toolchain = native_linker_toolchain
        expected_native_linker = (
            native_linker_contract(native_linker_toolchain)
            if native_linker_toolchain is not None else None
        )
        if expected_native_linker != contract.native_linker:
            raise ValueError("Sandbox native linker does not match its contract")
        if self._toolchain_root is not None and any(
            path.parent != self._toolchain_root / "bin" for path in self._tools.values()
        ):
            raise ValueError("Resolved tools are outside the selected toolchain")

    @property
    def contract(self) -> SandboxContract:
        return self._contract

    def execute(
        self, cargo_binary: Path, cargo_args: Sequence[str], *,
        project_root: Path, runtime_root: Path,
        verification_plan: SandboxVerificationPlan,
        probe_receipt: object,
    ) -> SandboxRunResult:
        if cargo_binary.resolve(strict=True) != self._requested_cargo:
            raise ValueError("Cargo binary drifted after sandbox discovery")
        self._validate_runtime_binding()
        command = ["cargo", *cargo_args]
        if (
            not isinstance(verification_plan, SandboxVerificationPlan)
            or verification_plan.command != tuple(command)
            or verification_plan.requirements != self._contract.requirements
        ):
            raise ValueError("Sandbox verification plan does not match execution")
        if verification_plan.native_link_trace and self._native_linker_toolchain is None:
            raise ValueError("Sandbox native linker trace toolchain is unavailable")
        if not isinstance(probe_receipt, SandboxProbeReceipt):
            raise ValueError("Sandbox execution requires a capability probe receipt")
        if probe_receipt.backend_version != self._backend_version:
            raise ValueError("Sandbox capability probe backend version drifted")
        validate_probe_receipt(
            probe_receipt, self._contract, verification_plan.requirements,
        )
        command_sha256 = canonical_sha256(command)
        marker = runtime_root / f"sandbox-{command_sha256}.started"
        marker.unlink(missing_ok=True)
        argv = self._argv(
            project_root, runtime_root, cargo_args, marker.name,
            command_sha256, verification_plan.environment,
        )
        stdout_path = runtime_root / f"sandbox-{command_sha256}.stdout"
        stderr_path = runtime_root / f"sandbox-{command_sha256}.stderr"
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            completed = self._executor(
                argv,
                cwd=runtime_root,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=verification_plan.timeout_seconds,
                check=False,
                preexec_fn=_resource_limiter(self._contract),
            )
        completed = subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            _read_capture(stdout_path),
            _read_capture(stderr_path),
        )
        command_started = _marker_matches(marker, self._contract.sha256, command_sha256)
        return SandboxRunResult(
            completed=completed,
            contract_sha256=self._contract.sha256,
            command_sha256=command_sha256,
            command_started=command_started,
            launcher_argv_sha256=canonical_sha256(_redacted_argv(argv)),
            requirements_sha256=self._contract.requirements.sha256,
            verification_plan_sha256=verification_plan.sha256,
            probe_receipt_sha256=probe_receipt.sha256,
        )

    def execute_project_test_process(
        self, executable: Path, *, project_root: Path, runtime_root: Path,
        arguments: Sequence[str], working_directory: str,
        environment: Mapping[str, str], timeout_seconds: int,
        input_sha256: str, probe_receipt: SandboxProbeReceipt,
    ) -> dict[str, Any]:
        from .project_test_process_sandbox import (
            execute_isolated_project_test_process,
        )

        self._validate_runtime_binding()
        return execute_isolated_project_test_process(
            launcher=self._launcher, contract=self._contract,
            executor=self._executor, executable=executable,
            workspace=project_root, runtime=runtime_root,
            arguments=arguments, working_directory=working_directory,
            environment=environment, timeout_seconds=timeout_seconds,
            input_sha256=input_sha256, probe_receipt=probe_receipt,
        )

    def probe(self, project_root: Path) -> object:
        self._validate_runtime_binding()
        return run_bubblewrap_probe(
            contract=self._contract,
            backend_version=self._backend_version,
            project_root=project_root,
            argv_builder=lambda runtime, command: self._probe_argv(
                project_root, runtime, command,
            ),
            executor=self._executor,
            preexec_fn=_resource_limiter(self._contract),
        )

    def _validate_runtime_binding(self) -> None:
        if file_sha256(self._launcher) != self._contract.launcher_sha256:
            raise ValueError("Sandbox launcher content drifted after discovery")
        if toolchain_sha256(self._tools, self._toolchain_root) != self._contract.toolchain_sha256:
            raise ValueError("Sandbox toolchain content drifted after discovery")
        if self._native_linker_toolchain is not None:
            validate_native_linker_toolchain(self._native_linker_toolchain)
    def _argv(
        self, project: Path, runtime: Path, cargo_args: Sequence[str],
        marker_name: str, command_sha256: str,
        environment: tuple[tuple[str, str], ...],
    ) -> list[str]:
        tool_bindings: tuple[tuple[Path, str], ...]
        if self._toolchain_root is None:
            tool_bindings = tuple(
                (path, f"/toolchain/bin/{name}")
                for name, path in sorted(self._tools.items())
            )
        else:
            tool_bindings = ((self._toolchain_root, "/toolchain"),)
        guest_command = (
            "/bin/sh", "-c",
            "umask 077; printf '%s\\n%s\\n' \"$1\" \"$2\" > \"$3\" || exit 125; "
            "shift 3; exec \"$@\"",
            "sandbox-launch", self._contract.sha256, command_sha256,
            f"/runtime/{marker_name}", "/toolchain/bin/cargo", *cargo_args,
        )
        return build_bubblewrap_argv(
            launcher=self._launcher, workspace=project, runtime=runtime,
            tool_bindings=tool_bindings, environment=environment,
            guest_command=guest_command,
        )

    def _probe_argv(
        self, project: Path, runtime: Path, command: Sequence[str],
    ) -> list[str]:
        environment = canonical_environment_items(cargo_guest_environment())
        cargo_argv = self._argv(
            project, runtime, ("check",), "probe-unused", "0" * 64, environment,
        )
        boundary = cargo_argv.index("--chdir")
        return [
            *cargo_argv[:boundary], "--chdir", "/workspace", "--", *command,
        ]


def discover_sandbox_backend(
    cargo_binary: Path, project_root: Path | None = None,
) -> SandboxDiscovery:
    from .sandbox_linux_discovery import discover_sandbox_backend as discover

    return discover(cargo_binary, project_root)


def _marker_matches(path: Path, contract_sha256: str, command_sha256: str) -> bool:
    try:
        return path.read_text(encoding="ascii") == f"{contract_sha256}\n{command_sha256}\n"
    except (OSError, UnicodeError):
        return False


def _read_capture(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(MAX_CAPTURE_BYTES)


__all__ = ["BubblewrapBackend", "discover_sandbox_backend"]
