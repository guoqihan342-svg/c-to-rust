from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping, Sequence

from .artifacts import content_sha256
from .c2rust_project_baseline_evidence import write_cas_artifact
from .c2rust_project_baseline_process_contract import (
    RUNTIME_OVERRIDE_KEYS, validated_command, validated_environment,
    validated_expected_returncodes, validated_portable_command,
    validated_portable_path, validated_stdin,
)


MAX_PROCESS_OUTPUT_BYTES = 4 * 1024 * 1024
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 3_600
_TOOLCHAIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    command_started: bool = True


Runner = Callable[
    [Sequence[str], Path, Mapping[str, str], int, bytes], ProcessOutcome,
]


def executable_binding(path: Path, role: str) -> dict[str, Any]:
    try:
        launcher = Path(os.path.abspath(Path(path)))
        resolved = launcher.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"c2rust_{role}_unavailable") from error
    if not launcher.is_file() or not resolved.is_file():
        raise ValueError(f"c2rust_{role}_invalid")
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "role": role,
        "executable_path": launcher.as_posix(),
        "sha256": digest.hexdigest(),
        "size_bytes": resolved.stat().st_size,
    }


def minimal_process_environment(
    runtime_root: Path, *, transpiler: Path, cargo: Path, rustc: Path,
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    runtime = Path(runtime_root).resolve()
    directories = {
        "CARGO_HOME": runtime / "cargo-home",
        "CARGO_TARGET_DIR": runtime / "cargo-target",
        "HOME": runtime / "home",
        "TMPDIR": runtime / "tmp",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    tool_dirs = [
        Path(transpiler).resolve().parent,
        Path(cargo).resolve().parent,
        Path(rustc).resolve().parent,
    ]
    if os.name == "posix":
        tool_dirs.extend(Path(item) for item in ("/usr/bin", "/bin"))
    path_value = os.pathsep.join(dict.fromkeys(path.as_posix() for path in tool_dirs))
    result = {
        "CARGO_HOME": directories["CARGO_HOME"].as_posix(),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_TARGET_DIR": directories["CARGO_TARGET_DIR"].as_posix(),
        "CARGO_TERM_COLOR": "never",
        "HOME": directories["HOME"].as_posix(),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": path_value,
        "RUSTC": Path(os.path.abspath(Path(rustc))).as_posix(),
        "TMPDIR": directories["TMPDIR"].as_posix(),
    }
    selected = normalized_environment_overrides(overrides)
    result.update(selected)
    return result


def normalized_environment_overrides(
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    selected = dict(overrides or {})
    if set(selected) - RUNTIME_OVERRIDE_KEYS:
        raise ValueError("c2rust_process_environment_override_invalid")
    for key in ("CARGO_HOME", "RUSTUP_HOME"):
        if key not in selected:
            continue
        value = selected[key]
        try:
            path = Path(value).resolve(strict=True)
        except (OSError, TypeError) as error:
            raise ValueError("c2rust_process_environment_path_invalid") from error
        if not path.is_dir() or not Path(value).is_absolute():
            raise ValueError("c2rust_process_environment_path_invalid")
        selected[key] = path.as_posix()
    if "RUSTC_BOOTSTRAP" in selected and selected["RUSTC_BOOTSTRAP"] != "1":
        raise ValueError("c2rust_process_rustc_bootstrap_invalid")
    return selected


def cargo_toolchain_prefix(value: str | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str) or _TOOLCHAIN.fullmatch(value) is None:
        raise ValueError("c2rust_cargo_toolchain_invalid")
    return [f"+{value}"]


def run_recorded_process(
    argv: Sequence[str], *, cwd: Path, environment: Mapping[str, str],
    timeout_seconds: int, out_root: Path, purpose: str,
    portable_argv: Sequence[str], portable_working_directory: str,
    stdin: bytes = b"", expected_returncodes: Sequence[int] = (0,),
    allowed_environment_keys: Sequence[str] = (),
    runner: Runner | None = None,
) -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
]:
    command = validated_command(argv)
    published_command = validated_portable_command(portable_argv)
    published_workdir = validated_portable_path(portable_working_directory)
    workdir = Path(cwd).resolve(strict=True)
    if not workdir.is_dir():
        raise ValueError("c2rust_process_working_directory_invalid")
    if (
        type(timeout_seconds) is not int
        or not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS
    ):
        raise ValueError("c2rust_process_timeout_invalid")
    input_bytes = validated_stdin(stdin, limit=MAX_PROCESS_OUTPUT_BYTES)
    expected = validated_expected_returncodes(expected_returncodes)
    env = validated_environment(environment, allowed_environment_keys)
    selected = runner or default_process_runner
    try:
        outcome = selected(command, workdir, env, timeout_seconds, input_bytes)
    except (OSError, subprocess.SubprocessError) as error:
        outcome = ProcessOutcome(
            None, b"", str(error).encode("utf-8", errors="replace"),
            command_started=False,
        )
    if not isinstance(outcome, ProcessOutcome):
        raise ValueError("c2rust_process_runner_result_invalid")
    stdout, stdout_limited = _bounded(outcome.stdout)
    stderr, stderr_limited = _bounded(outcome.stderr)
    stdout_ref = write_cas_artifact(
        out_root, "process-stdout", stdout, suffix="bin",
        limit=MAX_PROCESS_OUTPUT_BYTES,
    )
    stderr_ref = write_cas_artifact(
        out_root, "process-stderr", stderr, suffix="bin",
        limit=MAX_PROCESS_OUTPUT_BYTES,
    )
    stdin_ref = write_cas_artifact(
        out_root, "process-stdin", input_bytes, suffix="bin",
        limit=MAX_PROCESS_OUTPUT_BYTES,
    )
    output_limited = stdout_limited or stderr_limited
    passed = (
        outcome.command_started is True and outcome.timed_out is False
        and outcome.returncode in expected and not output_limited
    )
    evidence = {
        "schema_version": 2,
        "artifact_kind": "c2rust-project-process-execution",
        "purpose": purpose,
        "status": "passed" if passed else "failed",
        "argv": published_command,
        "argv_sha256": content_sha256(published_command),
        "local_execution_binding_sha256": content_sha256({
            "argv": command, "working_directory": workdir.as_posix(),
            "stdin_sha256": stdin_ref["sha256"],
            "expected_returncodes": expected,
            "environment": dict(sorted(env.items())),
        }),
        "working_directory": published_workdir,
        "environment_keys": sorted(env),
        "environment_sha256": content_sha256(dict(sorted(env.items()))),
        "timeout_seconds": timeout_seconds,
        "expected_returncodes": expected,
        "stdin_sha256": stdin_ref["sha256"],
        "stdin_ref": stdin_ref,
        "command_started": outcome.command_started,
        "timed_out": outcome.timed_out,
        "returncode": outcome.returncode,
        "output_limit_exceeded": output_limited,
        "stdout_sha256": stdout_ref["sha256"],
        "stderr_sha256": stderr_ref["sha256"],
        "stdout_ref": stdout_ref,
        "stderr_ref": stderr_ref,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return evidence, (stdout_ref, stderr_ref, stdin_ref)


def default_process_runner(
    argv: Sequence[str], cwd: Path, environment: Mapping[str, str],
    timeout_seconds: int, stdin: bytes,
) -> ProcessOutcome:
    try:
        completed = subprocess.run(
            list(argv), cwd=cwd, env=dict(environment), input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=timeout_seconds,
        )
        return ProcessOutcome(
            completed.returncode, completed.stdout, completed.stderr,
        )
    except subprocess.TimeoutExpired as error:
        return ProcessOutcome(
            None, _timeout_bytes(error.stdout), _timeout_bytes(error.stderr),
            timed_out=True,
        )


def _bounded(value: bytes) -> tuple[bytes, bool]:
    if type(value) is not bytes:
        raise ValueError("c2rust_process_output_invalid")
    return value[:MAX_PROCESS_OUTPUT_BYTES], len(value) > MAX_PROCESS_OUTPUT_BYTES


def _timeout_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    return value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")


__all__ = [
    "ProcessOutcome", "Runner", "cargo_toolchain_prefix", "executable_binding",
    "minimal_process_environment", "normalized_environment_overrides",
    "run_recorded_process",
]
