from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .context_contracts import canonical
from .context_frontier_reference import context_frontier_reference as reference
from .context_required_facts import context_retrieval_ready
from .context_frontier_wave_selection_validation import (
    validate_context_frontier_wave_selection,
)


_POLICY = "host-context-frontier-wave-materialization-v1"
_CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}
_OUTPUT_KEYS = {
    "schema_version", "artifact_kind", "policy", "run_id", "unit_id",
    "wave_index", "selection_directives", "selected_deferred_fact_refs",
    "selected_deferred_fact_set_sha256", "host_failure_fact_refs",
    "host_failure_fact_set_sha256", "supplemental_page_id",
    "selection_ready", "requires_host_recompute", "claim_boundary", "sha256",
}


def materialize_context_frontier_wave_selection(
    directives: Mapping[str, Any], *,
    directives_reference: Mapping[str, Any],
    context_bundle: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    retrieval: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    selection = validate_context_frontier_wave_selection(
        directives,
        directives_reference=directives_reference,
        context_bundle=context_bundle,
    )
    unit_id = selection["unit_id"]
    prepared = [dict(item) for item in entries]
    if not prepared or any(item.get("scc_id") != unit_id for item in prepared):
        raise ValueError("wave materialization entries span context groups")
    facts = _facts(context_bundle)
    visible = {
        digest for item in prepared for digest in item.get("fact_refs", [])
    }
    selected = selection["allowed_deferred_fact_refs"]
    interfaces = selection["required_interface_fact_refs"]
    if any(digest not in facts or digest in visible for digest in selected):
        raise ValueError("wave materialization deferred fact scope drifted")
    if any(digest not in visible for digest in interfaces):
        raise ValueError("wave materialization interface is not in required context")
    host_records = selection["host_failure_facts"]
    host_facts = {item["sha256"]: item["fact"] for item in host_records}
    supplemental = [*selected, *sorted(host_facts)]
    page_id = None
    if supplemental:
        part_index = max(
            int(item["page_metadata"]["part_index"]) for item in prepared
        ) + 1
        materialized = {
            "wave_index": selection["wave_index"],
            "scc_id": unit_id,
            "classification": "frontier-wave-expansion",
            "dependency_count": 0,
            "dependency_set_sha256": content_sha256(interfaces),
            "part_index": part_index,
            "facts": [
                {"sha256": digest, **dict((host_facts | facts)[digest])}
                for digest in supplemental
            ],
        }
        compact = canonical(materialized)
        page_id = "page-wave-" + hashlib.sha256(compact).hexdigest()[:24]
        payload = canonical_json_bytes(materialized)
        prepared.append({
            "scc_id": unit_id,
            "page_id": page_id,
            "fact_refs": supplemental,
            "payload": payload,
            "page_metadata": {
                **{key: value for key, value in materialized.items() if key != "facts"},
                "page_id": page_id,
                "fact_refs": supplemental,
                "materialized_bytes": len(compact),
                "estimated_tokens": len(payload),
                "materialized_sha256": hashlib.sha256(compact).hexdigest(),
            },
        })
    rebound = _dynamic_retrieval(
        retrieval, selection, directives_reference, selected, host_records,
    )
    output_payload = {
        "schema_version": 1,
        "artifact_kind": "context-frontier-wave-selection-materialization",
        "policy": _POLICY,
        "run_id": selection["run_id"],
        "unit_id": unit_id,
        "wave_index": selection["wave_index"],
        "selection_directives": reference(directives_reference),
        "selected_deferred_fact_refs": list(selected),
        "selected_deferred_fact_set_sha256": content_sha256(selected),
        "host_failure_fact_refs": sorted(host_facts),
        "host_failure_fact_set_sha256": content_sha256(sorted(host_facts)),
        "supplemental_page_id": page_id,
        "selection_ready": context_retrieval_ready({"retrieval": rebound}),
        "requires_host_recompute": False,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    output = {**output_payload, "sha256": content_sha256(output_payload)}
    return prepared, rebound, validate_context_frontier_wave_materialization(output)


def validate_context_frontier_wave_materialization(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OUTPUT_KEYS:
        raise ValueError("wave selection materialization shape is invalid")
    result = dict(value)
    payload = {key: item for key, item in result.items() if key != "sha256"}
    selected = _sha_list(result.get("selected_deferred_fact_refs"))
    host = _sha_list(result.get("host_failure_fact_refs"))
    if (
        result.get("schema_version") != 1
        or result.get("artifact_kind")
        != "context-frontier-wave-selection-materialization"
        or result.get("policy") != _POLICY
        or not _text(result.get("run_id"))
        or not _text(result.get("unit_id"))
        or not _count(result.get("wave_index"))
        or result.get("selected_deferred_fact_set_sha256") != content_sha256(selected)
        or result.get("host_failure_fact_set_sha256") != content_sha256(host)
        or not isinstance(result.get("selection_ready"), bool)
        or result.get("requires_host_recompute") is not False
        or result.get("claim_boundary") != _CLAIM_BOUNDARY
        or result.get("sha256") != content_sha256(payload)
    ):
        raise ValueError("wave selection materialization binding drifted")
    reference(result.get("selection_directives"))
    page_id = result.get("supplemental_page_id")
    if page_id is not None and not _text(page_id):
        raise ValueError("wave selection supplemental page identity is invalid")
    return result


def _dynamic_retrieval(
    retrieval: Mapping[str, Any], selection: Mapping[str, Any],
    artifact: Mapping[str, Any], selected: list[str], hosts: list[Any],
) -> dict[str, Any]:
    value = {
        key: item for key, item in retrieval.items()
        if key not in {
            "selection_receipt_sha256", "materialized_page_set_sha256",
            "selection_materialization_sha256",
        }
    }
    value.update({
        "frontier_wave_selection_policy": _POLICY,
        "frontier_wave_selection_sha256": selection["sha256"],
        "frontier_wave_selection_artifact_sha256": artifact["sha256"],
        "frontier_wave_selection_seed_sha256": selection["input_bindings"][
            "wave_selection_seed_sha256"
        ],
        "frontier_selected_deferred_fact_set_sha256": content_sha256(selected),
        "frontier_host_failure_fact_set_sha256": content_sha256(hosts),
    })
    receipt_payload = {key: item for key, item in value.items() if key != "fact_refs"}
    value["selection_receipt_sha256"] = hashlib.sha256(
        canonical(receipt_payload)
    ).hexdigest()
    return value


def _facts(value: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = value.get("shared_facts")
    if not isinstance(raw, Mapping):
        raise ValueError("wave materialization shared facts are invalid")
    return {str(key): item for key, item in raw.items() if isinstance(item, Mapping)}


def _sha_list(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or value != sorted(set(value))
        or any(not isinstance(item, str) or len(item) != 64 for item in value)
    ):
        raise ValueError("wave materialization SHA-256 list is invalid")
    return list(value)


def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 256


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


__all__ = [
    "materialize_context_frontier_wave_selection",
    "validate_context_frontier_wave_materialization",
]
