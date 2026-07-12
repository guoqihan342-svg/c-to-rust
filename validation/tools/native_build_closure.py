"""Resolve a hash-bound native build closure into a C compile contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .native_build_closure_paths import (
    _build_config,
    _checked_external_directory,
    _checked_output_under,
    _checked_repo_root,
    _logical_working_directory,
    _mapping_list,
    _repo_relative,
    _required_mapping,
    _string_list,
    _string_mapping,
    _symbol_bindings,
    _target_abi,
    _verify_path_ref,
    sha256_path,
)


def resolve_native_build_closure(
    spec: Mapping[str, Any] | Any,
    repo_root: str | Path,
    evidence_dir: str | Path,
    harness_path: str | Path,
) -> dict[str, Any] | None:
    """Return a compile command contract for ``linked_artifacts_v1``.

    The resolver intentionally selects behavior from the closure schema and
    mode only. Slice, function, target, and project identity fields are not
    inputs to this decision.
    """

    if not isinstance(spec, Mapping):
        raise ValueError("spec must be an object")
    build_profile = spec.get("build_profile")
    if not isinstance(build_profile, Mapping):
        if build_profile is None:
            return None
        raise ValueError("build_profile must be an object")
    if "oracle_build" not in build_profile:
        return None

    oracle_build = build_profile.get("oracle_build")
    if not isinstance(oracle_build, Mapping):
        raise ValueError("build_profile.oracle_build must be an object")
    if oracle_build.get("schema_version") != 1:
        raise ValueError("oracle_build.schema_version must be 1")
    if oracle_build.get("mode") != "linked_artifacts_v1":
        raise ValueError("oracle_build.mode must be linked_artifacts_v1")

    root = _checked_repo_root(repo_root)
    evidence = _checked_external_directory(evidence_dir, "evidence_dir")
    harness = _checked_output_under(evidence, harness_path, "harness_path")
    manifest_ref = _required_mapping(oracle_build.get("closure_manifest"), "oracle_build.closure_manifest")
    manifest_path, manifest_logical, manifest_sha = _verify_path_ref(
        root, manifest_ref, "oracle_build.closure_manifest", expected_kind="file"
    )

    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("native build closure manifest is not valid UTF-8 JSON") from exc
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha:
        raise ValueError("oracle_build.closure_manifest sha256 drifted while reopening")
    if not isinstance(manifest, Mapping):
        raise ValueError("native build closure manifest must be an object")
    if manifest.get("schema_version") != 1:
        raise ValueError("closure manifest schema_version must be 1")
    build_config = _build_config(manifest.get("build_config"))
    target_abi = _target_abi(manifest.get("target_abi"))
    toolchain = _string_mapping(manifest.get("toolchain"), "manifest.toolchain")

    source_root_ref = _required_mapping(manifest.get("source_root"), "manifest.source_root")
    _, source_root, source_root_sha = _verify_path_ref(
        root, source_root_ref, "manifest.source_root", expected_kind="directory"
    )
    compile_database_ref = _required_mapping(
        manifest.get("compile_database"),
        "manifest.compile_database",
    )
    _, compile_database_path, compile_database_sha = _verify_path_ref(
        root,
        compile_database_ref,
        "manifest.compile_database",
        expected_kind="file",
    )
    defines = _string_list(manifest.get("defines"), "manifest.defines")

    source_include_refs = _mapping_list(
        manifest.get("source_include_dirs"),
        "manifest.source_include_dirs",
    )
    source_include_dirs: list[dict[str, str]] = []
    for index, ref in enumerate(source_include_refs):
        _, logical, sha = _verify_path_ref(
            root,
            ref,
            f"manifest.source_include_dirs[{index}]",
            expected_kind="directory",
        )
        source_include_dirs.append({"path": logical, "sha256": sha})

    include_refs = _mapping_list(manifest.get("generated_include_dirs"), "manifest.generated_include_dirs")
    generated_include_dirs: list[dict[str, str]] = []
    for index, ref in enumerate(include_refs):
        _, logical, sha = _verify_path_ref(
            root,
            ref,
            f"manifest.generated_include_dirs[{index}]",
            expected_kind="directory",
        )
        generated_include_dirs.append({"path": logical, "sha256": sha})

    artifact_refs = _mapping_list(manifest.get("link_artifacts"), "manifest.link_artifacts")
    link_artifacts: list[dict[str, str]] = []
    artifact_hashes: dict[str, str] = {}
    for index, ref in enumerate(artifact_refs):
        _, logical, sha = _verify_path_ref(
            root, ref, f"manifest.link_artifacts[{index}]", expected_kind="file"
        )
        if logical in artifact_hashes:
            raise ValueError(f"manifest.link_artifacts contains duplicate path: {logical}")
        artifact_hashes[logical] = sha
        link_artifacts.append({"path": logical, "sha256": sha})

    system_link_args = _string_list(manifest.get("system_link_args"), "manifest.system_link_args")
    if any(arg == "-o" or arg.startswith("-o=") for arg in system_link_args):
        raise ValueError("manifest.system_link_args must not set the output path")
    symbol_bindings = _symbol_bindings(root, manifest.get("symbol_bindings"), artifact_hashes)

    output_name = harness.with_suffix(".exe").name
    try:
        harness_arg = harness.relative_to(evidence).as_posix()
    except ValueError:
        harness_arg = _repo_relative(root, harness)
    define_args = [f"-D{item}" for item in defines]
    include_dirs = [*source_include_dirs, *generated_include_dirs]
    include_args = [f"-I{item['path']}" for item in include_dirs]
    artifact_args = [item["path"] for item in link_artifacts]
    return {
        "schema_version": 1,
        "mode": "linked_artifacts_v1",
        "working_directory": _logical_working_directory(root, evidence),
        "closure_manifest": {"path": manifest_logical, "sha256": manifest_sha},
        "build_config": build_config,
        "target_abi": target_abi,
        "toolchain": toolchain,
        "source_root": source_root,
        "source_root_ref": {"path": source_root, "sha256": source_root_sha},
        "compile_database": {
            "path": compile_database_path,
            "sha256": compile_database_sha,
        },
        "defines": defines,
        "source_include_dirs": source_include_dirs,
        "generated_include_dirs": generated_include_dirs,
        "resolved_include_paths": [item["path"] for item in include_dirs],
        "link_source_files": [],
        "link_artifacts": link_artifacts,
        "ordered_artifact_args": artifact_args,
        "system_link_args": system_link_args,
        "symbol_bindings": symbol_bindings,
        "link_strategy": "compile_harness_with_native_build_closure",
        "oracle_source_mode": str(
            (spec.get("c_boundary") or {}).get("oracle_source_mode")
            or "declared_c_boundary_sources"
        ),
        "argv": [
            "cc",
            "-std=c99",
            *define_args,
            *include_args,
            harness_arg,
            *artifact_args,
            *system_link_args,
            "-o",
            output_name,
        ],
        "status": "draft_not_executed",
    }


def resolve_native_build_closure_or_block(
    spec: Mapping[str, Any] | Any,
    repo_root: str | Path,
    evidence_dir: str | Path,
    harness_path: str | Path,
) -> dict[str, Any] | None:
    """Resolve a closure while preserving invalid declarations as fail-closed evidence."""

    try:
        return resolve_native_build_closure(spec, repo_root, evidence_dir, harness_path)
    except ValueError as error:
        build_profile = spec.get("build_profile") if isinstance(spec, Mapping) else None
        oracle_build = build_profile.get("oracle_build") if isinstance(build_profile, Mapping) else None
        if oracle_build is None:
            raise
        root = _checked_repo_root(repo_root)
        evidence = _checked_external_directory(evidence_dir, "evidence_dir")
        source = spec.get("source") if isinstance(spec, Mapping) else None
        c_boundary = spec.get("c_boundary") if isinstance(spec, Mapping) else None
        return {
            "schema_version": 1,
            "mode": "linked_artifacts_v1",
            "working_directory": _logical_working_directory(root, evidence),
            "closure_manifest": (
                dict(oracle_build.get("closure_manifest"))
                if isinstance(oracle_build, Mapping)
                and isinstance(oracle_build.get("closure_manifest"), Mapping)
                else None
            ),
            "build_config": None,
            "target_abi": None,
            "toolchain": None,
            "source_root": (
                str(source.get("source_root"))
                if isinstance(source, Mapping) and source.get("source_root")
                else "."
            ),
            "defines": [],
            "source_include_dirs": [],
            "generated_include_dirs": [],
            "resolved_include_paths": [],
            "link_source_files": [],
            "link_artifacts": [],
            "ordered_artifact_args": [],
            "system_link_args": [],
            "symbol_bindings": [],
            "link_strategy": "native_build_closure_invalid",
            "oracle_source_mode": (
                str(c_boundary.get("oracle_source_mode"))
                if isinstance(c_boundary, Mapping) and c_boundary.get("oracle_source_mode")
                else "declared_c_boundary_sources"
            ),
            "argv": [],
            "status": "native_build_closure_invalid",
            "diagnostics": [f"native_build_closure_invalid:{error}"],
        }


__all__ = [
    "resolve_native_build_closure",
    "resolve_native_build_closure_or_block",
    "sha256_path",
]
