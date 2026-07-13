from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from .build_facts import summarize_path
from .compile_security import safe_semantic_flag
from .ledger_security import assert_no_secrets


_DRIVER_FLAG = re.compile(
    r"^-(?:D|U|O|g|m|f|W|std=|pipe$|pthread$|shared$|static$|pie$|no-pie$)"
)
_FIXED_LINK_FLAGS = {
    "-Bstatic", "-Bdynamic", "-nostdlib", "-nodefaultlibs", "-pie",
    "-pthread", "-rdynamic", "-shared", "-static", "/DLL",
}
_RPATH_OPTIONS = {"-rpath", "--rpath", "-rpath-link", "--rpath-link"}


def normalize_system_link_argument(
    repo_root: Path, base: Path, value: str
) -> str | None:
    if value in _FIXED_LINK_FLAGS or value.startswith(("-l", "/DEFAULTLIB:")):
        return _safe(value)
    if value.startswith("-Wl,"):
        return _normalize_linker_driver_argument(repo_root, base, value)
    if _DRIVER_FLAG.match(value) and not _contains_absolute_path(value):
        return _safe(safe_semantic_flag(value))
    return None


def _normalize_linker_driver_argument(
    repo_root: Path, base: Path, value: str
) -> str | None:
    parts = value.split(",")
    normalized = list(parts)
    index = 1
    while index < len(parts):
        option = parts[index]
        if option in _RPATH_OPTIONS and index + 1 < len(parts):
            bound = _normalize_path_list(repo_root, base, parts[index + 1])
            if bound is None:
                return None
            normalized[index + 1] = bound
            index += 2
            continue
        if _contains_absolute_path(option):
            return None
        index += 1
    return _safe(",".join(normalized))


def _normalize_path_list(repo_root: Path, base: Path, value: str) -> str | None:
    trailing_separator = value.endswith(":")
    windows_value = value[:-1] if trailing_separator else value
    if re.match(r"^[A-Za-z]:[\\/]", windows_value):
        normalized = _normalize_repository_path(repo_root, base, windows_value)
        return normalized + (":" if trailing_separator else "") if normalized else None
    result: list[str] = []
    for item in value.split(":"):
        if not item:
            continue
        if item.startswith(("$ORIGIN", "${ORIGIN}")):
            result.append(item)
            continue
        if _is_absolute(item):
            normalized = _normalize_repository_path(repo_root, base, item)
            if normalized is None:
                return None
            result.append(normalized)
            continue
        if "\\" in item or ".." in PurePosixPath(item).parts:
            return None
        result.append(item)
    if not result:
        return None
    return ":".join(result) + (":" if trailing_separator else "")


def _normalize_repository_path(
    repo_root: Path, base: Path, value: str
) -> str | None:
    summary = summarize_path(value, repo_root, base)
    if summary["scope"] != "repository":
        return None
    suffix = "" if summary["path"] == "." else "/" + summary["path"]
    return "<repository>" + suffix


def _safe(value: str) -> str | None:
    try:
        assert_no_secrets(value, "link_system_argument")
    except ValueError:
        return None
    return value


def _contains_absolute_path(value: str) -> bool:
    return any(_is_absolute(part) for part in re.split(r"[,=]", value) if part)


def _is_absolute(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


__all__ = ["normalize_system_link_argument"]
