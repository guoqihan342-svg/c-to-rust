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
_LIBRARY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}$")


def normalize_system_link_argument(
    repo_root: Path, base: Path, value: str
) -> str | None:
    if value in _FIXED_LINK_FLAGS or _is_library_selector(value):
        return _safe(value)
    if value.startswith("-Wl,"):
        return _normalize_linker_driver_argument(repo_root, base, value)
    if _DRIVER_FLAG.match(value) and not _contains_absolute_path(value):
        return _safe(safe_semantic_flag(value))
    return None


def _is_library_selector(value: str) -> bool:
    if value.startswith("-l:"):
        name = value[3:]
    elif value.startswith("-l"):
        name = value[2:]
    elif value.upper().startswith("/DEFAULTLIB:"):
        name = value[len("/DEFAULTLIB:"):]
    else:
        return False
    return _LIBRARY_NAME.fullmatch(name) is not None


def contains_external_link_option_path(value: str) -> bool:
    parts = [part for part in re.split(r"[,=]", value) if part]
    if value.startswith("-l") and len(value) > 2:
        parts.append(value[3:] if value.startswith("-l:") else value[2:])
    elif value.upper().startswith("/DEFAULTLIB:"):
        parts.append(value[len("/DEFAULTLIB:"):])
    return any(_contains_absolute_path(part) for part in parts)


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
    return any(
        _has_absolute_fragment(part)
        for part in re.split(r"[,=]", value) if part
    )


def _has_absolute_fragment(value: str) -> bool:
    candidates = [value]
    if value.startswith("@"):
        candidates.append(value[1:])
    for separator in ("/", "\\"):
        position = value.find(separator)
        if position > 0:
            candidates.append(value[position:])
    drive = re.search(r"[A-Za-z]:[\\/]", value)
    if drive:
        candidates.append(value[drive.start():])
    return any(_is_absolute(candidate) for candidate in candidates)


def _is_absolute(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


__all__ = [
    "contains_external_link_option_path", "normalize_system_link_argument",
]
