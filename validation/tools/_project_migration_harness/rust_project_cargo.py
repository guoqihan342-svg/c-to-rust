from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import cargo_project
from .artifacts import canonical_json_bytes
from .orchestration_facts import read_artifact_reference
from .project_interface_coordinator import coordinate_project_interfaces
from .rust_candidate_facts import derive_rust_metadata
from .rust_ffi_facts import NoFfiBoundaryError, derive_ffi_boundary_facts
from .rust_project_cargo_render import (
    GENERATOR, RUST_PROJECT_IR_FILE, render_cargo_project,
)
from .rust_project_ir_validation import (
    VIRTUAL_CRATE_ROOT_MODULE_ID, reopen_rust_project_ir_bindings,
)
from .rust_project_ir_cohort import PARENT_DAG_KEY
from .rust_project_native_cargo import native_link_build_script
VIRTUAL_CRATE_ROOT = VIRTUAL_CRATE_ROOT_MODULE_ID
MAX_UNSAFE_OBLIGATIONS = 4_096
_PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_FEATURE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
_CFG = re.compile(r'[A-Za-z0-9_ .,"=()!-]{1,256}\Z')
_EDITIONS = {"2015", "2018", "2021", "2024"}
_CRATE_TYPES = {"rlib", "lib", "staticlib", "cdylib"}
def reconstruct_cargo_project_from_ir(
    rust_project_ir: Mapping[str, Any], artifact_root: Path, *,
    max_source_bytes: int = cargo_project.MAX_SOURCE_BYTES,
) -> cargo_project.CargoProjectPlan:
    """Render a candidate Cargo generation only from a reopened RustProjectIR."""
    if (
        isinstance(max_source_bytes, bool) or not isinstance(max_source_bytes, int)
        or not 1 <= max_source_bytes <= cargo_project.MAX_SOURCE_BYTES
    ):
        _fail("candidate_size_limit_invalid", "candidate")
    try:
        root = Path(artifact_root).resolve(strict=True)
        binding = reopen_rust_project_ir_bindings(rust_project_ir, root)
        coordination = coordinate_project_interfaces(rust_project_ir)
    except (OSError, TypeError, ValueError) as error:
        _fail("rust_project_ir_binding_invalid", "rust_project_ir", detail=error)
    if coordination.get("status") != "candidate-ready":
        diagnostics = coordination.get("diagnostics")
        code = diagnostics[0].get("code") if isinstance(diagnostics, list) and diagnostics else None
        _fail(str(code or "rust_project_ir_repair_required"), "rust_project_ir")
    dag = _dag_payload(rust_project_ir, root)
    dependencies, order = cargo_project._migration_dag(dag)
    candidates = _candidate_sources(rust_project_ir, root, max_source_bytes)
    cargo_project._validate_candidates(candidates, dependencies)
    accepted = {item.group_id: item for item in candidates}
    cargo_project._validate_accepted(accepted, dependencies, order)
    unsafe_policy = cargo_project._unsafe_policy(dag.get("unsafe_policy"), candidates)
    _validate_ir_configuration(rust_project_ir, candidates)
    return render_cargo_project(
        rust_project_ir, binding, coordination, dependencies, order,
        candidates, unsafe_policy,
        "verification-cohort" if PARENT_DAG_KEY in dag else "full-project",
    )
def _dag_payload(ir: Mapping[str, Any], root: Path) -> dict[str, Any]:
    try:
        raw = read_artifact_reference(root, ir["bindings"]["migration_dag"])
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, KeyError) as error:
        _fail("rust_project_ir_dag_unreadable", "rust_project_ir", detail=error)
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail("rust_project_ir_dag_noncanonical", "rust_project_ir")
    return value
