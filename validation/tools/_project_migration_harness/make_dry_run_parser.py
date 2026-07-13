from __future__ import annotations
from collections.abc import Mapping
import hashlib
from pathlib import PurePosixPath, PureWindowsPath
import re
import shlex
from typing import Any

from .artifacts import content_sha256
from .compile_security import SUPPORTED_COMPILER


PARSER_NAME = "project-migration-make-dry-run-direct-argv"
PARSER_VERSION = 1
MAX_STDOUT_BYTES = 4 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_COMMANDS = 4_096
_PREFIX = r"(?:(?:[a-z0-9_+.]+-){0,4})?"
_ARCHIVER = re.compile(
    rf"^{_PREFIX}(?:ar|gcc-ar|llvm-ar)(?:-[0-9.]+)?$", re.IGNORECASE
)
_RANLIB = re.compile(
    rf"^{_PREFIX}(?:ranlib|gcc-ranlib|llvm-ranlib)(?:-[0-9.]+)?$",
    re.IGNORECASE,
)
_LINKER = re.compile(
    rf"^{_PREFIX}(?:ld(?:\.lld|\.gold)?|gold|lld|mold)(?:-[0-9.]+)?$",
    re.IGNORECASE,
)
_SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".i", ".ii", ".s", ".asm")
_LINK_SUFFIXES = (".o", ".obj", ".lo", ".a", ".lib", ".so", ".dylib")
_DRIVER_PAIRS = {
    "-B", "-D", "-I", "-L", "-MF", "-MJ", "-MQ", "-MT", "-U",
    "-idirafter", "-imacros", "-include", "-iquote", "-isystem",
    "-isysroot", "-target", "--sysroot", "--target", "-x", "-Xclang",
    "-Xlinker",
}
_DRIVER_PATH_PAIRS = {
    "-B", "-I", "-L", "-MF", "-MJ", "-idirafter", "-imacros",
    "-include", "-iquote", "-isystem", "-isysroot", "--sysroot",
}
_LINKER_PAIRS = {
    "-e", "-L", "-m", "-Map", "-rpath", "-rpath-link", "-soname", "-T",
    "--dynamic-linker", "--entry", "--library-path", "--rpath",
    "--rpath-link", "--script", "--soname", "--version-script",
}
_LINKER_PATH_PAIRS = _LINKER_PAIRS - {"-e", "-m", "--entry", "-soname", "--soname"}
_PATH_PREFIXES = (
    "--sysroot=", "--library-path=", "--script=", "--version-script=",
    "-idirafter", "-imacros", "-include", "-iquote", "-isystem",
    "-isysroot", "-rpath-link=", "-rpath=", "-MF", "-MJ", "-Map=",
    "-B", "-I", "-L", "-T",
)
_SPECIAL = {
    "bash": "shell_command", "cd": "cd", "cmd": "shell_command",
    "command": "shell_command", "configure": "configure", "dash": "shell_command",
    "env": "shell_command", "exec": "shell_command", "libtool": "libtool",
    "powershell": "shell_command", "pwsh": "shell_command", "sh": "shell_command",
    "time": "shell_command", "zsh": "shell_command",
}

class MakeDryRunParseError(ValueError):
    def __init__(self, code: str, line_number: int | None = None) -> None:
        super().__init__(code)
        self.code, self.line_number = code, line_number

def parse_make_dry_run_stdout(stdout: str | bytes) -> dict[str, Any]:
    raw, text = _decode(stdout)
    commands: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.split("\n"), 1):
        line = raw_line.removesuffix("\r").strip()
        if not line:
            continue
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            _fail("line_limit_exceeded", line_number)
        _shell_free(line, line_number)
        try:
            argv = shlex.split(line, posix=True)
        except ValueError as error:
            raise MakeDryRunParseError("make_dry_run_argv_parse_failed", line_number) from error
        commands.append(_record(argv, line_number, len(commands)))
        if len(commands) > MAX_COMMANDS:
            _fail("command_limit_exceeded")
    if not commands:
        _fail("no_direct_commands")
    return {
        "parser": {"name": PARSER_NAME, "version": PARSER_VERSION},
        "raw_stdout": {"encoding": "utf-8", "sha256": hashlib.sha256(raw).hexdigest(),
                       "size_bytes": len(raw)},
        "working_directory": ".",
        "commands": commands,
    }

