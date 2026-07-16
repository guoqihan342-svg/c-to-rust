from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .build_facts import resolve_repository_path
from .build_adapter import MAKE_REPORT_INPUT_KIND, MAKE_REPORT_RAW_ROLE
from .compile_database import command_arguments
from .discovery_database import load_compile_database


_ADAPTERS = {"cmake": "ctest-json-v1", "make": "make-dry-run-v1"}
MAX_COMPILE_EVIDENCE_ENTRIES = 10_000
MAX_BUILD_IR_EVIDENCE_PATHS = 100_000
_AUTOMAKE_DEPFILE = re.compile(r"\.(?:Po|Plo|Tpo|Tlo)\Z", re.ASCII)


def select_project_test_adapter(
    repo_root: Path, discovery: Mapping[str, Any], build_ir: Mapping[str, Any],
) -> dict[str, Any]:
    raw = discovery.get("build_system_facts", {}).get("systems")
    if (
        not isinstance(raw, list) or not raw
        or not all(isinstance(item, str) for item in raw)
        or raw != sorted(set(raw))
    ):
        return _blocked("project_test_adapter_unavailable")
    systems = set(raw)
    if len(systems) == 1:
        system = next(iter(systems))
        adapter = _ADAPTERS.get(system)
        return _selected(adapter) if adapter else _blocked(
            "project_test_adapter_unavailable"
        )
    if systems != set(_ADAPTERS):
        return _blocked("project_test_adapter_ambiguous")
    try:
        candidates = _mixed_candidates(repo_root, discovery, build_ir)
    except (OSError, TypeError, ValueError):
        return _blocked("project_test_adapter_evidence_invalid")
    if not candidates:
        return _blocked("project_test_adapter_unbound")
    if len(candidates) != 1:
        return _blocked("project_test_adapter_ambiguous")
    return _selected(_ADAPTERS[next(iter(candidates))])


def _mixed_candidates(
    repo_root: Path, discovery: Mapping[str, Any], build_ir: Mapping[str, Any],
) -> set[str]:
    candidates: set[str] = set()
    raw_roles = {
        item.get("role") for item in _mapping_list(build_ir.get("raw_fact_refs"))
    }
    provenance_roles = {
        item.get("provenance", {}).get("raw_fact_role")
        for item in [
            *_mapping_list(build_ir.get("translation_units")),
            *_mapping_list(build_ir.get("targets")),
        ]
        if isinstance(item.get("provenance"), Mapping)
    }
    make_role_bound = (
        MAKE_REPORT_RAW_ROLE in raw_roles
        and MAKE_REPORT_RAW_ROLE in provenance_roles
    )
    make_input_selected = discovery.get("input_kind") == MAKE_REPORT_INPUT_KIND
    if make_role_bound != make_input_selected:
        raise ValueError("Make adapter evidence is inconsistent")
    if make_role_bound:
        candidates.add("make")
    paths = _build_ir_paths(build_ir)
    candidates.update(_path_candidates(paths))
    database = discovery.get("compile_database")
    if isinstance(database, Mapping) and database.get("status") == "bound":
        payload = _bound_compile_database(repo_root, database, build_ir)
        if len(payload) > MAX_COMPILE_EVIDENCE_ENTRIES:
            raise ValueError("compile evidence entry limit exceeded")
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("compile evidence entry invalid")
            argv = command_arguments(entry)
            values = [*argv]
            values.extend(
                value for key in ("directory", "file", "output")
                if isinstance((value := entry.get(key)), str)
            )
            candidates.update(_path_candidates(values))
    elif not candidates:
        raise ValueError("compile evidence unavailable")
    return candidates


def _bound_compile_database(
    repo_root: Path, binding: Mapping[str, Any], build_ir: Mapping[str, Any],
) -> list[Any]:
    metadata = _mapping_list(build_ir.get("build_metadata"))
    if len(metadata) != 1:
        raise ValueError("build metadata is not unique")
    expected = metadata[0]
    if expected.get("kind") != "file" or expected.get("materialized") is not True:
        raise ValueError("BuildIR metadata is not materialized")
    for key in ("path", "sha256", "size_bytes"):
        if binding.get(key) != expected.get(key):
            raise ValueError("compile database is not BuildIR-bound")
    path, digest = binding.get("path"), binding.get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError("compile database binding invalid")
    resolved = resolve_repository_path(repo_root, path)
    size = binding.get("size_bytes")
    if (
        isinstance(size, bool) or not isinstance(size, int) or size < 0
        or resolved.stat().st_size != size
    ):
        raise ValueError("compile database size binding changed")
    payload, blocker = load_compile_database(resolved, digest)
    if blocker is not None or payload is None:
        raise ValueError(blocker or "compile database unavailable")
    return payload


def _build_ir_paths(build_ir: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for unit in _mapping_list(build_ir.get("translation_units")):
        output = unit.get("output")
        if isinstance(output, Mapping) and isinstance(output.get("path"), str):
            values.append(str(output["path"]))
    for target in _mapping_list(build_ir.get("targets")):
        for output in _mapping_list(target.get("outputs")):
            if isinstance(output.get("path"), str):
                values.append(str(output["path"]))
    if len(values) > MAX_BUILD_IR_EVIDENCE_PATHS:
        raise ValueError("BuildIR evidence path limit exceeded")
    return values


def _path_candidates(values: list[str]) -> set[str]:
    candidates: set[str] = set()
    for raw in values:
        normalized = raw.replace("\\", "/")
        parts = normalized.split("/")
        if "CMakeFiles" in parts:
            candidates.add("cmake")
        if ".deps/" in normalized and _AUTOMAKE_DEPFILE.search(normalized):
            candidates.add("make")
    return candidates


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError("adapter evidence list invalid")
    return value


def _selected(adapter: str | None) -> dict[str, Any]:
    if adapter is None:
        return _blocked("project_test_adapter_unavailable")
    return {"status": "selected", "adapter": adapter}


def _blocked(code: str) -> dict[str, Any]:
    return {"status": "blocked", "blocker": {"code": code}}


__all__ = ["select_project_test_adapter"]
