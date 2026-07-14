from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
from typing import Any, Callable

from .c_toolchain_files import hash_stable_file
from .c_toolchain_profile import (
    COMPETITION_PROFILE_PATH, MAX_PROFILE_BYTES, competition_profile_binding,
    reopen_profile_binding, validate_profile_binding,
)


MAX_TOOL_BYTES = 512 * 1024 * 1024
MAX_TOOL_REQUESTS = 128
MAX_TOOL_RECORDS = 128
TOOL_ROLES = (
    "archiver", "compiler-driver", "compiler-wrapper", "linker",
    "linker-driver", "ranlib",
)
ENVIRONMENT_ALLOWLIST = (
    "AR", "CC", "CLANG_PATH", "COMPILER_PATH", "CPATH", "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH", "DISTCC_HOSTS", "GCC_EXEC_PREFIX", "ICECC_VERSION",
    "INCLUDE", "LANG", "LC_ALL", "LIB", "LIBPATH", "LIBRARY_PATH",
    "MACOSX_DEPLOYMENT_TARGET", "PATH", "PATHEXT", "SDKROOT", "SystemRoot",
    "TMP", "TMPDIR", "TEMP", "WINDIR", "WSL_DISTRO_NAME", "WSL_INTEROP",
)

_SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9_+.-]{0,127}\Z", re.ASCII)
_WRAPPERS = {"ccache", "sccache", "distcc", "icecc"}
_MSVC = {"cl": "msvc-compiler", "link": "msvc-linker", "lib": "msvc-archiver"}
_CLANG = re.compile(r"(?:(?:[a-z0-9_+.]+-)+)?clang(?:\+\+)?(?:-[0-9]+)?\Z")
_CLANG_CL = re.compile(r"(?:(?:[a-z0-9_+.]+-)+)?clang-cl(?:-[0-9]+)?\Z")
_GNU = re.compile(
    r"(?:(?:[a-z0-9_+.]+-)+)?(?:gcc|g\+\+|cc|c\+\+)(?:-[0-9.]+)?\Z"
)
_INTEL = re.compile(r"(?:icc|icx|icl)(?:-[0-9.]+)?\Z")
_LINKER = re.compile(
    r"(?:(?:[a-z0-9_+.]+-)+)?(?:ld(?:\.(?:bfd|gold|lld))?|gold|mold|lld|lld-link|wasm-ld)\Z"
)
_ARCHIVER = re.compile(
    r"(?:(?:[a-z0-9_+.]+-)+)?(?:ar|gcc-ar|llvm-ar)(?:-[0-9.]+)?\Z"
)
_RANLIB = re.compile(
    r"(?:(?:[a-z0-9_+.]+-)+)?(?:ranlib|gcc-ranlib|llvm-ranlib)(?:-[0-9.]+)?\Z"
)
_LLVM_MULTICALL = re.compile(
    r"(?P<prefix>(?:(?:[a-z0-9_+.]+-)+)?)llvm-(?P<mode>ar|ranlib)"
    r"(?:-[0-9.]+)?\Z"
)

Resolver = Callable[..., str | os.PathLike[str] | None]


@dataclass(frozen=True, slots=True)
class HostToolBinding:
    token: str
    roles: tuple[str, ...]
    family: str
    basename: str
    resolved_path: str
    resolution_mode: str
    binary: dict[str, Any]


class HostToolBindingError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_requests(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError("c_toolchain_requests_invalid")
    if len(value) > MAX_TOOL_REQUESTS:
        raise ValueError("c_toolchain_requests_limit_exceeded")
    requests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"token", "roles"}:
            raise ValueError("c_toolchain_request_fields_invalid")
        token = _token(item.get("token"))
        roles = item.get("roles")
        if (
            not isinstance(roles, list) or not roles
            or any(type(role) is not str or role not in TOOL_ROLES for role in roles)
        ):
            raise ValueError("c_toolchain_request_roles_invalid")
        if roles != sorted(set(roles)):
            raise ValueError("c_toolchain_request_roles_invalid")
        family, _ = classify_tool_basename(_basename(token))
        validate_role_family(roles, family)
        if token in seen:
            raise ValueError("c_toolchain_request_token_duplicate")
        seen.add(token)
        requests.append({"token": token, "roles": list(roles)})
    return sorted(requests, key=lambda item: item["token"])


