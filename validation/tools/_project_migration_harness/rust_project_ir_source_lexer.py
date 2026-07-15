from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


def rust_tokens(source: str) -> list[Token]:
    result: list[Token] = []
    index = 0
    while index < len(source):
        if source[index].isspace():
            index += 1
            continue
        if source.startswith("//", index):
            index = source.find("\n", index)
            index = len(source) if index < 0 else index + 1
            continue
        if source.startswith("/*", index):
            index = _block_comment_end(source, index)
            continue
        literal = _literal_end(source, index)
        if literal is not None:
            result.append(Token(source[index:literal], index, literal))
            index = literal
            continue
        if identifier_start(source[index]):
            end = index + 1
            while end < len(source) and identifier_continue(source[end]):
                end += 1
            result.append(Token(source[index:end], index, end))
            index = end
            continue
        if not source[index].isascii():
            raise ValueError("unsupported Rust identifier")
        pair = source[index:index + 2]
        token = pair if pair in {
            "::", "->", "=>", "..", "<=", ">=", "==", "!=", "&&", "||",
        } else source[index]
        result.append(Token(token, index, index + len(token)))
        index += len(token)
    return result


def require_balanced(tokens: list[Token]) -> None:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    for token in tokens:
        if token.text in pairs:
            stack.append(pairs[token.text])
        elif token.text in pairs.values():
            if not stack or stack.pop() != token.text:
                raise ValueError("unbalanced Rust tokens")
    if stack:
        raise ValueError("unbalanced Rust tokens")


def after_balanced(
    tokens: list[Token], index: int, opening: str, closing: str,
) -> int:
    if tokens[index].text != opening:
        raise ValueError("invalid balanced token start")
    depth = 0
    for position in range(index, len(tokens)):
        if tokens[position].text == opening:
            depth += 1
        elif tokens[position].text == closing:
            depth -= 1
            if depth == 0:
                return position + 1
    raise ValueError("unbalanced Rust tokens")


def identifier(value: str) -> bool:
    return bool(value) and identifier_start(value[0]) and all(
        identifier_continue(char) for char in value[1:]
    )


def identifier_start(value: str) -> bool:
    return value.isascii() and (value.isalpha() or value == "_")


def identifier_continue(value: str) -> bool:
    return identifier_start(value) or (value.isascii() and value.isdigit())


def _block_comment_end(source: str, start: int) -> int:
    depth = 1
    index = start + 2
    while index < len(source) and depth:
        if source.startswith("/*", index):
            depth += 1
            index += 2
        elif source.startswith("*/", index):
            depth -= 1
            index += 2
        else:
            index += 1
    if depth:
        raise ValueError("unterminated Rust comment")
    return index


def _literal_end(source: str, index: int) -> int | None:
    prefix = index
    if source.startswith(("br", "cr"), index):
        prefix += 1
    if prefix < len(source) and source[prefix] == "r":
        cursor = prefix + 1
        while cursor < len(source) and source[cursor] == "#":
            cursor += 1
        if cursor < len(source) and source[cursor] == '"':
            closing = '"' + "#" * (cursor - prefix - 1)
            found = source.find(closing, cursor + 1)
            if found < 0:
                raise ValueError("unterminated Rust raw string")
            return found + len(closing)
    quote_index = index + 1 if source[index:index + 1] in {"b", "c"} else index
    if quote_index >= len(source) or source[quote_index] not in {'"', "'"}:
        return None
    if source[quote_index] == "'" and quote_index == index:
        if (
            index + 2 < len(source)
            and identifier_start(source[index + 1])
            and source[index + 2] != "'"
        ):
            return None
    quote = source[quote_index]
    cursor = quote_index + 1
    while cursor < len(source):
        if source[cursor] == "\\":
            cursor += 2
        elif source[cursor] == quote:
            return cursor + 1
        elif source[cursor] == "\n" and quote == '"':
            raise ValueError("unterminated Rust string")
        else:
            cursor += 1
    raise ValueError("unterminated Rust literal")


__all__ = [
    "Token", "after_balanced", "identifier", "require_balanced", "rust_tokens",
]
