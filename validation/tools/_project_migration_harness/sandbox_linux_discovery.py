from __future__ import annotations

from pathlib import Path
import platform
import shutil
import stat
import subprocess

from .sandbox_contract import SandboxContract, SandboxDiscovery
from .sandbox_linux_probe import bubblewrap_version
from .sandbox_native_linker import resolve_native_linker_toolchain
from .sandbox_native_linker_contract import native_linker_contract
from .sandbox_toolchain import file_sha256, resolve_toolchain


def discover_sandbox_backend(
    cargo_binary: Path, project_root: Path | None = None,
) -> SandboxDiscovery:
    from .sandbox_linux import BubblewrapBackend

    if platform.system() != "Linux":
        return SandboxDiscovery(None, "sandbox_os_unsupported")
    launcher_value = shutil.which("bwrap")
    if not launcher_value:
        return SandboxDiscovery(None, "bubblewrap_unavailable")
    try:
        launcher = Path(launcher_value).resolve(strict=True)
        _validate_launcher(launcher)
        toolchain = resolve_toolchain(cargo_binary, project_root)
        try:
            native_linker_toolchain = resolve_native_linker_toolchain()
        except ValueError:
            native_linker_toolchain = None
        contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256=file_sha256(launcher),
            toolchain_sha256=toolchain.sha256,
            native_linker=(
                native_linker_contract(native_linker_toolchain)
                if native_linker_toolchain is not None else None
            ),
        )
        backend = BubblewrapBackend(
            launcher, toolchain.paths(), contract,
            requested_cargo=cargo_binary, toolchain_root=toolchain.root,
            backend_version=bubblewrap_version(launcher),
            native_linker_toolchain=native_linker_toolchain,
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


__all__ = ["discover_sandbox_backend"]
