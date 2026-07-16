from __future__ import annotations

import re


MAX_FUNCTION_SOURCE_BYTES = 1024 * 1024
MAX_INTEGER_MAGNITUDES = 64
_INTEGER = re.compile(
    r"(?<![A-Za-z0-9_.])"
    r"(?P<number>0[xX][0-9A-Fa-f]+|0[bB][01]+|0[0-7]*|[1-9][0-9]*)"
    r"(?:[uU](?:ll|LL|l|L)?|(?:ll|LL|l|L)[uU]?)?"
    r"(?![A-Za-z0-9_.])",
    re.ASCII,
)


def source_integer_magnitudes(source: str | bytes | None) -> tuple[int, ...]:
    if source is None:
        return ()
    if isinstance(source, bytes):
        try:
            text = source.decode("utf-8")
        except UnicodeError as error:
            raise ValueError("semantic function source is not UTF-8") from error
    elif isinstance(source, str):
        text = source
    else:
        raise ValueError("semantic function source must be text")
    if len(text.encode("utf-8")) > MAX_FUNCTION_SOURCE_BYTES:
        raise ValueError("semantic function source is too large")
    visible = _mask_comments_and_literals(text)
    values: list[int] = []
    seen: set[int] = set()
    for match in _INTEGER.finditer(visible):
        value = _parse_magnitude(match.group("number"))
        if value not in seen:
            seen.add(value)
            values.append(value)
        if len(values) == MAX_INTEGER_MAGNITUDES:
            break
    return tuple(values)


def _parse_magnitude(value: str) -> int:
    lowered = value.lower()
    if lowered.startswith("0x"):
        return int(lowered[2:], 16)
    if lowered.startswith("0b"):
        return int(lowered[2:], 2)
    if len(lowered) > 1 and lowered.startswith("0"):
        return int(lowered[1:] or "0", 8)
    return int(lowered, 10)


def _mask_comments_and_literals(value: str) -> str:
    output = list(value)
    index = 0
    while index < len(value):
        if value.startswith("//", index):
            end = value.find("\n", index + 2)
            end = len(value) if end < 0 else end
            _mask(output, index, end)
            index = end
        elif value.startswith("/*", index):
            end = value.find("*/", index + 2)
            end = len(value) if end < 0 else end + 2
            _mask(output, index, end)
            index = end
        elif value[index] in {'"', "'"}:
            index = _mask_quoted(value, output, index, value[index])
        else:
            index += 1
    return "".join(output)


def _mask_quoted(value: str, output: list[str], start: int, quote: str) -> int:
    index = start + 1
    while index < len(value):
        if value[index] == "\\":
            index += 2
            continue
        if value[index] == quote:
            index += 1
            break
        index += 1
    _mask(output, start, min(index, len(value)))
    return min(index, len(value))


def _mask(output: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if output[index] not in "\r\n":
            output[index] = " "


__all__ = ["source_integer_magnitudes"]
