from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .build_facts import file_binding, is_linklike


MAX_DIRECTORIES = 4_096
MAX_FILES = 256
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def detect_generated_build_facts(
    repo_root: Path, compile_database_path: Path
) -> dict[str, Any]:
    root = repo_root.resolve()
    scan_root = compile_database_path.resolve().parent
    try:
        scan_root.relative_to(root)
    except ValueError:
        return _report([], [], ["generated_fact_root_external"])
    link_files: list[dict[str, Any]] = []
    metadata_files: list[dict[str, Any]] = []
    blockers: list[str] = []
    directories_seen = 0
    total_bytes = 0
    for current_text, directories, files in os.walk(
        scan_root, topdown=True, followlinks=False
    ):
        directories_seen += 1
        if directories_seen > MAX_DIRECTORIES:
            blockers.append("generated_fact_directory_limit_exceeded")
            directories[:] = []
            break
        current = Path(current_text)
        directories[:] = sorted(
            name for name in directories if not is_linklike(current / name)
        )
        for name in sorted(files):
            role = _fact_role(name)
            if role is None:
                continue
            path = current / name
            if is_linklike(path):
                blockers.append("generated_fact_linked")
                continue
            if len(link_files) + len(metadata_files) >= MAX_FILES:
                blockers.append("generated_fact_file_limit_exceeded")
                directories[:] = []
                break
            try:
                size = path.stat().st_size
                if size > MAX_FILE_BYTES:
                    blockers.append("generated_fact_size_limit_exceeded")
                    continue
                if total_bytes + size > MAX_TOTAL_BYTES:
                    blockers.append("generated_fact_total_size_limit_exceeded")
                    directories[:] = []
                    break
                binding = file_binding(root, path, max_bytes=MAX_FILE_BYTES)
            except (OSError, ValueError):
                blockers.append("generated_fact_unreadable")
                continue
            total_bytes += binding["size_bytes"]
            binding["kind"] = "file"
            (link_files if role == "link" else metadata_files).append(binding)
        if blockers and blockers[-1] in {
            "generated_fact_file_limit_exceeded",
            "generated_fact_total_size_limit_exceeded",
        }:
            break
    return _report(link_files, metadata_files, blockers)


def _fact_role(name: str) -> str | None:
    if name == "link.txt":
        return "link"
    if name in {"build.ninja", "intro-targets.json"}:
        return "metadata"
    return None


def _report(
    link_files: list[dict[str, Any]],
    metadata_files: list[dict[str, Any]],
    blockers: list[str],
) -> dict[str, Any]:
    link_files.sort(key=lambda item: item["path"])
    metadata_files.sort(key=lambda item: item["path"])
    return {
        "status": "blocked" if blockers else (
            "detected" if link_files or metadata_files else "not_detected"
        ),
        "link_command_files": link_files,
        "metadata_files": metadata_files,
        "blockers": sorted(set(blockers)),
        "commands_executed": False,
        "scan_limits": {
            "max_directories": MAX_DIRECTORIES,
            "max_files": MAX_FILES,
            "max_file_bytes": MAX_FILE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
        },
    }


__all__ = ["detect_generated_build_facts"]
