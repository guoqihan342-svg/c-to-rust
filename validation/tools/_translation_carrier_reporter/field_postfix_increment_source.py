from __future__ import annotations

import re
from typing import Any

from .errors import ReporterError


def validate_carrier_source(c_source: str, contract: dict[str, Any]) -> None:
    entry = contract["entry_arguments"][0]
    state = contract["state_output"]
    target = rf"\b{re.escape(str(entry['parameter']))}\s*->\s*{re.escape(str(state['field_path'][0]))}"
    pattern = re.compile(rf"{target}\s*\+\+\s*;")
    if len(pattern.findall(c_source)) != 1:
        raise ReporterError(
            "carrier must contain one direct mutable record u32 field postfix increment"
        )
