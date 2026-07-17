from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any


LINK_CLOSURE_SCHEMA_VERSION = 2
LEGACY_LINK_CLOSURE_SCHEMA_VERSION = 1


def link_closure_schema_version(value: Mapping[str, Any]) -> int:
    version = value.get("schema_version")
    if version is None:
        return LEGACY_LINK_CLOSURE_SCHEMA_VERSION
    if type(version) is not int or version not in {
        LEGACY_LINK_CLOSURE_SCHEMA_VERSION, LINK_CLOSURE_SCHEMA_VERSION,
    }:
        raise ValueError("target_link_closure_schema_version_invalid")
    return version


def reopen_discovered_link_closure(
    discovered: Mapping[str, Any], stored: Mapping[str, Any],
) -> dict[str, Any]:
    """Project current discovery to the explicitly stored closure version."""
    stored_version = link_closure_schema_version(stored)
    current_version = link_closure_schema_version(discovered)
    if current_version != LINK_CLOSURE_SCHEMA_VERSION:
        raise ValueError("target_link_closure_current_schema_invalid")
    result = copy.deepcopy(dict(discovered))
    if stored_version == LINK_CLOSURE_SCHEMA_VERSION:
        return result
    if "schema_version" in stored:
        result["schema_version"] = LEGACY_LINK_CLOSURE_SCHEMA_VERSION
    else:
        result.pop("schema_version", None)
    for target in result.get("targets", []):
        if isinstance(target, dict):
            target.pop("ordered_link_occurrences", None)
    return result


__all__ = [
    "LEGACY_LINK_CLOSURE_SCHEMA_VERSION",
    "LINK_CLOSURE_SCHEMA_VERSION",
    "link_closure_schema_version",
    "reopen_discovered_link_closure",
]
