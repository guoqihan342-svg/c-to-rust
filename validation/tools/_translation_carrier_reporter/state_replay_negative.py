from __future__ import annotations

import re
from typing import Any

from .constant_state_contract import KIND as CONSTANT_STATE_KIND
from .constant_state_model import negative_partition_probe_source as constant_probe
from .field_add_contract import KIND as FIELD_ADD_KIND
from .field_add_model import negative_partition_probe_source as field_add_probe
from .field_scalar_add_contract import KIND as FIELD_SCALAR_ADD_KIND
from .field_scalar_add_model import negative_partition_probe_source as field_scalar_probe
from .interior_projection_contract import KIND as INTERIOR_PROJECTION_KIND
from .interior_projection_model import negative_partition_probe_source as projection_probe


def mutation_spec(contract: dict[str, Any]) -> tuple[re.Pattern[bytes], bytes, bytes] | None:
    kind = contract.get("kind")
    if kind == CONSTANT_STATE_KIND:
        return re.compile(rb"\b0(?=(?:u32|i32\s+as\s+u32\))?\s*;)"), b"0", b"1"
    if kind == INTERIOR_PROJECTION_KIND:
        alias = str(contract["alias"]["local"]).encode("ascii")
        path = [str(item).encode("ascii") for item in contract["state_output"]["alias_field_path"]]
        access = rb"\b" + re.escape(alias) + b"".join(
            rb"\s*\.\s*" + re.escape(item) for item in path
        )
        return (
            re.compile(
                access
                + rb"\s*=\s*(?:\(\s*)?(?P<value>0)"
                + rb"(?=(?:u32\s*;|i32\s+as\s+u32\s*\)\s*;|\s*;))"
            ),
            b"0",
            b"1",
        )
    if kind in {FIELD_ADD_KIND, FIELD_SCALAR_ADD_KIND}:
        return re.compile(rb"\bwrapping_add\b"), b"wrapping_add", b"wrapping_sub"
    return None


def negative_partition_probe_source(context: Any) -> str | None:
    kind = context.contract.get("kind")
    if kind == CONSTANT_STATE_KIND:
        return constant_probe(context)
    if kind == INTERIOR_PROJECTION_KIND:
        return projection_probe(context)
    if kind == FIELD_ADD_KIND:
        return field_add_probe(context)
    if kind == FIELD_SCALAR_ADD_KIND:
        return field_scalar_probe(context)
    return None
