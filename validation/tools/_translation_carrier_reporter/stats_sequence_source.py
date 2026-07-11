from __future__ import annotations

import re
from typing import Any

from .errors import ReporterError


def validate_carrier_source(c_source: str, contract: dict[str, Any]) -> None:
    owner = contract["owner"]
    alias = contract["alias"]
    projection = contract["projection_path"]
    updates = contract["updates"]
    owner_name = re.escape(str(owner["parameter"]))
    owner_type = re.escape(str(owner["rust_type"]))
    alias_name = re.escape(str(alias["local"]))
    alias_c_type = re.escape(str(alias["c_type"]))
    alias_record = re.escape(str(alias["rust_type"]))
    projection_access = _owner_access(owner_name, projection)

    typedef = re.compile(
        rf"\btypedef\s+struct\s+{alias_record}\s*\*\s*{alias_c_type}\s*;"
    )
    if len(typedef.findall(c_source)) != 1:
        raise ReporterError("carrier must declare exactly one pointer typedef for the projected record")

    increment = _owner_access(owner_name, updates[0]["target"]["owner_field_path"]) + r"\s*\+\+\s*;"
    additions = []
    for update in updates[1:]:
        target = _owner_access(owner_name, update["target"]["owner_field_path"])
        source = _alias_access(alias_name, update["source"]["alias_field_path"])
        additions.append(rf"{target}\s*\+=\s*{source}\s*;")
    alias_declaration = rf"\b{alias_c_type}\s+{alias_name}\s*=\s*&\s*{projection_access}\s*;"
    body_pattern = re.compile(
        rf"(?:static\s+)?bool\s+[A-Za-z_][A-Za-z0-9_]*\s*\(\s*"
        rf"struct\s+{owner_type}\s*\*\s*{owner_name}\s*\)\s*\{{"
        rf"\s*{alias_declaration}\s*{increment}\s*{additions[0]}\s*{additions[1]}"
        rf"\s*return\s+true\s*;\s*\}}",
        re.DOTALL,
    )
    matches = list(body_pattern.finditer(c_source))
    if len(matches) != 1:
        raise ReporterError(
            "carrier function body must contain only the alias setup, three ordered updates, and fixed true return"
        )
    residual = c_source[: matches[0].start()] + c_source[matches[0].end() :]
    if re.search(r"\b(?:static\s+)?bool\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", residual):
        raise ReporterError("carrier must contain exactly one bool function")


def _owner_access(root: str, path: list[str]) -> str:
    return rf"\b{root}\s*->\s*{re.escape(str(path[0]))}" + "".join(
        rf"\s*\.\s*{re.escape(str(item))}" for item in path[1:]
    )


def _alias_access(root: str, path: list[str]) -> str:
    return rf"\b{root}\s*->\s*{re.escape(str(path[0]))}" + "".join(
        rf"\s*\.\s*{re.escape(str(item))}" for item in path[1:]
    )
