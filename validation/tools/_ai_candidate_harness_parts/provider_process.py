from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import tempfile
from typing import BinaryIO, Callable

from .provider_session import export_session_identity, parse_session_identity_export
from .provider_process_tree import process_group_popen_kwargs, terminate_and_drain


MAX_PROVIDER_STDOUT_BYTES = 2_000_000
MAX_PROVIDER_STDERR_BYTES = 256_000
OPENCODE_LOG_PATH_ENV = "OPENCODE_LOG_PATH"
PROVIDER_BALANCE_SENTINEL = "provider_error=insufficient_balance"
PROVIDER_AUTH_SENTINEL = "provider_error=authentication_failed"
PROVIDER_INVOCATION_SENTINEL = "provider_error=invocation_failed"


@dataclass(frozen=True)
class ProviderExecution:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    identity_receipt: dict[str, str] | None = None
    process_started: bool = True


def subprocess_runner(argv: list[str], timeout_seconds: int) -> ProviderExecution:
    return subprocess_runner_with_environment(argv, timeout_seconds)


def subprocess_runner_with_environment(
    argv: list[str], timeout_seconds: int, *,
    environment: Mapping[str, str] | None = None, cwd: Path | None = None,
    on_started: Callable[[], None] | None = None,
) -> ProviderExecution:
    process_environment = dict(environment) if environment is not None else None
    log_snapshot = snapshot_opencode_log(argv, environment=environment)
    try:
        completed = _run_process(
            argv,
            timeout_seconds,
            environment=process_environment,
            cwd=cwd,
            on_started=on_started,
        )
    except OSError:
        return ProviderExecution(
            returncode=127,
            stdout="",
            stderr=PROVIDER_INVOCATION_SENTINEL,
            process_started=False,
        )
    except subprocess.TimeoutExpired as error:
        stderr = append_provider_log_diagnostic(
            decode_timeout_output(error.stderr),
            log_snapshot,
        )
        return ProviderExecution(
            returncode=124,
            stdout=decode_timeout_output(error.stdout),
            stderr=stderr,
            timed_out=True,
        )
    stderr = completed.stderr
    if completed.returncode != 0:
        stderr = append_provider_log_diagnostic(stderr, log_snapshot)
    identity_receipt = (
        export_session_identity(
            argv,
            completed.stdout,
            environment=environment,
            cwd=cwd,
        )
        if completed.returncode == 0
        else None
    )
    return ProviderExecution(
        completed.returncode,
        completed.stdout,
        stderr,
        identity_receipt=identity_receipt,
        process_started=True,
    )


def _run_process(
    argv: list[str], timeout_seconds: int, *,
    environment: dict[str, str] | None, cwd: Path | None,
    on_started: Callable[[], None] | None,
) -> subprocess.CompletedProcess[str]:
    common = {
        "env": environment,
        "cwd": str(cwd) if cwd is not None else None,
    }
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            argv,
            stdout=stdout_file,
            stderr=stderr_file,
            **process_group_popen_kwargs(),
            **common,
        )
        try:
            if on_started is not None:
                on_started()
        except BaseException:
            terminate_and_drain(process)
            raise
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            terminate_and_drain(process)
            error.stdout = _bounded_process_output(
                stdout_file, MAX_PROVIDER_STDOUT_BYTES,
            )
            error.stderr = _bounded_process_output(
                stderr_file, MAX_PROVIDER_STDERR_BYTES,
            )
            raise
        return subprocess.CompletedProcess(
            argv,
            returncode,
            _bounded_process_output(stdout_file, MAX_PROVIDER_STDOUT_BYTES),
            _bounded_process_output(stderr_file, MAX_PROVIDER_STDERR_BYTES),
        )


def _bounded_process_output(stream: BinaryIO, limit: int) -> str:
    stream.seek(0)
    return stream.read(limit + 1).decode("utf-8", errors="replace")


def snapshot_opencode_log(
    argv: list[str], *, environment: Mapping[str, str] | None = None,
) -> tuple[Path, int, str, str, str] | None:
    try:
        model = argv[argv.index("--model") + 1]
        agent = argv[argv.index("--agent") + 1]
    except (ValueError, IndexError):
        return None
    if "/" not in model:
        return None
    provider_id, model_id = model.rsplit("/", 1)
    candidates = opencode_log_candidates(environment=environment)
    if not candidates:
        return None
    path = candidates[0]
    try:
        offset = path.stat().st_size
    except FileNotFoundError:
        offset = 0
    except OSError:
        return None
    return path, offset, provider_id, model_id, agent


def opencode_log_candidates(
    *, environment: Mapping[str, str] | None = None,
) -> list[Path]:
    values = environment if environment is not None else os.environ
    candidates: list[Path] = []
    override = values.get(OPENCODE_LOG_PATH_ENV)
    if override:
        candidates.append(Path(override))
    xdg_data_home = values.get("XDG_DATA_HOME")
    if xdg_data_home:
        candidates.append(Path(xdg_data_home) / "opencode" / "log" / "opencode.log")
    home = values.get("HOME")
    if home:
        candidates.append(
            Path(home) / ".local" / "share" / "opencode" / "log" / "opencode.log"
        )
    elif environment is None:
        candidates.append(
            Path.home() / ".local" / "share" / "opencode" / "log" / "opencode.log"
        )
    local_app_data = values.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "opencode" / "log" / "opencode.log")
    return candidates


def appended_provider_log_diagnostic(
    snapshot: tuple[Path, int, str, str, str] | None,
) -> str:
    if snapshot is None:
        return ""
    path, offset, provider_id, model_id, agent = snapshot
    try:
        with path.open("rb") as handle:
            if handle.seek(0, os.SEEK_END) < offset:
                return ""
            handle.seek(offset)
            appended = handle.read(MAX_PROVIDER_STDERR_BYTES)
    except OSError:
        return ""
    text = appended.decode("utf-8", errors="replace")
    matching = "\n".join(
        line
        for line in text.splitlines()
        if f"providerID={provider_id}" in line
        and f"modelID={model_id}" in line
        and f"agent={agent}" in line
    ).lower()
    if "insufficient balance" in matching or "no resource package" in matching:
        return PROVIDER_BALANCE_SENTINEL
    if (
        "unauthorized" in matching
        or "invalid api key" in matching
        or "authentication" in matching
    ):
        return PROVIDER_AUTH_SENTINEL
    return ""


def append_provider_log_diagnostic(
    stderr: str,
    snapshot: tuple[Path, int, str, str, str] | None,
) -> str:
    diagnostic = appended_provider_log_diagnostic(snapshot)
    if not diagnostic or diagnostic in stderr:
        return stderr
    return "\n".join(part for part in (stderr, diagnostic) if part)


def decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


__all__ = [
    "MAX_PROVIDER_STDERR_BYTES",
    "MAX_PROVIDER_STDOUT_BYTES",
    "OPENCODE_LOG_PATH_ENV",
    "PROVIDER_AUTH_SENTINEL",
    "PROVIDER_BALANCE_SENTINEL",
    "PROVIDER_INVOCATION_SENTINEL",
    "ProviderExecution",
    "append_provider_log_diagnostic",
    "appended_provider_log_diagnostic",
    "decode_timeout_output",
    "export_session_identity",
    "opencode_log_candidates",
    "parse_session_identity_export",
    "snapshot_opencode_log",
    "subprocess_runner",
    "subprocess_runner_with_environment",
]
