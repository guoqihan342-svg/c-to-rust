from __future__ import annotations

import hashlib
import json
import re
from typing import Any


ASSERTION_MARKER_PREFIX = "C2R_REPLAY_ASSERT:"
ASSERTION_ID_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_ASSERTIONS = 512
MAX_LABEL_BYTES = 256


def build_replay_assertion_inventory(plan: dict[str, Any]) -> dict[str, Any]:
    from validation.tools.replay_call_plan import validate_replay_call_plan

    validate_replay_call_plan(plan)
    case_ids = plan.get("fixture", {}).get("case_ids")
    if (
        not isinstance(case_ids, list)
        or not case_ids
        or not all(_label(item) for item in case_ids)
        or len(case_ids) != len(set(case_ids))
    ):
        raise ValueError("replay assertion inventory requires unique case ids")
    fields = _observable_fields(plan)
    if not fields or len(fields) != len(set(fields)):
        raise ValueError("replay assertion inventory requires unique observable fields")
    if len(case_ids) * len(fields) > MAX_ASSERTIONS:
        raise ValueError("replay assertion inventory exceeds the assertion limit")

    assertions = []
    for case_id in case_ids:
        for ordinal, field in enumerate(fields):
            descriptor = {
                "plan_sha256": plan["plan_sha256"],
                "case_id": case_id,
                "observable_field": field,
                "ordinal": ordinal,
            }
            assertions.append(
                {
                    "assertion_id": hashlib.sha256(
                        _canonical_bytes(descriptor)
                    ).hexdigest(),
                    "case_id": case_id,
                    "observable_field": field,
                }
            )
    payload = {
        "schema_version": 1,
        "plan_sha256": plan["plan_sha256"],
        "assertions": assertions,
    }
    payload["assertion_inventory_sha256"] = hashlib.sha256(
        _canonical_bytes(payload)
    ).hexdigest()
    validate_replay_assertion_inventory(payload)
    return payload


def validate_replay_assertion_inventory(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "plan_sha256",
        "assertions",
        "assertion_inventory_sha256",
    }:
        raise ValueError("replay assertion inventory shape is invalid")
    if value.get("schema_version") != 1 or not ASSERTION_ID_RE.fullmatch(
        str(value.get("plan_sha256") or "")
    ):
        raise ValueError("replay assertion inventory identity is invalid")
    assertions = value.get("assertions")
    if not isinstance(assertions, list) or not 1 <= len(assertions) <= MAX_ASSERTIONS:
        raise ValueError("replay assertion inventory entries are invalid")
    identities: set[str] = set()
    coordinates: set[tuple[str, str]] = set()
    for item in assertions:
        if (
            not isinstance(item, dict)
            or set(item) != {"assertion_id", "case_id", "observable_field"}
            or not ASSERTION_ID_RE.fullmatch(str(item.get("assertion_id") or ""))
            or not _label(item.get("case_id"))
            or not _label(item.get("observable_field"))
        ):
            raise ValueError("replay assertion inventory entry is invalid")
        identity = item["assertion_id"]
        coordinate = (item["case_id"], item["observable_field"])
        if identity in identities or coordinate in coordinates:
            raise ValueError("replay assertion inventory contains duplicates")
        identities.add(identity)
        coordinates.add(coordinate)
    expected = dict(value)
    actual_sha = expected.pop("assertion_inventory_sha256")
    if hashlib.sha256(_canonical_bytes(expected)).hexdigest() != actual_sha:
        raise ValueError("replay assertion inventory sha256 drifted")


def assertion_id_for(
    inventory: dict[str, Any], case_id: str, observable_field: str
) -> str:
    validate_replay_assertion_inventory(inventory)
    matches = [
        item["assertion_id"]
        for item in inventory["assertions"]
        if item["case_id"] == case_id
        and item["observable_field"] == observable_field
    ]
    if len(matches) != 1:
        raise ValueError("replay assertion coordinate is not unique")
    return matches[0]


def render_assertion_guard(
    actual: str,
    expected: str,
    assertion_id: str,
    *,
    indent: str,
) -> str:
    if not ASSERTION_ID_RE.fullmatch(assertion_id):
        raise ValueError("replay assertion id is invalid")
    marker = json.dumps(ASSERTION_MARKER_PREFIX + assertion_id)
    return f"{indent}if {actual} != {expected} {{ panic!({marker}); }}\n"


