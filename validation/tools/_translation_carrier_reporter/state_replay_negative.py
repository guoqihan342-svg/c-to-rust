from __future__ import annotations

import re
from typing import Any

from .constant_state_contract import KIND as CONSTANT_STATE_KIND
from .constant_state_model import negative_partition_probe_source as constant_probe
from .field_add_contract import KIND as FIELD_ADD_KIND
from .field_add_model import negative_partition_probe_source as field_add_probe
from .field_scalar_add_contract import KIND as FIELD_SCALAR_ADD_KIND
from .field_scalar_add_model import negative_partition_probe_source as field_scalar_probe


def mutation_spec(contract: dict[str, Any]) -> tuple[re.Pattern[bytes], bytes, bytes] | None:
    kind = contract.get("kind")
    if kind == CONSTANT_STATE_KIND:
        return re.compile(rb"\b0(?=(?:u32|i32\s+as\s+u32\))?\s*;)"), b"0", b"1"
    if kind in {FIELD_ADD_KIND, FIELD_SCALAR_ADD_KIND}:
        return re.compile(rb"\bwrapping_add\b"), b"wrapping_add", b"wrapping_sub"
    return None


def negative_partition_probe_source(context: Any) -> str | None:
    kind = context.contract.get("kind")
    if kind == CONSTANT_STATE_KIND:
        return constant_probe(context)
    if kind == FIELD_ADD_KIND:
        return field_add_probe(context)
    if kind == FIELD_SCALAR_ADD_KIND:
        return field_scalar_probe(context)
    return None
