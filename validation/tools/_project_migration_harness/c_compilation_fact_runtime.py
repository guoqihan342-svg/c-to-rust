from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .build_ir_toolchains import tool_basename
from .clang_fact_command_security import rebuild_clang_compile_context
from .clang_fact_runner_paths import cleanup_runtime, create_runtime, validate_c_repository
from .clang_fact_runner_process import ClangProcessResult, run_bounded_bubblewrap
from .c_compilation_fact_raw import (
    MAX_C_COMPILER_STDERR_BYTES,
    MAX_C_COMPILER_STDOUT_BYTES,
)
from .sandbox_bubblewrap_argv import build_bubblewrap_argv, resource_limiter
from .sandbox_contract import SandboxContract
from .sandbox_environment import canonical_environment_items, cargo_guest_environment
from .sandbox_linux_probe import bubblewrap_version, run_bubblewrap_probe
from .sandbox_probe import SandboxProbeReceipt
from .sandbox_toolchain import file_sha256


C_COMPILATION_TIMEOUT_SECONDS = 60
_SYSTEM_ROOTS = tuple(Path(value) for value in ("/usr", "/bin", "/lib", "/lib64"))


@dataclass(frozen=True, slots=True)
class CCompilerBinding:
    toolchain_id: str
    path: Path
    portable: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CCompilationRuntime:
    repository: Path
    launcher: Path
    contract: SandboxContract
    probe: SandboxProbeReceipt
    compilers: dict[str, CCompilerBinding]


def prepare_c_compilation_runtime(
    repo_root: Path,
    build_ir: Mapping[str, Any],
) -> CCompilationRuntime:
    if platform.system() != "Linux":
        raise RuntimeError("c_compilation_fact_linux_required")
    repository, _ = validate_c_repository(Path(repo_root), build_ir)
    launcher_value = shutil.which("bwrap")
    if not launcher_value:
        raise RuntimeError("c_compilation_fact_bubblewrap_unavailable")
    launcher = Path(launcher_value).resolve(strict=True)
    _validate_launcher(launcher)
    compilers = _compiler_bindings(build_ir)
    toolchain_digest = content_sha256([
        binding.portable for binding in sorted(
            compilers.values(), key=lambda item: item.toolchain_id
        )
    ])
    contract = SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256=file_sha256(launcher),
        toolchain_sha256=toolchain_digest,
    )
    environment = canonical_environment_items(cargo_guest_environment())
    first = compilers[sorted(compilers)[0]]
    version = bubblewrap_version(launcher)
    probe = run_bubblewrap_probe(
        contract=contract,
        backend_version=version,
        project_root=repository,
        argv_builder=lambda runtime, command: build_bubblewrap_argv(
            launcher=launcher,
            workspace=repository,
            runtime=runtime,
            tool_bindings=(),
            environment=environment,
            guest_command=tuple(command),
        ),
        executor=subprocess.run,
        preexec_fn=resource_limiter(contract),
        required_tool=first.path.name,
    )
    if not isinstance(probe, SandboxProbeReceipt):
        raise RuntimeError("c_compilation_fact_probe_invalid")
    return CCompilationRuntime(repository, launcher, contract, probe, compilers)


