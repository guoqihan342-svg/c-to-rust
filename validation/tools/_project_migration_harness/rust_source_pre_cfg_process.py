from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import platform
import signal
import subprocess
import threading
import time
from typing import Any

from .artifacts import content_sha256
from .build_facts import is_linklike
from .rust_source_pre_cfg_schema import MAX_RUST_WITNESS_OUTPUT_BYTES


RUST_SOURCE_PARSER_TIMEOUT_SECONDS = 30
MAX_RUST_PARSER_STDERR_BYTES = 1024 * 1024
MAX_RUST_PARSER_BINARY_BYTES = 64 * 1024 * 1024
MAX_RUST_PARSER_INPUT_BYTES = 64 * 1024 * 1024
_BINARY_NAMES = {"c2r_rust_source_witness", "c2r_rust_source_witness.exe"}


@dataclass(frozen=True, slots=True)
class RustSourceProcessResult:
    started: bool
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_limit_exceeded: bool
    command_sha256: str


def bind_rust_source_parser_binary(
    tool_root: Path,
    parser_binary: Path,
) -> dict[str, Any]:
    root = Path(tool_root).resolve(strict=True)
    requested = Path(parser_binary)
    if not requested.is_absolute() and any(
        part in {"", ".", ".."} for part in requested.parts
    ):
        raise ValueError("rust_source_parser_binary_path_invalid")
    lexical = requested if requested.is_absolute() else root / requested
    _reject_links(lexical)
    binary = lexical.resolve(strict=True)
    try:
        relative = binary.relative_to(root)
    except ValueError as error:
        raise ValueError("rust_source_parser_binary_outside_tool_root") from error
    if (
        binary.name not in _BINARY_NAMES
        or not binary.is_file()
        or binary.stat().st_size <= 0
        or binary.stat().st_size > MAX_RUST_PARSER_BINARY_BYTES
    ):
        raise ValueError("rust_source_parser_binary_invalid")
    data = binary.read_bytes()
    if len(data) != binary.stat().st_size:
        raise ValueError("rust_source_parser_binary_drifted")
    return {
        "name": "c2r_rust_source_witness",
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _reject_links(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError("rust_source_parser_binary_link_forbidden")


def run_rust_source_parser(
    *, tool_root: Path, parser_binary: Path, source: bytes,
) -> RustSourceProcessResult:
    binding = bind_rust_source_parser_binary(tool_root, parser_binary)
    if type(source) is not bytes or len(source) > MAX_RUST_PARSER_INPUT_BYTES:
        raise ValueError("rust_source_parser_input_invalid")
    root = Path(tool_root).resolve(strict=True)
    binary = root.joinpath(*Path(binding["path"]).parts).resolve(strict=True)
    command_sha256 = content_sha256({
        "argv": ["c2r_rust_source_witness"],
        "stdin_sha256": hashlib.sha256(source).hexdigest(),
    })
    kwargs: dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": str(root),
        "env": _process_environment(),
        "shell": False,
        "close_fds": True,
    }
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen([str(binary)], **kwargs)
    except (OSError, subprocess.SubprocessError):
        return RustSourceProcessResult(
            False, None, b"", b"", False, False, command_sha256,
        )
    combined = MAX_RUST_WITNESS_OUTPUT_BYTES + MAX_RUST_PARSER_STDERR_BYTES
    budget = _CaptureBudget(combined)
    stdout, stderr = bytearray(), bytearray()
    threads = [
        threading.Thread(
            target=_read_stream,
            args=(process.stdout, stdout, MAX_RUST_WITNESS_OUTPUT_BYTES, budget),
            daemon=True,
        ),
        threading.Thread(
            target=_read_stream,
            args=(process.stderr, stderr, MAX_RUST_PARSER_STDERR_BYTES, budget),
            daemon=True,
        ),
        threading.Thread(
            target=_write_input, args=(process.stdin, source), daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    timed_out = _wait(process, budget.flooded)
    for thread in threads:
        thread.join(timeout=2)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    return RustSourceProcessResult(
        True, process.returncode, bytes(stdout), bytes(stderr), timed_out,
        budget.flooded.is_set(), command_sha256,
    )


class _CaptureBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.used = 0
        self.lock = threading.Lock()
        self.flooded = threading.Event()

    def append(self, target: bytearray, limit: int, data: bytes) -> None:
        with self.lock:
            allowed = min(
                len(data), max(0, limit - len(target)),
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


def _write_input(stream: Any, source: bytes) -> None:
    if stream is None:
        return
    try:
        stream.write(source)
        stream.flush()
        stream.close()
    except OSError:
        return


def _wait(process: subprocess.Popen[Any], flooded: threading.Event) -> bool:
    deadline = time.monotonic() + RUST_SOURCE_PARSER_TIMEOUT_SECONDS
    timed_out = False
    while process.poll() is None:
        if flooded.is_set():
            _kill_process(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _kill_process(process)
            break
        time.sleep(0.01)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _kill_process(process)
        process.wait(timeout=2)
    return timed_out


def _kill_process(process: subprocess.Popen[Any]) -> None:
    if platform.system().lower() != "windows":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (OSError, ProcessLookupError):
            pass
    try:
        process.kill()
    except OSError:
        pass


def _process_environment() -> dict[str, str]:
    result = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
    if platform.system().lower() == "windows" and os.environ.get("SystemRoot"):
        result["SystemRoot"] = os.environ["SystemRoot"]
    return result


__all__ = [
    "MAX_RUST_PARSER_BINARY_BYTES", "MAX_RUST_PARSER_INPUT_BYTES",
    "MAX_RUST_PARSER_STDERR_BYTES",
    "RUST_SOURCE_PARSER_TIMEOUT_SECONDS", "RustSourceProcessResult",
    "bind_rust_source_parser_binary", "run_rust_source_parser",
]
