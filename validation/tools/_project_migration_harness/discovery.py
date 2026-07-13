from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_facts import (
    detect_build_system_facts,
    detect_generated_build_facts,
    is_linklike,
)
from .compile_database import parse_compile_entry
from .discovery_database import load_compile_database, select_compile_database
from .discovery_variants import finalize_variants
from .generated_closure import discover_generated_build_closure


CLAIM_BOUNDARY = {
    "role": "repository_input_discovery_only",
    "semantic_gate": False,
    "build_commands_executed": False,
    "must_not_claim": [
        "build success",
        "translation success",
        "semantic equivalence",
        "whole-project migration",
    ],
}


def discover_project(
    repo_root: str | Path,
    compile_database: str | Path | None = None,
    max_units: int = 10_000,
) -> dict[str, Any]:
    root = Path(repo_root)
    empty_facts = {
        "status": "unavailable",
        "systems": [],
        "markers": [],
        "blockers": [],
        "build_commands_executed": False,
    }
    if isinstance(max_units, bool) or not isinstance(max_units, int) or max_units < 1:
        return report(empty_facts, {"status": "unresolved"}, [], [], ["max_units_invalid"])
    if not root.exists() or not root.is_dir():
        return report(
            empty_facts,
            {"status": "unresolved"},
            [],
            [],
            ["repository_root_invalid"],
        )
    if is_linklike(root):
        return report(
            empty_facts,
            {"status": "unresolved"},
            [],
            [],
            ["repository_root_linked"],
        )
    root = root.resolve()
    build_facts = detect_build_system_facts(root)
    build_blockers = list(build_facts.get("blockers", []))
    database_binding, database_path, selection_blockers = select_compile_database(
        root, compile_database
    )
    if database_path is None:
        return report(
            build_facts,
            database_binding,
            [],
            [],
            build_blockers + selection_blockers,
        )
    payload, load_blocker = load_compile_database(
        database_path, str(database_binding.get("sha256", ""))
    )
    if load_blocker is not None:
        return report(
            build_facts,
            database_binding,
            [],
            [],
            build_blockers + selection_blockers + [load_blocker],
        )
    assert payload is not None
    database_binding["entry_count"] = len(payload)
    parsed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    blockers = list(selection_blockers)
    blockers.extend(build_blockers)
    for entry_index, entry in enumerate(payload):
        unit, rejected_entry = parse_compile_entry(entry, entry_index, root)
        if unit is not None:
            parsed.append(unit)
        if rejected_entry is not None:
            rejected.append(rejected_entry)
            if rejected_entry["blocking"]:
                blockers.append(rejected_entry["reason"])
    units, variant_rejections, variant_blockers = finalize_variants(parsed, max_units)
    rejected.extend(variant_rejections)
    blockers.extend(variant_blockers)
    if not parsed:
        blockers.append("no_c_translation_units")
    generated_facts = detect_generated_build_facts(root, database_path)
    build_facts["generated_stage"] = generated_facts
    generated_closure = discover_generated_build_closure(
        root, database_path, generated_facts, units
    )
    rejected.sort(key=lambda item: (item["entry_index"], item["reason"]))
    return report(
        build_facts,
        database_binding,
        units,
        rejected,
        blockers,
        generated_closure,
    )


def report(build_facts: dict[str, Any], database: dict[str, Any],
           units: list[dict[str, Any]], rejected: list[dict[str, Any]],
           blockers: list[str],
           generated_closure: dict[str, Any] | None = None) -> dict[str, Any]:
    unique_blockers = sorted(set(blockers))
    status = "ready" if units and not unique_blockers else "blocked"
    claim_boundary = dict(CLAIM_BOUNDARY)
    claim_boundary["translation_units_complete"] = status == "ready"
    claim_boundary["generated_build_closure_complete"] = (
        isinstance(generated_closure, dict)
        and generated_closure.get("status") == "ready"
    )
    return {
        "schema_version": 1,
        "status": status,
        "build_system_facts": build_facts,
        "compile_database": database,
        "translation_units": units,
        "rejected_entries": rejected,
        "generated_build_closure": generated_closure or {
            "schema_version": 1,
            "status": "unavailable",
            "blockers": [{"kind": "compile_database_unavailable"}],
        },
        "blockers": unique_blockers,
        "claim_boundary": claim_boundary,
    }


__all__ = ["discover_project"]
