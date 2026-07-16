from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Callable

from .candidate_semantic_integer_literals import (
    macro_expression_text,
    parse_c_integer_literal,
)


MAX_EXPRESSION_BYTES = 512
MAX_EXPRESSION_TOKENS = 64
MAX_EXPRESSION_DEPTH = 16
MAX_RESOLVED_MACROS = 128
MAX_INTEGER_BITS = 64
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)
_INTEGER = re.compile(
    r"(?:0[xX][0-9A-Fa-f]+|0[bB][01]+|0[0-7]*|[1-9][0-9]*)"
    r"(?:[uU](?:ll|LL|l|L)?|(?:ll|LL|l|L)[uU]?)?",
    re.ASCII,
)


class MacroExpressionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MacroResolution:
    values: dict[str, int]
    failures: dict[str, str]


@dataclass(frozen=True)
class _IntegerValue:
    value: int
    unary_minus_safe: bool


def resolve_integer_macro_roots(
    definitions: Mapping[str, str], roots: Sequence[str],
) -> MacroResolution:
    cache: dict[str, _IntegerValue] = {}
    states: dict[str, str] = {}
    stack: list[str] = []

    def resolve(name: str) -> _IntegerValue:
        if name in cache:
            return cache[name]
        if states.get(name) == "visiting":
            raise MacroExpressionError("dependency_cycle")
        expression = definitions.get(name)
        if expression is None:
            raise MacroExpressionError("unresolved_symbol")
        if len(cache) + len(stack) >= MAX_RESOLVED_MACROS:
            raise MacroExpressionError("resolution_budget_exceeded")
        states[name] = "visiting"
        stack.append(name)
        try:
            value = _ExpressionParser(expression, resolve).parse()
        except MacroExpressionError:
            states[name] = "failed"
            raise
        finally:
            stack.pop()
        if value.value.bit_length() > MAX_INTEGER_BITS:
            states[name] = "failed"
            raise MacroExpressionError("integer_range_exceeded")
        states[name] = "resolved"
        cache[name] = value
        return value

    values: dict[str, int] = {}
    failures: dict[str, str] = {}
    for root in roots:
        try:
            values[root] = resolve(root).value
        except MacroExpressionError as error:
            failures[root] = error.code
    return MacroResolution(values, failures)


class _ExpressionParser:
    def __init__(
        self, expression: str, resolve: Callable[[str], _IntegerValue],
    ) -> None:
        if len(expression.encode("utf-8")) > MAX_EXPRESSION_BYTES:
            raise MacroExpressionError("replacement_budget_exceeded")
        self.tokens = _tokens(expression)
        self.index = 0
        self.resolve = resolve

    def parse(self) -> _IntegerValue:
        if not self.tokens:
            raise MacroExpressionError("expression_unsupported")
        value = self._unary(0)
        if self.index != len(self.tokens):
            raise MacroExpressionError("expression_unsupported")
        return value

    def _unary(self, depth: int) -> _IntegerValue:
        if depth > MAX_EXPRESSION_DEPTH:
            raise MacroExpressionError("expression_depth_exceeded")
        token = self._peek()
        if token in {"+", "-"}:
            self.index += 1
            value = self._unary(depth + 1)
            if token == "+":
                return value
            if not value.unary_minus_safe:
                raise MacroExpressionError("unsafe_unsigned_unary_minus")
            result = -value.value
            return _IntegerValue(result, abs(result) <= (1 << 63) - 1)
        if token == "(":
            self.index += 1
            value = self._unary(depth + 1)
            if self._peek() != ")":
                raise MacroExpressionError("expression_unsupported")
            self.index += 1
            return value
        if token is None or token == ")":
            raise MacroExpressionError("expression_unsupported")
        self.index += 1
        if _IDENTIFIER.fullmatch(token):
            return self.resolve(token)
        try:
            value = parse_c_integer_literal(token)
        except ValueError as error:
            raise MacroExpressionError("expression_unsupported") from error
        digits = _literal_digits(token)
        unsigned = "u" in token.lower()[len(digits):]
        decimal = not digits.lower().startswith(("0x", "0b", "0")) or digits == "0"
        if decimal and not unsigned and value > (1 << 63) - 1:
            raise MacroExpressionError("integer_range_exceeded")
        safe_bound = (1 << 63) - 1 if decimal else (1 << 31) - 1
        return _IntegerValue(value, not unsigned and value <= safe_bound)

    def _peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None


def _tokens(expression: str) -> tuple[str, ...]:
    visible = macro_expression_text(
        expression.replace("\\\r\n", " ").replace("\\\n", " "),
    )
    result: list[str] = []
    index = 0
    while index < len(visible):
        if visible[index].isspace():
            index += 1
            continue
        matched = _INTEGER.match(visible, index) or _IDENTIFIER.match(visible, index)
        if matched is not None:
            result.append(matched.group())
            index = matched.end()
        elif visible[index] in "()+-":
            result.append(visible[index])
            index += 1
        else:
            raise MacroExpressionError("expression_unsupported")
        if len(result) > MAX_EXPRESSION_TOKENS:
            raise MacroExpressionError("token_budget_exceeded")
    return tuple(result)


def _literal_digits(value: str) -> str:
    matched = re.match(
        r"0[xX][0-9A-Fa-f]+|0[bB][01]+|0[0-7]*|[1-9][0-9]*", value,
    )
    return matched.group() if matched is not None else ""


__all__ = [
    "MacroExpressionError", "MacroResolution", "resolve_integer_macro_roots",
]
