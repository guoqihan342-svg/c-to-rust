from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any

from .sandbox_contract import SandboxContract, canonical_sha256
from .sandbox_environment import cargo_guest_environment
from .sandbox_probe import make_probe_receipt, validate_probe_receipt
from .sandbox_requirements import ENVIRONMENT_ALLOWLIST, REQUIRED_CAPABILITIES


_MAX_PROBE_BYTES = 64 * 1024
_NAMESPACES = ("mnt", "net", "pid", "user")
_PROBE_SCRIPT = r"""
set -eu
umask 077
if (printf probe > /workspace/.c2r-sandbox-probe) 2>/dev/null; then exit 41; fi
cargo_path=$(command -v cargo)
if [ -z "$cargo_path" ]; then exit 42; fi
if (printf probe > "$cargo_path") 2>/dev/null; then exit 43; fi
if /usr/bin/find /home/sandbox -mindepth 1 -print -quit | /usr/bin/grep -q .; then exit 44; fi
printf runtime > /runtime/write-ok
printf temporary > /tmp/write-ok
printf home > /home/sandbox/write-ok
for name in mnt net pid user; do
  value=$(/usr/bin/readlink "/proc/self/ns/$name")
  printf '%s=%s\n' "$name" "$value"
done > /runtime/namespaces
/usr/bin/env > /runtime/environment
/bin/cat /proc/self/status > /runtime/status
/bin/cat /proc/self/limits > /runtime/limits
/bin/cat /proc/net/route > /runtime/routes
"""


