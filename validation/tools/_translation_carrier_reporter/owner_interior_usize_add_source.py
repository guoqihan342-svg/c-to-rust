from __future__ import annotations

import re
from typing import Any

from .errors import ReporterError


def validate_carrier_source(c_source: str, contract: dict[str, Any]) -> None:
    owner = contract["owner"]
    alias = contract["alias"]
    projection = contract["projection_path"]
    state = contract["state_output"]["owner_field_path"]
    rhs = contract["rhs"]["alias_field_path"]
    owner_name = re.escape(str(owner["parameter"]))
    alias_name = re.escape(str(alias["local"]))
    alias_c_type = re.escape(str(alias["c_type"]))
    alias_record = re.escape(str(alias["rust_type"]))
    projection_access = rf"{owner_name}\s*->\s*{re.escape(str(projection[0]))}" + "".join(
        rf"\s*\.\s*{re.escape(str(item))}" for item in projection[1:]
    )
    alias_typedef = re.compile(
        rf"typedef\s+struct\s+{alias_record}\s*\*\s*{alias_c_type}\s*;"
    )
    alias_declaration = re.compile(
        rf"\b{alias_c_type}\s+{alias_name}\s*=\s*&\s*{projection_access}\s*;"
    )
    update = re.compile(
        rf"\b{owner_name}\s*->\s*{re.escape(str(state[0]))}\s*\+=\s*"
        rf"{alias_name}\s*->\s*{re.escape(str(rhs[0]))}\s*;"
    )
    if len(alias_typedef.findall(c_source)) != 1:
        raise ReporterError("carrier must declare exactly one pointer typedef for the projected record")
    if len(alias_declaration.findall(c_source)) != 1:
        raise ReporterError("carrier must declare exactly one mutable owner interior alias through its pointer typedef")
    if len(update.findall(c_source)) != 1:
        raise ReporterError("carrier must add the aliased direct u32 rhs to the direct usize accumulator")
