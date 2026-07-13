from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, Sequence

from . import cargo_project


MAX_CANDIDATES = 512
MAX_TOTAL_SOURCE_BYTES = 8_000_000
MAX_MANIFEST_BYTES = 128_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def normalize_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(manifest, Mapping):
        return manifest
    container = manifest
    nested = manifest.get("migration_dag")
    if isinstance(nested, Mapping) and ("groups" in nested or "sccs" in nested):
        container = nested
    entries = container.get("groups")
    id_key, dependency_keys, wave_key = "group_id", ("dependencies", "depends_on"), "group_ids"
    if entries is None:
        entries = container.get("sccs")
        id_key, dependency_keys, wave_key = "scc_id", ("dependency_scc_ids",), "scc_ids"
    if entries is None:
        return manifest
    if not isinstance(entries, list) or not entries:
        raise cargo_project.ProjectInputError("dag_invalid", "dag")
    dependencies: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise cargo_project.ProjectInputError("dag_invalid", "dag")
        group_id = cargo_project._group_id(entry.get(id_key))
        if group_id in dependencies:
            raise cargo_project.ProjectInputError("dag_group_duplicate", "dag", group_id)
        raw_dependencies: Any = []
        for key in dependency_keys:
            if key in entry:
                raw_dependencies = entry[key]
                break
        if not isinstance(raw_dependencies, list):
            raise cargo_project.ProjectInputError("dag_dependencies_invalid", "dag", group_id)
        dependencies[group_id] = [cargo_project._group_id(value) for value in raw_dependencies]
    normalized = dict(manifest)
    normalized["dag"] = dependencies
    waves = container.get("waves")
    if waves is not None:
        normalized["dag_order"] = _wave_order(waves, set(dependencies), wave_key, id_key)
    if "unsafe_policy" not in normalized and isinstance(container.get("unsafe_policy"), Mapping):
        normalized["unsafe_policy"] = container["unsafe_policy"]
    return normalized


def load_candidates(
    descriptors: Sequence[Mapping[str, Any]],
    candidate_root: Path,
    max_source_bytes: int,
) -> list[cargo_project.CandidateSource]:
    if (
        isinstance(descriptors, (str, bytes))
        or not isinstance(descriptors, Sequence)
        or len(descriptors) > MAX_CANDIDATES
    ):
        raise cargo_project.ProjectInputError("candidate_descriptors_invalid", "candidate")
    if (
        isinstance(max_source_bytes, bool)
        or not isinstance(max_source_bytes, int)
        or max_source_bytes < 1
        or max_source_bytes > cargo_project.MAX_SOURCE_BYTES
    ):
        raise cargo_project.ProjectInputError("candidate_size_limit_invalid", "candidate")
    root = trusted_root(candidate_root)
    candidates: list[cargo_project.CandidateSource] = []
    total_size = 0
    for descriptor in descriptors:
        if not isinstance(descriptor, Mapping):
            raise cargo_project.ProjectInputError("candidate_descriptor_invalid", "candidate")
        group_id = cargo_project._group_id(descriptor.get("group_id"))
        source_path, source = _candidate_source(
            root, descriptor.get("source_path"), max_source_bytes, group_id,
        )
        total_size += len(source)
        if total_size > MAX_TOTAL_SOURCE_BYTES:
            raise cargo_project.ProjectInputError("candidate_sources_too_large", "candidate")
        sha256 = descriptor.get("sha256")
        if not isinstance(sha256, str):
            sha256 = ""
        candidates.append(cargo_project.CandidateSource(
            group_id=group_id,
            status=descriptor.get("status") if isinstance(descriptor.get("status"), str) else "",
            source_path=source_path,
            sha256=sha256,
            source=source,
            public_symbols=cargo_project._symbols(descriptor.get("public_symbols"), group_id),
            required_symbols=cargo_project._symbols(descriptor.get("required_symbols"), group_id),
            unsafe_count=descriptor.get("unsafe_count"),
        ))
    return candidates


def trusted_root(value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, TypeError):
        raise cargo_project.ProjectInputError("candidate_root_invalid", "candidate") from None
    if not root.is_dir():
        raise cargo_project.ProjectInputError("candidate_root_invalid", "candidate")
    return root


