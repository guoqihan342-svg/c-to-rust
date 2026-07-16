from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath

from .sandbox_contract import SandboxContract
from .sandbox_environment import bubblewrap_environment_args


_SYSTEM_DIRECTORIES = ("/usr", "/bin", "/lib", "/lib64")
_SYSTEM_FILES = (
    "/etc/ld.so.cache",
    "/etc/ld.so.conf",
    "/etc/passwd",
    "/etc/group",
)
_REDACTION_SAFE_PATHS = {
    "/proc", "/dev", "/tmp", "/workspace", "/runtime",
    "/toolchain", "/toolchain/bin", "/home", "/home/sandbox",
    "/usr", "/bin", "/lib", "/lib64",
}


def build_bubblewrap_argv(
    *, launcher: Path, workspace: Path, runtime: Path,
    tool_bindings: tuple[tuple[Path, str], ...],
    environment: tuple[tuple[str, str], ...],
    guest_command: tuple[str, ...],
    guest_working_directory: str = "/workspace",
) -> list[str]:
    """Build the fixed isolation argv around an already validated command."""
    if (
        type(guest_command) is not tuple
        or not guest_command
        or any(type(item) is not str for item in guest_command)
    ):
        raise ValueError("sandbox guest command must be a non-empty string tuple")
    working = PurePosixPath(guest_working_directory)
    if (
        not working.is_absolute() or working.parts[:2] != ("/", "workspace")
        or any(part in {"", ".", ".."} for part in working.parts[1:])
    ):
        raise ValueError("sandbox guest working directory is invalid")
    argv = [
        str(launcher), "--die-with-parent", "--new-session",
        "--unshare-all", "--cap-drop", "ALL", "--clearenv",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/workspace", "--dir", "/runtime",
        "--dir", "/toolchain", "--dir", "/toolchain/bin",
        "--dir", "/home", "--dir", "/home/sandbox", "--dir", "/etc",
    ]
    for system_path in _SYSTEM_DIRECTORIES:
        if Path(system_path).exists():
            argv.extend(("--ro-bind", system_path, system_path))
    for host_path, guest_path in _system_file_bindings():
        argv.extend(("--ro-bind", host_path, guest_path))
    argv.extend((
        "--ro-bind", str(workspace), "/workspace",
        "--bind", str(runtime), "/runtime",
    ))
    for host_path, guest_path in tool_bindings:
        argv.extend(("--ro-bind", str(host_path), guest_path))
    argv.extend(bubblewrap_environment_args(environment))
    argv.extend(("--chdir", guest_working_directory, "--", *guest_command))
    return argv


def redacted_bubblewrap_argv(argv: Sequence[str]) -> list[str]:
    return [
        "<host-or-guest-path>"
        if _is_absolute_path(value) and value not in _REDACTION_SAFE_PATHS
        else value
        for value in argv
    ]


def resource_limiter(contract: SandboxContract) -> Callable[[], None]:
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


def _system_file_bindings() -> list[tuple[str, str]]:
    result = []
    for value in _SYSTEM_FILES:
        if Path(value).is_file():
            result.append((value, value))
    if Path("/etc/ld.so.conf.d").is_dir():
        result.append(("/etc/ld.so.conf.d", "/etc/ld.so.conf.d"))
    if Path("/etc/alternatives").is_dir():
        result.append(("/etc/alternatives", "/etc/alternatives"))
    return result


def _is_absolute_path(value: str) -> bool:
    return (
        PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


__all__ = [
    "build_bubblewrap_argv", "redacted_bubblewrap_argv", "resource_limiter",
]
