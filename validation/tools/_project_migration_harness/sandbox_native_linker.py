from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
from typing import Any, Callable

from .artifacts import content_sha256
from .c_toolchain_files import hash_stable_file, read_stable_file


_DRIVER_INVOCATION = "/usr/bin/cc"
_DRIVER_INVOCATION_PATH = Path(_DRIVER_INVOCATION)
_TRUSTED_SYSTEM_TREES = (Path("/usr/bin"), Path("/bin"))
_DRIVER_FAMILY = "gnu-compiler"
_LINKER_FAMILY = "linker"
_PROBE_TIMEOUT_SECONDS = 2
_MAX_PROBE_STREAM_BYTES = 64 * 1024
_MAX_TOOL_BYTES = 512 * 1024 * 1024
_PORTABLE_BASENAME = re.compile(r"[A-Za-z0-9_.+-]+\Z", re.ASCII)
_TARGET_TRIPLE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.+]{0,62}"
    r"(?:-[A-Za-z0-9][A-Za-z0-9_.+]{0,62}){2,4}\Z",
    re.ASCII,
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
Executor = Callable[..., subprocess.CompletedProcess[Any]]


@dataclass(frozen=True, slots=True)
class NativeLinkerToolchain:
    driver_invocation_path: Path
    driver_resolved_path: Path
    driver_sha256: str
    linker_resolved_path: Path
    linker_sha256: str
    target_triple: str
    binding_sha256: str

    @property
    def resolved_driver_path(self) -> Path:
        return self.driver_resolved_path

    @property
    def resolved_linker_path(self) -> Path:
        return self.linker_resolved_path

    def payload(self) -> dict[str, object]:
        return _binding_payload(
            self.driver_resolved_path,
            self.driver_sha256,
            self.linker_resolved_path,
            self.linker_sha256,
            self.target_triple,
        )


def resolve_native_linker_toolchain(
    executor: Executor = subprocess.run,
) -> NativeLinkerToolchain:
    _require_linux()
    driver = _resolve_fixed_driver()
    driver_sha256 = _hash_executable(driver)
    linker_report = _run_probe(executor, "-print-prog-name=ld")
    target_triple = _run_probe(executor, "-dumpmachine")
    _validate_target_triple(target_triple)

    current_driver = _resolve_fixed_driver()
    if current_driver != driver or _hash_executable(current_driver) != driver_sha256:
        raise ValueError("native_linker_driver_drifted_during_resolution")

    linker = _resolve_reported_linker(linker_report)
    linker_sha256 = _hash_executable(linker)
    payload = _binding_payload(
        driver, driver_sha256, linker, linker_sha256, target_triple,
    )
    binding = NativeLinkerToolchain(
        driver_invocation_path=_DRIVER_INVOCATION_PATH,
        driver_resolved_path=driver,
        driver_sha256=driver_sha256,
        linker_resolved_path=linker,
        linker_sha256=linker_sha256,
        target_triple=target_triple,
        binding_sha256=content_sha256(payload),
    )
    validate_native_linker_toolchain(binding)
    return binding


def validate_native_linker_toolchain(binding: NativeLinkerToolchain) -> None:
    _require_linux()
    if not isinstance(binding, NativeLinkerToolchain):
        raise ValueError("native_linker_binding_type_invalid")
    if (
        not isinstance(binding.driver_invocation_path, Path)
        or not isinstance(binding.driver_resolved_path, Path)
        or not isinstance(binding.linker_resolved_path, Path)
        or binding.driver_invocation_path.as_posix() != _DRIVER_INVOCATION
    ):
        raise ValueError("native_linker_binding_path_invalid")
    _validate_target_triple(binding.target_triple)
    for value in (
        binding.driver_sha256, binding.linker_sha256, binding.binding_sha256,
    ):
        if type(value) is not str or _SHA256.fullmatch(value) is None:
            raise ValueError("native_linker_binding_sha256_invalid")

    current_driver = _resolve_fixed_driver()
    if current_driver != binding.driver_resolved_path:
        raise ValueError("native_linker_driver_path_drifted")
    current_linker = _resolve_trusted_executable(binding.linker_resolved_path)
    if current_linker != binding.linker_resolved_path:
        raise ValueError("native_linker_linker_path_drifted")
    if _read_executable_sha256(current_driver) != binding.driver_sha256:
        raise ValueError("native_linker_driver_content_drifted")
    if _read_executable_sha256(current_linker) != binding.linker_sha256:
        raise ValueError("native_linker_linker_content_drifted")
    if content_sha256(binding.payload()) != binding.binding_sha256:
        raise ValueError("native_linker_binding_sha256_drifted")


def _resolve_fixed_driver() -> Path:
    return _resolve_trusted_executable(_DRIVER_INVOCATION_PATH)


