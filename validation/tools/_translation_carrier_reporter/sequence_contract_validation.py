from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .record_contract import noalias_pairs, normalize_c_type, require_dict


def validate_noalias(
    spec: dict[str, Any],
    contract: dict[str, Any],
    entry_by_name: dict[str, dict[str, Any]],
) -> None:
    declared = noalias_pairs(contract.get("noalias_required"), "noalias_required")
    pointer = require_dict(
        spec.get("c_boundary", {}).get("pointer_contract"), "c_boundary.pointer_contract"
    )
    if pointer.get("aliasing_proven") is not True:
        raise ReporterError("pointer aliasing metadata is not proven")
    if declared != noalias_pairs(pointer.get("noalias_required"), "pointer noalias_required"):
        raise ReporterError("noalias contract drifted")
    roots = {
        str(item["entry_parameter"])
        for item in contract["external_callee"]["arguments"]
        if item["mode"] == "record_ref"
        and entry_by_name[str(item["entry_parameter"])]["pass_mode"] == "mutable_ref"
    }
    roots.add(str(contract["state_output"]["parameter"]))
    ordered = sorted(roots)
    required = {
        (ordered[left], ordered[right])
        for left in range(len(ordered))
        for right in range(left + 1, len(ordered))
    }
    if not required:
        raise ReporterError("noalias contract must be non-empty")
    if declared != required:
        raise ReporterError("noalias contract must cover the complete mutable root pair set")


def validate_signatures(
    spec: dict[str, Any],
    contract: dict[str, Any],
    entry_by_name: dict[str, dict[str, Any]],
) -> None:
    boundary = require_dict(spec.get("c_boundary"), "c_boundary")
    signatures = boundary.get("signatures")
    if not isinstance(signatures, list):
        raise ReporterError("c_boundary.signatures must be a list")
    entry_matches = [item for item in signatures if isinstance(item, dict) and item.get("function") == spec.get("function_name")]
    if len(entry_matches) != 1 or normalize_c_type(entry_matches[0].get("return_type")) not in {"bool", "_Bool"}:
        raise ReporterError("sequence replay entry signature drifted")
    entries = contract["entry_arguments"]
    actual_entry = [item for item in entry_matches[0].get("parameters", []) if isinstance(item, dict)]
    if [item.get("name") for item in actual_entry] != [item["parameter"] for item in entries]:
        raise ReporterError("sequence replay entry parameters drifted")
    if [normalize_c_type(item.get("c_type")) for item in actual_entry] != [
        normalize_c_type(item["c_type"]) for item in entries
    ]:
        raise ReporterError("sequence replay entry parameter types drifted")
    if [item.get("direction") for item in actual_entry] != [item["direction"] for item in entries]:
        raise ReporterError("sequence replay entry parameter directions drifted")

    external = contract["external_callee"]
    declarations = [
        item
        for item in boundary.get("external_direct_callees", [])
        if isinstance(item, dict) and item.get("name") == external["name"]
    ]
    if len(declarations) != 1:
        raise ReporterError("sequence replay external declaration drifted")
    external_matches = [
        item
        for item in signatures
        if isinstance(item, dict)
        and item.get("function") == external["name"]
        and item.get("id") == declarations[0].get("signature_ref")
    ]
    if len(external_matches) != 1 or normalize_c_type(external_matches[0].get("return_type")) != "uint32_t":
        raise ReporterError("sequence replay external signature drifted")
    observations = external["arguments"]
    actual_external = [item for item in external_matches[0].get("parameters", []) if isinstance(item, dict)]
    expected_types = [
        (
            f"struct {entry_by_name[str(item['entry_parameter'])]['rust_type']} *"
            if item["mode"] == "record_ref"
            else "uint32_t"
        )
        for item in observations
    ]
    if [item.get("name") for item in actual_external] != [item["parameter"] for item in observations]:
        raise ReporterError("sequence replay external parameters drifted")
    if [normalize_c_type(item.get("c_type")) for item in actual_external] != [
        normalize_c_type(item) for item in expected_types
    ]:
        raise ReporterError("sequence replay external parameter types drifted")