def validate_inventory_replay_source(
    plan: dict[str, Any], inventory: dict[str, Any], replay_source: str
) -> None:
    from validation.tools.replay_call_plan import replay_call_plan_marker

    validate_replay_assertion_inventory(inventory)
    if inventory["plan_sha256"] != plan.get("plan_sha256"):
        raise ValueError("replay assertion inventory plan binding drifted")
    if replay_source.count(replay_call_plan_marker(plan).rstrip("\n")) != 1:
        raise ValueError("replay call plan marker is missing or duplicated")
    validate_inventory_source_markers(inventory, replay_source)


def validate_inventory_source_markers(
    inventory: dict[str, Any], replay_source: str
) -> None:
    validate_replay_assertion_inventory(inventory)
    expected = {
        ASSERTION_MARKER_PREFIX + item["assertion_id"]
        for item in inventory["assertions"]
    }
    observed = set(
        re.findall(
            re.escape(ASSERTION_MARKER_PREFIX) + r"[0-9a-f]{64}",
            replay_source,
        )
    )
    if observed != expected or any(replay_source.count(item) != 1 for item in expected):
        raise ValueError("replay assertion source markers drifted from inventory")


def validate_inventory_fixture_identity(
    inventory: dict[str, Any], fixture_identity: Any
) -> None:
    validate_replay_assertion_inventory(inventory)
    if not isinstance(fixture_identity, dict):
        raise ValueError("replay assertion fixture identity is missing")
    cases = fixture_identity.get("cases")
    behavior_fields = fixture_identity.get("behavior_fields")
    if not isinstance(cases, list) or not isinstance(behavior_fields, list):
        raise ValueError("replay assertion fixture identity is incomplete")
    expected_cases = [
        item.get("id") for item in cases if isinstance(item, dict)
    ]
    observed_cases = list(
        dict.fromkeys(item["case_id"] for item in inventory["assertions"])
    )
    observed_fields = set(
        item["observable_field"] for item in inventory["assertions"]
    )
    if (
        len(expected_cases) != len(cases)
        or expected_cases != observed_cases
        or not behavior_fields
        or not all(_label(item) for item in behavior_fields)
        or not observed_fields.issubset(set(behavior_fields))
    ):
        raise ValueError("replay assertion inventory drifted from fixture identity")


def validated_runtime_localization(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict) or set(value) != {"case_id", "observable_field"}:
        return None
    if not _label(value.get("case_id")) or not _label(value.get("observable_field")):
        return None
    return {
        "case_id": value["case_id"],
        "observable_field": value["observable_field"],
    }


def _observable_fields(plan: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    if plan.get("schema_version") == 2:
        for key in ("identity_assertions", "pointer_identity_assertions"):
            for item in plan.get(key, []):
                if isinstance(item, dict) and _label(item.get("fixture_field")):
                    fields.append(item["fixture_field"])
    for item in plan.get("assertions", []):
        if isinstance(item, dict) and _label(item.get("fixture_field")):
            fields.append(item["fixture_field"])
    runtime = plan.get("scripted_runtime")
    if isinstance(runtime, dict):
        for probe in runtime.get("probes", []):
            expected = probe.get("expected") if isinstance(probe, dict) else None
            field = expected.get("field") if isinstance(expected, dict) else None
            if _label(field):
                fields.append(field)
            fields_list = expected.get("fields") if isinstance(expected, dict) else None
            if isinstance(fields_list, list) and len(fields_list) == 1 and _label(fields_list[0]):
                fields.append(fields_list[0])
    return fields


def _label(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value.encode("utf-8")) <= MAX_LABEL_BYTES
        and not any(character in value for character in "\x00\r\n")
    )


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")


__all__ = [
    "ASSERTION_MARKER_PREFIX",
    "assertion_id_for",
    "build_replay_assertion_inventory",
    "render_assertion_guard",
    "validate_inventory_replay_source",
    "validate_inventory_fixture_identity",
    "validate_inventory_source_markers",
    "validate_replay_assertion_inventory",
    "validated_runtime_localization",
]