def run_c_syntax_plan(
    *,
    runtime: CCompilationRuntime,
    repo_root: Path,
    runtime_parent: Path,
    unit: Mapping[str, Any],
) -> tuple[dict[str, Any], ClangProcessResult, bool, bool]:
    binding = runtime.compilers.get(str(unit.get("toolchain_id")))
    if binding is None:
        raise ValueError("c_compilation_fact_toolchain_binding_missing")
    rebuilt = rebuild_clang_compile_context(unit)
    source = f"/workspace/{rebuilt['source_path']}"
    argv = [
        str(binding.path),
        *rebuilt["argv"],
        "-fsyntax-only",
        source,
    ]
    compile_context = {
        "language": unit["language"],
        "working_directory": rebuilt["working_directory"],
        "semantic_arguments": rebuilt["semantic_arguments"],
        "includes": rebuilt["includes"],
        "defines": rebuilt["defines"],
    }
    compile_arguments = unit.get("compile_arguments")
    if not isinstance(compile_arguments, Mapping):
        raise ValueError("c_compilation_fact_compile_arguments_invalid")
    core = {
        "schema_version": 1,
        "artifact_kind": "c-compilation-syntax-plan",
        "unit_id": unit["unit_id"],
        "source": dict(unit["source"]),
        "toolchain_id": binding.toolchain_id,
        "toolchain_binding_sha256": binding.portable["binding_sha256"],
        "expanded_argv_sha256": compile_arguments["expanded_argv_sha256"],
        "compile_context_sha256": content_sha256(compile_context),
        "argv_sha256": content_sha256(argv),
        "sandbox_contract_sha256": runtime.contract.sha256,
        "sandbox_probe_sha256": runtime.probe.sha256,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    plan = {**core, "plan_sha256": content_sha256(core)}
    repository = Path(repo_root).resolve(strict=True)
    if repository != runtime.repository:
        raise ValueError("c_compilation_fact_repository_drifted")
    before = _compiler_identity(binding.path)
    isolated = create_runtime(Path(runtime_parent), repository)
    environment = canonical_environment_items(cargo_guest_environment())
    try:
        sandbox_argv = build_bubblewrap_argv(
            launcher=runtime.launcher,
            workspace=repository,
            runtime=isolated,
            tool_bindings=(),
            environment=environment,
            guest_command=tuple(argv),
        )
        result = run_bounded_bubblewrap(
            sandbox_argv,
            timeout_seconds=C_COMPILATION_TIMEOUT_SECONDS,
            max_stdout_bytes=MAX_C_COMPILER_STDOUT_BYTES,
            max_stderr_bytes=MAX_C_COMPILER_STDERR_BYTES,
            max_combined_bytes=(
                MAX_C_COMPILER_STDOUT_BYTES + MAX_C_COMPILER_STDERR_BYTES
            ),
            preexec_fn=resource_limiter(runtime.contract),
        )
    finally:
        cleanup_verified = cleanup_runtime(isolated)
    compiler_stable = before == _compiler_identity(binding.path)
    return plan, result, cleanup_verified, compiler_stable


def _compiler_bindings(
    build_ir: Mapping[str, Any],
) -> dict[str, CCompilerBinding]:
    values = _required_compiler_records(build_ir)
    result: dict[str, CCompilerBinding] = {}
    for record in values:
        toolchain_id = record.get("toolchain_id")
        tools = record.get("tools")
        drivers = [
            item for item in tools
            if isinstance(item, Mapping) and item.get("relation") == "driver"
        ] if isinstance(tools, list) else []
        if (
            not isinstance(toolchain_id, str)
            or not toolchain_id
            or record.get("role") != "compiler-driver"
            or record.get("wrappers") != []
            or len(drivers) != 1
        ):
            raise ValueError("c_compilation_fact_toolchain_invalid")
        tool = drivers[0]
        path_value = tool.get("resolved_path")
        if not isinstance(path_value, str):
            raise ValueError("c_compilation_fact_compiler_path_invalid")
        path = Path(path_value).resolve(strict=True)
        if (
            not path.is_file()
            or not os.access(path, os.X_OK)
            or not any(path.is_relative_to(root) for root in _SYSTEM_ROOTS if root.exists())
            or tool_basename(str(record.get("driver")))
            != tool_basename(str(tool.get("token")))
        ):
            raise ValueError("c_compilation_fact_compiler_path_invalid")
        binary = tool.get("binary")
        identity = _compiler_identity(path)
        if binary != identity:
            raise ValueError("c_compilation_fact_compiler_drifted")
        portable_core = {
            "schema_version": 1,
            "artifact_kind": "c-compiler-portable-binding",
            "toolchain_id": toolchain_id,
            "family": tool.get("family"),
            "basename": path.name,
            "binary": identity,
            "target": tool.get("target"),
            "version": tool.get("version"),
        }
        portable = {
            **portable_core,
            "binding_sha256": content_sha256(portable_core),
        }
        if toolchain_id in result:
            raise ValueError("c_compilation_fact_toolchain_duplicate")
        result[toolchain_id] = CCompilerBinding(toolchain_id, path, portable)
    return result


def _required_compiler_records(
    build_ir: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    units = build_ir.get("translation_units")
    values = build_ir.get("toolchains")
    if not isinstance(units, list) or not units:
        raise ValueError("c_compilation_fact_translation_units_invalid")
    if not isinstance(values, list) or not values:
        raise ValueError("c_compilation_fact_toolchains_invalid")
    required: set[str] = set()
    for unit in units:
        toolchain_id = unit.get("toolchain_id") if isinstance(unit, Mapping) else None
        if not isinstance(toolchain_id, str) or not toolchain_id:
            raise ValueError("c_compilation_fact_unit_toolchain_invalid")
        required.add(toolchain_id)
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in values:
        toolchain_id = record.get("toolchain_id") if isinstance(record, Mapping) else None
        if not isinstance(toolchain_id, str) or not toolchain_id:
            raise ValueError("c_compilation_fact_toolchain_invalid")
        if toolchain_id in indexed:
            raise ValueError("c_compilation_fact_toolchain_duplicate")
        indexed[toolchain_id] = record
    if not required.issubset(indexed):
        raise ValueError("c_compilation_fact_toolchain_binding_missing")
    return [indexed[toolchain_id] for toolchain_id in sorted(required)]


def _compiler_identity(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    return {"sha256": file_sha256(path), "size_bytes": size}


def _validate_launcher(path: Path) -> None:
    metadata = path.stat()
    if (
        path.name != "bwrap"
        or not path.is_file()
        or not os.access(path, os.X_OK)
        or metadata.st_uid != 0
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ValueError("c_compilation_fact_bubblewrap_untrusted")


__all__ = [
    "C_COMPILATION_TIMEOUT_SECONDS",
    "CCompilationRuntime",
    "prepare_c_compilation_runtime",
    "run_c_syntax_plan",
]
