from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .orchestration_facts import read_artifact_reference


PARENT_DAG_KEY = "parent_migration_dag"


def validate_cohort_dag(payload: Mapping[str, Any], artifact_root: Path) -> None:
    parent = payload.get(PARENT_DAG_KEY)
    if parent is None:
        return
    if not isinstance(parent, Mapping) or set(parent) != {
        "scope", "artifact", "selected_unit_ids",
    } or parent.get("scope") != "verification-dependency-closure":
        raise ValueError("bound cohort parent DAG schema is invalid")
    selected = parent.get("selected_unit_ids")
    if (
        not isinstance(selected, list) or not selected
        or selected != sorted(set(selected)) or set(selected) != set(payload.get("dag", {}))
    ):
        raise ValueError("bound cohort selected units are invalid")
    reference = parent.get("artifact")
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("bound cohort parent DAG reference is invalid")
    try:
        raw = read_artifact_reference(artifact_root, reference)
        full = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("bound cohort parent DAG cannot be reopened") from error
    if (
        len(raw) != reference.get("size_bytes")
        or not isinstance(full, dict) or canonical_json_bytes(full) != raw
        or PARENT_DAG_KEY in full
    ):
        raise ValueError("bound cohort parent DAG content is invalid")
    full_dag, full_order = full.get("dag"), full.get("dag_order")
    if not isinstance(full_dag, dict) or not isinstance(full_order, list):
        raise ValueError("bound cohort parent DAG closure is invalid")
    selected_set = set(selected)
    if not selected_set <= set(full_dag):
        raise ValueError("bound cohort units are outside the parent DAG")
    expected = {}
    for unit_id in selected:
        dependencies = full_dag.get(unit_id)
        if not isinstance(dependencies, list) or any(item not in selected_set for item in dependencies):
            raise ValueError("bound cohort is not dependency closed")
        expected[unit_id] = dependencies
    if payload.get("dag") != expected:
        raise ValueError("bound cohort DAG drifted from its parent")
    if payload.get("dag_order") != [unit for unit in full_order if unit in selected_set]:
        raise ValueError("bound cohort order drifted from its parent")


__all__ = ["PARENT_DAG_KEY", "validate_cohort_dag"]
