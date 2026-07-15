from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from collections.abc import Mapping
from typing import Any

from .artifacts import checked_relative_path
from .c_toolchain_schema import tool_records_by_token
from .clang_toolchain_binding import (
    reopen_clang_toolchain_binding, validate_clang_toolchain_receipt,
)
from .gate_evidence import read_content_addressed_json
from .sandbox_contract import SandboxContract, validate_contract
from .sandbox_probe import SandboxProbeReceipt, validate_probe_receipt


_MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ClangHostBindings:
    portable: dict[str, Any]
    receipt: dict[str, Any]
    tool_bindings: tuple[tuple[Path, str], ...]


def load_clang_host_bindings(
    ledger_path: Path, receipt: Mapping[str, Any],
) -> ClangHostBindings:
    reopened = reopen_clang_toolchain_binding(Path(ledger_path), receipt)
    validated = validate_clang_toolchain_receipt(reopened)
    reference = validated["host_evidence"]
    evidence = read_content_addressed_json(
        Path(ledger_path), reference["path"], reference["sha256"],
    )
    records = tool_records_by_token(evidence)
    if set(records) != {"clang"}:
        raise ValueError("clang_fact_runner_toolchain_set_invalid")
    tool = records["clang"]
    portable = validated["portable_binding"]
    binary = _secure_path(tool.get("resolved_path"), "file", "clang_binary")
    if _file_binding(binary, _MAX_EXECUTABLE_BYTES) != portable["binary"]:
        raise ValueError("clang_fact_runner_binary_drifted")
    probes = {item.get("kind"): item for item in tool.get("probes", [])}
    resource = _bound_probe_path(
        probes.get("resource-dir"), portable["resource_dir"],
        "resource_dir", required=True,
    )
    sysroot = _bound_probe_path(
        probes.get("sysroot"), portable["sysroot"],
        "sysroot", required=False,
    )
    bindings = [(binary, "/toolchain/bin/clang")]
    if resource is None:
        raise ValueError("clang_fact_runner_resource_dir_missing")
    bindings.append((resource, "/toolchain/resource"))
    if sysroot is not None:
        bindings.append((sysroot, "/toolchain/sysroot"))
    return ClangHostBindings(portable, validated, tuple(bindings))


def verify_clang_host_binding_current(
    ledger_path: Path, receipt: Mapping[str, Any],
) -> None:
    reopen_clang_toolchain_binding(Path(ledger_path), receipt)


def validate_clang_sandbox(
    launcher: Path, contract: SandboxContract, probe: SandboxProbeReceipt,
    portable: Mapping[str, Any],
) -> Path:
    validate_contract(contract)
    validate_probe_receipt(probe, contract, contract.requirements)
    if (
        contract.native_linker is not None
        or contract.toolchain_sha256 != portable.get("binding_sha256")
    ):
        raise ValueError("clang_fact_runner_sandbox_toolchain_drifted")
    binary = _secure_path(launcher, "file", "bubblewrap")
    if binary.name != "bwrap" or not os.access(binary, os.X_OK):
        raise ValueError("clang_fact_runner_bubblewrap_invalid")
    if _file_sha256(binary, _MAX_EXECUTABLE_BYTES) != contract.launcher_sha256:
        raise ValueError("clang_fact_runner_bubblewrap_drifted")
    return binary


def validate_c_repository(
    repo_root: Path, build_ir: Mapping[str, Any],
) -> tuple[Path, dict[str, str]]:
    repository = _secure_path(repo_root, "dir", "repository")
    _reject_tree_links(repository)
    sources = build_ir.get("source_inputs")
    if not isinstance(sources, list) or not sources:
        raise ValueError("clang_fact_runner_source_set_invalid")
    result: dict[str, str] = {}
    for binding in sources:
        if not isinstance(binding, Mapping):
            raise ValueError("clang_fact_runner_source_binding_invalid")
        relative = checked_relative_path(binding.get("path"))
        path = _repository_path(repository, relative, "file")
        expected = {
            "sha256": binding.get("sha256"), "size_bytes": binding.get("size_bytes"),
        }
        if _file_binding(path, max(path.stat().st_size, 1)) != expected:
            raise ValueError("clang_fact_runner_source_drifted")
        if relative in result and result[relative] != expected["sha256"]:
            raise ValueError("clang_fact_runner_source_binding_conflict")
        result[relative] = str(expected["sha256"])
    return repository, dict(sorted(result.items()))


