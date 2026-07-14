from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable

from .c_toolchain_output import (
    EMPTY_SHA256, encoded_probe_streams, reported_value,
)
from .c_toolchain_runner import (
    MAX_PROBE_STREAM_BYTES, PROBE_TIMEOUT_SECONDS, ProbeExecution,
    bounded_subprocess_runner,
)


PROBE_KINDS = ("version", "target", "sysroot", "resource-dir", "linker-path")
Runner = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ProbePlan:
    kind: str
    arguments: tuple[str, ...]
    interpretation: str
    applicable: bool = True


def probe_plans(
    family: str, roles: list[str] | tuple[str, ...],
) -> list[ProbePlan]:
    plans = {
        "version": ProbePlan("version", (), "tool-version", False),
        "target": ProbePlan("target", (), "reported-target", False),
        "sysroot": ProbePlan(
            "sysroot", (), "reported-sysroot-or-default", False,
        ),
        "resource-dir": ProbePlan(
            "resource-dir", (), "clang-default-resource-root", False,
        ),
        "linker-path": ProbePlan(
            "linker-path", (), "derived-linker-token", False,
        ),
    }
    if family == "compiler-wrapper":
        return [plans[kind] for kind in PROBE_KINDS]
    if family in {"msvc-compiler", "msvc-linker", "msvc-archiver"}:
        plans["version"] = ProbePlan("version", ("/?",), "tool-version")
        if family == "msvc-compiler":
            plans["target"] = ProbePlan(
                "target", ("/Bv",), "reported-target",
            )
    else:
        version_args = ("--version",)
        if family in {"clang-compiler", "clang-cl-compiler"}:
            version_args = ("--no-default-config", "--version")
        plans["version"] = ProbePlan(
            "version", version_args, "tool-version",
        )
    if family in {"gnu-compiler", "intel-compiler"}:
        plans["target"] = ProbePlan(
            "target", ("-dumpmachine",), "reported-target",
        )
        plans["sysroot"] = ProbePlan(
            "sysroot", ("-print-sysroot",), "reported-sysroot-or-default",
        )
    elif family in {"clang-compiler", "clang-cl-compiler"}:
        plans["target"] = ProbePlan(
            "target", ("--no-default-config", "-print-target-triple"),
            "reported-target",
        )
        plans["resource-dir"] = ProbePlan(
            "resource-dir", ("--no-default-config", "-print-resource-dir"),
            "clang-default-resource-root",
        )
    if "linker-driver" in roles and family in {
        "gnu-compiler", "intel-compiler", "clang-compiler",
        "clang-cl-compiler",
    }:
        prefix = ("--no-default-config",) if family.startswith("clang") else ()
        plans["linker-path"] = ProbePlan(
            "linker-path", (*prefix, "-print-prog-name=ld"),
            "derived-linker-token",
        )
    return [plans[kind] for kind in PROBE_KINDS]


def run_tool_probes(
    resolved_path: str, family: str, roles: list[str] | tuple[str, ...], *,
    environment: Mapping[str, str], runner: Runner | None,
) -> list[dict[str, Any]]:
    executable = Path(resolved_path)
    if not executable.is_absolute():
        raise ValueError("c_toolchain_probe_executable_not_absolute")
    records = []
    for plan in probe_plans(family, roles):
        if not plan.applicable:
            records.append(_not_applicable(plan))
            continue
        argv = [str(executable), *plan.arguments]
        try:
            execution = _invoke_runner(runner, argv, environment)
        except subprocess.TimeoutExpired as error:
            execution = ProbeExecution(
                None, _bytes(error.stdout), _bytes(error.stderr), timed_out=True,
            )
        except (OSError, TypeError, ValueError, subprocess.SubprocessError):
            execution = ProbeExecution(None, b"", b"", started=False)
        records.append(_probe_record(plan, execution, family))
    return records


def _invoke_runner(
    runner: Runner | None, argv: list[str], environment: Mapping[str, str],
) -> ProbeExecution:
    value = (runner or bounded_subprocess_runner)(
        argv,
        environment=dict(environment),
        timeout_seconds=PROBE_TIMEOUT_SECONDS,
        max_output_bytes=MAX_PROBE_STREAM_BYTES,
    )
    if isinstance(value, ProbeExecution):
        return value
    if isinstance(value, subprocess.CompletedProcess):
        return ProbeExecution(
            int(value.returncode), _bytes(value.stdout), _bytes(value.stderr),
        )
    if isinstance(value, Mapping) and set(value) == {
        "returncode", "stdout", "stderr", "timed_out", "flooded", "started",
    }:
        if any(type(value[key]) is not bool for key in (
            "timed_out", "flooded", "started",
        )):
            raise TypeError("c_toolchain_probe_runner_result_invalid")
        return ProbeExecution(
            value["returncode"],
            _bytes(value["stdout"]),
            _bytes(value["stderr"]),
            value["timed_out"],
            value["flooded"],
            value["started"],
        )
    raise TypeError("c_toolchain_probe_runner_result_invalid")


def _probe_record(
    plan: ProbePlan, execution: ProbeExecution, family: str,
) -> dict[str, Any]:
    stdout = execution.stdout[:MAX_PROBE_STREAM_BYTES + 1]
    stderr = execution.stderr[:MAX_PROBE_STREAM_BYTES + 1]
    value = None
    if (
        execution.flooded
        or len(stdout) > MAX_PROBE_STREAM_BYTES
        or len(stderr) > MAX_PROBE_STREAM_BYTES
    ):
        status = "output-flood"
    elif execution.timed_out:
        status = "timed-out"
    elif not execution.started or type(execution.returncode) is not int:
        status = "failed"
    else:
        try:
            value = reported_value(plan.kind, stdout, stderr, family)
        except UnicodeDecodeError:
            status, value = "failed", None
        else:
            accepts_nonzero = family.startswith("msvc-") and plan.kind in {
                "version", "target",
            }
            if execution.returncode != 0 and not (accepts_nonzero and value):
                status, value = "failed", None
            elif value is None and plan.kind == "sysroot":
                status = "reported-empty/default"
            elif value is None:
                status = "failed"
            else:
                status = "reported"
    return {
        "kind": plan.kind,
        "arguments": list(plan.arguments),
        "interpretation": plan.interpretation,
        "status": status,
        "returncode": execution.returncode,
        "value": value,
        **encoded_probe_streams(stdout, stderr),
    }


def _not_applicable(plan: ProbePlan) -> dict[str, Any]:
    return {
        "kind": plan.kind,
        "arguments": [],
        "interpretation": plan.interpretation,
        "status": "not-applicable",
        "returncode": None,
        "value": None,
        **encoded_probe_streams(b"", b""),
    }


def _bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8") if isinstance(value, str) else b""


__all__ = [
    "EMPTY_SHA256", "MAX_PROBE_STREAM_BYTES", "PROBE_KINDS",
    "PROBE_TIMEOUT_SECONDS", "ProbeExecution", "ProbePlan",
    "bounded_subprocess_runner", "probe_plans", "run_tool_probes",
]
