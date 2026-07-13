from __future__ import annotations

import re
from typing import Any


IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
WORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline",
    "int", "long", "register", "restrict", "return", "short", "signed", "sizeof",
    "static", "struct", "switch", "typedef", "union", "unsigned", "void", "volatile",
    "while", "_Alignas", "_Alignof", "_Atomic", "_Bool", "_Complex", "_Generic",
    "_Imaginary", "_Noreturn", "_Static_assert", "_Thread_local",
}
DECORATORS = {"__attribute__", "__declspec", "asm", "__asm", "__asm__", "_Alignas"}


def mask_non_code(text: str) -> tuple[str, list[tuple[str, int]]]:
    output = list(text)
    issues: list[tuple[str, int]] = []
    function_macros: dict[str, int] = {}
    state = "code"
    state_start = index = line_start = 0
    while index < len(text):
        char, pair = text[index], text[index:index + 2]
        if state == "code":
            if char == "#" and not text[line_start:index].strip():
                directive_end = _logical_line_end(text, index)
                directive = text[index:directive_end]
                _classify_directive(directive, index, issues, function_macros)
                state, state_start = "preprocessor", index
            elif pair == "//":
                state, state_start = "line_comment", index
            elif pair == "/*":
                state, state_start = "block_comment", index
            elif char in {'"', "'"}:
                state, state_start = ("string" if char == '"' else "character"), index
            elif char == "\\" and index + 1 < len(text) and text[index + 1] in "\r\n":
                issues.append(("line_splice_outside_directive", index))
                index += 1
                continue
            else:
                if char == "\n":
                    line_start = index + 1
                index += 1
                continue
        if state in {"preprocessor", "line_comment"} and char == "\n":
            output[index] = "\n"
            if continued(text, index):
                line_start = index + 1
            else:
                state, line_start = "code", index + 1
            index += 1
            continue
        if state == "block_comment" and pair == "*/":
            output[index:index + 2] = [" ", " "]
            state, index = "code", index + 2
            continue
        if state in {"string", "character"} and char == "\\":
            output[index] = " "
            if index + 1 < len(text):
                output[index + 1] = "\n" if text[index + 1] == "\n" else " "
            index += 2
            continue
        quote = '"' if state == "string" else "'"
        if state in {"string", "character"} and char == quote and index != state_start:
            output[index] = " "
            state, index = "code", index + 1
            continue
        output[index] = "\n" if char == "\n" else " "
        if char == "\n":
            line_start = index + 1
        index += 1
    if state in {"block_comment", "string", "character"}:
        issues.append((f"unterminated_{state}", state_start))
    masked = "".join(output)
    for name, offset in function_macros.items():
        if re.search(rf"\b{re.escape(name)}\s*\(", masked):
            issues.append(("function_like_macro_call_unsupported", offset))
    return masked, sorted(set(issues), key=lambda item: (item[1], item[0]))


def _classify_directive(
    directive: str,
    offset: int,
    issues: list[tuple[str, int]],
    function_macros: dict[str, int],
) -> None:
    normalized = directive.replace("\\\r\n", " ").replace("\\\n", " ")
    match = re.match(r"\s*#\s*([A-Za-z_]\w*)\b(.*)", normalized, re.DOTALL)
    if match is None:
        issues.append(("preprocessor_directive_invalid", offset))
        return
    directive_name, body = match.group(1), match.group(2)
    if directive_name in {"if", "ifdef", "ifndef", "elif", "else", "endif"}:
        issues.append(("conditional_preprocessor_unsupported", offset))
    if directive_name == "define":
        macro = re.match(r"\s*([A-Za-z_]\w*)\(", body)
        if macro is not None:
            function_macros[macro.group(1)] = offset


def _logical_line_end(text: str, start: int) -> int:
    index = start
    while True:
        newline = text.find("\n", index)
        if newline < 0:
            return len(text)
        if not continued(text, newline):
            return newline
        index = newline + 1


def continued(text: str, newline: int) -> bool:
    index = newline - 1 - int(newline > 0 and text[newline - 1] == "\r")
    count = 0
    while index >= 0 and text[index] == "\\":
        count += 1
        index -= 1
    return count % 2 == 1


def matching(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def function_name(header: str) -> str | None:
    candidates: list[str] = []
    depth = 0
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*|[()=]", header):
        token = match.group()
        if token == "=" and depth == 0:
            return None
        if token == "(":
            found = list(IDENT.finditer(header[:match.start()]))
            if depth == 0 and found and found[-1].group() not in DECORATORS:
                candidates.append(found[-1].group())
            depth += 1
        elif token == ")":
            depth -= 1
            if depth < 0:
                return None
    return candidates[-1] if depth == 0 and candidates else None


def global_candidates(statement: str, start: int, end: int) -> list[dict[str, Any]]:
    declaration_start = start + len(statement) - len(statement.lstrip())
    clean = statement.strip().rstrip(";")
    if not clean or re.search(r"\b(?:typedef|_Static_assert)\b", clean):
        return []
    if re.fullmatch(r"\s*(?:struct|union|enum)\s+[A-Za-z_]\w*\s*(?:\{.*\})?\s*", clean, re.DOTALL):
        return []
    pointer = re.search(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", clean)
    if pointer is None and "=" not in clean and re.search(r"\b[A-Za-z_]\w*\s*\(", clean):
        return []
    flat = re.sub(r"\{[^{}]*\}", " ", clean)
    result: list[dict[str, Any]] = []
    for part in split_top_level(flat, ","):
        fp = re.search(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", part)
        declarator = re.sub(r"\[[^\]]*\]", " ", part.split("=", 1)[0])
        identifiers = [item for item in IDENT.findall(declarator) if item not in WORDS]
        name = fp.group(1) if fp else (identifiers[-1] if identifiers else None)
        if name:
            linkage = (
                "internal" if re.search(r"\bstatic\b", clean)
                else "external_declaration"
                if re.search(r"\bextern\b", clean) and "=" not in clean
                else "external"
            )
            result.append({
                "symbol": name,
                "linkage": linkage,
                "start": declaration_start,
                "end": end,
            })
    return result


def split_top_level(text: str, delimiter: str) -> list[str]:
    result: list[str] = []
    depth = last = 0
    for index, char in enumerate(text):
        depth += int(char in "([")
        depth -= int(char in ")]")
        if char == delimiter and depth == 0:
            result.append(text[last:index])
            last = index + 1
    result.append(text[last:])
    return result


__all__ = [
    "IDENT", "WORDS", "function_name", "global_candidates", "mask_non_code",
    "matching", "split_top_level",
]
