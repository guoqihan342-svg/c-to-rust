from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping
from typing import Any


PROBE_TIMEOUT_SECONDS = 5
MAX_PROBE_STREAM_BYTES = 32 * 1024


@dataclass(frozen=True, slots=True)
class ProbeExecution:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    flooded: bool = False
    started: bool = True


def bounded_subprocess_runner(
    argv: list[str], *, environment: Mapping[str, str],
    timeout_seconds: int, max_output_bytes: int,
) -> ProbeExecution:
    if (
        not isinstance(argv, list)
        or not argv
        or not Path(argv[0]).is_absolute()
        or timeout_seconds != PROBE_TIMEOUT_SECONDS
        or max_output_bytes != MAX_PROBE_STREAM_BYTES
    ):
        raise ValueError("c_toolchain_probe_runner_contract_invalid")
    child_environment = {
        key: value
        for key, value in environment.items()
        if type(key) is str and type(value) is str
    }
    if os.name != "nt":
        child_environment.update({"LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "env": child_environment,
        "shell": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0,
        )
    else:
        kwargs["start_new_session"] = True
    with tempfile.TemporaryDirectory(prefix="c-toolchain-probe-") as temporary:
        kwargs["cwd"] = temporary
        try:
            process = subprocess.Popen(argv, **kwargs)
        except OSError:
            return ProbeExecution(None, b"", b"", started=False)
        streams = [bytearray(), bytearray()]
        flooded = threading.Event()
        threads = [
            threading.Thread(
                target=_read_stream,
                args=(stream, streams[index], max_output_bytes, flooded),
                daemon=True,
            )
            for index, stream in enumerate((process.stdout, process.stderr))
        ]
        for thread in threads:
            thread.start()
        timed_out = _wait_for_process(process, flooded, timeout_seconds)
        for thread in threads:
            thread.join(timeout=1)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        return ProbeExecution(
            process.returncode,
            bytes(streams[0][:max_output_bytes + 1]),
            bytes(streams[1][:max_output_bytes + 1]),
            timed_out=timed_out,
            flooded=flooded.is_set(),
        )


def _wait_for_process(
    process: subprocess.Popen[Any], flooded: threading.Event,
    timeout_seconds: int,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        if flooded.is_set():
            _kill_process_tree(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _kill_process_tree(process)
            break
        time.sleep(0.01)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        process.wait(timeout=1)
    return timed_out


def _read_stream(
    stream: Any, target: bytearray, limit: int, flooded: threading.Event,
) -> None:
    if stream is None:
        return
    try:
        while len(target) <= limit:
            chunk = stream.read(min(4096, limit + 1 - len(target)))
            if not chunk:
                return
            target.extend(chunk)
            if len(target) > limit:
                flooded.set()
                return
    except OSError:
        return


def _kill_process_tree(process: subprocess.Popen[Any]) -> None:
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (OSError, ProcessLookupError):
            pass
    try:
        process.kill()
    except OSError:
        pass


__all__ = [
    "MAX_PROBE_STREAM_BYTES", "PROBE_TIMEOUT_SECONDS", "ProbeExecution",
    "bounded_subprocess_runner",
]
