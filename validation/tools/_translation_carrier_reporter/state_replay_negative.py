from __future__ import annotations

import re
from typing import Any

from .constant_state_contract import KIND as CONSTANT_STATE_KIND
from .constant_state_model import negative_partition_probe_source as constant_probe
from .field_add_contract import KIND as FIELD_ADD_KIND
from .field_add_model import negative_partition_probe_source as field_add_probe
from .field_scalar_add_contract import KIND as FIELD_SCALAR_ADD_KIND
from .field_scalar_add_model import negative_partition_probe_source as field_scalar_probe
from .field_postfix_increment_contract import KIND as FIELD_POSTFIX_INCREMENT_KIND
from .field_postfix_increment_model import (
    negative_partition_probe_source as field_postfix_increment_probe,
)
from .owner_interior_usize_add_contract import KIND as OWNER_INTERIOR_USIZE_ADD_KIND
from .owner_interior_usize_add_model import (
    negative_partition_probe_source as owner_interior_usize_add_probe,
)
from .stats_sequence_contract import KIND as STATS_SEQUENCE_KIND
from .stats_sequence_model import negative_partition_probe_source as stats_sequence_probe
from .guarded_stats_sequence_contract import KIND as GUARDED_STATS_SEQUENCE_KIND
from .guarded_stats_sequence_model import (
    negative_partition_probe_source as guarded_stats_sequence_probe,
)
from .interior_projection_contract import KIND as INTERIOR_PROJECTION_KIND
from .interior_projection_model import negative_partition_probe_source as projection_probe
from .reset_add_while_continue_contract import KIND as RESET_ADD_CONTINUE_KIND
from .reset_add_while_continue_model import negative_partition_probe_source as reset_add_probe


def mutation_spec(contract: dict[str, Any]) -> tuple[re.Pattern[bytes], bytes, bytes] | None:
    kind = contract.get("kind")
    if kind == RESET_ADD_CONTINUE_KIND:
        return re.compile(rb"\bcontinue;"), b"continue;", b"/*noop*/;"
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
    if kind in {
        FIELD_ADD_KIND,
        FIELD_SCALAR_ADD_KIND,
        FIELD_POSTFIX_INCREMENT_KIND,
        OWNER_INTERIOR_USIZE_ADD_KIND,
    }:
        return re.compile(rb"\bwrapping_add\b"), b"wrapping_add", b"wrapping_sub"
    if kind == STATS_SEQUENCE_KIND:
        owner = str(contract["owner"]["parameter"]).encode("ascii")
        path = [
            str(item).encode("ascii")
            for item in contract["updates"][2]["target"]["owner_field_path"]
        ]
        access = rb"\b" + re.escape(owner) + b"".join(
            rb"\s*\.\s*" + re.escape(item) for item in path
        )
        return (
            re.compile(
                access
                + rb"\s*=\s*"
                + access
                + rb"\s*\.\s*(?P<value>wrapping_add)\b"
            ),
            b"wrapping_add",
            b"wrapping_sub",
        )
    if kind == GUARDED_STATS_SEQUENCE_KIND:
        owner = str(contract["owner"]["parameter"]).encode("ascii")
        path = [
            str(item).encode("ascii")
            for item in contract["guard"]["predicates"][1]["lhs"]["owner_field_path"]
        ]
        access = rb"\b" + re.escape(owner) + b"".join(
            rb"\s*\.\s*" + re.escape(item) for item in path
        )
        return re.compile(access + rb"\s*(?P<value>==)(?!=)"), b"==", b"!="
    return None


def negative_partition_probe_source(context: Any) -> str | None:
    kind = context.contract.get("kind")
    if kind == RESET_ADD_CONTINUE_KIND:
        return reset_add_probe(context)
    if kind == CONSTANT_STATE_KIND:
        return constant_probe(context)
    if kind == INTERIOR_PROJECTION_KIND:
        return projection_probe(context)
    if kind == FIELD_ADD_KIND:
        return field_add_probe(context)
    if kind == FIELD_SCALAR_ADD_KIND:
        return field_scalar_probe(context)
    if kind == FIELD_POSTFIX_INCREMENT_KIND:
        return field_postfix_increment_probe(context)
    if kind == OWNER_INTERIOR_USIZE_ADD_KIND:
        return owner_interior_usize_add_probe(context)
    if kind == STATS_SEQUENCE_KIND:
        return stats_sequence_probe(context)
    if kind == GUARDED_STATS_SEQUENCE_KIND:
        return guarded_stats_sequence_probe(context)
    return None
