from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_FLAG = re.compile(
    r"(?:-std=(?:c|gnu)(?:89|90|99|11|17|18|2x|23)|-m(?:32|64)|"
    r"-O(?:0|1|2|3|s|g)|-f(?:short-enums|signed-char|unsigned-char|wrapv|"
    r"no-strict-aliasing|PIC|pic))\Z",
    re.ASCII,
)
_TYPE_MAP = {
    "signed char": ("i8", True), "int8_t": ("i8", True),
    "unsigned char": ("u8", False), "uint8_t": ("u8", False),
    "short": ("i16", True), "short int": ("i16", True),
    "signed short": ("i16", True), "signed short int": ("i16", True),
    "int16_t": ("i16", True),
    "unsigned short": ("u16", False), "unsigned short int": ("u16", False),
    "uint16_t": ("u16", False),
    "int": ("i32", True), "signed": ("i32", True),
    "signed int": ("i32", True), "int32_t": ("i32", True),
    "unsigned": ("u32", False), "unsigned int": ("u32", False),
    "uint32_t": ("u32", False),
    "long long": ("i64", True), "long long int": ("i64", True),
    "signed long long": ("i64", True), "signed long long int": ("i64", True),
    "int64_t": ("i64", True),
    "unsigned long long": ("u64", False),
    "unsigned long long int": ("u64", False), "uint64_t": ("u64", False),
}


class SemanticBackendError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ScalarType:
    c_name: str
    rust_name: str
    signed: bool


@dataclass(frozen=True)
class ScalarFunction:
    symbol: str
    result: ScalarType
    parameters: tuple[ScalarType, ...]


def parse_scalar_function(symbol: str, source: str) -> ScalarFunction:
    clean = re.sub(r"/\*.*?\*/|//[^\r\n]*", " ", source, flags=re.DOTALL)
    prefix = clean.split("{", 1)[0].strip()
    match = re.fullmatch(
        rf"(.+?)\b{re.escape(symbol)}\s*\(([^()]*)\)\s*", prefix,
        re.DOTALL,
    )
    if match is None:
        raise SemanticBackendError("semantic_c_signature_unsupported")
    result = _scalar_type(match.group(1), declaration=True)
    raw_parameters = match.group(2).strip()
    if not raw_parameters or raw_parameters == "void":
        parameters: tuple[ScalarType, ...] = ()
    else:
        values = [item.strip() for item in raw_parameters.split(",")]
        if len(values) > 4:
            raise SemanticBackendError("semantic_c_signature_unsupported")
        parameters = tuple(
            _scalar_type(item, declaration=False) for item in values
        )
    return ScalarFunction(symbol, result, parameters)


def compile_arguments(
    facts: list[dict[str, Any]], unit_id: str,
) -> tuple[str, ...]:
    unit = _single_fact(facts, "compile_unit", unit_id)
    if unit.get("language") != "c" or unit.get("redacted_define_count") != 0:
        raise SemanticBackendError("semantic_compile_context_unsupported")
    values = []
    flags = sorted(
        (
            fact["payload"] for fact in facts
            if fact["kind"] == "compile_semantic_flag"
            and fact["payload"].get("unit_id") == unit_id
        ),
        key=lambda item: int(item.get("index", -1)),
    )
    for item in flags:
        flag = item.get("value")
        if not isinstance(flag, str) or _FLAG.fullmatch(flag) is None:
            raise SemanticBackendError("semantic_compile_flag_unsupported")
        values.append(flag)
    for fact in facts:
        payload = fact["payload"]
        if payload.get("unit_id") != unit_id:
            continue
        if fact["kind"] == "compile_define":
            name, assigned = payload.get("name"), payload.get("value")
            if (
                not valid_identifier(name) or not isinstance(assigned, str)
                or len(assigned) > 512
            ):
                raise SemanticBackendError("semantic_compile_define_invalid")
            values.append(f"-D{name}={assigned}")
        elif fact["kind"] == "compile_include":
            if (
                payload.get("scope") != "repository"
                or payload.get("kind") not in {"user", "quote", "system", "after"}
            ):
                raise SemanticBackendError("semantic_compile_include_unsupported")
            path = payload.get("path")
            if not isinstance(path, str) or not path or "\\" in path or ".." in path.split("/"):
                raise SemanticBackendError("semantic_compile_include_invalid")
            values.append(f"-I/workspace/csrc/{path}")
    return tuple(values)


def valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _scalar_type(value: str, *, declaration: bool) -> ScalarType:
    tokens = value.replace("\n", " ").split()
    tokens = [
        item for item in tokens
        if item not in {
            "static", "inline", "extern", "const", "volatile", "register",
        }
    ]
    if not declaration:
        if len(tokens) < 2 or not valid_identifier(tokens[-1]):
            raise SemanticBackendError("semantic_c_signature_unsupported")
        tokens.pop()
    normalized = " ".join(tokens)
    mapped = _TYPE_MAP.get(normalized)
    if mapped is None or any(char in normalized for char in "*[]()"):
        raise SemanticBackendError("semantic_c_signature_unsupported")
    return ScalarType(normalized, mapped[0], mapped[1])


def _single_fact(
    facts: list[dict[str, Any]], kind: str, unit_id: str,
) -> dict[str, Any]:
    matches = [
        fact["payload"] for fact in facts
        if fact["kind"] == kind and fact["payload"].get("unit_id") == unit_id
    ]
    if len(matches) != 1:
        raise SemanticBackendError(f"semantic_{kind}_fact_invalid")
    return matches[0]


__all__ = [
    "ScalarFunction", "ScalarType", "SemanticBackendError",
    "compile_arguments", "parse_scalar_function", "valid_identifier",
]
