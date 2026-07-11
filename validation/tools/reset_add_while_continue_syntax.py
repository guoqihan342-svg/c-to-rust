from __future__ import annotations

import re
from typing import Any


def validate_c_reset_add_while_continue_source(
    source: str, contract: dict[str, Any]
) -> dict[str, Any]:
    entries = {item["parameter"]: item for item in contract["entry_arguments"]}
    owner_name = contract["owner_parameter"]
    owner = entries[owner_name]
    projection = contract["projection"]
    reset = contract["reset_state"]
    add = contract["add_state"]
    rhs = add["rhs"]
    control = contract["control_flow"]
    alias = projection["alias_local"]

    projected = c_member_access(owner_name, projection["path"], arrow=True)
    alias_reset = c_member_access(alias, reset["alias_field_path"], arrow=True)
    owner_reset = c_member_access(owner_name, reset["owner_field_path"], arrow=True)
    owner_add = c_member_access(owner_name, add["owner_field_path"], arrow=True)
    source_expression = re.escape(rhs["source_expression"])

    typedef = _unique(
        re.compile(
            rf"\btypedef\s+struct\s+{re.escape(projection['alias_rust_type'])}\s*\*\s*"
            rf"{re.escape(projection['alias_c_pointer_type'])}\s*;"
        ),
        source,
        "projection pointer typedef",
    )
    declaration = _unique(
        re.compile(
            rf"\b{re.escape(projection['alias_c_pointer_type'])}\s+{re.escape(alias)}"
            rf"\s*=\s*&\s*\(?\s*{projected}\s*\)?\s*;"
        ),
        source,
        "interior alias declaration",
    )
    sentinel_decl = _unique(
        re.compile(
            rf"\bbool\s+{re.escape(control['sentinel_local'])}\s*=\s*true\s*;"
        ),
        source,
        "true sentinel declaration",
    )
    loop = _unique(
        re.compile(
            rf"\bwhile\s*\(\s*{re.escape(control['sentinel_local'])}\s*\)\s*\{{"
        ),
        source,
        "sentinel while",
    )
    sentinel_assign = _unique(
        re.compile(
            rf"\b{re.escape(control['sentinel_local'])}\s*=\s*false\s*;"
        ),
        source,
        "body-first false sentinel assignment",
    )
    reset_match = _unique(
        re.compile(rf"{alias_reset}\s*=\s*(?:\(\s*uint32_t\s*\)\s*)?0[uU]?\s*;"),
        source,
        "alias reset",
    )
    add_match = _unique(
        re.compile(rf"{owner_add}\s*\+=\s*{source_expression}\s*;"),
        source,
        "owner wrapping-add source expression",
    )
    continue_match = _unique(re.compile(r"\bcontinue\s*;"), source, "current while continue")
    false_return = _unique(re.compile(r"\breturn\s+false\s*;"), source, "unreachable false return")
    true_return = _unique(re.compile(r"\breturn\s+true\s*;"), source, "terminal true return")

    if len(re.findall(r"\bwhile\s*\(", source)) != 1:
        raise ValueError("carrier must contain exactly one current while loop")
    if re.search(rf"{owner_reset}\s*=\s*(?:\(\s*uint32_t\s*\)\s*)?0[uU]?\s*;", source):
        raise ValueError("carrier must reset projected state through the alias, not owner")
    if len(_mutation_matches(source, alias_reset)) != 1:
        raise ValueError("carrier alias reset mutation must be unique")
    if len(_mutation_matches(source, owner_add)) != 1:
        raise ValueError("carrier owner add mutation must be unique")
    ordered = (
        typedef,
        declaration,
        sentinel_decl,
        loop,
        sentinel_assign,
        reset_match,
        add_match,
        continue_match,
        false_return,
        true_return,
    )
    if [item.start() for item in ordered] != sorted(item.start() for item in ordered):
        raise ValueError("carrier reset/add/continue statement order drifted")
    if source[loop.end() : sentinel_assign.start()].strip():
        raise ValueError("sentinel false assignment must be first in while body")
    if source[continue_match.end() : false_return.start()].strip():
        raise ValueError("unreachable false return must immediately follow continue")
    if re.fullmatch(r"\s*}\s*", source[false_return.end() : true_return.start()]) is None:
        raise ValueError("terminal true return must follow the current while")

    return _syntax_report(contract, "c_interior_pointer_alias")


