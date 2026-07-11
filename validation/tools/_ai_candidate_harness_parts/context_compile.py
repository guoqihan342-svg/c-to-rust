from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context_compile_args import declared_compile_context, summarize_entry
from .context_security import (
    canonical_json_bytes,
    logical_path,
    resolve_under,
    sha256_path,
)


MAX_COMPILE_DATABASE_BYTES = 8 * 1024 * 1024
MAX_COMPILE_ENTRIES = 10_000
MAX_DISCOVERY_DIRECTORIES = 256


def build_compile_context(
    spec: dict[str, Any],
    *,
    source_root: Path | None,
    source_file: str | None,
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    declared = declared_compile_context(spec, source_root, known_roots)
    if source_root is None:
        return {"status": "source_root_unavailable", "declared": declared}
    databases, rejected = compile_database_candidates(spec, source_root)
    if not databases:
        return {
            "status": "compile_database_not_found",
            "declared": declared,
            "rejected_inputs": rejected,
        }

    target_path = resolve_source_file(source_root, source_file)
    database_results = [
        parse_database(path, source_root, target_path, spec, known_roots)
        for path in databases
    ]
    selected = [result for result in database_results if result.get("status") == "selected"]
    if selected:
        selected.sort(key=lambda item: (str(item["input"]["path"]), str(item["selected_entry"]["entry_sha256"])))
        result = selected[0]
        result["declared"] = declared
        if len(selected) > 1:
            result["selection_note"] = "multiple_databases_matched_first_deterministic"
        return result
    return {
        "status": "compile_command_not_selected",
        "declared": declared,
        "databases": database_results,
        "rejected_inputs": rejected,
    }


def compile_database_candidates(spec: dict[str, Any], source_root: Path) -> tuple[list[Path], list[str]]:
    candidates: set[Path] = set()
    rejected: list[str] = []
    build_profile = spec.get("build_profile")
    declared = build_profile.get("compiler_command_source") if isinstance(build_profile, dict) else None
    if isinstance(declared, str) and Path(declared).name == "compile_commands.json":
        try:
            path = resolve_under(source_root, declared)
        except ValueError:
            rejected.append("declared_compile_database_outside_source_root")
        else:
            if path.is_file():
                candidates.add(path)
            else:
                rejected.append("declared_compile_database_missing")

    root_candidate = source_root / "compile_commands.json"
    if root_candidate.is_file() and not root_candidate.is_symlink():
        candidates.add(root_candidate.resolve())
    children = sorted(
        (child for child in source_root.iterdir() if child.is_dir() and not child.is_symlink()),
        key=lambda path: path.name,
    )[:MAX_DISCOVERY_DIRECTORIES]
    for child in children:
        candidate = child / "compile_commands.json"
        if candidate.is_file() and not candidate.is_symlink():
            candidates.add(candidate.resolve())
    return sorted(candidates, key=lambda path: logical_path(source_root, path)), sorted(set(rejected))


def parse_database(
    path: Path,
    source_root: Path,
    target_path: Path | None,
    spec: dict[str, Any],
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    size_bytes = path.stat().st_size
    input_binding = {
        "path": logical_path(source_root, path),
        "sha256": sha256_path(path),
        "size_bytes": size_bytes,
    }
    if size_bytes > MAX_COMPILE_DATABASE_BYTES:
        return {"status": "omitted_too_large", "input": input_binding}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "invalid_compile_database", "input": input_binding}
    if not isinstance(payload, list) or len(payload) > MAX_COMPILE_ENTRIES:
        return {"status": "invalid_compile_database_shape", "input": input_binding}

    valid: list[tuple[Path, Path, dict[str, Any]]] = []
    rejected_entries = 0
    for entry in payload:
        resolved = resolve_entry(entry, source_root)
        if resolved is None:
            rejected_entries += 1
            continue
        working_directory, entry_file = resolved
        valid.append((working_directory, entry_file, entry))
    matches = [item for item in valid if target_path is not None and item[1] == target_path]
    if target_path is None and len(valid) == 1:
        matches = valid
    if not matches:
        return {
            "status": "no_matching_entry" if target_path is not None else "ambiguous_without_source_file",
            "input": input_binding,
            "entry_count": len(payload),
            "valid_entry_count": len(valid),
            "rejected_entry_count": rejected_entries,
        }
    matches.sort(key=lambda item: canonical_json_bytes(item[2]))
    working_directory, entry_file, entry = matches[0]
    summary = summarize_entry(entry, source_root, working_directory, entry_file, spec, known_roots)
    return {
        "status": "selected",
        "input": input_binding,
        "entry_count": len(payload),
        "matching_entry_count": len(matches),
        "rejected_entry_count": rejected_entries,
        "selected_entry": summary,
    }


def resolve_entry(entry: Any, source_root: Path) -> tuple[Path, Path] | None:
    if not isinstance(entry, dict):
        return None
    directory = entry.get("directory", ".")
    file_value = entry.get("file")
    if not isinstance(directory, str) or not isinstance(file_value, str):
        return None
    try:
        working_directory = resolve_under(source_root, directory)
        entry_file = resolve_under(source_root, file_value, base=working_directory)
    except ValueError:
        return None
    return working_directory, entry_file


def resolve_source_file(source_root: Path, source_file: str | None) -> Path | None:
    if not isinstance(source_file, str) or not source_file:
        return None
    try:
        return resolve_under(source_root, source_file)
    except ValueError:
        return None
