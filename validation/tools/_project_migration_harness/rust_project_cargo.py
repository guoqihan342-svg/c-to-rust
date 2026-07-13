from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import cargo_project
from .artifacts import canonical_json_bytes, content_sha256
from .orchestration_facts import read_artifact_reference
from .project_interface_coordinator import coordinate_project_interfaces
from .rust_candidate_facts import derive_rust_metadata
from .rust_ffi_facts import NoFfiBoundaryError, derive_ffi_boundary_facts
from .rust_project_ir import canonical_rust_project_ir_bytes
from .rust_project_ir_validation import (
    VIRTUAL_CRATE_ROOT_MODULE_ID, reopen_rust_project_ir_bindings,
)
from .rust_project_ir_cohort import PARENT_DAG_KEY
GENERATOR = "deterministic-rust-project-ir-cargo-v1"
RUST_PROJECT_IR_FILE = "migration-rust-project-ir.json"
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
    return _render(
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


def _render(
    ir: Mapping[str, Any], binding: Mapping[str, Any], coordination: Mapping[str, Any],
    dependencies: Mapping[str, tuple[str, ...]], order: list[str],
    candidates: list[cargo_project.CandidateSource], unsafe_policy: Mapping[str, Any],
    scope: str,
) -> cargo_project.CargoProjectPlan:
    by_unit = {item.group_id: item for item in candidates}
    module_by_unit = {str(item["unit_id"]): item for item in ir["modules"]}
    conditions = _module_conditions(ir)
    files: dict[str, bytes] = {
        "Cargo.toml": _cargo_toml(ir),
        "Cargo.lock": _cargo_lock(str(ir["crate"]["crate_id"])),
        RUST_PROJECT_IR_FILE: canonical_rust_project_ir_bytes(ir),
    }
    lines = ["// Generated only from a validated RustProjectIR.", ""]
    groups = []
    for unit_id in order:
        candidate = by_unit[unit_id]
        module = module_by_unit[unit_id]
        module_id = str(module["module_id"])
        condition = conditions.get(module_id)
        if condition:
            lines.append(f"#[cfg({condition})]")
        lines.append(f"mod {candidate.module_name};")
        if candidate.public_symbols:
            if condition:
                lines.append(f"#[cfg({condition})]")
            lines.append(
                f"pub use self::{candidate.module_name}::{{{', '.join(candidate.public_symbols)}}};"
            )
        lines.append("")
        files[str(module["rust_path"])] = candidate.source
        groups.append({
            "group_id": unit_id, "module_name": candidate.module_name,
            "dependencies": list(dependencies[unit_id]),
            "source": {"path": candidate.source_path, "sha256": candidate.sha256,
                       "size_bytes": len(candidate.source)},
            "public_symbols": list(candidate.public_symbols),
            "required_symbols": list(candidate.required_symbols),
            "unsafe_count": candidate.unsafe_count,
        })
    files["src/lib.rs"] = ("\n".join(lines).rstrip() + "\n").encode("ascii")
    refs = [_ref(path, data) for path, data in sorted(files.items())]
    dag_payload = {"dependencies": {key: list(dependencies[key]) for key in sorted(dependencies)},
                   "order": order}
    manifest = {
        "schema_version": 1, "generator": GENERATOR,
        "rust_project_ir_scope": scope,
        "rust_project_ir_sha256": ir["ir_sha256"],
        "rust_project_interface_sha256": ir["interface_sha256"],
        "rust_project_ir_completeness": dict(ir["interface_completeness"]),
        "domain_binding_sha256": content_sha256(binding),
        "interface_coordination_sha256": content_sha256(coordination),
        "dag_sha256": hashlib.sha256(cargo_project.canonical_json_bytes(dag_payload)).hexdigest(),
        "accepted_groups": groups, "unsafe_policy": dict(unsafe_policy),
        "cargo_executed": False, "files": refs,
    }
    files[cargo_project.LAST_GOOD_MANIFEST] = cargo_project.canonical_json_bytes(manifest)
    return cargo_project.CargoProjectPlan(files=files, last_good_manifest=manifest)


def _module_conditions(ir: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    for item in ir["cfgs"]:
        for module_id in item["module_ids"]:
            values.setdefault(str(module_id), []).append(str(item["expression"]))
    feature_modules: dict[str, list[str]] = {}
    for item in ir["features"]:
        for module_id in item["module_ids"]:
            feature_modules.setdefault(str(module_id), []).append(str(item["name"]))
    result = {}
    for module in ir["modules"]:
        module_id = str(module["module_id"])
        parts = sorted(values.get(module_id, []))
        names = sorted(feature_modules.get(module_id, []))
        if names:
            feature = ", ".join(f'feature = "{name}"' for name in names)
            parts.append(f"any({feature})" if len(names) > 1 else feature)
        if parts:
            result[module_id] = f"all({', '.join(parts)})" if len(parts) > 1 else parts[0]
    return result


def _cargo_toml(ir: Mapping[str, Any]) -> bytes:
    crate = ir["crate"]
    lines = [
        "[package]", f'name = "{crate["crate_id"]}"', 'version = "0.0.0"',
        f'edition = "{crate["edition"]}"', "publish = false", "", "[lib]",
        'path = "src/lib.rs"',
        "crate-type = [" + ", ".join(f'"{item}"' for item in crate["crate_types"]) + "]",
        "", "[features]",
    ]
    features = {item["feature_id"]: item for item in ir["features"]}
    defaults = sorted(str(item["name"]) for item in features.values() if item["default"])
    lines.append("default = [" + ", ".join(f'"{item}"' for item in defaults) + "]")
    for item in sorted(features.values(), key=lambda value: str(value["name"])):
        enabled = [str(features[feature_id]["name"]) for feature_id in item["enables"]]
        lines.append(f'{item["name"]} = [' + ", ".join(f'"{name}"' for name in enabled) + "]")
    return ("\n".join(lines) + "\n").encode("ascii")


def _cargo_lock(crate_name: str) -> bytes:
    return ("# This file is automatically @generated by Cargo.\n"
            "# It is not intended for manual editing.\nversion = 3\n\n"
            f'[[package]]\nname = "{crate_name}"\nversion = "0.0.0"\n').encode("ascii")


def _ref(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _fail(
    code: str, stage: str, group_id: str | None = None, detail: Exception | None = None,
) -> None:
    del detail
    raise cargo_project.ProjectInputError(code, stage, group_id)


__all__ = [
    "GENERATOR", "RUST_PROJECT_IR_FILE", "VIRTUAL_CRATE_ROOT",
    "reconstruct_cargo_project_from_ir",
]