def _resolve_reported_linker(value: str) -> Path:
    if PurePosixPath(value).is_absolute():
        return _resolve_trusted_executable(Path(value))
    if _PORTABLE_BASENAME.fullmatch(value) is None or value in {".", ".."}:
        raise ValueError("native_linker_reported_path_invalid")
    for root in _TRUSTED_SYSTEM_TREES:
        candidate = root / value
        try:
            candidate.resolve(strict=True)
        except FileNotFoundError:
            continue
        except (OSError, RuntimeError) as error:
            raise ValueError("native_linker_linker_unavailable") from error
        return _resolve_trusted_executable(candidate)
    raise ValueError("native_linker_linker_unavailable")


def _resolve_trusted_executable(candidate: Path) -> Path:
    if not candidate.is_absolute():
        raise ValueError("native_linker_path_not_absolute")
    if not any(candidate.is_relative_to(root) for root in _TRUSTED_SYSTEM_TREES):
        raise ValueError("native_linker_path_outside_trusted_tree")
    try:
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError) as error:
        raise ValueError("native_linker_executable_unavailable") from error
    if not _is_in_trusted_system_tree(resolved):
        raise ValueError("native_linker_path_outside_trusted_tree")
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise ValueError("native_linker_executable_invalid")
    return resolved


def _is_in_trusted_system_tree(path: Path) -> bool:
    for candidate in _TRUSTED_SYSTEM_TREES:
        try:
            root = candidate.resolve(strict=True)
        except OSError:
            continue
        if root.is_dir() and path.is_relative_to(root):
            return True
    return False


def _run_probe(executor: Executor, argument: str) -> str:
    argv = [_DRIVER_INVOCATION, argument]
    try:
        completed = executor(
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LC_ALL": "C", "LANG": "C"},
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
            text=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("native_linker_probe_timed_out") from error
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError("native_linker_probe_failed") from error
    stdout = _decode_probe_stream(getattr(completed, "stdout", None))
    _decode_probe_stream(getattr(completed, "stderr", None))
    if type(getattr(completed, "returncode", None)) is not int:
        raise ValueError("native_linker_probe_result_invalid")
    if completed.returncode != 0:
        raise ValueError("native_linker_probe_nonzero")
    return _single_reported_line(stdout)


def _decode_probe_stream(value: object) -> str:
    try:
        if isinstance(value, bytes):
            raw = value
        elif isinstance(value, str):
            raw = value.encode("utf-8", errors="strict")
        else:
            raise ValueError("native_linker_probe_output_type_invalid")
        if len(raw) > _MAX_PROBE_STREAM_BYTES:
            raise ValueError("native_linker_probe_output_limit_exceeded")
        return raw.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError("native_linker_probe_output_not_utf8") from error


def _single_reported_line(value: str) -> str:
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    if (
        not value
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
    ):
        raise ValueError("native_linker_probe_value_invalid")
    return value


def _hash_executable(path: Path) -> str:
    try:
        result = hash_stable_file(path, executable=True, limit=_MAX_TOOL_BYTES)
    except ValueError as error:
        raise ValueError("native_linker_executable_hash_failed") from error
    return str(result["sha256"])


def _read_executable_sha256(path: Path) -> str:
    try:
        _, identity = read_stable_file(
            path, _MAX_TOOL_BYTES, executable=True,
        )
    except ValueError as error:
        raise ValueError("native_linker_executable_reopen_failed") from error
    return str(identity["sha256"])


def _binding_payload(
    driver: Path, driver_sha256: str, linker: Path, linker_sha256: str,
    target_triple: str,
) -> dict[str, object]:
    return {
        "driver": {
            "basename": _portable_basename(driver.name),
            "family": _DRIVER_FAMILY,
            "sha256": driver_sha256,
        },
        "linker": {
            "basename": _portable_basename(linker.name),
            "family": _LINKER_FAMILY,
            "sha256": linker_sha256,
        },
        "target_triple": target_triple,
    }


def _portable_basename(value: str) -> str:
    if _PORTABLE_BASENAME.fullmatch(value) is None or value in {".", ".."}:
        raise ValueError("native_linker_basename_invalid")
    return value


def _validate_target_triple(value: object) -> None:
    if (
        type(value) is not str
        or len(value.encode("ascii", errors="ignore")) != len(value)
        or len(value) > 255
        or _TARGET_TRIPLE.fullmatch(value) is None
    ):
        raise ValueError("native_linker_target_triple_invalid")


def _require_linux() -> None:
    if platform.system() != "Linux":
        raise ValueError("native_linker_linux_required")


__all__ = [
    "NativeLinkerToolchain", "resolve_native_linker_toolchain",
    "validate_native_linker_toolchain",
]
