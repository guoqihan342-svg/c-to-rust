from __future__ import annotations

import re
from typing import Mapping


_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_VARIABLE = re.compile(r"[A-Za-z0-9_.-]+")


def expand_ninja(value: str, variables: Mapping[str, str]) -> str:
    current = value
    for _ in range(16):
        output: list[str] = []
        index = 0
        changed = False
        while index < len(current):
            if current[index] != "$":
                output.append(current[index])
                index += 1
                continue
            if index + 1 >= len(current):
                raise ValueError("ninja_dangling_escape")
            next_char = current[index + 1]
            if next_char in {"$", " ", ":"}:
                output.append(next_char)
                index += 2
                continue
            if next_char == "{":
                end = current.find("}", index + 2)
                if end < 0:
                    raise ValueError("ninja_variable_invalid")
                name = current[index + 2:end]
                index = end + 1
            else:
                matched = _VARIABLE.match(current, index + 1)
                if matched is None:
                    raise ValueError("ninja_variable_invalid")
                name = matched.group(0)
                index = matched.end()
            output.append(str(variables.get(name, "")))
            changed = True
        expanded = "".join(output)
        if not changed or expanded == current:
            return expanded
        current = expanded
    raise ValueError("ninja_variable_cycle")


def logical_lines(text: str) -> list[str]:
    result: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = pending + raw
        if line.endswith("$") and not line.endswith("$$"):
            pending = line[:-1]
        else:
            result.append(line)
            pending = ""
    if pending:
        raise ValueError("ninja_continuation_incomplete")
    return result


def parse_assignment(value: str) -> tuple[str, str] | None:
    if "=" not in value:
        return None
    name, content = value.split("=", 1)
    name = name.strip()
    return (name, content.strip()) if _NAME.fullmatch(name) is not None else None


def split_ninja_words(value: str) -> list[str]:
    protected = value.replace("$$", "\0").replace("$ ", "\1").replace("$:", "\2")
    return [
        item.replace("\0", "$").replace("\1", " ").replace("\2", ":")
        for item in protected.split()
    ]


def unescaped_colon(value: str) -> int:
    for index, char in enumerate(value):
        if char == ":" and (index == 0 or value[index - 1] != "$"):
            return index
    return -1


__all__ = [
    "expand_ninja", "logical_lines", "parse_assignment",
    "split_ninja_words", "unescaped_colon",
]
