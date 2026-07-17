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
    "-export-dynamic", "-no-pie", "-nostartfiles", "-pthread", "-pthreads",
    "-r", "-rdynamic", "-s", "-shared", "-static", "-static-libgcc",
    "-static-libstdc++", "/DLL",
}
_FORWARDED_FLAGS = {
    "--as-needed", "--build-id", "--eh-frame-hdr", "--end-group",
    "--export-dynamic", "--fatal-warnings", "--gc-sections",
    "--no-as-needed", "--no-export-dynamic", "--no-gc-sections",
    "--no-undefined", "--no-whole-archive", "--start-group",
    "--strip-all", "--warn-common", "--whole-archive", "-Bdynamic",
    "-Bstatic", "-E", "-S", "-s",
}
_RPATH_OPTIONS = {"-rpath", "--rpath"}
_Z_KEYWORDS = {
    "combreloc", "defs", "execstack", "global", "initfirst", "interpose",
    "lazy", "muldefs", "nocombreloc", "nocopyreloc", "nodefaultlib",
    "nodelete", "nodlopen", "nodump", "noexecstack", "norelro", "now",
    "origin", "pack-relative-relocs", "relro", "separate-code", "text",
    "notext",
}
_LIBRARY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}$")
_ENTRY_NAME = re.compile(
    r"^(?:0x[0-9A-Fa-f]+|[0-9]+|[A-Za-z_.$][A-Za-z0-9_.$@-]{0,254})$"
)
_EMULATION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}$")
_Z_ASSIGNMENT = re.compile(
    r"^(?:common-page-size|max-page-size|stack-size)="
    r"(?:0x[0-9A-Fa-f]+|[1-9][0-9]*)$"
)


def normalize_system_link_argument(
    repo_root: Path, base: Path, value: str
) -> str | None:
    if value in _FIXED_LINK_FLAGS or _is_library_selector(value):
        return _safe(value)
    if value.startswith("-Wl"):
        return (
            _normalize_linker_driver_argument(repo_root, base, value)
            if value.startswith("-Wl,") else None
        )
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
    parts = value[4:].split(",")
    if not parts or any(not part for part in parts):
        return None
    if all(part in _FORWARDED_FLAGS for part in parts):
        return _safe(value)
    if len(parts) == 1:
        return _normalize_single_forwarded_argument(repo_root, base, parts[0])
    if len(parts) != 2:
        return None
    option, argument = parts
    if option in _RPATH_OPTIONS:
        normalized = _normalize_path_list(repo_root, base, argument)
        return _safe(f"-Wl,{option},{normalized}") if normalized else None
    if option == "-z" and _valid_z_argument(argument):
        return _safe(value)
    if option in {"-soname", "--soname"} and _LIBRARY_NAME.fullmatch(argument):
        return _safe(value)
    if option in {"-e", "--entry"} and _ENTRY_NAME.fullmatch(argument):
        return _safe(value)
    if option in {"-m", "--emulation"} and _EMULATION_NAME.fullmatch(argument):
        return _safe(value)
    return None


def _normalize_single_forwarded_argument(
    repo_root: Path, base: Path, argument: str,
) -> str | None:
    if _is_library_selector(argument):
        return _safe(f"-Wl,{argument}")
    if argument.startswith(("-rpath=", "--rpath=")):
        option, path = argument.split("=", 1)
        normalized = _normalize_path_list(repo_root, base, path)
        return _safe(f"-Wl,{option}={normalized}") if normalized else None
    if argument.startswith("--build-id="):
        style = argument.split("=", 1)[1]
        if style in {"md5", "none", "sha1", "uuid"} or re.fullmatch(
            r"0x[0-9A-Fa-f]+", style,
        ):
            return _safe(f"-Wl,{argument}")
    if argument.startswith("--hash-style=") and argument.split("=", 1)[1] in {
        "both", "gnu", "sysv",
    }:
        return _safe(f"-Wl,{argument}")
    return None


def _valid_z_argument(value: str) -> bool:
    return value in _Z_KEYWORDS or _Z_ASSIGNMENT.fullmatch(value) is not None


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
        if _bounded_origin_path(item):
            result.append(item)
            continue
        if item.startswith(("$", "${")):
            return None
        if _is_absolute(item):
            normalized = _normalize_repository_path(repo_root, base, item)
            if normalized is None:
                return None
            result.append(normalized)
            continue
        if "\\" in item or ".." in PurePosixPath(item).parts:
            return None
        if _normalize_repository_path(repo_root, base, item) is None:
            return None
        result.append(item)
    if not result:
        return None
    return ":".join(result) + (":" if trailing_separator else "")


def _bounded_origin_path(value: str) -> bool:
    for origin in ("$ORIGIN", "${ORIGIN}"):
        if value == origin:
            return True
        if value.startswith(origin + "/"):
            suffix = value[len(origin) + 1:]
            return (
                bool(suffix)
                and "\\" not in suffix
                and ".." not in PurePosixPath(suffix).parts
            )
    return False


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
