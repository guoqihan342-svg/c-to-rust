from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    content_sha256,
    write_json_artifact,
)
from validation.tools._project_migration_harness.build_facts import file_binding
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.make_build_ir_adapter import (
    MakeReportSelection,
    materialize_selected_build_ir_stage,
)
from validation.tools._project_migration_harness.make_dry_run_contract import (
    canonical_make_dry_run_report_bytes,
    create_make_dry_run_report,
)
from validation.tools._project_migration_harness.make_dry_run_host_evidence import (
    MAKE_REQUIRED_CAPABILITIES,
    canonical_make_host_preflight_bytes,
)
from validation.tools._project_migration_harness.make_dry_run_runner import (
    MakeDryRunExecution,
    MakeDryRunPreflight,
    canonical_make_dry_run_plan_bytes,
    create_make_dry_run_plan,
    run_make_dry_run,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "project_migration_build_ir_equivalence"
)


@dataclass(frozen=True, slots=True)
class BuildIRLane:
    adapter: str
    project_root: Path
    artifact_root: Path
    build_ir: dict[str, Any]
    build_ir_reference: dict[str, Any]
    verification: dict[str, Any]


class _ControlledMakeBackend:
    def __init__(
        self, preflight: MakeDryRunPreflight, execution: MakeDryRunExecution,
    ) -> None:
        self._preflight = preflight
        self._execution = execution

    def preflight(self, plan, *, project_root, runtime_root):
        return self._preflight

    def execute(
        self, make_binary, make_args, *, project_root, runtime_root,
        plan, preflight,
    ):
        return self._execution


def materialize_cmake_lane(base: Path, name: str) -> BuildIRLane:
    root, manifest = _copy_fixture(base, name)
    database = root / manifest["compile_database"]
    discovery = discover_project(root, compile_database=database, max_units=8)
    return _materialize_lane(base, name, "compile-database-cmake", root, discovery, None)


def materialize_ninja_lane(base: Path, name: str) -> BuildIRLane:
    root, manifest = _copy_fixture(base, name)
    database = root / manifest["ninja_compile_database"]
    discovery = discover_project(root, compile_database=database, max_units=8)
    return _materialize_lane(base, name, "compile-database-ninja", root, discovery, None)


def materialize_make_lane(
    base: Path, name: str, *, define_value: str = "7",
) -> BuildIRLane:
    root, manifest = _copy_fixture(base, name, define_value=define_value)
    selection = _create_make_report(root, manifest)
    discovery = discover_project(root, make_report=selection, max_units=8)
    return _materialize_lane(base, name, "make-dry-run", root, discovery, selection)


def load_expected_common_contract() -> dict[str, Any]:
    return json.loads(
        (FIXTURE_ROOT / "expected-common-contract.json").read_text(encoding="utf-8")
    )


def _copy_fixture(
    base: Path, name: str, *, define_value: str = "7",
) -> tuple[Path, dict[str, Any]]:
    if not name or not define_value.isdigit():
        raise ValueError("build_ir_equivalence_fixture_identity_invalid")
    root = base / name / "project"
    shutil.copytree(FIXTURE_ROOT, root)
    manifest = _load_manifest(root)
    if define_value != manifest["define"]["value"]:
        _rewrite_define(root, manifest, define_value)
        manifest = _load_manifest(root)
    return root, manifest


def _load_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    boundary = manifest.get("claim_boundary", {})
    if (
        manifest.get("schema_version") != 1
        or manifest.get("artifact_kind")
        != "project-migration-build-ir-equivalence-fixture"
        or boundary.get("semantic_gate") is not False
        or boundary.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("build_ir_equivalence_fixture_contract_invalid")
    databases = [json.loads(
        (root / manifest[key]).read_text(encoding="utf-8")
    ) for key in ("compile_database", "ninja_compile_database")]
    if (
        any(not isinstance(database, list) or len(database) != 1 for database in databases)
        or any(database[0].get("arguments") != manifest["compile_argv"] for database in databases)
        or any(database[0].get("file") != manifest["source"] for database in databases)
        or any(database[0].get("output") != manifest["compile_output"] for database in databases)
    ):
        raise ValueError("build_ir_equivalence_compile_facts_invalid")
    stdout_lines = (root / manifest["make_stdout"]).read_text(
        encoding="utf-8"
    ).splitlines()
    expected_lines = [
        " ".join(manifest["compile_argv"]),
        " ".join(manifest["link_argv"]),
    ]
    link_fact = (root / "build/CMakeFiles/program.dir/link.txt").read_text(
        encoding="utf-8"
    ).strip().split()
    ninja_input = f'../{manifest["compile_output"]}'
    ninja_output = f'../{manifest["linked_output"]}'
    expected_ninja = (
        "rule link\n"
        f'  command = {" ".join(manifest["ninja_link_argv"])}\n\n'
        f"build {ninja_output}: link {ninja_input}\n"
    )
    makefile = (root / manifest["makefile"]).read_text(encoding="utf-8")
    if (
        stdout_lines != expected_lines
        or link_fact != manifest["cmake_link_argv"]
        or manifest["ninja_link_argv"] != ["clang", ninja_input, "-o", ninja_output]
        or (root / manifest["ninja_file"]).read_text(encoding="utf-8") != expected_ninja
        or any(line not in makefile for line in expected_lines)
    ):
        raise ValueError("build_ir_equivalence_command_facts_invalid")
    return manifest


def _rewrite_define(
    root: Path, manifest: dict[str, Any], define_value: str,
) -> None:
    name = manifest["define"]["name"]
    old_value = manifest["define"]["value"]
    old_flag, new_flag = f"-D{name}={old_value}", f"-D{name}={define_value}"
    for relative in (manifest["makefile"], manifest["make_stdout"]):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if text.count(old_flag) != 1:
            raise ValueError("build_ir_equivalence_define_fixture_invalid")
        path.write_text(text.replace(old_flag, new_flag), encoding="utf-8", newline="\n")
    cmake = root / "CMakeLists.txt"
    cmake_text = cmake.read_text(encoding="utf-8")
    old_definition, new_definition = f"{name}={old_value}", f"{name}={define_value}"
    if cmake_text.count(old_definition) != 1:
        raise ValueError("build_ir_equivalence_define_fixture_invalid")
    cmake.write_text(
        cmake_text.replace(old_definition, new_definition),
        encoding="utf-8", newline="\n",
    )
    updated_arguments = None
    for key in ("compile_database", "ninja_compile_database"):
        database_path = root / manifest[key]
        database = json.loads(database_path.read_text(encoding="utf-8"))
        arguments = database[0]["arguments"]
        if arguments.count(old_flag) != 1:
            raise ValueError("build_ir_equivalence_define_fixture_invalid")
        updated_arguments = [new_flag if item == old_flag else item for item in arguments]
        database[0]["arguments"] = updated_arguments
        database_path.write_bytes(canonical_json_bytes(database))
    manifest["compile_argv"] = list(updated_arguments or [])
    manifest["define"]["value"] = define_value
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))


