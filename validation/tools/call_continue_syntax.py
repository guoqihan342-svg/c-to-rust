from __future__ import annotations

import re
from typing import Any


def validate_c_call_continue_source(source: str, contract: dict[str, Any]) -> dict[str, Any]:
    entries = {item["parameter"]: item for item in contract["entry_arguments"]}
    db, local, owner = (item["parameter"] for item in contract["entry_arguments"])
    projection = contract["projection"]
    alias = projection["alias_local"]
    external = contract["external_callee"]
    local_argument = next(
        item for item in external["arguments"] if item["mode"] == "entry_local_copy"
    )
    local_entry = local_argument["entry_parameter"]
    call_local = local_argument["callee_parameter"]
    assigned = contract["assigned_state"]
    add = contract["add_state"]
    control = contract["control_flow"]
    projected = c_access(owner, projection["path"], arrow=True)
    alias_state = c_access(alias, assigned["alias_field_path"], arrow=True)
    owner_state = c_access(owner, assigned["owner_field_path"], arrow=True)
    owner_add = c_access(owner, add["owner_field_path"], arrow=True)

    typedef = unique(re.compile(
        rf"\btypedef\s+struct\s+{re.escape(projection['alias_rust_type'])}\s*\*\s*"
        rf"{re.escape(projection['alias_c_pointer_type'])}\s*;"
    ), source, "alias typedef")
    alias_decl = unique(re.compile(
        rf"\b{re.escape(projection['alias_c_pointer_type'])}\s+{re.escape(alias)}\s*=\s*"
        rf"&\s*\(?\s*{projected}\s*\)?\s*;"
    ), source, "owner interior alias")
    local_decl = None
    if call_local != local_entry:
        local_decl = unique(re.compile(
            rf"\b{re.escape(entries[local_entry]['c_type'])}\s+{re.escape(call_local)}\s*=\s*"
            rf"{re.escape(local_entry)}\s*;"
        ), source, "entry local copy")
    sentinel_decl = unique(re.compile(
        rf"\bbool\s+{re.escape(control['sentinel_local'])}\s*=\s*true\s*;"
    ), source, "run-once sentinel")
    loop = unique(re.compile(
        rf"\bwhile\s*\(\s*{re.escape(control['sentinel_local'])}\s*\)\s*\{{"
    ), source, "run-once while")
    clear = unique(re.compile(
        rf"\b{re.escape(control['sentinel_local'])}\s*=\s*false\s*;"
    ), source, "body-first sentinel clear")
    call_condition = unique(re.compile(
        rf"\(\s*{alias_state}\s*=\s*{re.escape(external['name'])}\s*\(\s*"
        rf"{re.escape(db)}\s*,\s*&\s*{re.escape(call_local)}\s*,\s*{re.escape(alias)}\s*\)\s*\)"
        rf"\s*==\s*(?:FAILED_ADDR|(?:\(\s*uint32_t\s*\)\s*)?{contract['comparison']['sentinel']}[uU]?)"
    ), source, "assigned external-call equality")
    reset = unique(re.compile(rf"{alias_state}\s*=\s*(?:\(\s*uint32_t\s*\)\s*)?0[uU]?\s*;"), source, "hit alias reset")
    addition = unique(re.compile(
        rf"{owner_add}\s*\+=\s*{re.escape(add['rhs']['source_expression'])}\s*;"
    ), source, "hit owner add")
    continuation = unique(re.compile(r"\bcontinue\s*;"), source, "current-level continue")
    miss = unique(re.compile(r"\breturn\s+false\s*;"), source, "miss return")
    terminal = unique(re.compile(r"\breturn\s+true\s*;"), source, "terminal return")
    if re.search(rf"{owner_state}\s*=\s*(?:\(\s*uint32_t\s*\)\s*)?0[uU]?\s*;", source):
        raise ValueError("hit reset must use the owner interior alias")
    ordered = tuple(item for item in (
        typedef, alias_decl, local_decl, sentinel_decl, loop, clear, call_condition,
        reset, addition, continuation, miss, terminal,
    ) if item is not None)
    require_order(ordered, "C call/compare/reset/add/continue order drifted")
    if source[loop.end():clear.start()].strip():
        raise ValueError("sentinel clear must be first in while body")
    return syntax_report(contract, "c_interior_pointer_alias")


