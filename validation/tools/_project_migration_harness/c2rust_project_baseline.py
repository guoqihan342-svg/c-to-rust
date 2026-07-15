from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Mapping

from .artifacts import canonical_json_bytes, content_sha256
from .c2rust_project_baseline_cargo import prepare_generated_cargo
from .c2rust_project_baseline_compile_db import normalize_compilation_database
from .c2rust_project_baseline_diagnostics import (
    has_multi_configuration_source, has_transpiler_error_diagnostics,
)
from .c2rust_project_baseline_evidence import (
    reopen_c2rust_project_baseline, snapshot_generated_tree, write_cas_artifact,
)
from .c2rust_project_baseline_process import (
    Runner, cargo_toolchain_prefix, executable_binding,
    minimal_process_environment, normalized_environment_overrides,
    run_recorded_process,
)
from .c2rust_project_baseline_report import (
    C2RustProjectBaselineRun, finish_baseline_run as _finish,
)
from .c2rust_project_baseline_workdirs import (
    portable_package_workdir, portable_repository_workdir,
    repository_working_directory, translated_source_working_directories,
)


def run_c2rust_project_baseline(
    *, repo_root: Path, compile_commands: Path, c2rust_transpile: Path,
    out_root: Path, cargo: Path, rustc: Path, timeout_seconds: int = 300,
    cargo_toolchain: str | None = None,
    environment_overrides: Mapping[str, str] | None = None,
    runner: Runner | None = None,
) -> C2RustProjectBaselineRun:
    repository = Path(repo_root).resolve(strict=True)
    output = Path(out_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    normalized = normalize_compilation_database(repository, compile_commands)
    runtime_tools = [
        executable_binding(c2rust_transpile, "c2rust-transpile"),
        executable_binding(cargo, "cargo"),
        executable_binding(rustc, "rustc"),
    ]
    tools = [_portable_tool(item) for item in runtime_tools]
    cargo_prefix = cargo_toolchain_prefix(cargo_toolchain)
    selected_overrides = normalized_environment_overrides(environment_overrides)
    policy = {
        "timeout_seconds": timeout_seconds,
        "minimal_environment": True,
        "cargo_offline": True,
        "cargo_check_all_targets": True,
        "all_discovered_wrappers_required": True,
        "cargo_toolchain": cargo_toolchain,
        "environment_override_keys": sorted(selected_overrides),
        "environment_overrides_sha256": content_sha256(selected_overrides),
        "rustc_bootstrap": selected_overrides.get("RUSTC_BOOTSTRAP") == "1",
    }
    original_path = Path(compile_commands).resolve(strict=True)
    original_ref = write_cas_artifact(
        output, "compile-database", original_path.read_bytes(), suffix="json",
    )
    normalized_bytes = canonical_json_bytes(normalized.payload())
    normalized_ref = write_cas_artifact(
        output, "normalized-compile-database", normalized_bytes, suffix="json",
    )
    run_id = content_sha256({
        "normalized_compile_database_sha256": normalized_ref["sha256"],
        "sources": list(normalized.sources),
        "tools": tools,
        "policy": policy,
    })
    workspaces = output / "workspaces"
    workspaces.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(
        prefix=f"c2rust-baseline-{run_id[:12]}-", dir=workspaces,
    )).resolve(strict=True)
    runtime_database = workspace / "input" / "compile_commands.json"
    runtime_database.parent.mkdir(parents=True)
    runtime_database.write_bytes(normalized_bytes)
    generated_root = workspace / "generated-output"
    environment = minimal_process_environment(
        workspace / "runtime",
        transpiler=Path(runtime_tools[0]["executable_path"]),
        cargo=Path(runtime_tools[1]["executable_path"]),
        rustc=Path(runtime_tools[2]["executable_path"]),
        overrides=selected_overrides,
    )
    executions: list[dict[str, Any]] = []
    artifacts: dict[tuple[str, str, int], dict[str, Any]] = {}
    _register(artifacts, "compile-database", original_ref)
    _register(artifacts, "normalized-compile-database", normalized_ref)
    transpile_argv = [
        runtime_tools[0]["executable_path"],
        runtime_database.as_posix(),
        "--emit-build-files",
        "--preserve-unused-functions",
        "--overwrite-existing",
        "--output-dir",
        generated_root.as_posix(),
    ]
    transpile, refs = run_recorded_process(
        transpile_argv, cwd=repository, environment=environment,
        timeout_seconds=timeout_seconds, out_root=output,
        purpose="c2rust-transpile-project", runner=runner,
        portable_argv=[
            "c2rust-transpile", "private-local:normalized-compile-database",
            "--emit-build-files", "--preserve-unused-functions",
            "--overwrite-existing", "--output-dir",
            "private-local:generated-output",
        ],
        portable_working_directory="repository-root",
    )
    executions.append(transpile)
    _register_process_refs(artifacts, refs)
    generated = _empty_generated(output, workspace)
    if transpile["status"] != "passed":
        return _finish(
            output, run_id, repository, original_path, original_ref,
            normalized_ref, normalized.sources, tools, policy,
            executions, generated, artifacts,
            ["c2rust_transpile_execution_failed"],
        )
    pre_cargo_blockers: list[str] = []
    if has_multi_configuration_source(normalized.entries):
        pre_cargo_blockers.append(
            "c2rust_multi_configuration_source_unsupported",
        )
    try:
        diagnostics_failed = has_transpiler_error_diagnostics(
            output, transpile["stderr_ref"],
        )
    except ValueError:
        pre_cargo_blockers.append("c2rust_transpile_diagnostics_unavailable")
    else:
        if diagnostics_failed:
            pre_cargo_blockers.append("c2rust_transpile_diagnostics_failed")
    if pre_cargo_blockers:
        generated = _snapshot_if_available(
            output, workspace, generated_root, generated, artifacts,
        )
        return _finish(
            output, run_id, repository, original_path, original_ref,
            normalized_ref, normalized.sources, tools, policy,
            executions, generated, artifacts, pre_cargo_blockers,
        )
    try:
        preparation = prepare_generated_cargo(
            generated_root,
            translated_source_working_directories(repository, normalized.entries),
        )
    except (OSError, UnicodeError, ValueError) as error:
        blocker = str(error) or "c2rust_generated_project_invalid"
        generated = _snapshot_if_available(
            output, workspace, generated_root, generated, artifacts,
        )
        return _finish(
            output, run_id, repository, original_path, original_ref,
            normalized_ref, normalized.sources, tools, policy,
            executions, generated, artifacts, [blocker],
        )
    snapshot, snapshot_ref = snapshot_generated_tree(generated_root, output)
    _register(artifacts, "generated-snapshot", snapshot_ref)
    for entry in snapshot["files"]:
        _register(artifacts, "generated-file", entry["content_ref"])
    generated = {
        "workspace": workspace.relative_to(output).as_posix(),
        "snapshot_ref": snapshot_ref,
        "manifests": [
            path.relative_to(generated_root).as_posix()
            for path in preparation.manifests
        ],
        "wrappers": list(preparation.wrappers),
        "repairs": list(preparation.repairs),
    }
    blockers: list[str] = []
    cargo_path = runtime_tools[1]["executable_path"]
    for index, manifest in enumerate(preparation.manifests):
        execution, refs = run_recorded_process(
            [
                cargo_path, *cargo_prefix, "check", "--offline", "--all-targets",
                "--manifest-path", manifest.as_posix(),
            ],
            cwd=manifest.parent, environment=environment,
            timeout_seconds=timeout_seconds, out_root=output,
            purpose=f"cargo-check-all-targets-{index}", runner=runner,
            portable_argv=[
                "cargo", *cargo_prefix, "check", "--offline", "--all-targets",
                "--manifest-path", manifest.relative_to(generated_root).as_posix(),
            ],
            portable_working_directory=portable_package_workdir(
                generated_root, manifest.parent,
            ),
        )
        executions.append(execution)
        _register_process_refs(artifacts, refs)
        if execution["status"] != "passed":
            blockers.append("c2rust_cargo_check_failed")
    if not blockers:
        for wrapper in preparation.wrappers:
            manifest = generated_root.joinpath(
                *Path(wrapper["manifest_path"]).parts
            )
            source_working_directory = repository_working_directory(
                repository, wrapper["source_working_directory"],
            )
            execution, refs = run_recorded_process(
                [
                    cargo_path, *cargo_prefix, "run", "--offline", "--manifest-path",
                    manifest.as_posix(), "--bin", wrapper["name"],
                ],
                cwd=source_working_directory, environment=environment,
                timeout_seconds=timeout_seconds, out_root=output,
                purpose=f"cargo-run-wrapper-{wrapper['name']}", runner=runner,
                portable_argv=[
                    "cargo", *cargo_prefix, "run", "--offline",
                    "--manifest-path", wrapper["manifest_path"],
                    "--bin", wrapper["name"],
                ],
                portable_working_directory=portable_repository_workdir(
                    repository, source_working_directory,
                ),
            )
            executions.append(execution)
            _register_process_refs(artifacts, refs)
            if execution["status"] != "passed":
                blockers.append("c2rust_wrapper_execution_failed")
    return _finish(
        output, run_id, repository, original_path, original_ref,
        normalized_ref, normalized.sources, tools, policy,
        executions, generated, artifacts, blockers,
    )


