from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any


MAX_LINKER_SYMBOLS = 8
_LINKER_FAILURE = re.compile(
    r"^linking with `[A-Za-z0-9_.+-]{1,32}` failed: "
    r"exit (?:status|code): [1-9][0-9]*$"
)
_SYMBOL = r"(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)"
_UNDEFINED_LINES = (
    re.compile(rf"^(?:rust-lld|ld\.lld): error: undefined symbol: {_SYMBOL}$"),
    re.compile(rf"^(?:[^\r\n]{{1,512}}: )?undefined reference to [`']{_SYMBOL}['`]$"),
    re.compile(
        rf"^(?:[^\r\n]{{1,512}}: )?error LNK(?:2001|2019): "
        rf"unresolved external symbol {_SYMBOL}(?: referenced in function .{{1,256}})?$"
    ),
)
_CONTEXT_LINES = (
    re.compile(r"^>>> referenced by [^\r\n]{1,1024}$"),
    re.compile(r"^>>>[ \t]{2,}[^\r\n]{1,1024}$"),
    re.compile(r"^>>> did you mean: [A-Za-z_][A-Za-z0-9_]*$"),
    re.compile(r"^[^\r\n]{1,512}: in function [`'][^\r\n]{1,256}['`]:$"),
    re.compile(r"^collect2: error: ld returned [1-9][0-9]* exit status$"),
    re.compile(
        r"^[^\r\n]{1,512} : fatal error LNK1120: "
        r"[1-9][0-9]* unresolved externals?$"
    ),
    re.compile(
        r"^(?:note: )?some arguments are omitted\. "
        r"use `--verbose` to show all linker arguments$"
    ),
)
_UNCLASSIFIED_BLOCKER = "linker-diagnostic-unclassified"


@dataclass(frozen=True, slots=True)
class LinkerDiagnosticParse:
    recognized_parent: bool
    symbols: tuple[str, ...]
    blocker_code: str | None


def parse_rustc_linker_diagnostic(value: Any) -> LinkerDiagnosticParse:
    if not _recognized_parent(value):
        return LinkerDiagnosticParse(False, (), None)
    children = value.get("children")
    if not isinstance(children, list):
        return LinkerDiagnosticParse(True, (), None)
    if len(children) > 32:
        return LinkerDiagnosticParse(True, (), "linker-diagnostic-overflow")
    symbols: list[str] = []
    for child in children:
        if not isinstance(child, Mapping) or child.get("level") != "note":
            return LinkerDiagnosticParse(True, (), _UNCLASSIFIED_BLOCKER)
        message = child.get("message")
        if not isinstance(message, str):
            return LinkerDiagnosticParse(True, (), _UNCLASSIFIED_BLOCKER)
        lines = message.splitlines()
        try:
            message_bytes = len(message.encode("utf-8"))
        except UnicodeError:
            return LinkerDiagnosticParse(True, (), _UNCLASSIFIED_BLOCKER)
        if message_bytes > 32_768 or len(lines) > 128:
            return LinkerDiagnosticParse(True, (), "linker-diagnostic-overflow")
        classified_line = False
        for line in lines:
            normalized = line.strip()
            if not normalized:
                continue
            classified_line = True
            symbol = _undefined_symbol(normalized)
            if symbol is not None and symbol not in symbols:
                symbols.append(symbol)
                if len(symbols) > MAX_LINKER_SYMBOLS:
                    return LinkerDiagnosticParse(
                        True, (), "linker-symbol-overflow",
                    )
                continue
            if symbol is None and not _context_line(normalized):
                return LinkerDiagnosticParse(True, (), _UNCLASSIFIED_BLOCKER)
        if not classified_line:
            return LinkerDiagnosticParse(True, (), _UNCLASSIFIED_BLOCKER)
    return LinkerDiagnosticParse(True, tuple(symbols), None)


def rustc_linker_undefined_symbols(value: Any) -> list[str]:
    parsed = parse_rustc_linker_diagnostic(value)
    return list(parsed.symbols) if parsed.blocker_code is None else []


def _recognized_parent(value: Any) -> bool:
    if (
        not isinstance(value, Mapping)
        or value.get("level") != "error"
        or value.get("code") is not None
        or not isinstance(value.get("message"), str)
        or _LINKER_FAILURE.fullmatch(value["message"]) is None
    ):
        return False
    return True


def _undefined_symbol(line: str) -> str | None:
    for pattern in _UNDEFINED_LINES:
        match = pattern.fullmatch(line)
        if match is not None:
            return str(match.group("symbol"))
    return None


def _context_line(line: str) -> bool:
    return any(pattern.fullmatch(line) is not None for pattern in _CONTEXT_LINES)


__all__ = [
    "LinkerDiagnosticParse", "MAX_LINKER_SYMBOLS",
    "parse_rustc_linker_diagnostic", "rustc_linker_undefined_symbols",
]
