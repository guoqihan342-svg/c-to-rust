from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .build_facts import json_sha256
from .meson_bindings import (
    MesonBindingCollector, bind_buildsystem_files, bind_targets,
    validate_dependency_target_ids,
)
from .meson_paths import (
    FILE_LIMITS, MAX_REFERENCED_BYTES, MAX_REFERENCED_FILE_BYTES,
    MAX_SNAPSHOT_BYTES, MesonPathError, configured_directory, configured_file,
    fixed_paths, meson_signal, path_present, read_snapshot_files,
    recheck_snapshot_files, repository_lexical_path,
)
from .meson_schema import (
    MesonSchemaError, sanitize_build_options, sanitize_buildsystem_files,
    sanitize_compilers, sanitize_dependencies, sanitize_targets, strict_json,
    validate_meson_info,
)
from .meson_schema_common import (
    MAX_BUILDSYSTEM_FILES, MAX_COMPILERS, MAX_DEPENDENCIES, MAX_OPTIONS,
    MAX_PATH_REFERENCES, MAX_TARGETS,
)


def inspect_meson_introspection(
    repo_root: Path, compile_database_path: Path,
) -> dict[str, Any]:
    root = repo_root.resolve()
    database_lexical = Path(os.path.abspath(compile_database_path))
    try:
        database = configured_file(root, str(database_lexical))
    except MesonPathError as error:
        blocker = (
            "meson_compile_database_external"
            if str(error) in {
                "meson_foreign_absolute_path", "meson_path_outside_repository",
            }
            else str(error)
        )
        return _report("blocked", [blocker])
    build_root = database.parent
    signal = meson_signal(root, build_root)
    if not (signal["meson_info_manifest"] or signal["meson_ninja_header"]):
        return _report("not_detected", [], signal=signal)
    paths = fixed_paths(build_root)
    missing = [
        f"meson_{name}_missing" for name, path in paths.items()
        if not path_present(path)
    ]
    if missing:
        return _report(
            "blocked", missing, signal=signal, build_root=build_root, root=root
        )
    bindings: list[dict[str, Any]] = []
    try:
        raw_files, bindings = read_snapshot_files(root, paths)
        directories = validate_meson_info(strict_json(raw_files["info"], "info"))
        configured = {
            name: configured_directory(root, value, name)
            for name, value in directories.items()
        }
        _validate_directories(root, build_root, configured)
        target_specs = sanitize_targets(strict_json(raw_files["targets"], "targets"))
        options, ninja_backend = sanitize_build_options(
            strict_json(raw_files["buildoptions"], "buildoptions")
        )
        if not ninja_backend:
            raise MesonSchemaError("meson_ninja_backend_not_confirmed")
        dependencies = sanitize_dependencies(
            strict_json(raw_files["dependencies"], "dependencies")
        )
        compilers = sanitize_compilers(
            strict_json(raw_files["compilers"], "compilers")
        )
        buildsystem_specs = sanitize_buildsystem_files(
            strict_json(raw_files["buildsystem_files"], "buildsystem_files")
        )
        collector = MesonBindingCollector(root)
        targets = bind_targets(root, target_specs, collector)
        validate_dependency_target_ids(dependencies, targets)
        buildsystem_files = bind_buildsystem_files(buildsystem_specs, collector)
        referenced = collector.artifacts()
        recheck_snapshot_files(root, paths, raw_files)
    except (MesonSchemaError, MesonPathError) as error:
        return _report(
            "blocked", [str(error)], signal=signal, build_root=build_root,
            root=root, snapshot_files=bindings,
        )
    payload = {
        "build_root": repository_lexical_path(root, build_root),
        "directories": {
            name: repository_lexical_path(root, path)
            for name, path in configured.items()
        },
        "snapshot_files": sorted(bindings, key=lambda item: item["path"]),
        "referenced_artifacts": referenced,
        "targets": targets,
        "build_options": options,
        "dependencies": dependencies,
        "compilers": compilers,
        "buildsystem_files": buildsystem_files,
        "authority": _authority(),
    }
    return _report(
        "ready", [], signal=signal, build_root=build_root, root=root,
        snapshot_files=bindings, payload=payload,
    )


def verify_meson_introspection(
    repo_root: Path, compile_database_path: Path, expected: dict[str, Any],
) -> list[dict[str, Any]]:
    if expected.get("status") != "ready":
        return []
    if json_sha256(_snapshot_payload(expected)) != expected.get("snapshot_sha256"):
        return [{"kind": "meson_snapshot_binding_invalid"}]
    current = inspect_meson_introspection(repo_root, compile_database_path)
    if current.get("status") != "ready":
        return [{"kind": "meson_snapshot_reinspection_blocked"}]
    if current.get("snapshot_sha256") != expected.get("snapshot_sha256"):
        return [{"kind": "meson_snapshot_drift"}]
    return []


def _validate_directories(
    root: Path, build_root: Path, configured: dict[str, Path],
) -> None:
    if configured["source"] != root:
        raise MesonPathError("meson_source_directory_mismatch")
    if configured["build"] != build_root:
        raise MesonPathError("meson_build_directory_mismatch")
    if configured["info"] != build_root / "meson-info":
        raise MesonPathError("meson_info_directory_mismatch")


def _authority() -> dict[str, Any]:
    return {
        "compile_commands": "compile_commands.json",
        "link_commands": "build.ninja",
        "introspection_parameters_authoritative": False,
        "parameters_exposed": False,
        "build_root_selection": {
            "method": "compile_database_parent",
            "discovery_performed": False,
            "uniqueness_proven": False,
            "evidence_boundary": "only_compile_database_parent_inspected",
        },
    }


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key) for key in (
            "build_root", "directories", "snapshot_files", "referenced_artifacts",
            "targets", "build_options", "dependencies", "compilers",
            "buildsystem_files", "authority",
        )
    }


def _report(status: str, blockers: list[str], **values: Any) -> dict[str, Any]:
    root = values.get("root")
    build_root = values.get("build_root")
    payload = values.get("payload") or {}
    report = {
        "schema_version": 2,
        "status": status,
        "signal": values.get("signal") or {},
        "build_root": repository_lexical_path(root, build_root)
        if isinstance(root, Path) and isinstance(build_root, Path) else None,
        "snapshot_files": sorted(
            values.get("snapshot_files") or [], key=lambda item: item["path"]
        ),
        "referenced_artifacts": payload.get("referenced_artifacts", []),
        "targets": payload.get("targets", []),
        "build_options": payload.get("build_options", []),
        "dependencies": payload.get("dependencies", []),
        "compilers": payload.get("compilers", {}),
        "buildsystem_files": payload.get("buildsystem_files", []),
        "directories": payload.get("directories", {}),
        "authority": _authority(),
        "blockers": sorted(set(blockers)),
        "commands_executed": False,
        "limits": {
            **FILE_LIMITS,
            "max_snapshot_bytes": MAX_SNAPSHOT_BYTES,
            "max_referenced_bytes": MAX_REFERENCED_BYTES,
            "max_referenced_file_bytes": MAX_REFERENCED_FILE_BYTES,
            "max_targets": MAX_TARGETS,
            "max_build_options": MAX_OPTIONS,
            "max_dependencies": MAX_DEPENDENCIES,
            "max_compilers": MAX_COMPILERS,
            "max_buildsystem_files": MAX_BUILDSYSTEM_FILES,
            "max_path_references": MAX_PATH_REFERENCES,
        },
    }
    report["snapshot_sha256"] = json_sha256(payload) if status == "ready" else None
    return report


__all__ = ["inspect_meson_introspection", "verify_meson_introspection"]