def resolve_host_tool(
    token: str, roles: Sequence[str], *, environment: Mapping[str, str],
    resolver: Resolver | None = None,
) -> HostToolBinding:
    token = _token(token)
    requested_family, requested_basename = classify_tool_basename(_basename(token))
    validate_role_family(roles, requested_family)
    mode = "absolute" if _is_absolute(token) else "path-search"
    if mode == "path-search" and ("/" in token or "\\" in token):
        raise HostToolBindingError("relative_tool_path_rejected")
    try:
        value = (resolver or default_resolver)(token, environment=environment)
    except (OSError, TypeError, ValueError) as error:
        raise HostToolBindingError("tool_resolution_failed") from error
    if value is None:
        raise HostToolBindingError("tool_unresolved")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise HostToolBindingError("resolved_tool_not_absolute")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise HostToolBindingError("resolved_tool_unavailable") from error
    if not resolved.is_file() or resolved.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        raise HostToolBindingError("resolved_tool_not_executable_file")
    try:
        resolved_family, resolved_basename = classify_tool_basename(
            _basename(resolved.name)
        )
    except ValueError as error:
        raise HostToolBindingError("resolved_tool_basename_unsupported") from error
    if not resolved_tool_family_compatible(
        requested_family,
        requested_basename,
        resolved_family,
        resolved_basename,
    ):
        raise HostToolBindingError("resolved_tool_family_mismatch")
    validate_role_family(roles, requested_family)
    return HostToolBinding(
        token,
        tuple(roles),
        requested_family,
        requested_basename,
        str(resolved),
        mode,
        hash_stable_file(resolved, executable=True, limit=MAX_TOOL_BYTES),
    )


def default_resolver(
    token: str, *, environment: Mapping[str, str],
) -> str | None:
    if _is_absolute(token):
        return token
    return shutil.which(token, path=_environment_value(environment, "PATH") or "")


def classify_tool_basename(value: str) -> tuple[str, str]:
    basename = value.lower()
    if basename.endswith(".exe"):
        basename = basename[:-4]
    if not _SAFE_NAME.fullmatch(basename):
        raise ValueError("c_toolchain_basename_unsupported")
    if basename in _WRAPPERS:
        return "compiler-wrapper", basename
    if basename in _MSVC:
        return _MSVC[basename], basename
    if _CLANG_CL.fullmatch(basename):
        return "clang-cl-compiler", basename
    if _CLANG.fullmatch(basename):
        return "clang-compiler", basename
    if _GNU.fullmatch(basename):
        return "gnu-compiler", basename
    if _INTEL.fullmatch(basename):
        return "intel-compiler", basename
    if _LINKER.fullmatch(basename):
        return "linker", basename
    if _ARCHIVER.fullmatch(basename):
        return "archiver", basename
    if _RANLIB.fullmatch(basename):
        return "ranlib", basename
    raise ValueError("c_toolchain_basename_unsupported")


def resolved_tool_family_compatible(
    requested_family: str,
    requested_basename: str,
    resolved_family: str,
    resolved_basename: str,
) -> bool:
    if requested_family == resolved_family:
        return True
    if requested_family != "ranlib" or resolved_family != "archiver":
        return False
    requested = _LLVM_MULTICALL.fullmatch(requested_basename)
    resolved = _LLVM_MULTICALL.fullmatch(resolved_basename)
    return bool(
        requested
        and resolved
        and requested.group("mode") == "ranlib"
        and resolved.group("mode") == "ar"
        and requested.group("prefix") == resolved.group("prefix")
    )


def validate_role_family(roles: Sequence[str], family: str) -> None:
    allowed = {
        "compiler-wrapper": {"compiler-wrapper"},
        "gnu-compiler": {"compiler-driver", "linker-driver"},
        "clang-compiler": {"compiler-driver", "linker-driver"},
        "clang-cl-compiler": {"compiler-driver", "linker-driver"},
        "intel-compiler": {"compiler-driver", "linker-driver"},
        "msvc-compiler": {"compiler-driver", "linker-driver"},
        "linker": {"linker"}, "msvc-linker": {"linker"},
        "archiver": {"archiver"}, "msvc-archiver": {"archiver"},
        "ranlib": {"ranlib"},
    }[family]
    if not roles or any(role not in allowed for role in roles):
        raise ValueError("c_toolchain_role_family_invalid")


def _token(value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("c_toolchain_token_invalid")
    if len(value.encode("utf-8")) > 4096 or any(char in value for char in "\r\n\x00"):
        raise ValueError("c_toolchain_token_invalid")
    _basename(value)
    return value


def _basename(value: str) -> str:
    windows = PureWindowsPath(value).name
    posix = PurePosixPath(value.replace("\\", "/")).name
    result = windows if len(windows) <= len(posix) else posix
    if not result:
        raise ValueError("c_toolchain_token_invalid")
    return result


def _is_absolute(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _environment_value(value: Mapping[str, str], name: str) -> str | None:
    if name in value:
        return value[name]
    if os.name == "nt":
        folded = name.casefold()
        return next((item for key, item in value.items() if str(key).casefold() == folded), None)
    return None


__all__ = [
    "COMPETITION_PROFILE_PATH", "ENVIRONMENT_ALLOWLIST", "HostToolBinding",
    "HostToolBindingError", "MAX_PROFILE_BYTES", "MAX_TOOL_RECORDS",
    "MAX_TOOL_REQUESTS", "TOOL_ROLES", "classify_tool_basename",
    "competition_profile_binding", "hash_stable_file",
    "reopen_profile_binding", "resolve_host_tool", "resolved_tool_family_compatible",
    "validate_profile_binding", "validate_requests", "validate_role_family",
]
