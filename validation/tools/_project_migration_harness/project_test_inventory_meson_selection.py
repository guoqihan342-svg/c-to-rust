from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .build_facts import file_binding, resolve_repository_path
from .meson_introspection import inspect_meson_introspection


MAX_MESON_MARKER_BYTES = 1024 * 1024


def meson_selection_is_bound(
    repo_root: Path, discovery: Mapping[str, Any], build_ir: Mapping[str, Any],
) -> bool:
    root = Path(repo_root).resolve(strict=True)
    _validate_discovery_markers(root, discovery)
    database = discovery.get("compile_database")
    path = database.get("path") if isinstance(database, Mapping) else None
    if not isinstance(path, str):
        raise ValueError("Meson compile database is unbound")
    report = inspect_meson_introspection(
        root, resolve_repository_path(root, path),
    )
    if report.get("status") != "ready":
        return False
    report_ids = {
        str(item["id"])
        for item in _mapping_list(report.get("targets"))
        if isinstance(item.get("outputs"), list) and item["outputs"]
    }
    build_ir_ids: list[str] = []
    for target in _mapping_list(build_ir.get("targets")):
        provenance = target.get("provenance")
        meson_id = provenance.get("meson_target_id") if isinstance(
            provenance, Mapping,
        ) else None
        if isinstance(meson_id, str) and meson_id:
            build_ir_ids.append(meson_id)
    return (
        bool(report_ids)
        and len(build_ir_ids) == len(set(build_ir_ids))
        and set(build_ir_ids) == report_ids
    )


def _validate_discovery_markers(
    root: Path, discovery: Mapping[str, Any],
) -> None:
    facts = discovery.get("build_system_facts")
    markers = facts.get("markers") if isinstance(facts, Mapping) else None
    if (
        not isinstance(facts, Mapping) or facts.get("status") != "detected"
        or facts.get("blockers") != [] or not isinstance(markers, list)
    ):
        raise ValueError("Meson discovery facts are invalid")
    meson_markers = [
        item for item in markers
        if isinstance(item, Mapping) and item.get("build_system") == "meson"
    ]
    if not meson_markers or not any(
        item.get("path") == "meson.build" for item in meson_markers
    ):
        raise ValueError("Meson root marker is unbound")
    for marker in meson_markers:
        if set(marker) != {"build_system", "path", "sha256", "size_bytes"}:
            raise ValueError("Meson marker schema is invalid")
        path = marker.get("path")
        if not isinstance(path, str):
            raise ValueError("Meson marker path is invalid")
        current = file_binding(
            root, resolve_repository_path(root, path),
            max_bytes=MAX_MESON_MARKER_BYTES,
        )
        if current != {
            key: marker[key] for key in ("path", "sha256", "size_bytes")
        }:
            raise ValueError("Meson marker binding changed")


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError("Meson target evidence is invalid")
    return value


__all__ = ["meson_selection_is_bound"]
