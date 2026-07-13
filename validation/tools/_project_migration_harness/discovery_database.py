from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .build_facts import (
    file_binding,
    is_linklike,
    resolve_repository_path,
)


MAX_COMPILE_DATABASE_BYTES = 64 * 1024 * 1024
MAX_COMPILE_DATABASE_SCAN_DIRECTORIES = 4_096


def select_compile_database(
    repo_root: Path, explicit: str | Path | None
) -> tuple[dict[str, Any], Path | None, list[str]]:
    if explicit is not None:
        try:
            selected = resolve_repository_path(repo_root, explicit)
            binding = file_binding(
                repo_root, selected, max_bytes=MAX_COMPILE_DATABASE_BYTES
            )
        except (OSError, ValueError):
            return (
                {"status": "invalid", "selection": "explicit"},
                None,
                ["explicit_compile_database_invalid"],
            )
        return {"status": "bound", "selection": "explicit", **binding}, selected, []
    candidates, scan_blockers = compile_database_candidates(repo_root)
    bound_candidates: list[tuple[dict[str, Any], Path]] = []
    for candidate in candidates:
        try:
            binding = file_binding(
                repo_root, candidate, max_bytes=MAX_COMPILE_DATABASE_BYTES
            )
        except (OSError, ValueError):
            continue
        bound_candidates.append((binding, candidate))
    bindings = [item[0] for item in bound_candidates]
    if scan_blockers:
        return (
            {"status": "incomplete", "selection": "discovered", "candidates": bindings},
            None,
            scan_blockers,
        )
    if not bound_candidates:
        return {"status": "missing", "selection": "discovered"}, None, [
            "compile_database_not_found"
        ]
    if len(bound_candidates) > 1:
        return (
            {"status": "ambiguous", "selection": "discovered", "candidates": bindings},
            None,
            ["multiple_compile_databases"],
        )
    return (
        {"status": "bound", "selection": "discovered", **bindings[0]},
        bound_candidates[0][1],
        [],
    )


def compile_database_candidates(repo_root: Path) -> tuple[list[Path], list[str]]:
    candidates: set[Path] = set()
    blockers: list[str] = []
    scanned_directories = 0
    root_candidate = repo_root / "compile_commands.json"
    if root_candidate.is_file() and not is_linklike(root_candidate):
        candidates.add(root_candidate.resolve())
    children = sorted(
        (
            child
            for child in repo_root.iterdir()
            if child.is_dir()
            and not is_linklike(child)
            and child.name.lower().startswith(("build", "out"))
        ),
        key=lambda path: path.name,
    )
    for child in children:
        for current_text, directories, files in os.walk(
            child, topdown=True, followlinks=False
        ):
            scanned_directories += 1
            if scanned_directories > MAX_COMPILE_DATABASE_SCAN_DIRECTORIES:
                blockers.append("compile_database_scan_limit_exceeded")
                directories[:] = []
                break
            current = Path(current_text)
            directories[:] = sorted(
                name for name in directories if not is_linklike(current / name)
            )
            if "compile_commands.json" in files:
                candidate = current / "compile_commands.json"
                if candidate.is_file() and not is_linklike(candidate):
                    candidates.add(candidate.resolve())
        if blockers:
            break
    return (
        sorted(candidates, key=lambda path: path.relative_to(repo_root).as_posix()),
        blockers,
    )


def load_compile_database(
    path: Path, expected_sha256: str
) -> tuple[list[Any] | None, str | None]:
    try:
        if is_linklike(path) or not path.is_file():
            return None, "compile_database_binding_changed"
        payload_bytes = path.read_bytes()
        if len(payload_bytes) > MAX_COMPILE_DATABASE_BYTES:
            return None, "compile_database_too_large"
        if hashlib.sha256(payload_bytes).hexdigest() != expected_sha256:
            return None, "compile_database_binding_changed"
        payload = json.loads(payload_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "compile_database_invalid_json"
    if not isinstance(payload, list):
        return None, "compile_database_invalid_shape"
    return payload, None


__all__ = ["load_compile_database", "select_compile_database"]