def validate_make_dry_run_commands(commands: Any) -> list[dict[str, Any]]:
    if not isinstance(commands, list) or not 0 < len(commands) <= MAX_COMMANDS:
        raise ValueError("make dry-run commands are invalid")
    previous = 0
    for ordinal, command in enumerate(commands):
        line = command.get("line_number") if isinstance(command, Mapping) else None
        argv = command.get("argv") if isinstance(command, Mapping) else None
        if (
            isinstance(line, bool) or not isinstance(line, int) or line <= previous
            or not isinstance(argv, list) or dict(command) != _record(argv, line, ordinal)
        ):
            raise ValueError("make dry-run command binding is invalid")
        previous = line
    return [dict(command) for command in commands]

def _decode(stdout: str | bytes) -> tuple[bytes, str]:
    try:
        raw = stdout.encode("utf-8") if isinstance(stdout, str) else stdout
    except UnicodeError as error:
        raise MakeDryRunParseError("make_dry_run_stdout_not_utf8") from error
    if not isinstance(raw, bytes):
        raise TypeError("make dry-run stdout must be str or bytes")
    if len(raw) > MAX_STDOUT_BYTES:
        _fail("stdout_limit_exceeded")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MakeDryRunParseError("make_dry_run_stdout_not_utf8") from error
    if "\x00" in text:
        _fail("shell_control_rejected")
    return raw, text
def _shell_free(line: str, line_number: int) -> None:
    quote: str | None = None
    for index, character in enumerate(line):
        if quote == "'":
            quote = None if character == "'" else quote
        elif quote == '"':
            if character == '"':
                quote = None
            elif character in "$`\\":
                _fail("shell_control_rejected", line_number)
        elif character in "'\"":
            quote = character
        elif character in ";|&<>()`$\\*?[]{}":
            _fail("shell_control_rejected", line_number)
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            _fail("shell_control_rejected", line_number)
    if quote is not None:
        _fail("argv_parse_failed", line_number)
def _record(argv: list[str], line: int, ordinal: int) -> dict[str, Any]:
    if not argv or not all(isinstance(item, str) and item for item in argv):
        _fail("argv_invalid", line)
    raw_tool = argv[0]
    basename = raw_tool.replace("\\", "/").rsplit("/", 1)[-1]
    tool = basename.removesuffix(".exe").lower()
    if tool in _SPECIAL:
        _fail(f"{_SPECIAL[tool]}_rejected", line)
    if re.fullmatch(r"(?:g?make)(?:\[\d+\])?:?", tool):
        _fail("recursive_make_rejected", line)
    if tool in {"autoconf", "automake", "cmake", "meson"}:
        _fail("configure_rejected", line)
    if tool in {"glibtool", "glibtoolize", "libtoolize"}:
        _fail("libtool_rejected", line)
    if raw_tool != basename or "/" in raw_tool or "\\" in raw_tool:
        _fail("tool_path_escape", line)
    _safe_arguments(argv[1:], line)
    if SUPPORTED_COMPILER.fullmatch(tool) and tool not in {"cl", "clang-cl"}:
        kind, inputs, outputs = _compiler(argv, line)
    elif _ARCHIVER.fullmatch(tool):
        kind, inputs, outputs = _archive(argv, line)
    elif _RANLIB.fullmatch(tool):
        kind, inputs, outputs = _ranlib(argv, line)
    elif _LINKER.fullmatch(tool):
        kind, inputs, outputs = _linker(argv, line)
    else:
        _fail("unknown_command", line)
    return {"ordinal": ordinal, "line_number": line, "kind": kind, "tool": tool,
            "argv": list(argv), "argv_sha256": content_sha256(argv),
            "inputs": inputs, "outputs": outputs}
def _scan(
    argv: list[str], line: int, pairs: set[str], path_pairs: set[str]
) -> tuple[list[str], list[str], bool, set[str]]:
    inputs: list[str] = []
    outputs: list[str] = []
    libraries = False
    flags: set[str] = set()
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument in {"-o", "--output"}:
            index += 1
            outputs.append(_required_path(argv, index, line))
        elif argument.startswith("--output="):
            outputs.append(_path(argument.split("=", 1)[1], line))
        elif argument.startswith("-o") and len(argument) > 2:
            outputs.append(_path(argument[2:], line))
        elif argument in pairs:
            flags.add(argument)
            index += 1
            value = _required(argv, index, line)
            if argument in path_pairs:
                _path(value, line)
        elif argument.startswith("-l") and len(argument) > 2:
            libraries = True
        elif argument.startswith("-"):
            flags.add(argument)
            _attached_path(argument, line)
        else:
            inputs.append(_path(argument, line))
        index += 1
    return inputs, outputs, libraries, flags
