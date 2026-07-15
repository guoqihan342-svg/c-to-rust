from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import re
import shutil
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .make_dry_run_binding import validated_working_directory
from .make_dry_run_host_evidence import MAKE_ENVIRONMENT
from .make_dry_run_process import run_make_bubblewrap_process


_SYSTEM_DIRECTORIES = ("/usr", "/bin", "/lib", "/lib64")
_SYSTEM_FILES = (
    "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/passwd", "/etc/group",
)
_NAMESPACES = ("mnt", "net", "pid", "user")
_PROBE_SCRIPT = r"""
set -eu
umask 077
if (printf probe > /workspace/.make-dry-run-probe) 2>/dev/null; then exit 41; fi
if (printf probe > /toolchain/bin/make) 2>/dev/null; then exit 42; fi
printf runtime > /runtime/write-ok
printf temporary > /tmp/write-ok
for name in mnt net pid user; do
  value=$(/usr/bin/readlink "/proc/self/ns/$name")
  printf '%s=%s\n' "$name" "$value"
done > /runtime/namespaces
/usr/bin/env > /runtime/environment
/bin/cat /proc/self/status > /runtime/status
/bin/cat /proc/self/limits > /runtime/limits
/bin/cat /proc/net/route > /runtime/routes
"""


def run_make_sandbox_preflight(
    *, launcher: Path, make_binary: Path, project: Path, runtime: Path,
    plan: Mapping[str, Any],
) -> tuple[str, bool]:
    probe = runtime / "preflight-probe"
    if probe.exists():
        raise ValueError("make_dry_run_probe_root_exists")
    probe.mkdir(mode=0o700)
    cleanup = False
    try:
        host_namespaces = _host_namespaces()
        argv = _base_bubblewrap_argv(
            launcher=launcher,
            make_binary=make_binary,
            workspace=project,
            runtime=probe,
            working_directory=plan["working_directory"],
            guest_command=("/bin/sh", "-c", _PROBE_SCRIPT, "make-probe"),
        )
        result = run_make_bubblewrap_process(
            argv,
            timeout_seconds=30,
            max_stdout_bytes=64 * 1024,
            max_stderr_bytes=64 * 1024,
            resource_limits=plan["resource_limits"],
        )
        raw = {
            name: _read_probe_file(probe / name)
            for name in ("namespaces", "environment", "status", "limits", "routes")
        }
        _validate_probe(result, raw, host_namespaces, plan)
        observation = {
            "returncode": result.returncode,
            "files": {
                name: hashlib.sha256(text.encode("utf-8")).hexdigest()
                for name, text in sorted(raw.items())
            },
            "host_namespaces_sha256": content_sha256(host_namespaces),
            "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        }
        observation_sha256 = content_sha256(observation)
    finally:
        try:
            shutil.rmtree(probe)
            cleanup = not probe.exists()
        except OSError:
            cleanup = False
    if not cleanup:
        raise ValueError("make_dry_run_probe_cleanup_failed")
    return observation_sha256, cleanup


def build_make_bubblewrap_argv(
    *, launcher: Path, make_binary: Path, workspace: Path, runtime: Path,
    working_directory: str, make_args: tuple[str, ...], marker_name: str,
    plan_sha256: str, command_sha256: str,
) -> list[str]:
    if (
        not re.fullmatch(r"make-[0-9a-f]{64}\.started", marker_name)
        or not is_sha256(plan_sha256) or not is_sha256(command_sha256)
        or type(make_args) is not tuple
        or any(type(item) is not str or not item for item in make_args)
    ):
        raise ValueError("make_dry_run_bubblewrap_command_invalid")
    marker = f"/runtime/{marker_name}"
    guest = (
        "/bin/sh", "-c",
        "umask 077; printf '%s\\n%s\\n' \"$1\" \"$2\" > \"$3\" "
        "|| exit 125; shift 3; exec \"$@\"",
        "make-launch", plan_sha256, command_sha256, marker,
        "/toolchain/bin/make", *make_args,
    )
    return _base_bubblewrap_argv(
        launcher=launcher, make_binary=make_binary, workspace=workspace,
        runtime=runtime, working_directory=working_directory,
        guest_command=guest,
    )


def _base_bubblewrap_argv(
    *, launcher: Path, make_binary: Path, workspace: Path, runtime: Path,
    working_directory: str, guest_command: tuple[str, ...],
) -> list[str]:
    workdir = validated_working_directory(working_directory)
    binary = make_binary.resolve(strict=True)
    root = workspace.resolve(strict=True)
    output = runtime.resolve(strict=True)
    if not root.is_dir() or not output.is_dir():
        raise ValueError("make_dry_run_bubblewrap_root_invalid")
    argv = [
        str(launcher.resolve(strict=True)), "--die-with-parent", "--new-session",
        "--unshare-all", "--cap-drop", "ALL", "--clearenv",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/workspace", "--dir", "/runtime",
        "--dir", "/toolchain", "--dir", "/toolchain/bin",
        "--dir", "/home", "--dir", "/home/sandbox", "--dir", "/etc",
    ]
    for value in _SYSTEM_DIRECTORIES:
        if Path(value).exists():
            argv.extend(("--ro-bind", value, value))
    for value in _SYSTEM_FILES:
        if Path(value).is_file():
            argv.extend(("--ro-bind", value, value))
    if Path("/etc/ld.so.conf.d").is_dir():
        argv.extend(("--ro-bind", "/etc/ld.so.conf.d", "/etc/ld.so.conf.d"))
    argv.extend((
        "--ro-bind", str(root), "/workspace",
        "--bind", str(output), "/runtime",
        "--ro-bind", str(binary), "/toolchain/bin/make",
    ))
    for key, value in MAKE_ENVIRONMENT:
        argv.extend(("--setenv", key, value))
    guest_workdir = "/workspace" if workdir == "." else f"/workspace/{workdir}"
    argv.extend(("--chdir", guest_workdir, "--", *guest_command))
    return argv


def _validate_probe(
    result: Any, raw: Mapping[str, str], host: Mapping[str, str],
    plan: Mapping[str, Any],
) -> None:
    if (
        not result.started or result.returncode != 0 or result.stdout or result.stderr
        or result.timed_out or result.output_limit_exceeded
        or not result.cleanup_verified
    ):
        raise ValueError("make_dry_run_capability_probe_failed")
    guest = _key_values(raw["namespaces"])
    if set(guest) != set(_NAMESPACES) or any(
        guest[name] == host[name] for name in _NAMESPACES
    ):
        raise ValueError("make_dry_run_namespace_probe_failed")
    routes = [line for line in raw["routes"].splitlines() if line.strip()]
    if len(routes) != 1 or not routes[0].lstrip().startswith("Iface"):
        raise ValueError("make_dry_run_network_probe_failed")
    status = _status_values(raw["status"])
    if any(
        not status.get(name) or any(character != "0" for character in status[name])
        for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    ):
        raise ValueError("make_dry_run_privilege_probe_failed")
    environment = _key_values(raw["environment"])
    allowed = {key for key, _ in MAKE_ENVIRONMENT} | {"OLDPWD", "PWD", "SHLVL", "_"}
    if (
        any(environment.get(key) != value for key, value in MAKE_ENVIRONMENT)
        or not set(environment).issubset(allowed)
    ):
        raise ValueError("make_dry_run_environment_probe_failed")
    _validate_limit_observation(raw["limits"], plan["resource_limits"])


def _validate_limit_observation(text: str, limits: Mapping[str, int]) -> None:
    expected = {
        "Max cpu time": str(limits["cpu_seconds"]),
        "Max file size": str(limits["file_size_bytes"]),
        "Max address space": str(limits["address_space_bytes"]),
        "Max processes": str(limits["process_count"]),
        "Max open files": str(limits["open_files"]),
    }
    for label, expected_value in expected.items():
        lines = [line for line in text.splitlines() if line.startswith(label)]
        columns = lines[0][len(label):].split() if len(lines) == 1 else []
        if len(columns) < 2 or columns[0] != expected_value or columns[1] != expected_value:
            raise ValueError("make_dry_run_resource_probe_failed")


def _host_namespaces() -> dict[str, str]:
    try:
        return {name: os.readlink(f"/proc/self/ns/{name}") for name in _NAMESPACES}
    except OSError as error:
        raise ValueError("make_dry_run_host_namespace_unavailable") from error


def _read_probe_file(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > 64 * 1024:
        raise ValueError("make_dry_run_probe_output_limit_exceeded")
    return data.decode("utf-8", errors="strict")


def _key_values(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in result:
            raise ValueError("make_dry_run_probe_key_values_invalid")
        result[key] = value
    return result


def _status_values(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        matched = re.fullmatch(
            r"(Cap(?:Inh|Prm|Eff|Bnd|Amb)):\s*([0-9a-fA-F]+)", line,
        )
        if matched:
            result[matched.group(1)] = matched.group(2)
    return result


__all__ = ["build_make_bubblewrap_argv", "run_make_sandbox_preflight"]
