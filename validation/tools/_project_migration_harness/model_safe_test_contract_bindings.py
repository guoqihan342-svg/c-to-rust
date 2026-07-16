from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifact_write_once import write_once_json_artifact
from .artifacts import content_sha256
from .model_safe_test_contract import (
    WITHHELD_FIELDS,
    build_model_safe_test_contract,
    validate_test_contract_reference,
    validate_test_inventory_binding,
)


def materialize_model_safe_test_contracts(
    inventory: Mapping[str, Any], dag: Mapping[str, Any], *,
    output: Path, out_root_rel: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_test_inventory_binding(inventory)
    groups = dag.get("groups")
    if not isinstance(groups, list):
        raise ValueError("test contract migration groups are invalid")
    bindings: list[dict[str, Any]] = []
    if inventory.get("status") == "ready":
        for group in groups:
            if not isinstance(group, Mapping):
                raise ValueError("test contract migration group is invalid")
            group_id = group.get("group_id")
            scope = group.get("target_scope")
            if not isinstance(group_id, str) or not group_id:
                raise ValueError("test contract group identity is invalid")
            if not isinstance(scope, Mapping):
                continue
            contract = build_model_safe_test_contract(
                inventory, group_id=group_id, target_scope=scope,
            )
            if contract["test_count"] == 0:
                continue
            reference = write_once_json_artifact(
                output,
                f"plan/model-safe-test-contracts/{contract['contract_sha256']}.json",
                contract,
            )
            bindings.append({
                "group_id": group_id,
                "artifact": _prefix(reference, out_root_rel),
            })
    bindings.sort(key=lambda item: item["group_id"])
    index_payload = {
        "schema_version": 1,
        "artifact_kind": "model-safe-project-test-contract-index",
        "status": "ready" if bindings else "unavailable",
        "inventory_sha256": inventory["inventory_sha256"],
        "contracts": bindings,
        "withheld_fields": list(WITHHELD_FIELDS),
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    index = {**index_payload, "index_sha256": content_sha256(index_payload)}
    index_reference = write_once_json_artifact(
        output,
        f"plan/model-safe-test-contract-index-{index['index_sha256']}.json",
        index,
    )
    return bindings, index_reference


def portfolio_test_contract_references(
    portfolio: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    raw = portfolio.get("model_safe_test_contracts", [])
    if not isinstance(raw, list):
        raise ValueError("portfolio test contract bindings are invalid")
    result: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"group_id", "artifact"}:
            raise ValueError("portfolio test contract binding is invalid")
        group_id = item.get("group_id")
        if not isinstance(group_id, str) or not group_id or group_id in result:
            raise ValueError("portfolio test contract group binding is invalid")
        result[group_id] = validate_test_contract_reference(item.get("artifact"))
    if list(result) != sorted(result):
        raise ValueError("portfolio test contract bindings are not canonical")
    return result


def _prefix(reference: Mapping[str, Any], root: str) -> dict[str, Any]:
    return {**dict(reference), "path": f"{root.rstrip('/')}/{reference['path']}"}


__all__ = [
    "materialize_model_safe_test_contracts",
    "portfolio_test_contract_references",
]
