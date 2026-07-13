from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from validation.tools.replay_assertion_inventory import (
    ASSERTION_ID_RE,
    ASSERTION_MARKER_PREFIX,
    validate_replay_assertion_inventory,
)


PANIC_RE = re.compile(
    r"thread '[^'\r\n]{1,256}'(?: \([1-9][0-9]*\))? panicked at "
    r"<generated-replay>[/\\]generated_replay\.rs:"
    r"(?P<line>[1-9][0-9]*):[1-9][0-9]*:\r?\n"
    + re.escape(ASSERTION_MARKER_PREFIX)
    + r"(?P<assertion_id>[0-9a-f]{64})(?:\r?\n|$)"
)


def authenticate_runtime_assertion_id(
    candidate_source: str,
    replay_source: str,
    run_stderr: str,
) -> str | None:
    matches = list(PANIC_RE.finditer(run_stderr))
    if len(matches) != 1:
        return None
    assertion_id = matches[0].group("assertion_id")
    marker = ASSERTION_MARKER_PREFIX + assertion_id
    if marker in candidate_source or replay_source.count(marker) != 1:
        return None
    replay_line = next(
        (
            index
            for index, line in enumerate(replay_source.splitlines(), 1)
            if marker in line
        ),
        None,
    )
    if replay_line is None:
        return None
    prefix_line_count = (candidate_source + "\n").count("\n")
    return (
        assertion_id
        if int(matches[0].group("line")) == prefix_line_count + replay_line
        else None
    )


def runtime_assertion_failure_envelope(
    assertion_id: Any, inventory: dict[str, Any] | None
) -> dict[str, str] | None:
    if not isinstance(assertion_id, str) or ASSERTION_ID_RE.fullmatch(assertion_id) is None:
        return None
    try:
        validate_replay_assertion_inventory(inventory)
    except ValueError:
        return None
    if assertion_id not in {
        item["assertion_id"] for item in inventory["assertions"]
    }:
        return None
    return {
        "assertion_id": assertion_id,
        "replay_call_plan_sha256": inventory["plan_sha256"],
        "assertion_inventory_sha256": inventory["assertion_inventory_sha256"],
    }


def localized_runtime_assertion_details(
    value: Any, inventory: dict[str, Any] | None
) -> dict[str, str] | None:
    if not isinstance(value, Mapping) or set(value) != {
        "assertion_id",
        "replay_call_plan_sha256",
        "assertion_inventory_sha256",
    }:
        return None
    try:
        validate_replay_assertion_inventory(inventory)
    except ValueError:
        return None
    if (
        value.get("replay_call_plan_sha256") != inventory["plan_sha256"]
        or value.get("assertion_inventory_sha256")
        != inventory["assertion_inventory_sha256"]
    ):
        return None
    matches = [
        item
        for item in inventory["assertions"]
        if item["assertion_id"] == value.get("assertion_id")
    ]
    if len(matches) != 1:
        return None
    return {
        "case_id": matches[0]["case_id"],
        "observable_field": matches[0]["observable_field"],
    }


__all__ = [
    "authenticate_runtime_assertion_id",
    "localized_runtime_assertion_details",
    "runtime_assertion_failure_envelope",
]
