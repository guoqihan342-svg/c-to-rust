from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .artifacts import content_sha256
from .project_diagnostic_shape import build_project_diagnostic


_RUSTC_CODE = re.compile(r"e[0-9]{4}\Z")
_UNIT_PATH = re.compile(r"src/unit_([0-9a-f]{64})\.rs\Z")
_SYMBOL_RESOLUTION_CODES = frozenset({"e0412", "e0425", "e0432", "e0433"})
_ENVIRONMENT_RUSTC_CODES = frozenset({
    "e0460", "e0461", "e0462", "e0463", "e0464", "e0465",
    "e0514", "e0554", "e0635", "e0658", "e0786",
})
_ENTITY_FIELDS = (
    ("public_api", "symbol"),
    ("shared_types", "name"),
    ("global_ownership", "symbol"),
    ("initialization", "function"),
    ("ffi_boundaries", "link_name"),
    ("features", "name"),
)


@dataclass(frozen=True, slots=True)
class CargoDiagnosticPartition:
    unit_diagnostics: dict[tuple[str, str], list[dict[str, Any]]]
    project_diagnostics: list[dict[str, Any]]
    admission_blocker: str | None


def partition_cargo_diagnostics(
    *, gate_kind: str, diagnostics: Any,
    candidate_members: Sequence[Mapping[str, Any]],
    rust_project_ir: Mapping[str, Any],
) -> CargoDiagnosticPartition:
    if gate_kind not in {"cargo-check", "cargo-test"}:
        raise ValueError("Cargo diagnostic gate kind is invalid")
    if not isinstance(diagnostics, list) or len(diagnostics) > 64:
        return CargoDiagnosticPartition({}, [], "diagnostic-set-invalid")
    path_owners, owner_blocker = _candidate_path_owners(
        candidate_members, rust_project_ir,
    )
    if owner_blocker is not None:
        return CargoDiagnosticPartition({}, [], owner_blocker)
    unit: dict[tuple[str, str], list[dict[str, Any]]] = {}
    project: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        if not _structured_error(diagnostic, gate_kind):
            return CargoDiagnosticPartition({}, [], "diagnostic-not-structured")
        if diagnostic.get("code") in _ENVIRONMENT_RUSTC_CODES:
            return CargoDiagnosticPartition(
                {}, [], "diagnostic-environment-failure",
            )
        location = str(diagnostic.get("file", ""))
        owner = path_owners.get(location)
        if owner is not None:
            identity, owner_module = owner
            matched_entities, matched_modules = _matching_ir_entities(
                str(diagnostic.get("message", "")), rust_project_ir,
            )
            if (
                diagnostic.get("code") in _SYMBOL_RESOLUTION_CODES
                and any(module != owner_module for module in matched_modules)
            ):
                project.append(_project_diagnostic(
                    diagnostic, gate_kind, rust_project_ir,
                    matched=(matched_entities, matched_modules),
                    extra_module_ids=[owner_module],
                ))
            else:
                unit.setdefault(identity, []).append(_unit_projection(diagnostic))
            continue
        if _UNIT_PATH.fullmatch(location) is not None:
            return CargoDiagnosticPartition({}, [], "unit-path-not-unique")
        normalized = _project_diagnostic(diagnostic, gate_kind, rust_project_ir)
        if normalized is None:
            return CargoDiagnosticPartition({}, [], "diagnostic-unclassified")
        project.append(normalized)
    project.sort(
        key=lambda item: item["project_diagnostic"]["diagnostic_sha256"],
    )
    hashes = [item["project_diagnostic"]["diagnostic_sha256"] for item in project]
    if len(set(hashes)) != len(hashes):
        return CargoDiagnosticPartition({}, [], "project-diagnostic-duplicate")
    return CargoDiagnosticPartition(unit, project, None)


def _structured_error(value: Any, gate_kind: str) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("origin") == "rustc-compiler-message"
        and value.get("level") == "error"
        and value.get("stage") == gate_kind
    )