def _candidate_sources(
    ir: Mapping[str, Any], root: Path, limit: int,
) -> list[cargo_project.CandidateSource]:
    modules = {item["unit_id"]: item for item in ir["modules"]}
    public = _public_symbols(ir)
    obligations = _unsafe_counts(ir)
    ffi = _ffi_facts(ir)
    result = []
    total = 0
    for reference in ir["bindings"]["candidates"]:
        unit_id = str(reference["unit_id"])
        module = modules.get(unit_id)
        if module is None:
            _fail("rust_project_ir_module_missing", "rust_project_ir", unit_id)
        try:
            source = read_artifact_reference(root, reference["source"])
            text = source.decode("utf-8")
        except (OSError, UnicodeError, ValueError) as error:
            _fail("candidate_source_unreadable", "candidate", unit_id, error)
        total += len(source)
        if len(source) > limit or total > 8_000_000:
            _fail("candidate_sources_too_large", "candidate", unit_id)
        metadata = derive_rust_metadata(text)
        if tuple(metadata["public_symbols"]) != public.get(str(module["module_id"]), ()):
            _fail("rust_project_ir_public_api_drift", "rust_project_ir", unit_id)
        if int(metadata["unsafe_count"]) != obligations.get(str(module["module_id"]), 0):
            _fail("rust_project_ir_unsafe_obligation_drift", "rust_project_ir", unit_id)
        if _derived_ffi(text, str(reference["source"]["sha256"])) != ffi.get(
            str(module["module_id"]), (),
        ):
            _fail("rust_project_ir_ffi_boundary_drift", "rust_project_ir", unit_id)
        result.append(cargo_project.CandidateSource(
            group_id=unit_id, status="accepted",
            source_path=str(reference["source"]["path"]),
            sha256=str(reference["source"]["sha256"]), source=source,
            public_symbols=tuple(metadata["public_symbols"]),
            required_symbols=tuple(metadata["required_symbols"]),
            unsafe_count=int(metadata["unsafe_count"]),
        ))
    return result


def _public_symbols(ir: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for item in ir["public_api"]:
        if item["visibility"] == "public":
            values.setdefault(str(item["module_id"]), []).append(str(item["symbol"]))
    return {key: tuple(sorted(items)) for key, items in values.items()}


def _unsafe_counts(ir: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in ir["unsafe_obligations"]:
        module_id = str(item["module_id"])
        counts[module_id] = counts.get(module_id, 0) + 1
        if counts[module_id] > MAX_UNSAFE_OBLIGATIONS:
            _fail("rust_project_ir_unsafe_obligations_unbounded", "rust_project_ir")
    return counts


def _ffi_facts(ir: Mapping[str, Any]) -> dict[str, tuple[tuple[str, str, str, str], ...]]:
    values: dict[str, list[tuple[str, str, str, str]]] = {}
    for item in ir["ffi_boundaries"]:
        values.setdefault(str(item["module_id"]), []).append((
            str(item["symbol"]), str(item["direction"]), str(item["abi"]),
            str(item["link_name"]),
        ))
    return {key: tuple(sorted(items)) for key, items in values.items()}


def _derived_ffi(source: str, digest: str) -> tuple[tuple[str, str, str, str], ...]:
    try:
        facts = derive_ffi_boundary_facts(source, digest)
    except NoFfiBoundaryError:
        return ()
    return tuple(sorted((
        item["symbol"], item["direction"], item["abi"], item["link_name"],
    ) for item in facts))


def _validate_ir_configuration(
    ir: Mapping[str, Any], candidates: list[cargo_project.CandidateSource],
) -> None:
    crate = ir["crate"]
    if not _PACKAGE.fullmatch(str(crate["crate_id"])):
        _fail("rust_project_ir_crate_name_invalid", "rust_project_ir")
    if crate["edition"] not in _EDITIONS or crate["targets"] != ["library"]:
        _fail("rust_project_ir_target_unsupported", "rust_project_ir")
    if not set(crate["crate_types"]) <= _CRATE_TYPES:
        _fail("rust_project_ir_crate_type_unsupported", "rust_project_ir")
    if crate["root_module_id"] != VIRTUAL_CRATE_ROOT:
        _fail("rust_project_ir_authoritative_root_invalid", "rust_project_ir")
    by_unit = {item.group_id: item for item in candidates}
    for module in ir["modules"]:
        candidate = by_unit[str(module["unit_id"])]
        expected = f"src/{candidate.module_name}.rs"
        if module["parent_module_id"] is not None or module["rust_path"] != expected:
            _fail("rust_project_ir_module_layout_unsupported", "rust_project_ir", candidate.group_id)
    for feature in ir["features"]:
        if not _FEATURE.fullmatch(str(feature["name"])):
            _fail("rust_project_ir_feature_invalid", "rust_project_ir")
    if any(not _CFG.fullmatch(str(item["expression"])) for item in ir["cfgs"]):
        _fail("rust_project_ir_cfg_invalid", "rust_project_ir")
    try:
        native_link_build_script(ir)
    except ValueError as error:
        _fail(str(error), "rust_project_ir")


def _fail(
    code: str, stage: str, group_id: str | None = None, detail: Exception | None = None,
) -> None:
    del detail
    raise cargo_project.ProjectInputError(code, stage, group_id)


__all__ = [
    "GENERATOR", "RUST_PROJECT_IR_FILE", "VIRTUAL_CRATE_ROOT",
    "reconstruct_cargo_project_from_ir",
]
