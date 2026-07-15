from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from .artifacts import content_sha256


@dataclass(frozen=True, slots=True)
class ClangProcessResult:
    started: bool
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    output_limit_exceeded: bool = False
    launcher_argv_sha256: str | None = None


def run_bounded_bubblewrap(
    argv: Sequence[str], *, timeout_seconds: int,
    max_stdout_bytes: int, max_stderr_bytes: int, max_combined_bytes: int,
    preexec_fn: Callable[[], None],
) -> ClangProcessResult:
    """Run one direct bubblewrap argv and retain only a bounded raw prefix."""
    command = _command(argv)
    _limits(timeout_seconds, max_stdout_bytes, max_stderr_bytes, max_combined_bytes)
    digest = content_sha256(command)
    if platform.system().lower() != "linux":
        raise RuntimeError("clang_fact_runner_linux_required")
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": "/",
        "env": {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin", "TZ": "UTC"},
        "shell": False,
        "start_new_session": True,
        "close_fds": True,
        "preexec_fn": preexec_fn,
    }
    try:
        process = subprocess.Popen(command, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return ClangProcessResult(
            False, None, b"", b"", launcher_argv_sha256=digest,
        )
    budget = _CaptureBudget(max_combined_bytes)
    streams = (bytearray(), bytearray())
    threads = (
        threading.Thread(
            target=_read_stream,
            args=(process.stdout, streams[0], max_stdout_bytes, budget),
            daemon=True,
        ),
        threading.Thread(
            target=_read_stream,
            args=(process.stderr, streams[1], max_stderr_bytes, budget),
            daemon=True,
        ),
    )
    for thread in threads:
        thread.start()
    timed_out = _wait(process, budget.flooded, timeout_seconds)
    for thread in threads:
        thread.join(timeout=2)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    return ClangProcessResult(
        True, process.returncode, bytes(streams[0]), bytes(streams[1]),
        timed_out=timed_out, output_limit_exceeded=budget.flooded.is_set(),
        launcher_argv_sha256=digest,
    )


class _CaptureBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.used = 0
        self.lock = threading.Lock()
        self.flooded = threading.Event()

    def append(self, target: bytearray, stream_limit: int, data: bytes) -> None:
        with self.lock:
            allowed = min(
                len(data), max(0, stream_limit - len(target)),
                max(0, self.maximum - self.used),
            )
            target.extend(data[:allowed])
            self.used += allowed
            if allowed != len(data):
                self.flooded.set()


def _read_stream(
    stream: Any, target: bytearray, limit: int, budget: _CaptureBudget,
) -> None:
    if stream is None:
        return
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            budget.append(target, limit, chunk)
    except OSError:
        return


def _wait(
    process: subprocess.Popen[Any], flooded: threading.Event,
    timeout_seconds: int,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        if flooded.is_set():
            _kill_process_group(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _kill_process_group(process)
            break
        time.sleep(0.01)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _kill_process_group(process)
        process.wait(timeout=2)
    return timed_out


def _kill_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _command(value: Sequence[str]) -> list[str]:
    if (
        isinstance(value, (str, bytes)) or not value
        or any(type(item) is not str for item in value)
    ):
        raise ValueError("clang_fact_runner_argv_invalid")
    command = list(value)
    if command[0].rsplit("/", 1)[-1] != "bwrap":
        raise ValueError("clang_fact_runner_bubblewrap_required")
    return command


def _limits(timeout: int, stdout: int, stderr: int, combined: int) -> None:
    values = (timeout, stdout, stderr, combined)
    if any(type(value) is not int or value < 1 for value in values):
        raise ValueError("clang_fact_runner_limits_invalid")
    if stdout > combined or stderr > combined or combined > 64 * 1024 * 1024:
        raise ValueError("clang_fact_runner_limits_invalid")


__all__ = ["ClangProcessResult", "run_bounded_bubblewrap"]