def validate_rust_reset_add_while_continue_draft(
    source: str, contract: dict[str, Any]
) -> dict[str, Any]:
    forbidden = {
        "unsafe": re.compile(r"\bunsafe\b"),
        "raw_pointer": re.compile(r"\*\s*(?:const|mut)\b"),
        "pointer_api": re.compile(r"\b(?:core|std)::ptr\b"),
    }
    found = [label for label, pattern in forbidden.items() if pattern.search(source)]
    if found:
        raise ValueError("generated Rust draft must not use " + ", ".join(found))

    entries = {item["parameter"]: item for item in contract["entry_arguments"]}
    owner_name = contract["owner_parameter"]
    owner = entries[owner_name]
    projection = contract["projection"]
    reset = contract["reset_state"]
    add = contract["add_state"]
    rhs = add["rhs"]
    source_entry = entries[rhs["parameter"]]
    control = contract["control_flow"]
    alias = projection["alias_local"]

    _unique(
        re.compile(
            rf"\b{re.escape(source_entry['parameter'])}\s*:\s*&\s*"
            rf"{re.escape(source_entry['rust_type'])}\b"
        ),
        source,
        "readonly source reference",
    )
    _unique(
        re.compile(
            rf"\b{re.escape(owner_name)}\s*:\s*&\s*mut\s+{re.escape(owner['rust_type'])}\b"
        ),
        source,
        "mutable owner reference",
    )
    if re.search(rf"\b{re.escape(source_entry['parameter'])}\s*:\s*&\s*mut\b", source):
        raise ValueError("generated Rust source root must remain readonly")

    projected = rust_member_access(owner_name, projection["path"])
    alias_reset = rust_member_access(alias, reset["alias_field_path"])
    owner_reset = rust_member_access(owner_name, reset["owner_field_path"])
    owner_add = rust_member_access(owner_name, add["owner_field_path"])
    rhs_access = rust_member_access(rhs["parameter"], rhs["field_path"])
    alias_decl = _unique(
        re.compile(
            rf"\blet\s+(?:mut\s+)?{re.escape(alias)}"
            rf"(?:\s*:\s*&\s*mut\s+{re.escape(projection['alias_rust_type'])})?"
            rf"\s*=\s*&\s*mut\s+{projected}\s*;"
        ),
        source,
        "safe mutable interior projection",
    )
    sentinel_decl = _unique(
        re.compile(
            rf"\blet\s+mut\s+{re.escape(control['sentinel_local'])}"
            rf"(?:\s*:\s*bool)?\s*=\s*true\s*;"
        ),
        source,
        "true sentinel declaration",
    )
    loop = _unique(
        re.compile(
            rf"\bwhile\s+{re.escape(control['sentinel_local'])}"
            rf"(?:\s*!=\s*false)?\s*\{{"
        ),
        source,
        "sentinel while",
    )
    sentinel_assign = _unique(
        re.compile(rf"\b{re.escape(control['sentinel_local'])}\s*=\s*false\s*;"),
        source,
        "body-first false sentinel assignment",
    )
    reset_match = _unique(
        re.compile(rf"{alias_reset}\s*=\s*(?:\(\s*0i32\s+as\s+u32\s*\)|0(?:u32)?)\s*;"),
        source,
        "projected alias reset",
    )
    add_match = _unique(
        re.compile(
            rf"{owner_add}\s*=\s*{owner_add}\s*\.\s*wrapping_add\s*\(\s*{rhs_access}\s*\)\s*;"
        ),
        source,
        "owner wrapping_add",
    )
    continue_match = _unique(re.compile(r"\bcontinue\s*;"), source, "current while continue")
    false_return = _unique(re.compile(r"\breturn\s+false\s*;"), source, "unreachable false return")
    true_return = _unique(re.compile(r"\breturn\s+true\s*;"), source, "terminal true return")

    if len(re.findall(r"\bwhile\b", source)) != 1:
        raise ValueError("generated Rust draft must contain exactly one current while")
    if re.search(rf"{owner_reset}\s*=\s*(?:\(\s*0i32\s+as\s+u32\s*\)|0(?:u32)?)\s*;", source):
        raise ValueError("generated Rust draft must reset projected state through alias")
    if len(_mutation_matches(source, alias_reset)) != 1:
        raise ValueError("generated Rust alias reset mutation must be unique")
    if len(_mutation_matches(source, owner_add)) != 1:
        raise ValueError("generated Rust owner add mutation must be unique")
    ordered = (
        alias_decl,
        sentinel_decl,
        loop,
        sentinel_assign,
        reset_match,
        add_match,
        continue_match,
        false_return,
        true_return,
    )
    if [item.start() for item in ordered] != sorted(item.start() for item in ordered):
        raise ValueError("generated Rust reset/add/continue statement order drifted")
    if source[loop.end() : sentinel_assign.start()].strip():
        raise ValueError("generated Rust sentinel assignment must be first in while body")
    if source[continue_match.end() : false_return.start()].strip():
        raise ValueError("generated Rust unreachable false return must immediately follow continue")
    if re.fullmatch(r"\s*}\s*", source[false_return.end() : true_return.start()]) is None:
        raise ValueError("generated Rust terminal true return must follow current while")
    return {
        **_syntax_report(contract, "safe_mutable_reference"),
        "raw_pointer_count": 0,
        "unsafe_count": 0,
        "wrapping_add_count": 1,
        "continue_count": 1,
    }


def _syntax_report(contract: dict[str, Any], projection_mode: str) -> dict[str, Any]:
    return {
        "status": "passed",
        "projection_mode": projection_mode,
        "alias_local": contract["projection"]["alias_local"],
        "projection_path": list(contract["projection"]["path"]),
        "pointer_root_count": 2,
        "noalias_required": [list(pair) for pair in contract["noalias_required"]],
        "continue_target": contract["control_flow"]["continue_target"],
    }


def _unique(pattern: re.Pattern[str], source: str, label: str) -> re.Match[str]:
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise ValueError(f"carrier must contain exactly one declared {label}")
    return matches[0]


def _mutation_matches(source: str, access: str) -> list[re.Match[str]]:
    return list(re.finditer(rf"{access}\s*(?:\+=|-=|\*=|/=|%=|=)", source))


def c_member_access(root: str, path: list[str], *, arrow: bool) -> str:
    head = rf"\b{re.escape(root)}\s*{'->' if arrow else '.'}\s*{re.escape(path[0])}"
    return head + "".join(rf"\s*\.\s*{re.escape(item)}" for item in path[1:])


def rust_member_access(root: str, path: list[str]) -> str:
    return rf"\b{re.escape(root)}" + "".join(
        rf"\s*\.\s*{re.escape(item)}" for item in path
    )
