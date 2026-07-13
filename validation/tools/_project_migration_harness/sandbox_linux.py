from __future__ import annotations

from pathlib import Path
import platform
import shutil
import stat
import subprocess
from typing import Callable, Sequence

from .sandbox_contract import (
    SandboxContract,
    SandboxDiscovery,
    SandboxRunResult,
    canonical_sha256,
    validate_contract,
)
from .sandbox_requirements import SandboxVerificationPlan
from .sandbox_linux_probe import bubblewrap_version, run_bubblewrap_probe
from .sandbox_probe import SandboxProbeReceipt, validate_probe_receipt
from .sandbox_toolchain import (
    file_sha256,
    resolve_toolchain,
    toolchain_sha256,
)


MAX_CAPTURE_BYTES = 1024 * 1024 + 1
Executor = Callable[..., subprocess.CompletedProcess[str]]


class BubblewrapBackend:
    def __init__(
        self, launcher: Path, tools: dict[str, Path], contract: SandboxContract,
        *, executor: Executor | None = None, requested_cargo: Path | None = None,
        toolchain_root: Path | None = None, backend_version: str = "test-only",
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
            command_sha256,
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
    def _argv(
        self, project: Path, runtime: Path, cargo_args: Sequence[str],
        marker_name: str, command_sha256: str,
    ) -> list[str]:
        argv = [
            str(self._launcher), "--die-with-parent", "--new-session",
            "--unshare-all", "--cap-drop", "ALL", "--clearenv",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--dir", "/workspace", "--dir", "/runtime", "--dir", "/tools",
            "--dir", "/home", "--dir", "/home/sandbox", "--dir", "/etc",
        ]
        for system_path in ("/usr", "/bin", "/lib", "/lib64"):
            if Path(system_path).exists():
                argv.extend(("--ro-bind", system_path, system_path))
        for host_path, guest_path in _system_files():
            argv.extend(("--ro-bind", host_path, guest_path))
        argv.extend((
            "--ro-bind", str(project), "/workspace",
            "--bind", str(runtime), "/runtime",
        ))
        tool_directory = "/tools"
        if self._toolchain_root is None:
            for name, path in sorted(self._tools.items()):
                argv.extend(("--ro-bind", str(path), f"/tools/{name}"))
        else:
            tool_directory = "/toolchain/bin"
            argv.extend((
                "--dir", "/toolchain",
                "--ro-bind", str(self._toolchain_root), "/toolchain",
            ))
        argv.extend(_guest_environment(tool_directory))
        argv.extend((
            "--chdir", "/workspace", "--", "/bin/sh", "-c",
            "umask 077; printf '%s\\n%s\\n' \"$1\" \"$2\" > \"$3\" || exit 125; "
            "shift 3; exec \"$@\"",
            "sandbox-launch", self._contract.sha256, command_sha256,
            f"/runtime/{marker_name}", f"{tool_directory}/cargo", *cargo_args,
        ))
        return argv

    def _probe_argv(
        self, project: Path, runtime: Path, command: Sequence[str],
    ) -> list[str]:
        argv = self._argv(
            project, runtime, ("check",), "probe-unused", "0" * 64,
        )
        boundary = argv.index("--chdir")
        return [*argv[:boundary], "--chdir", "/workspace", "--", *command]


def discover_sandbox_backend(
    cargo_binary: Path, project_root: Path | None = None,
) -> SandboxDiscovery:
    if platform.system() != "Linux":
        return SandboxDiscovery(None, "sandbox_os_unsupported")
    launcher_value = shutil.which("bwrap")
    if not launcher_value:
        return SandboxDiscovery(None, "bubblewrap_unavailable")
    try:
        launcher = Path(launcher_value).resolve(strict=True)
        _validate_launcher(launcher)
        toolchain = resolve_toolchain(cargo_binary, project_root)
        launcher_sha256 = file_sha256(launcher)
        contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256=launcher_sha256,
            toolchain_sha256=toolchain.sha256,
        )
        backend_version = bubblewrap_version(launcher)
        backend = BubblewrapBackend(
            launcher, toolchain.paths(), contract,
            requested_cargo=cargo_binary, toolchain_root=toolchain.root,
            backend_version=backend_version,
        )
    except (OSError, ValueError):
        return SandboxDiscovery(None, "sandbox_toolchain_untrusted")
    try:
        probe_root = Path(project_root or Path.cwd()).resolve(strict=True)
        receipt = backend.probe(probe_root)
    except (OSError, ValueError, subprocess.SubprocessError):
        return SandboxDiscovery(None, "sandbox_capability_probe_failed")
    return SandboxDiscovery(backend, None, receipt)


def _validate_launcher(path: Path) -> None:
    metadata = path.stat()
    if (
        not path.is_file()
        or metadata.st_uid != 0
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ValueError("bubblewrap launcher is untrusted")


def _system_files() -> list[tuple[str, str]]:
    result = []
    for value in ("/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/passwd", "/etc/group"):
        if Path(value).is_file():
            result.append((value, value))
    if Path("/etc/ld.so.conf.d").is_dir():
        result.append(("/etc/ld.so.conf.d", "/etc/ld.so.conf.d"))
    return result


def _guest_environment(tool_directory: str) -> list[str]:
    values = {
        "CARGO_HOME": "/runtime/cargo-home",
        "CARGO_NET_OFFLINE": "true",
        "CARGO_TARGET_DIR": "/runtime/target",
        "CARGO_TERM_COLOR": "never",
        "HOME": "/home/sandbox",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": f"{tool_directory}:/usr/bin:/bin",
        "RUSTC": f"{tool_directory}/rustc",
        "RUSTDOC": f"{tool_directory}/rustdoc",
        "TMPDIR": "/tmp",
    }
    return [item for key, value in sorted(values.items()) for item in ("--setenv", key, value)]


def _marker_matches(path: Path, contract_sha256: str, command_sha256: str) -> bool:
    try:
        return path.read_text(encoding="ascii") == f"{contract_sha256}\n{command_sha256}\n"
    except (OSError, UnicodeError):
        return False


def _read_capture(path: Path) -> str:
    with path.open("rb") as handle:
        return handle.read(MAX_CAPTURE_BYTES).decode("utf-8", errors="replace")


def _redacted_argv(argv: Sequence[str]) -> list[str]:
    redacted = []
    for value in argv:
        if value.startswith("/") and value not in {
            "/proc", "/dev", "/tmp", "/workspace", "/runtime", "/tools",
            "/home", "/home/sandbox", "/usr", "/bin", "/lib", "/lib64",
        }:
            redacted.append("<host-or-guest-path>")
        else:
            redacted.append(value)
    return redacted


def _resource_limiter(contract: SandboxContract) -> Callable[[], None]:
    def apply() -> None:
        import resource

        limits = (
            (resource.RLIMIT_CPU, contract.cpu_seconds),
            (resource.RLIMIT_AS, contract.address_space_bytes),
            (resource.RLIMIT_FSIZE, contract.file_size_bytes),
            (resource.RLIMIT_NPROC, contract.process_count),
            (resource.RLIMIT_NOFILE, contract.open_files),
        )
        for kind, value in limits:
            resource.setrlimit(kind, (value, value))

    return apply


__all__ = ["BubblewrapBackend", "discover_sandbox_backend"]
