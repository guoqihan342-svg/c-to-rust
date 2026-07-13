from __future__ import annotations

from pathlib import Path, PurePosixPath

from .build_facts import resolve_repository_path


def link_fact_working_directory(
    repo_root: Path, fact_path: str, fallback: Path
) -> Path:
    """Derive the CMake link-script cwd from its CMakeFiles ancestor."""
    parts = PurePosixPath(fact_path).parts
    indexes = [index for index, part in enumerate(parts) if part == "CMakeFiles"]
    if PurePosixPath(fact_path).name != "link.txt" or not indexes:
        return fallback
    candidate = Path(*parts[: indexes[-1]]) if indexes[-1] else Path(".")
    resolved = resolve_repository_path(repo_root, candidate)
    if not resolved.is_dir():
        raise ValueError("link_fact_working_directory_invalid")
    return resolved


__all__ = ["link_fact_working_directory"]