def _unit_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"code", "stage", "message", "file", "line", "column"}
    return {key: item for key, item in value.items() if key in allowed}


def _project_diagnostic(
    value: Mapping[str, Any], gate_kind: str, rust_project_ir: Mapping[str, Any],
    *, matched: tuple[list[str], list[str]] | None = None,
    extra_module_ids: Sequence[str] = (),
) -> dict[str, Any] | None:
    code = value.get("code")
    file_value = value.get("file")
    message = value.get("message")
    if (
        not isinstance(code, str) or _RUSTC_CODE.fullmatch(code) is None
        or not isinstance(file_value, str) or not file_value
        or not isinstance(message, str) or not message
    ):
        return None
    entity_ids, module_ids = (
        _matching_ir_entities(message, rust_project_ir)
        if matched is None else matched
    )
    location = {
        "file": file_value,
        "line": value.get("line"),
        "column": value.get("column"),
    }
    event_sha = content_sha256({
        "source_code": code, "stage": gate_kind,
        "message": message[:512], "location": location,
    })
    stable_entities = sorted({
        code, f"event:{event_sha}", f"file:{file_value}", *entity_ids,
    })
    diagnostic = build_project_diagnostic(
        code=f"project-verifier-{code}",
        entity_ids=stable_entities,
        affected_module_ids=sorted({*module_ids, *extra_module_ids}),
    )
    return {
        "family": "compile",
        "source_code": code,
        "stage": gate_kind,
        "message": message[:512],
        "location": location,
        "project_diagnostic": diagnostic,
    }


def _matching_ir_entities(
    message: str, rust_project_ir: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    entities: set[str] = set()
    modules: set[str] = set()
    for section, field in _ENTITY_FIELDS:
        records = rust_project_ir.get(section)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, Mapping):
                continue
            value = record.get(field)
            if not isinstance(value, str) or not _contains_token(message, value):
                continue
            entities.add(f"{section}:{value}")
            owner_ids = record.get("module_ids", [record.get("module_id")])
            if isinstance(owner_ids, list):
                modules.update(str(item) for item in owner_ids if isinstance(item, str))
    return sorted(entities), sorted(modules)


def _candidate_path_owners(
    candidate_members: Sequence[Mapping[str, Any]],
    rust_project_ir: Mapping[str, Any],
) -> tuple[dict[str, tuple[tuple[str, str], str]], str | None]:
    expected: dict[tuple[str, str], tuple[str, str]] = {}
    for member in candidate_members:
        key = (str(member.get("unit_id")), str(member.get("content_sha256")))
        identity = (key[0], str(member.get("artifact_id")))
        if key in expected:
            return {}, "candidate-module-binding-not-unique"
        expected[key] = identity
    modules = rust_project_ir.get("modules")
    if not isinstance(modules, list):
        return ({}, None) if not expected else ({}, "candidate-module-coverage-invalid")
    paths: dict[str, tuple[tuple[str, str], str]] = {}
    covered: set[tuple[str, str]] = set()
    for module in modules:
        if not isinstance(module, Mapping):
            return {}, "candidate-module-binding-invalid"
        key = (str(module.get("unit_id")), str(module.get("candidate_sha256")))
        identity = expected.get(key)
        path = module.get("rust_path")
        module_id = module.get("module_id")
        if identity is None:
            continue
        if (
            key in covered or not isinstance(path, str) or not path
            or not isinstance(module_id, str) or not module_id or path in paths
        ):
            return {}, "candidate-module-binding-not-unique"
        covered.add(key)
        paths[path] = (identity, module_id)
    if covered != set(expected):
        return {}, "candidate-module-coverage-invalid"
    return paths, None


def _contains_token(message: str, token: str) -> bool:
    if not token or len(token) > 128:
        return False
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", message) is not None


__all__ = ["CargoDiagnosticPartition", "partition_cargo_diagnostics"]
