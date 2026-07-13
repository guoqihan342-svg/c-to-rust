from __future__ import annotations

import re

from .c_index_lexical import mask_non_code


IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TAGGED_TYPE = re.compile(r"\b(?:struct|union|enum)\s+([A-Za-z_][A-Za-z0-9_]*)")
_KEYWORDS = frozenset({
    "auto", "break", "case", "char", "const", "continue", "default",
    "do", "double", "else", "enum", "extern", "float", "for", "goto",
    "if", "inline", "int", "long", "register", "restrict", "return",
    "short", "signed", "sizeof", "static", "struct", "switch", "typedef",
    "union", "unsigned", "void", "volatile", "while", "_Alignas",
    "_Alignof", "_Atomic", "_Bool", "_Complex", "_Generic",
    "_Imaginary", "_Noreturn", "_Static_assert", "_Thread_local",
})


def identifiers(value: str) -> set[str]:
    return {
        token for token in IDENTIFIER.findall(value)
        if token not in _KEYWORDS and (len(token) >= 2 or token.isupper())
    }


def semantic_identifiers(
    value: str, *, declaration_context: bool
) -> set[str]:
    code, _issues = mask_non_code(value)
    result = set(_TAGGED_TYPE.findall(code))
    for token in IDENTIFIER.findall(code):
        if token in _KEYWORDS:
            continue
        if (
            (len(token) >= 2 and token.upper() == token)
            or token.endswith("_t")
            or token[:1].isupper()
            or (
                declaration_context
                and len(token) >= 8 and token.count("_") >= 2
            )
        ):
            result.add(token)
    return result


__all__ = ["IDENTIFIER", "identifiers", "semantic_identifiers"]
