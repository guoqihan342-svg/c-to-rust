from __future__ import annotations

import re
from typing import Any

from .errors import ReporterError


def validate_carrier_source(c_source: str, contract: dict[str, Any]) -> None:
    state = contract["state_output"]
    update = contract["state_update"]
    record_field = update["record_field"]
    scalar = update["scalar"]
    target = c_field_access(state["parameter"], state["field_path"], pointer=True)
    source = c_field_access(
        record_field["parameter"], record_field["field_path"], pointer=False
    )
    scalar_name = re.escape(str(scalar["parameter"]))
    pattern = re.compile(
        rf"{target}\s*=\s*(?:\(\s*uint32_t\s*\)\s*)?{source}\s*\+\s*{scalar_name}\s*;"
    )
    if len(pattern.findall(c_source)) != 1:
        raise ReporterError(
            "carrier must contain one declared nested target assignment from the record field plus scalar"
        )


def c_field_access(root: Any, path: Any, *, pointer: bool) -> str:
    components = [re.escape(str(item)) for item in path]
    separator = r"\s*->\s*" if pointer else r"\s*\.\s*"
    access = rf"\b{re.escape(str(root))}{separator}{components[0]}"
    return access + "".join(rf"\s*\.\s*{component}" for component in components[1:])