def _empty_generated(out_root: Path, workspace: Path) -> dict[str, Any]:
    return {
        "workspace": workspace.relative_to(out_root).as_posix(),
        "snapshot_ref": None, "manifests": [], "wrappers": [], "repairs": [],
    }


def _snapshot_if_available(
    out_root: Path, workspace: Path, generated_root: Path,
    generated: dict[str, Any],
    artifacts: dict[tuple[str, str, int], dict[str, Any]],
) -> dict[str, Any]:
    try:
        snapshot, reference = snapshot_generated_tree(generated_root, out_root)
    except (OSError, ValueError):
        return generated
    _register(artifacts, "generated-snapshot", reference)
    for entry in snapshot["files"]:
        _register(artifacts, "generated-file", entry["content_ref"])
    return {
        "workspace": workspace.relative_to(out_root).as_posix(),
        "snapshot_ref": reference, "manifests": [], "wrappers": [],
        "repairs": [],
    }


def _register_process_refs(
    artifacts: dict[tuple[str, str, int], dict[str, Any]],
    refs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    _register(artifacts, "process-stdout", refs[0])
    _register(artifacts, "process-stderr", refs[1])


def _register(
    artifacts: dict[tuple[str, str, int], dict[str, Any]],
    role: str, reference: Mapping[str, Any],
) -> None:
    identity = (
        str(reference["path"]), str(reference["sha256"]),
        int(reference["size_bytes"]),
    )
    artifacts.setdefault(identity, {
        "role": role, "visibility": "private-local", "ref": dict(reference),
    })


def _portable_tool(value: Mapping[str, Any]) -> dict[str, Any]:
    core = {
        "role": value["role"],
        "basename": Path(str(value["executable_path"])).name,
        "sha256": value["sha256"],
        "size_bytes": value["size_bytes"],
    }
    return {**core, "portable_identity_sha256": content_sha256(core)}


__all__ = [
    "C2RustProjectBaselineRun", "reopen_c2rust_project_baseline",
    "run_c2rust_project_baseline",
]