def _create_make_report(
    root: Path, manifest: dict[str, Any],
) -> MakeReportSelection:
    source = file_binding(root, root / manifest["source"])
    makefile = file_binding(root, root / manifest["makefile"])
    toolchain = file_binding(root, root / manifest["toolchain_evidence"])
    plan = create_make_dry_run_plan(
        makefile_ref=makefile, input_refs=[source], toolchain_ref=toolchain,
        targets=manifest["targets"], timeout_seconds=30,
    )
    plan_path = _write(root, "evidence/make-plan.json", canonical_make_dry_run_plan_bytes(plan))
    preflight = MakeDryRunPreflight(
        backend="equivalence-fixture-backend",
        backend_version="test-1",
        plan_sha256=plan["plan_sha256"],
        toolchain_sha256=toolchain["sha256"],
        launcher_sha256="1" * 64,
        make_sha256="2" * 64,
        probe_observation_sha256="3" * 64,
        capability_results=tuple((name, True) for name in MAKE_REQUIRED_CAPABILITIES),
        cleanup_ready=True,
    )
    sandbox_path = _write(
        root, "evidence/make-sandbox.json",
        canonical_make_host_preflight_bytes(preflight.payload()),
    )
    stdout = (root / manifest["make_stdout"]).read_bytes()
    execution = MakeDryRunExecution(
        stdout=stdout, stderr=b"", returncode=0, timed_out=False,
        command_started=True, cleanup_verified=True,
        plan_sha256=plan["plan_sha256"],
        command_sha256=content_sha256(plan["command"]),
    )
    sandbox = file_binding(root, sandbox_path)
    outcome = run_make_dry_run(
        plan, project_root=root, runtime_root=root / "evidence/runtime",
        make_binary=Path("make"), toolchain_ref=toolchain,
        sandbox_ref=sandbox, backend=_ControlledMakeBackend(preflight, execution),
    )
    stdout_cas = _write(
        root,
        f"evidence/cas/raw-stdout/{hashlib.sha256(stdout).hexdigest()}.bin",
        stdout,
    )
    stderr_cas = _write(
        root,
        f"evidence/cas/raw-stderr/{hashlib.sha256(b'').hexdigest()}.bin",
        b"",
    )
    report = create_make_dry_run_report(
        outcome=outcome,
        raw_stdout_ref=file_binding(root, stdout_cas),
        raw_stderr_ref=file_binding(root, stderr_cas),
        makefile_ref=makefile, source_refs=[source], input_refs=[source],
        toolchain_ref=toolchain, sandbox_ref=sandbox,
        execution_plan_ref=file_binding(root, plan_path), targets=manifest["targets"],
    )
    report_path = _write(
        root, "evidence/make-report.json", canonical_make_dry_run_report_bytes(report),
    )
    reference = file_binding(root, report_path)
    return MakeReportSelection(report_path, reference["sha256"], reference["size_bytes"])


def _materialize_lane(
    base: Path, name: str, adapter: str, root: Path,
    discovery: dict[str, Any], selection: MakeReportSelection | None,
) -> BuildIRLane:
    if discovery.get("status") != "ready":
        raise AssertionError(discovery)
    output = base / name / "artifacts"
    artifacts = {
        "discovery": write_json_artifact(output, "plan/discovery.json", discovery),
    }
    stage = materialize_selected_build_ir_stage(
        root, output, discovery, artifacts, selection,
    )
    if stage["verification"].get("status") != "verified":
        raise AssertionError(stage["verification"])
    return BuildIRLane(
        adapter, root, output, stage["build_ir"], artifacts["build_ir"],
        stage["verification"],
    )


def _write(root: Path, relative: str, data: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


__all__ = [
    "BuildIRLane", "load_expected_common_contract",
    "materialize_cmake_lane", "materialize_make_lane", "materialize_ninja_lane",
]
