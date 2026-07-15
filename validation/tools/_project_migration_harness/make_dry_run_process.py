from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
import platform
import signal
import subprocess
import threading
import time
from typing import Any


@dataclass(frozen=True, slots=True)
class MakeBubblewrapProcessResult:
    started: bool
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_limit_exceeded: bool
    cleanup_verified: bool


def run_make_bubblewrap_process(
    argv: Sequence[str], *, timeout_seconds: int,
    max_stdout_bytes: int, max_stderr_bytes: int,
    resource_limits: Mapping[str, int],
) -> MakeBubblewrapProcessResult:
    command = _command(argv)
    _limits(timeout_seconds, max_stdout_bytes, max_stderr_bytes)
    if platform.system() != "Linux":
        raise RuntimeError("make_dry_run_linux_required")
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": "/",
        "env": {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        "shell": False,
        "start_new_session": True,
        "close_fds": True,
        "preexec_fn": _resource_limiter(resource_limits),
    }
    try:
        process = subprocess.Popen(command, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return MakeBubblewrapProcessResult(
            False, None, b"", b"", False, False, False,
        )
    budget = _CaptureBudget(max_stdout_bytes + max_stderr_bytes)
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
    threads_stopped = all(not thread.is_alive() for thread in threads)
    if not threads_stopped:
        _kill_process_group(process)
        for thread in threads:
            thread.join(timeout=2)
        threads_stopped = all(not thread.is_alive() for thread in threads)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    cleanup = threads_stopped and _process_group_empty(process.pid)
    if not cleanup:
        _kill_process_group(process)
    return MakeBubblewrapProcessResult(
        True, process.returncode, bytes(streams[0]), bytes(streams[1]),
        timed_out, budget.flooded.is_set(), cleanup,
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
            chunk = stream.read(64 * 1024)
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
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return timed_out
    return timed_out


def _kill_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _process_group_empty(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def _command(value: Sequence[str]) -> list[str]:
    if (
        isinstance(value, (str, bytes)) or not value
        or any(type(item) is not str for item in value)
    ):
        raise ValueError("make_dry_run_bubblewrap_argv_invalid")
    command = list(value)
    if command[0].rsplit("/", 1)[-1] != "bwrap":
        raise ValueError("make_dry_run_bubblewrap_required")
    return command


def _limits(timeout: int, stdout: int, stderr: int) -> None:
    if any(type(value) is not int or value < 1 for value in (timeout, stdout, stderr)):
        raise ValueError("make_dry_run_process_limits_invalid")
    if stdout + stderr > 64 * 1024 * 1024:
        raise ValueError("make_dry_run_process_limits_invalid")


def _resource_limiter(limits: Mapping[str, int]):
    expected = {
        "address_space_bytes", "cpu_seconds", "file_size_bytes", "open_files",
        "process_count",
    }
    if set(limits) != expected or any(
        type(value) is not int or value < 1 for value in limits.values()
    ):
        raise ValueError("make_dry_run_resource_limits_invalid")

    def apply() -> None:
        import resource

        os.umask(0o077)
        values = (
            (resource.RLIMIT_AS, limits["address_space_bytes"]),
            (resource.RLIMIT_CPU, limits["cpu_seconds"]),
            (resource.RLIMIT_FSIZE, limits["file_size_bytes"]),
            (resource.RLIMIT_NOFILE, limits["open_files"]),
            (resource.RLIMIT_NPROC, limits["process_count"]),
        )
        for kind, value in values:
            resource.setrlimit(kind, (value, value))

    return apply


__all__ = ["MakeBubblewrapProcessResult", "run_make_bubblewrap_process"]