def fixed_out_root(ledger_path: Path) -> Path:
    database = _secure_path(ledger_path, "file", "ledger")
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise ValueError("clang_fact_runner_fixed_ledger_required")
    return database.parent.parent.resolve(strict=True)


def create_runtime(runtime_parent: Path, repository: Path) -> Path:
    requested = Path(runtime_parent)
    if _is_linklike(requested):
        raise ValueError("clang_fact_runner_runtime_link_rejected")
    requested.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = _secure_path(requested, "dir", "runtime_parent")
    if _overlaps(parent, repository):
        raise ValueError("clang_fact_runner_runtime_overlaps_repository")
    return Path(tempfile.mkdtemp(prefix="clang-fact-", dir=parent))


def cleanup_runtime(runtime: Path) -> bool:
    try:
        if _is_linklike(runtime):
            return False
        shutil.rmtree(runtime)
        return not runtime.exists() and not runtime.is_symlink()
    except OSError:
        return False


def _bound_probe_path(
    probe: Any, portable: Any, name: str, *, required: bool,
) -> Path | None:
    if not isinstance(probe, Mapping) or not isinstance(portable, Mapping):
        raise ValueError(f"clang_fact_runner_{name}_probe_invalid")
    projection = {
        key: probe.get(key) for key in ("status", "stdout_sha256", "stderr_sha256")
    }
    if projection != dict(portable):
        raise ValueError(f"clang_fact_runner_{name}_probe_drifted")
    status = probe.get("status")
    if status == "reported":
        return _secure_path(probe.get("value"), "dir", name)
    if required or status not in {"reported-empty/default", "not-applicable"}:
        raise ValueError(f"clang_fact_runner_{name}_missing")
    return None


def _repository_path(root: Path, relative: str, kind: str) -> Path:
    path = root.joinpath(*PurePosixPath(relative).parts)
    resolved = _secure_path(path, kind, "repository_input")
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("clang_fact_runner_repository_escape") from error
    return resolved


def _secure_path(value: Any, kind: str, name: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError(f"clang_fact_runner_{name}_path_invalid")
    requested = Path(value)
    if (
        not requested.is_absolute()
        or any(part in {".", ".."} for part in requested.parts)
    ):
        raise ValueError(f"clang_fact_runner_{name}_path_invalid")
    _reject_path_links(requested, name)
    try:
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"clang_fact_runner_{name}_path_invalid") from error
    if (kind == "file" and not resolved.is_file()) \
            or (kind == "dir" and not resolved.is_dir()):
        raise ValueError(f"clang_fact_runner_{name}_path_invalid")
    return resolved


def _reject_path_links(path: Path, name: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if _is_linklike(current):
            raise ValueError(f"clang_fact_runner_{name}_path_invalid")


def _reject_tree_links(root: Path) -> None:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            raise ValueError("clang_fact_runner_repository_unreadable") from error
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink() or _is_linklike(path):
                raise ValueError("clang_fact_runner_repository_link_rejected")
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)


def _file_binding(path: Path, maximum: int) -> dict[str, Any]:
    size = path.stat().st_size
    return {"sha256": _file_sha256(path, maximum), "size_bytes": size}


def _file_sha256(path: Path, maximum: int) -> str:
    size = path.stat().st_size
    if size < 1 or size > maximum:
        raise ValueError("clang_fact_runner_file_size_invalid")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_linklike(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(callable(junction) and junction())


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


__all__ = [
    "ClangHostBindings", "cleanup_runtime", "create_runtime", "fixed_out_root",
    "load_clang_host_bindings", "validate_c_repository", "validate_clang_sandbox",
    "verify_clang_host_binding_current",
]
