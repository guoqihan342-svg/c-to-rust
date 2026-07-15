from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .make_dry_run_host_evidence import (
    MAKE_REQUIRED_CAPABILITIES, validate_make_host_preflight,
)
from .make_dry_run_process import run_make_bubblewrap_process
from .make_dry_run_result import MakeDryRunExecution
from .make_dry_run_runner import MakeDryRunPreflight, validate_make_dry_run_plan
from .make_dry_run_sandbox import (
    build_make_bubblewrap_argv, run_make_sandbox_preflight,
)
from .make_dry_run_toolchain import (
    MAKE_TOOLCHAIN_KIND, canonical_make_toolchain_evidence_bytes,
    create_make_toolchain_evidence, file_sha256, gnu_make_version,
    trusted_executable, valid_backend_version, validate_make_toolchain_evidence,
)
from .sandbox_linux_probe import bubblewrap_version


@dataclass(frozen=True, slots=True)
class MakeDryRunBackendDiscovery:
    backend: LinuxBubblewrapMakeBackend | None
    make_binary: Path | None
    toolchain_evidence: dict[str, Any] | None
    reason_code: str | None


class LinuxBubblewrapMakeBackend:
    def __init__(
        self, launcher: Path, make_binary: Path, *, backend_version: str,
        make_version: str, toolchain_artifact_sha256: str,
    ) -> None:
        self._launcher = launcher.resolve(strict=True)
        self._make = make_binary.resolve(strict=True)
        self._backend_version = backend_version
        self._make_version = make_version
        self._toolchain_artifact_sha256 = toolchain_artifact_sha256
        if (
            not valid_backend_version(backend_version)
            or not valid_backend_version(make_version)
            or not is_sha256(toolchain_artifact_sha256)
        ):
            raise ValueError("make_dry_run_backend_identity_invalid")
        self._launcher_sha256 = file_sha256(self._launcher)
        self._make_sha256 = file_sha256(self._make)

    def preflight(
        self, plan: Mapping[str, Any], *, project_root: Path, runtime_root: Path,
    ) -> MakeDryRunPreflight:
        checked = validate_make_dry_run_plan(plan)
        project, runtime = _validated_roots(project_root, runtime_root)
        self._validate_tools()
        observation_sha256, cleanup = run_make_sandbox_preflight(
            launcher=self._launcher,
            make_binary=self._make,
            project=project,
            runtime=runtime,
            plan=checked,
        )
        result = MakeDryRunPreflight(
            backend="bubblewrap-v1",
            backend_version=self._backend_version,
            plan_sha256=checked["plan_sha256"],
            toolchain_sha256=self._toolchain_artifact_sha256,
            launcher_sha256=self._launcher_sha256,
            make_sha256=self._make_sha256,
            probe_observation_sha256=observation_sha256,
            capability_results=tuple(
                (name, True) for name in MAKE_REQUIRED_CAPABILITIES
            ),
            cleanup_ready=cleanup,
        )
        validate_make_host_preflight(
            result.payload(),
            expected_plan_sha256=checked["plan_sha256"],
            expected_toolchain_sha256=self._toolchain_artifact_sha256,
        )
        return result

    def execute(
        self, make_binary: Path, make_args: Sequence[str], *,
        project_root: Path, runtime_root: Path, plan: Mapping[str, Any],
        preflight: MakeDryRunPreflight,
    ) -> MakeDryRunExecution:
        checked = validate_make_dry_run_plan(plan)
        project, runtime = _validated_roots(project_root, runtime_root)
        self._validate_tools()
        if (
            make_binary.resolve(strict=True) != self._make
            or list(make_args) != checked["command"][1:]
        ):
            raise ValueError("make_dry_run_backend_command_drift")
        validate_make_host_preflight(
            preflight.payload(),
            expected_plan_sha256=checked["plan_sha256"],
            expected_toolchain_sha256=self._toolchain_artifact_sha256,
        )
        command_sha256 = content_sha256(checked["command"])
        marker_name = f"make-{command_sha256}.started"
        marker = runtime / marker_name
        marker.unlink(missing_ok=True)
        argv = build_make_bubblewrap_argv(
            launcher=self._launcher,
            make_binary=self._make,
            workspace=project,
            runtime=runtime,
            working_directory=checked["working_directory"],
            make_args=tuple(make_args),
            marker_name=marker_name,
            plan_sha256=checked["plan_sha256"],
            command_sha256=command_sha256,
        )
        process = run_make_bubblewrap_process(
            argv,
            timeout_seconds=checked["timeout_seconds"],
            max_stdout_bytes=checked["max_stdout_bytes"],
            max_stderr_bytes=checked["max_stderr_bytes"],
            resource_limits=checked["resource_limits"],
        )
        return MakeDryRunExecution(
            stdout=process.stdout,
            stderr=process.stderr,
            returncode=process.returncode if process.returncode is not None else -1,
            timed_out=process.timed_out,
            command_started=(
                process.started and _marker_matches(
                    marker, checked["plan_sha256"], command_sha256,
                )
            ),
            cleanup_verified=process.cleanup_verified,
            plan_sha256=checked["plan_sha256"],
            command_sha256=command_sha256,
            output_limit_exceeded=process.output_limit_exceeded,
        )

    def _validate_tools(self) -> None:
        trusted_executable(self._launcher, "bwrap")
        trusted_executable(self._make, "make")
        if (
            file_sha256(self._launcher) != self._launcher_sha256
            or file_sha256(self._make) != self._make_sha256
        ):
            raise ValueError("make_dry_run_backend_tool_drift")


