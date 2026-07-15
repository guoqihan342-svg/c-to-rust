from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any

from .build_facts import is_linklike
from .closure_paths import bind_repository_artifact, path_error_blocker


LINK_INPUT_SUFFIXES = {
    ".a", ".dll", ".dylib", ".lib", ".lo", ".o", ".obj", ".so",
}
_VERSIONED_SHARED_LIBRARY = re.compile(r"\.so(?:\.[0-9]+)+$", re.IGNORECASE)


def bind_positional_link_input(
    root: Path,
    base: Path,
    value: str,
    blockers: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None]:
    if not _looks_like_path(value):
        candidate = base / value
        try:
            if not candidate.is_file() and not is_linklike(candidate):
                return False, None
        except (OSError, ValueError):
            return False, None
    try:
        return True, bind_repository_artifact(root, value, base=base, kind="file")
    except (OSError, ValueError) as error:
        blockers.append(path_error_blocker(error, role="link_input", path=value))
        return True, None


def _looks_like_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    suffix = PurePosixPath(normalized).suffix.lower()
    return (
        suffix in LINK_INPUT_SUFFIXES
        or _VERSIONED_SHARED_LIBRARY.search(PurePosixPath(normalized).name) is not None
        or "/" in value
        or "\\" in value
        or value.startswith(".")
        or PureWindowsPath(value).is_absolute()
    )


__all__ = ["bind_positional_link_input"]
