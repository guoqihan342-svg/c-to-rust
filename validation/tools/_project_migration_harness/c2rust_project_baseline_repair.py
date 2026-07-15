from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .c2rust_project_baseline_rust_lexer import (
    RustToken, identifier, lex_rust, replace_token_text, significant_indexes,
)
from .c2rust_project_baseline_rust_structure import (
    RustFunction, find_rust_functions, module_static_declarations,
)


@dataclass(frozen=True, slots=True)
class StaticRepairResult:
    source: str
    renamed_statics: tuple[dict[str, Any], ...]
    rewritten_reference_count: int


@dataclass(frozen=True, slots=True)
class MainSignature:
    symbol: str
    parameter_count: int
    returns_value: bool


def add_deref_nullptr_allow(source: str) -> str:
    missing = [
        name for name in (
            "deref_nullptr", "unused_variables", "unreachable_code",
            "unused_must_use",
        )
        if f"allow({name})" not in source
    ]
    if not missing:
        return source
    marker = "".join(f"#![allow({name})]\n" for name in missing)
    if source.startswith("\ufeff"):
        return "\ufeff" + marker + source[1:]
    if source.startswith("#!") and not source.startswith("#!["):
        newline = source.find("\n")
        if newline >= 0:
            return source[:newline + 1] + marker + source[newline + 1:]
    return marker + source


def repair_module_static_parameter_collisions(source: str) -> StaticRepairResult:
    tokens = lex_rust(source)
    significant = significant_indexes(tokens)
    functions = find_rust_functions(tokens, significant)
    declarations = module_static_declarations(tokens, significant)
    parameters = set().union(*(item.parameter_names for item in functions))
    collisions = sorted(set(declarations) & parameters)
    if not collisions:
        return StaticRepairResult(source, (), 0)
    occupied = {token.text for token in tokens if token.is_identifier}
    names = {name: _fresh_static_name(name, occupied) for name in collisions}
    replacements: dict[int, str] = {
        declarations[name]: replacement for name, replacement in names.items()
    }
    body_positions = _body_positions(functions)
    parameter_tokens = set().union(*(item.parameter_tokens for item in functions))
    for function in functions:
        _rewrite_function_references(
            tokens, significant, function, names, replacements,
        )
    for position, token_index in enumerate(significant):
        token = tokens[token_index]
        if token.text not in names or token_index in replacements:
            continue
        if token_index in parameter_tokens or position in body_positions:
            continue
        if _non_static_context(tokens, significant, position):
            continue
        replacements[token_index] = names[token.text]
    renamed = tuple({"from": name, "to": names[name]} for name in collisions)
    return StaticRepairResult(
        replace_token_text(source, tokens, replacements), renamed,
        len(replacements) - len(collisions),
    )


def rename_single_public_main(
    source: str, replacement: str,
) -> tuple[str, MainSignature] | None:
    if not identifier(replacement):
        raise ValueError("c2rust_main_replacement_invalid")
    tokens = lex_rust(source)
    significant = significant_indexes(tokens)
    mains = [
        item for item in find_rust_functions(tokens, significant)
        if item.public and item.name == "main"
    ]
    if not mains:
        return None
    if len(mains) != 1:
        raise ValueError("c2rust_multiple_public_main_in_module")
    function = mains[0]
    rewritten = replace_token_text(
        source, tokens, {function.name_token: replacement},
    )
    return rewritten, MainSignature(
        replacement, function.parameter_count, function.returns_value,
    )


def _rewrite_function_references(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...],
    function: RustFunction, names: dict[str, str], replacements: dict[int, str],
) -> None:
    scopes: list[set[str]] = [set(function.parameter_names)]
    for position in range(function.body_open + 1, function.body_close):
        token_index = significant[position]
        text = tokens[token_index].text
        if text == "{":
            scopes.append(set())
            continue
        if text == "}":
            if len(scopes) > 1:
                scopes.pop()
            continue
        if text not in names:
            continue
        if _qualified_static(tokens, significant, position):
            replacements[token_index] = names[text]
            continue
        if _binding_declaration(tokens, significant, position):
            scopes[-1].add(text)
            continue
        if any(text in scope for scope in scopes):
            continue
        if not _non_static_context(tokens, significant, position):
            replacements[token_index] = names[text]


def _binding_declaration(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], position: int,
) -> bool:
    if position and tokens[significant[position - 1]].text == "const":
        return not (
            position >= 2 and tokens[significant[position - 2]].text == "raw"
        )
    for cursor in range(position - 1, max(-1, position - 12), -1):
        text = tokens[significant[cursor]].text
        if text in {"=", ";", "{", "}"}:
            return False
        if text in {"let", "for"}:
            return True
    return False


def _non_static_context(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], position: int,
) -> bool:
    previous = tokens[significant[position - 1]].text if position else ""
    following = (
        tokens[significant[position + 1]].text
        if position + 1 < len(significant) else ""
    )
    if previous == "." or following == ":":
        return True
    return previous in {"fn", "struct", "enum", "union", "type", "mod"}


def _qualified_static(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], position: int,
) -> bool:
    return (
        position >= 2
        and tokens[significant[position - 1]].text == "::"
        and tokens[significant[position - 2]].text in {"crate", "self", "super"}
    )


def _body_positions(functions: tuple[RustFunction, ...]) -> set[int]:
    return {
        position for function in functions
        for position in range(function.body_open + 1, function.body_close)
    }


def _fresh_static_name(name: str, occupied: set[str]) -> str:
    base = f"__c2rust_static_{name}"
    candidate = base
    suffix = 2
    while candidate in occupied:
        candidate = f"{base}_{suffix}"
        suffix += 1
    occupied.add(candidate)
    return candidate


__all__ = [
    "MainSignature", "StaticRepairResult", "add_deref_nullptr_allow",
    "rename_single_public_main", "repair_module_static_parameter_collisions",
]
