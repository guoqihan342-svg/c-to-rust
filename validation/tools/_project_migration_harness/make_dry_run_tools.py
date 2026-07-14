from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
import re

from .compile_security import SUPPORTED_COMPILER


_PREFIX = r"(?:(?:[a-z0-9_+.]+-){0,4})?"
_ARCHIVER = re.compile(
    rf"^{_PREFIX}(?:ar|gcc-ar|llvm-ar)(?:-[0-9.]+)?$", re.IGNORECASE,
)
_RANLIB = re.compile(
    rf"^{_PREFIX}(?:ranlib|gcc-ranlib|llvm-ranlib)(?:-[0-9.]+)?$",
    re.IGNORECASE,
)
_LINKER = re.compile(
    rf"^{_PREFIX}(?:ld(?:\.lld|\.gold)?|gold|lld|mold)(?:-[0-9.]+)?$",
    re.IGNORECASE,
)
_SPECIAL = {
    "bash": "shell_command", "cd": "cd", "cmd": "shell_command",
    "command": "shell_command", "configure": "configure",
    "dash": "shell_command", "env": "shell_command",
    "exec": "shell_command", "libtool": "libtool",
    "powershell": "shell_command", "pwsh": "shell_command",
    "sh": "shell_command", "time": "shell_command", "zsh": "shell_command",
}


def classify_make_tool(raw_tool: str) -> tuple[str, str]:
    basename = raw_tool.replace("\\", "/").rsplit("/", 1)[-1]
    tool = basename.removesuffix(".exe").lower()
    if tool in _SPECIAL:
        raise ValueError(f"{_SPECIAL[tool]}_rejected")
    if re.fullmatch(r"(?:g?make)(?:\[\d+\])?:?", tool):
        raise ValueError("recursive_make_rejected")
    if tool in {"autoconf", "automake", "cmake", "meson"}:
        raise ValueError("configure_rejected")
    if tool in {"glibtool", "glibtoolize", "libtoolize"}:
        raise ValueError("libtool_rejected")
    has_path = raw_tool != basename or "/" in raw_tool or "\\" in raw_tool
    if has_path and not (
        PurePosixPath(raw_tool).is_absolute()
        or PureWindowsPath(raw_tool).is_absolute()
    ):
        raise ValueError("tool_path_escape")
    if SUPPORTED_COMPILER.fullmatch(tool) and tool not in {"cl", "clang-cl"}:
        kind = "compiler"
    elif _ARCHIVER.fullmatch(tool):
        kind = "archive"
    elif _RANLIB.fullmatch(tool):
        kind = "ranlib"
    elif _LINKER.fullmatch(tool):
        kind = "linker"
    else:
        raise ValueError("unknown_command")
    return kind, raw_tool if raw_tool != tool else tool


__all__ = ["classify_make_tool"]
