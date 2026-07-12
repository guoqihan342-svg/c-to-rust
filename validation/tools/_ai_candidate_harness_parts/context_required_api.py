from __future__ import annotations

import json
import re
from typing import Any

from .context_security import sha256_bytes


REFERENCE_RE = re.compile(r"^&(?:(?P<lifetime>'[A-Za-z_][A-Za-z0-9_]*)\s+)?(?P<mutable>mut\s+)?(?P<target>.+)$")


def build_required_candidate_api(plan: dict[str, Any]) -> dict[str, Any]:
    parameters = [dict(parameter) for parameter in plan["parameters"]]
    return_type = str(plan["return_type"])
    lifetime_binding = _return_lifetime_binding(plan, parameters, return_type)
    if lifetime_binding is not None:
        parameter_index, lifetime = lifetime_binding
        parameters[parameter_index]["rust_type"] = _bind_reference_lifetime(
            str(parameters[parameter_index]["rust_type"]), lifetime
        )
        return_type = _bind_reference_lifetime(return_type, lifetime)

    signature = _function_signature(
        plan,
        parameters,
        return_type,
        lifetime="'out" if lifetime_binding is not None else None,
    )
    supporting_types_source = "\n\n".join(
        _supporting_type_source(item) for item in plan["supporting_types"]
    )
    payload = {
        "schema_version": 1,
        "status": "bound",
        "api_name": plan["api_name"],
        "plan_sha256": plan["plan_sha256"],
        "signature": signature,
        "supporting_types_source": supporting_types_source,
        "return_lifetime_from": (
            parameters[lifetime_binding[0]]["name"]
            if lifetime_binding is not None
            else None
        ),
    }
    payload["contract_sha256"] = sha256_bytes(_canonical_bytes(payload))
    return payload


def validate_required_candidate_api(plan: dict[str, Any], value: Any) -> None:
    if value != build_required_candidate_api(plan):
        raise ValueError("required candidate API drifted from ReplayCallPlan")


def _return_lifetime_binding(
    plan: dict[str, Any],
    parameters: list[dict[str, Any]],
    return_type: str,
) -> tuple[int, str] | None:
    if REFERENCE_RE.fullmatch(return_type) is None:
        return None
    identities = plan.get("identity_assertions")
    if not isinstance(identities, list) or len(identities) != 1:
        raise ValueError("reference return requires one identity assertion")
    identity = identities[0]
    expected_binding = identity.get("expected_binding") if isinstance(identity, dict) else None
    matches = [
        index
        for index, parameter in enumerate(parameters)
        if isinstance(parameter.get("source"), dict)
        and parameter["source"].get("binding") == expected_binding
    ]
    if len(matches) != 1:
        raise ValueError("reference return identity binding is ambiguous")
    parameter_type = str(parameters[matches[0]]["rust_type"])
    if REFERENCE_RE.fullmatch(parameter_type) is None:
        raise ValueError("reference return identity parameter is not a reference")
    return matches[0], "'out"


def _bind_reference_lifetime(rust_type: str, lifetime: str) -> str:
    match = REFERENCE_RE.fullmatch(rust_type)
    if match is None:
        raise ValueError("required candidate API lifetime target is not a reference")
    existing = match.group("lifetime")
    if existing not in {None, lifetime}:
        raise ValueError("required candidate API has a conflicting explicit lifetime")
    mutable = "mut " if match.group("mutable") else ""
    return f"&{lifetime} {mutable}{match.group('target')}"


def _function_signature(
    plan: dict[str, Any],
    parameters: list[dict[str, Any]],
    return_type: str,
    *,
    lifetime: str | None,
) -> str:
    visibility = "" if plan["visibility"] == "private" else f"{plan['visibility']} "
    unsafe = "unsafe " if plan["unsafe"] else ""
    abi = 'extern "C" ' if plan["abi"] == "C" else ""
    generics = f"<{lifetime}>" if lifetime is not None else ""
    arguments = ", ".join(
        f"{parameter['name']}: {parameter['rust_type']}" for parameter in parameters
    )
    return f"{visibility}{unsafe}{abi}fn {plan['api_name']}{generics}({arguments}) -> {return_type}"


def _supporting_type_source(item: dict[str, Any]) -> str:
    visibility = "" if item["visibility"] == "private" else f"{item['visibility']} "
    fields = "\n".join(
        f"    pub {field['name']}: {field['rust_type']}," for field in item["fields"]
    )
    return f"{visibility}struct {item['name']} {{\n{fields}\n}}"


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = ["build_required_candidate_api", "validate_required_candidate_api"]