def discover_make_dry_run_backend() -> MakeDryRunBackendDiscovery:
    if platform.system() != "Linux":
        return MakeDryRunBackendDiscovery(
            None, None, None, "make_dry_run_linux_required",
        )
    launcher_value = shutil.which("bwrap")
    make_value = shutil.which("make")
    if not launcher_value or not make_value:
        return MakeDryRunBackendDiscovery(
            None, None, None, "make_dry_run_tool_unavailable",
        )
    try:
        launcher = Path(launcher_value).resolve(strict=True)
        make_binary = Path(make_value).resolve(strict=True)
        trusted_executable(launcher, "bwrap")
        trusted_executable(make_binary, "make")
        backend_version = bubblewrap_version(launcher)
        make_version = gnu_make_version(make_binary)
        evidence = create_make_toolchain_evidence(
            backend_version=backend_version,
            launcher_sha256=file_sha256(launcher),
            launcher_size_bytes=launcher.stat().st_size,
            make_version=make_version,
            make_sha256=file_sha256(make_binary),
            make_size_bytes=make_binary.stat().st_size,
        )
        data = canonical_make_toolchain_evidence_bytes(evidence)
        backend = LinuxBubblewrapMakeBackend(
            launcher,
            make_binary,
            backend_version=backend_version,
            make_version=make_version,
            toolchain_artifact_sha256=hashlib.sha256(data).hexdigest(),
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return MakeDryRunBackendDiscovery(
            None, None, None, "make_dry_run_toolchain_untrusted",
        )
    return MakeDryRunBackendDiscovery(backend, make_binary, evidence, None)


def _validated_roots(project_root: Path, runtime_root: Path) -> tuple[Path, Path]:
    project = project_root.resolve(strict=True)
    runtime = runtime_root.resolve(strict=True)
    if (
        not project.is_dir() or not runtime.is_dir()
        or project == runtime or project.is_relative_to(runtime)
        or runtime.is_relative_to(project)
        or project.is_symlink() or runtime.is_symlink()
    ):
        raise ValueError("make_dry_run_backend_roots_invalid")
    return project, runtime


def _marker_matches(path: Path, plan_sha256: str, command_sha256: str) -> bool:
    try:
        return path.read_bytes() == f"{plan_sha256}\n{command_sha256}\n".encode("ascii")
    except OSError:
        return False


__all__ = [
    "LinuxBubblewrapMakeBackend", "MAKE_TOOLCHAIN_KIND",
    "MakeDryRunBackendDiscovery", "build_make_bubblewrap_argv",
    "canonical_make_toolchain_evidence_bytes", "create_make_toolchain_evidence",
    "discover_make_dry_run_backend", "validate_make_toolchain_evidence",
]