def project_target(value: Path, candidate_root: Path) -> Path:
    try:
        requested = Path(value).expanduser()
        if requested.name in {"", ".", ".."}:
            raise ValueError
        requested.parent.mkdir(parents=True, exist_ok=True)
        parent = requested.parent.resolve(strict=True)
        target = parent / requested.name
    except (OSError, TypeError, ValueError):
        raise cargo_project.ProjectInputError("project_root_invalid", "filesystem") from None
    if target.is_symlink() or target == candidate_root:
        raise cargo_project.ProjectInputError("project_root_untrusted", "filesystem")
    if target.is_relative_to(candidate_root) or candidate_root.is_relative_to(target):
        raise cargo_project.ProjectInputError("project_root_overlaps_candidates", "filesystem")
    return target


def existing_state(root: Path) -> tuple[str, bool]:
    if not root.exists():
        return "absent", False
    if root.is_symlink() or not root.is_dir():
        raise cargo_project.ProjectInputError("existing_project_invalid", "last_good")
    if not any(root.iterdir()):
        return "empty", False
    manifest_path = root / cargo_project.LAST_GOOD_MANIFEST
    try:
        raw = read_bounded(manifest_path, MAX_MANIFEST_BYTES)
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise cargo_project.ProjectInputError("last_good_manifest_invalid", "last_good") from None
    if (
        raw != cargo_project.canonical_json_bytes(manifest)
        or manifest.get("schema_version") != cargo_project.SCHEMA_VERSION
        or manifest.get("generator") != "deterministic-cargo-reconstruction-v1"
        or not isinstance(manifest.get("files"), list)
    ):
        raise cargo_project.ProjectInputError("last_good_manifest_invalid", "last_good")
    expected = {cargo_project.LAST_GOOD_MANIFEST}
    for ref in manifest["files"]:
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "size_bytes"}:
            raise cargo_project.ProjectInputError("last_good_manifest_invalid", "last_good")
        relative = generated_path(ref.get("path"))
        if (
            not isinstance(ref.get("sha256"), str)
            or not _SHA256.fullmatch(ref["sha256"])
            or isinstance(ref.get("size_bytes"), bool)
            or not isinstance(ref.get("size_bytes"), int)
            or ref["size_bytes"] < 0
        ):
            raise cargo_project.ProjectInputError("last_good_manifest_invalid", "last_good")
        try:
            data = read_bounded(root.joinpath(*relative.parts), cargo_project.MAX_SOURCE_BYTES)
        except (OSError, ValueError):
            raise cargo_project.ProjectInputError("last_good_file_invalid", "last_good") from None
        if len(data) != ref["size_bytes"] or digest(data) != ref["sha256"]:
            raise cargo_project.ProjectInputError("last_good_file_drift", "last_good")
        expected.add(relative.as_posix())
    actual: set[str] = set()
    for directory, directories, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        if any((base / name).is_symlink() for name in directories + filenames):
            raise cargo_project.ProjectInputError("last_good_link_forbidden", "last_good")
        actual.update((base / name).relative_to(root).as_posix() for name in filenames)
    if actual != expected:
        raise cargo_project.ProjectInputError("last_good_tree_drift", "last_good")
    return digest(raw), True


def generated_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str):
        raise cargo_project.ProjectInputError("generated_path_invalid", "filesystem")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise cargo_project.ProjectInputError("generated_path_invalid", "filesystem")
    return path


def read_bounded(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError("unbounded file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("unbounded file")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wave_order(waves: Any, groups: set[str], wave_key: str, id_key: str) -> list[str]:
    if not isinstance(waves, list) or not waves:
        raise cargo_project.ProjectInputError("dag_order_invalid", "dag")
    order: list[str] = []
    for wave in waves:
        raw_values = wave.get(wave_key, wave.get("groups")) if isinstance(wave, Mapping) else wave
        if not isinstance(raw_values, list):
            raise cargo_project.ProjectInputError("dag_order_invalid", "dag")
        values = [value.get(id_key) if isinstance(value, Mapping) else value for value in raw_values]
        order.extend(cargo_project._group_id(value) for value in values)
    if len(order) != len(set(order)) or set(order) != groups:
        raise cargo_project.ProjectInputError("dag_order_invalid", "dag")
    return order


def _candidate_source(root: Path, value: Any, limit: int, group_id: str) -> tuple[str, bytes]:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > 1_024:
        raise cargo_project.ProjectInputError("candidate_path_invalid", "candidate", group_id)
    unresolved = Path(value)
    path = unresolved if unresolved.is_absolute() else root / unresolved
    if path.is_symlink():
        raise cargo_project.ProjectInputError("candidate_path_untrusted", "candidate", group_id)
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root)
        source = read_bounded(resolved, limit)
    except (OSError, ValueError):
        raise cargo_project.ProjectInputError("candidate_path_untrusted", "candidate", group_id) from None
    return relative.as_posix(), source