def bubblewrap_version(
    path: Path, *, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> str:
    completed = (runner or subprocess.run)(
        [str(path), "--version"],
        env={"LANG": "C", "LC_ALL": "C"},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="strict",
        timeout=5, check=False,
    )
    stdout = completed.stdout.strip()
    if (
        completed.returncode != 0
        or completed.stderr
        or not stdout.startswith("bubblewrap ")
        or len(stdout) > 96
    ):
        raise ValueError("bubblewrap version is untrusted")
    version = stdout.removeprefix("bubblewrap ")
    if not version or any(character not in "0123456789.+_-" for character in version):
        raise ValueError("bubblewrap version is untrusted")
    return version


def run_bubblewrap_probe(
    *, contract: SandboxContract, backend_version: str, project_root: Path,
    argv_builder: Callable[[Path, Sequence[str]], list[str]],
    executor: Callable[..., subprocess.CompletedProcess[str]],
    preexec_fn: Callable[[], None],
) -> object:
    project = project_root.resolve(strict=True)
    if not project.is_dir():
        raise ValueError("sandbox probe project input is invalid")
    host_namespaces = _host_namespaces()
    probe_root = Path(tempfile.mkdtemp(prefix="c2r-sandbox-probe-"))
    runtime = probe_root / "runtime"
    runtime.mkdir(mode=0o700)
    stdout_path = probe_root / "stdout"
    stderr_path = probe_root / "stderr"
    observation: dict[str, Any] | None = None
    results: dict[str, bool] | None = None
    failure: Exception | None = None
    try:
        command = ("/bin/sh", "-c", _PROBE_SCRIPT, "sandbox-probe")
        argv = argv_builder(runtime, command)
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            completed = executor(
                argv, cwd=runtime,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                stdout=stdout, stderr=stderr, timeout=15, check=False,
                preexec_fn=preexec_fn,
            )
        raw = {
            name: _read_bounded(runtime / name)
            for name in ("namespaces", "environment", "status", "limits", "routes")
        }
        stdout_text = _read_bounded(stdout_path)
        stderr_text = _read_bounded(stderr_path)
        results = _validate_observation(
            raw, host_namespaces, contract, completed.returncode,
            stdout_text, stderr_text,
        )
        observation = {
            "returncode": completed.returncode,
            "launcher_argv_sha256": canonical_sha256(_redact_argv(argv)),
            "host_namespaces_sha256": canonical_sha256(host_namespaces),
            "files": {
                name: canonical_sha256(text) for name, text in sorted(raw.items())
            },
            "stdout_sha256": canonical_sha256(stdout_text),
            "stderr_sha256": canonical_sha256(stderr_text),
        }
    except Exception as error:
        failure = error
    finally:
        cleanup_verified = _cleanup(probe_root)
    if failure is not None:
        raise ValueError("sandbox capability probe execution failed") from failure
    if observation is None or results is None:
        raise ValueError("sandbox capability probe produced no observation")
    results["exit-cleanup"] = cleanup_verified
    receipt = make_probe_receipt(
        contract=contract, backend_version=backend_version,
        capability_results=results, raw_observation=observation,
        cleanup_verified=cleanup_verified,
    )
    validate_probe_receipt(receipt, contract, contract.requirements)
    return receipt


def _validate_observation(
    raw: Mapping[str, str], host_namespaces: Mapping[str, str],
    contract: SandboxContract, returncode: int,
    stdout: str, stderr: str,
) -> dict[str, bool]:
    if returncode != 0 or stdout or stderr:
        raise ValueError("sandbox probe command failed")
    guest = _key_values(raw["namespaces"])
    if set(guest) != set(_NAMESPACES) or any(
        guest[name] == host_namespaces[name] for name in _NAMESPACES
    ):
        raise ValueError("sandbox namespace probe failed")
    routes = [line for line in raw["routes"].splitlines() if line.strip()]
    if len(routes) != 1 or not routes[0].lstrip().startswith("Iface"):
        raise ValueError("sandbox network route probe failed")
    _validate_capabilities(raw["status"])
    _validate_environment(raw["environment"])
    _validate_limits(raw["limits"], contract)
    results = {name: True for name in REQUIRED_CAPABILITIES}
    results["exit-cleanup"] = False
    return results


def _validate_capabilities(status: str) -> None:
    values = _status_values(status)
    for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        value = values.get(name)
        if value is None or not value or any(character != "0" for character in value):
            raise ValueError("sandbox privilege probe failed")


def _validate_environment(environment: str) -> None:
    values = _key_values(environment)
    required = cargo_guest_environment()
    allowed = set(ENVIRONMENT_ALLOWLIST) | {"OLDPWD", "PWD", "SHLVL", "_"}
    if (
        any(values.get(key) != value for key, value in required.items())
        or not set(values).issubset(allowed)
    ):
        raise ValueError("sandbox environment allowlist probe failed")


def _validate_limits(limits: str, contract: SandboxContract) -> None:
    expected = {
        "Max cpu time": str(contract.cpu_seconds),
        "Max file size": str(contract.file_size_bytes),
        "Max address space": str(contract.address_space_bytes),
        "Max processes": str(contract.process_count),
        "Max open files": str(contract.open_files),
    }
    for label, value in expected.items():
        lines = [line for line in limits.splitlines() if line.startswith(label)]
        if len(lines) != 1:
            raise ValueError("sandbox resource limit probe failed")
        columns = lines[0][len(label):].split()
        if len(columns) < 2 or columns[0] != value or columns[1] != value:
            raise ValueError("sandbox resource limit probe failed")


def _host_namespaces() -> dict[str, str]:
    try:
        return {name: os.readlink(f"/proc/self/ns/{name}") for name in _NAMESPACES}
    except OSError as error:
        raise ValueError("host namespace identity is unavailable") from error


def _key_values(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in result:
            raise ValueError("sandbox probe key/value observation is invalid")
        result[key] = value
    return result


def _status_values(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        matched = re.fullmatch(r"(Cap(?:Inh|Prm|Eff|Bnd|Amb)):\s*([0-9a-fA-F]+)", line)
        if matched:
            result[matched.group(1)] = matched.group(2)
    return result


def _read_bounded(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > _MAX_PROBE_BYTES:
        raise ValueError("sandbox probe output exceeds its bound")
    return data.decode("utf-8", errors="strict")


def _cleanup(root: Path) -> bool:
    try:
        if root.is_symlink():
            return False
        shutil.rmtree(root)
        return not root.exists()
    except OSError:
        return False


def _redact_argv(argv: Sequence[str]) -> list[str]:
    return [
        "<path>" if value.startswith("/") and value not in {
            "/bin/sh", "/workspace", "/runtime", "/tmp",
        } else value
        for value in argv
    ]


__all__ = ["bubblewrap_version", "run_bubblewrap_probe"]
