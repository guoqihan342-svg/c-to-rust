from __future__ import annotations

import re
from typing import Any


def validate_c_interior_projection_source(
    source: str, contract: dict[str, Any]
) -> dict[str, Any]:
    owner = contract["owner"]
    alias = contract["alias"]
    state = contract["state_output"]
    projection = c_member_access(owner["parameter"], contract["projection_path"], arrow=True)
    alias_state = c_member_access(alias["local"], state["alias_field_path"], arrow=True)
    owner_state = c_member_access(owner["parameter"], state["owner_field_path"], arrow=True)

    typedef = re.compile(
        rf"\btypedef\s+struct\s+{re.escape(alias['rust_type'])}\s*\*\s*"
        rf"{re.escape(alias['c_pointer_type'])}\s*;"
    )
    declaration = re.compile(
        rf"\b{re.escape(alias['c_pointer_type'])}\s+{re.escape(alias['local'])}"
        rf"\s*=\s*&\s*\(?\s*{projection}\s*\)?\s*;"
    )
    assignment = re.compile(
        rf"{alias_state}\s*=\s*(?:\(\s*uint32_t\s*\)\s*)?0[uU]?\s*;"
    )
    direct_assignment = re.compile(
        rf"{owner_state}\s*=\s*(?:\(\s*uint32_t\s*\)\s*)?0[uU]?\s*;"
    )
    return_pattern = re.compile(r"\breturn\s+true\s*;")
    require_unique(typedef, source, "pointer typedef")
    require_unique(declaration, source, "interior alias declaration")
    require_unique(assignment, source, "alias state assignment")
    if direct_assignment.search(source) is not None:
        raise ValueError("carrier must update projected state through the declared alias")
    require_unique(return_pattern, source, "bool return")
    return {
        "status": "passed",
        "pointer_root_count": 1,
        "projection_mode": "owner_interior_mutable",
        "alias_local": alias["local"],
        "projection_path": list(contract["projection_path"]),
    }


def validate_rust_interior_projection_draft(
    source: str, contract: dict[str, Any]
) -> dict[str, Any]:
    owner = contract["owner"]
    alias = contract["alias"]
    state = contract["state_output"]
    forbidden = {
        "unsafe": re.compile(r"\bunsafe\b"),
        "raw_pointer": re.compile(r"\*(?:const|mut)\b"),
        "pointer_api": re.compile(r"\b(?:core|std)::ptr\b"),
    }
    found = [label for label, pattern in forbidden.items() if pattern.search(source)]
    if found:
        raise ValueError(
            "generated Rust draft interior projection must not use " + ", ".join(found)
        )

    projection = rust_member_access(owner["parameter"], contract["projection_path"])
    alias_state = rust_member_access(alias["local"], state["alias_field_path"])
    owner_state = rust_member_access(owner["parameter"], state["owner_field_path"])
    declaration = re.compile(
        rf"\blet\s+(?:mut\s+)?{re.escape(alias['local'])}"
        rf"(?:\s*:\s*&\s*mut\s+{re.escape(alias['rust_type'])})?"
        rf"\s*=\s*&\s*mut\s+{projection}\s*;"
    )
    assignment = re.compile(
        rf"{alias_state}\s*=\s*(?:\(\s*0i32\s+as\s+u32\s*\)|0(?:u32)?)\s*;"
    )
    direct_assignment = re.compile(
        rf"{owner_state}\s*=\s*(?:\(\s*0i32\s+as\s+u32\s*\)|0(?:u32)?)\s*;"
    )
    fixed_return = re.compile(
        r"(?:\breturn\s+true\s*;|(?m:^[ \t]*true[ \t]*$)(?=\s*\}))"
    )
    require_unique(declaration, source, "safe mutable interior projection")
    require_unique(assignment, source, "projected alias state assignment")
    if direct_assignment.search(source) is not None:
        raise ValueError("generated Rust draft must update state through the projected alias")
    require_unique(fixed_return, source, "fixed bool return")
    return {
        "status": "passed",
        "pointer_root_count": 1,
        "projection_mode": "safe_mutable_reference",
        "alias_local": alias["local"],
        "projection_path": list(contract["projection_path"]),
        "raw_pointer_count": 0,
        "unsafe_count": 0,
    }


def require_unique(pattern: re.Pattern[str], source: str, label: str) -> None:
    if len(pattern.findall(source)) != 1:
        raise ValueError(f"carrier must contain exactly one declared {label}")


def c_member_access(root: str, path: list[str], *, arrow: bool) -> str:
    head = rf"\b{re.escape(root)}\s*{'->' if arrow else '.'}\s*{re.escape(path[0])}"
    return head + "".join(rf"\s*\.\s*{re.escape(item)}" for item in path[1:])


def rust_member_access(root: str, path: list[str]) -> str:
    return rf"\b{re.escape(root)}" + "".join(
        rf"\s*\.\s*{re.escape(item)}" for item in path
    )