def validate_rust_call_continue_draft(source: str, contract: dict[str, Any]) -> dict[str, Any]:
    forbidden = {
        "unsafe": re.compile(r"\bunsafe\b"),
        "raw_pointer": re.compile(r"\*\s*(?:const|mut)\b"),
        "pointer_api": re.compile(r"\b(?:core|std)::ptr\b"),
    }
    found = [label for label, pattern in forbidden.items() if pattern.search(source)]
    if found:
        raise ValueError("generated Rust draft must not use " + ", ".join(found))
    db, local, owner = (item["parameter"] for item in contract["entry_arguments"])
    entries = {item["parameter"]: item for item in contract["entry_arguments"]}
    projection = contract["projection"]
    alias = projection["alias_local"]
    assigned = contract["assigned_state"]
    add = contract["add_state"]
    control = contract["control_flow"]
    external = contract["external_callee"]
    local_argument = next(
        item for item in external["arguments"] if item["mode"] == "entry_local_copy"
    )
    local_entry = local_argument["entry_parameter"]
    call_local = local_argument["callee_parameter"]

    unique(re.compile(
        rf"\b(?:pub\s+)?fn\s+(?!{re.escape(external['name'])}\b)[A-Za-z_][A-Za-z0-9_]*\s*\(\s*"
        rf"{re.escape(db)}\s*:\s*&\s*mut\s+{re.escape(entries[db]['rust_type'])}\s*,\s*"
        rf"(?:mut\s+)?{re.escape(local)}\s*:\s*{re.escape(entries[local]['rust_type'])}\s*,\s*"
        rf"(?:mut\s+)?{re.escape(owner)}\s*:\s*&\s*mut\s+{re.escape(entries[owner]['rust_type'])}\s*\)"
        rf"\s*->\s*bool\s*\{{"
    ), source, "safe target signature")
    alias_state = rust_access(alias, assigned["alias_field_path"])
    owner_state = rust_access(owner, assigned["owner_field_path"])
    owner_add = rust_access(owner, add["owner_field_path"])
    projected = rust_access(owner, projection["path"])
    rhs = rust_access(add["rhs"]["parameter"], add["rhs"]["field_path"])
    alias_decl = unique(re.compile(
        rf"\blet\s+(?:mut\s+)?{re.escape(alias)}(?:\s*:\s*&\s*mut\s+{re.escape(projection['alias_rust_type'])})?"
        rf"\s*=\s*&\s*mut\s+{projected}\s*;"
    ), source, "safe owner interior alias")
    local_decl = None
    if call_local != local_entry:
        local_decl = unique(re.compile(
            rf"\blet\s+mut\s+{re.escape(call_local)}(?:\s*:\s*{re.escape(entries[local_entry]['rust_type'])})?"
            rf"\s*=\s*{re.escape(local_entry)}\s*;"
        ), source, "entry local copy")
    sentinel_decl = unique(re.compile(
        rf"\blet\s+mut\s+{re.escape(control['sentinel_local'])}(?:\s*:\s*bool)?\s*=\s*true\s*;"
    ), source, "run-once sentinel")
    loop = unique(re.compile(rf"\bwhile\s+{re.escape(control['sentinel_local'])}(?:\s*!=\s*false)?\s*\{{"), source, "run-once while")
    clear = unique(re.compile(rf"\b{re.escape(control['sentinel_local'])}\s*=\s*false\s*;"), source, "body-first sentinel clear")
    assignment = unique(re.compile(
        rf"{alias_state}\s*=\s*{re.escape(external['name'])}\s*\(\s*"
        rf"(?:{re.escape(db)}|&\s*mut\s*\*\s*{re.escape(db)})\s*,\s*"
        rf"&\s*mut\s+{re.escape(call_local)}\s*,\s*{re.escape(alias)}\s*\)\s*;"
    ), source, "external call assignment")
    sentinel = int(contract["comparison"]["sentinel"])
    sentinel_forms = [rf"{sentinel}(?:u32)?"]
    signed_value = sentinel - (1 << 32)
    if signed_value < 0:
        sentinel_forms.append(
            rf"\(\s*\(\s*{signed_value}i32\s*\)\s*as\s*u32\s*\)"
        )
    comparison = unique(re.compile(
        rf"\bif\s*(?:\(\s*)?{alias_state}\s*==\s*(?:{'|'.join(sentinel_forms)})"
        rf"\s*(?:\)\s*)?\{{"
    ), source, "exact sentinel comparison")
    reset = unique(re.compile(
        rf"{alias_state}\s*=\s*(?:0(?:u32)?|\(\s*0i32\s+as\s+u32\s*\))\s*;"
    ), source, "hit alias reset")
    addition = unique(re.compile(
        rf"{owner_add}\s*=\s*{owner_add}\s*\.\s*wrapping_add\s*\(\s*{rhs}\s*\)\s*;"
    ), source, "hit owner wrapping_add")
    continuation = unique(re.compile(r"\bcontinue\s*;"), source, "current-level continue")
    miss = unique(re.compile(r"\breturn\s+false\s*;"), source, "miss return")
    terminal = unique(re.compile(r"\breturn\s+true\s*;"), source, "terminal return")
    if re.search(rf"{owner_state}\s*=\s*0(?:u32)?\s*;", source):
        raise ValueError("generated Rust hit reset must use the owner interior alias")
    if len(re.findall(rf"(?<!fn )\b{re.escape(external['name'])}\s*\(", source)) != 1:
        raise ValueError("generated Rust must contain exactly one direct external call")
    ordered = tuple(item for item in (
        alias_decl, local_decl, sentinel_decl, loop, clear, assignment, comparison,
        reset, addition, continuation, miss, terminal,
    ) if item is not None)
    require_order(ordered, "generated Rust call/compare/reset/add/continue order drifted")
    if source[loop.end():clear.start()].strip():
        raise ValueError("generated Rust sentinel clear must be first in while body")
    return {
        **syntax_report(contract, "safe_mutable_reference"),
        "raw_pointer_count": 0,
        "unsafe_count": 0,
        "external_call_count": 1,
        "equality_count": 1,
        "wrapping_add_count": 1,
        "continue_count": 1,
    }


def syntax_report(contract: dict[str, Any], projection_mode: str) -> dict[str, Any]:
    return {
        "status": "passed",
        "projection_mode": projection_mode,
        "argument_modes": [item["mode"] for item in contract["external_callee"]["arguments"]],
        "pointer_root_count": 2,
        "noalias_required": [list(pair) for pair in contract["noalias_required"]],
        "continue_target": contract["control_flow"]["continue_target"],
    }


def unique(pattern: re.Pattern[str], source: str, label: str) -> re.Match[str]:
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise ValueError(f"carrier must contain exactly one declared {label}")
    return matches[0]


def require_order(matches: tuple[re.Match[str], ...], message: str) -> None:
    if [item.start() for item in matches] != sorted(item.start() for item in matches):
        raise ValueError(message)


def c_access(root: str, path: list[str], *, arrow: bool) -> str:
    head = rf"\b{re.escape(root)}\s*{'->' if arrow else '.'}\s*{re.escape(path[0])}"
    return head + "".join(rf"\s*\.\s*{re.escape(item)}" for item in path[1:])


def rust_access(root: str, path: list[str]) -> str:
    return rf"\b{re.escape(root)}" + "".join(
        rf"\s*\.\s*{re.escape(item)}" for item in path
    )