def _compiler(argv: list[str], line: int) -> tuple[str, list[str], list[str]]:
    inputs, outputs, libraries, flags = _scan(argv, line, _DRIVER_PAIRS, _DRIVER_PATH_PAIRS)
    if len(outputs) != 1:
        _fail("output_ambiguous", line)
    if flags & {"-E", "-S"}:
        _fail("compile_mode_unsupported", line)
    sources = [item for item in inputs if _source(item)]
    objects = [item for item in inputs if _link_input(item)]
    if len(sources) + len(objects) != len(inputs):
        _fail("compiler_input_unsupported", line)
    if "-c" in flags:
        if len(sources) != 1 or objects or libraries or any(
            item.startswith("-Wl,") or item in {"-shared", "-pie", "-rdynamic"}
            for item in flags
        ):
            _fail("compile_link_ambiguous", line)
        return "compile", sources, outputs
    if sources:
        _fail("compile_link_ambiguous", line)
    if not objects and not libraries:
        _fail("link_input_missing", line)
    return "link", objects, outputs
def _archive(argv: list[str], line: int) -> tuple[str, list[str], list[str]]:
    if len(argv) < 3:
        _fail("archive_argv_invalid", line)
    mode = argv[1].removeprefix("-")
    if not mode or any(char not in "DPUcqrsuv" for char in mode) or not set(mode) & {"q", "r", "s"}:
        _fail("archive_mode_unsupported", line)
    archive = _path(argv[2], line)
    members = [_path(item, line) for item in argv[3:]]
    if set(mode) & {"q", "r"} and not members:
        _fail("archive_member_missing", line)
    if any(not _link_input(item) for item in members):
        _fail("archive_member_unsupported", line)
    return "archive", members, [archive]
def _ranlib(argv: list[str], line: int) -> tuple[str, list[str], list[str]]:
    operands = [item for item in argv[1:] if item not in {"-D", "-U"}]
    if len(operands) != 1 or any(item.startswith("-") for item in operands):
        _fail("ranlib_argv_invalid", line)
    archive = _path(operands[0], line)
    return "ranlib", [archive], [archive]
def _linker(argv: list[str], line: int) -> tuple[str, list[str], list[str]]:
    inputs, outputs, libraries, _ = _scan(argv, line, _LINKER_PAIRS, _LINKER_PATH_PAIRS)
    if len(outputs) != 1:
        _fail("output_ambiguous", line)
    if any(_source(item) for item in inputs):
        _fail("compile_link_ambiguous", line)
    if any(not _link_input(item) for item in inputs):
        _fail("link_input_unsupported", line)
    if not inputs and not libraries:
        _fail("link_input_missing", line)
    return "link", inputs, outputs
def _safe_arguments(arguments: list[str], line: int) -> None:
    for argument in arguments:
        if "\\" in argument or argument.startswith("@") or ",@" in argument:
            _fail("path_escape", line)
        if re.search(r"(?:^|[=,:])(?:/|~(?:/|$)|[A-Za-z]:/)", argument):
            _fail("path_escape", line)
        if re.search(r"(?:^|[/=,:])\.\.(?:[/,:]|$)", argument):
            _fail("path_escape", line)
        _attached_path(argument, line)
def _attached_path(argument: str, line: int) -> None:
    for prefix in _PATH_PREFIXES:
        if argument.startswith(prefix) and len(argument) > len(prefix):
            _path(argument[len(prefix):], line)
            return
def _required(argv: list[str], index: int, line: int) -> str:
    if index >= len(argv) or not argv[index]:
        _fail("option_value_missing", line)
    return argv[index]
def _required_path(argv: list[str], index: int, line: int) -> str:
    return _path(_required(argv, index, line), line)
def _path(value: str, line: int) -> str:
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (
        not value or value == "-" or "\\" in value or posix.is_absolute()
        or windows.is_absolute() or windows.drive or ".." in posix.parts
        or (posix.parts and posix.parts[0].startswith("~"))
    ):
        _fail("path_escape", line)
    normalized = posix.as_posix()
    if normalized in {"", "."}:
        _fail("path_escape", line)
    return normalized
def _source(path: str) -> bool:
    return path.lower().endswith(_SOURCE_SUFFIXES)
def _link_input(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith(_LINK_SUFFIXES) or bool(re.search(r"\.so(?:\.\d+)+$", lowered))
def _fail(reason: str, line: int | None = None) -> None:
    raise MakeDryRunParseError(f"make_dry_run_{reason}", line)
__all__ = [
    "MAX_COMMANDS", "MAX_LINE_BYTES", "MAX_STDOUT_BYTES", "MakeDryRunParseError",
    "PARSER_NAME", "PARSER_VERSION", "parse_make_dry_run_stdout",
    "validate_make_dry_run_commands",
]
