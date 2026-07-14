from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    write_json_artifact,
)
from validation.tools._project_migration_harness.build_adapter import (
    materialize_selected_build_ir_stage,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools.project_migration_build_ir_equivalence_test_support import (
    BuildIRLane,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "project_migration_build_ir_equivalence_extended"
)
LANES = {"cmake", "meson", "ninja"}


def materialize_extended_lane(
    base: Path,
    name: str,
    lane: str,
    *,
    declared_dependency: bool = False,
    compiler: str = "clang",
    reported_compiler: str | None = None,
) -> BuildIRLane:
    if lane not in LANES:
        raise ValueError("build_ir_extended_lane_invalid")
    root, manifest = _copy_fixture(
        base, name, declared_dependency=declared_dependency, compiler=compiler,
        reported_compiler=reported_compiler,
    )
    database = root / manifest["compile_databases"][lane]
    discovery = discover_project(root, compile_database=database, max_units=8)
    if discovery.get("status") != "ready":
        raise AssertionError(discovery)
    output = base / name / "artifacts"
    artifacts = {
        "discovery": write_json_artifact(output, "plan/discovery.json", discovery),
    }
    stage = materialize_selected_build_ir_stage(
        root, output, discovery, artifacts, None,
    )
    if stage["verification"].get("status") != "verified":
        raise AssertionError(stage["verification"])
    return BuildIRLane(
        adapter=f"compile-database-{lane}",
        project_root=root,
        artifact_root=output,
        build_ir=stage["build_ir"],
        build_ir_reference=artifacts["build_ir"],
        verification=stage["verification"],
    )


def load_extended_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    boundary = manifest.get("claim_boundary", {})
    if (
        manifest.get("schema_version") != 1
        or manifest.get("artifact_kind")
        != "project-migration-build-ir-equivalence-extended-fixture"
        or set(manifest.get("compile_databases", {})) != LANES
        or boundary.get("semantic_gate") is not False
        or boundary.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("build_ir_extended_fixture_contract_invalid")
    databases = [
        json.loads((root / path).read_text(encoding="utf-8"))
        for path in manifest["compile_databases"].values()
    ]
    if any(database != databases[0] for database in databases[1:]):
        raise ValueError("build_ir_extended_compile_facts_differ")
    if not isinstance(databases[0], list) or len(databases[0]) != 2:
        raise ValueError("build_ir_extended_compile_facts_invalid")
    return manifest


def _copy_fixture(
    base: Path,
    name: str,
    *,
    declared_dependency: bool,
    compiler: str,
    reported_compiler: str | None,
) -> tuple[Path, dict[str, Any]]:
    if not name:
        raise ValueError("build_ir_extended_fixture_name_invalid")
    root = base / name / "project"
    shutil.copytree(FIXTURE_ROOT, root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    _bind_meson_paths(root, str(manifest.get("meson_path_placeholder")))
    if compiler != "clang":
        _set_compiler(root, compiler)
    if reported_compiler is not None and reported_compiler != compiler:
        _set_meson_reported_compiler(root, reported_compiler)
    if declared_dependency:
        _enable_declared_dependency(root)
    return root, load_extended_manifest(root)


def _bind_meson_paths(root: Path, placeholder: str) -> None:
    if placeholder != "@ROOT@":
        raise ValueError("build_ir_extended_meson_placeholder_invalid")
    replacement = root.resolve().as_posix()
    replaced = 0
    for path in sorted((root / "meson/meson-info").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        count = text.count(placeholder)
        if count:
            path.write_text(
                text.replace(placeholder, replacement),
                encoding="utf-8",
                newline="\n",
            )
            replaced += count
    if replaced == 0:
        raise ValueError("build_ir_extended_meson_placeholder_missing")


def _enable_declared_dependency(root: Path) -> None:
    path = root / "meson/meson-info/intro-targets.json"
    targets = json.loads(path.read_text(encoding="utf-8"))
    executables = [item for item in targets if item.get("type") == "executable"]
    if len(executables) != 1 or executables[0].get("dependencies") != []:
        raise ValueError("build_ir_extended_dependency_fixture_invalid")
    executables[0]["dependencies"] = ["threads"]
    path.write_bytes(canonical_json_bytes(targets))


def _set_compiler(root: Path, compiler: str) -> None:
    if compiler not in {"clang", "gcc"}:
        raise ValueError("build_ir_extended_compiler_invalid")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for relative in manifest["compile_databases"].values():
        path = root / relative
        database = json.loads(path.read_text(encoding="utf-8"))
        for entry in database:
            if entry["arguments"][0] != "clang":
                raise ValueError("build_ir_extended_compiler_fixture_invalid")
            entry["arguments"][0] = compiler
        path.write_bytes(canonical_json_bytes(database))
    for relative in (
        "cmake/CMakeFiles/program.dir/link.txt",
        "ninja/build.ninja",
        "meson/build.ninja",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if "clang" not in text:
            raise ValueError("build_ir_extended_linker_fixture_invalid")
        path.write_text(
            text.replace("clang", compiler), encoding="utf-8", newline="\n",
        )
    _set_meson_reported_compiler(root, compiler)


def _set_meson_reported_compiler(root: Path, compiler: str) -> None:
    if compiler not in {"clang", "gcc"}:
        raise ValueError("build_ir_extended_reported_compiler_invalid")
    targets_path = root / "meson/meson-info/intro-targets.json"
    targets = json.loads(targets_path.read_text(encoding="utf-8"))
    for target in targets:
        for group in target["target_sources"]:
            group["compiler"] = [compiler]
    targets_path.write_bytes(canonical_json_bytes(targets))
    compilers_path = root / "meson/meson-info/intro-compilers.json"
    compilers = json.loads(compilers_path.read_text(encoding="utf-8"))
    record = compilers["host"]["c"]
    record.update({
        "id": compiler,
        "exelist": [compiler],
        "linker_exelist": [compiler],
    })
    compilers_path.write_bytes(canonical_json_bytes(compilers))


__all__ = [
    "load_extended_manifest",
    "materialize_extended_lane",
]
