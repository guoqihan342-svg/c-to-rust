from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from pathlib import Path
from typing import Any

from .build_ir import stable_build_id
from .build_ir_external_dependencies import project_link_external_dependencies
from .build_ir_link_occurrences import project_link_authority
from .make_build_ir_link_scan import scan_make_archive, scan_make_link


MAKE_RAW_ROLE = "make-dry-run-report"
def project_make_link_authority(
    repo_root: Path, report: Mapping[str, Any],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind every non-source target to one ordered, fail-closed argv scan."""
    commands = {
        command["ordinal"]: command for command in report.get("commands", [])
        if isinstance(command, Mapping)
    }
    authority_dependencies: list[dict[str, Any]] = []
    resolution_dependencies: list[dict[str, Any]] = []
    contracts: dict[int, dict[str, Any]] = {}
    search_root_count = 0
    for target in targets:
        if target.get("kind") not in {"archive", "link"}:
            continue
        provenance = target.get("provenance")
        ordinal = (
            provenance.get("command_ordinal")
            if isinstance(provenance, Mapping) else None
        )
        command = commands.get(ordinal)
        if command is None or command.get("kind") != target.get("kind"):
            raise ValueError("make_build_ir_link_command_missing")
        raw, resolution_rows = (
            scan_make_archive(command, target, report)
            if target["kind"] == "archive"
            else scan_make_link(repo_root, command, target, report)
        )
        current, boundaries = project_link_external_dependencies(
            raw, target["target_id"], provenance_role=MAKE_RAW_ROLE,
        )
        if boundaries:
            raise ValueError("make_build_ir_native_link_unbound")
        authority = project_link_authority(
            raw, target["target_id"], target["ordered_inputs"], current,
        )
        if authority is None:
            raise ValueError("make_build_ir_link_authority_missing")
        target["ordered_link_arguments"] = list(raw["ordered_system_link_args"])
        target.update(authority)
        authority_dependencies.extend(current)
        resolution_dependencies.extend(
            _resolution_dependencies(target["target_id"], resolution_rows)
        )
        search_root_count += len(raw["search_roots"])
        contracts[int(ordinal)] = {
            "ordered_link_arguments": copy.deepcopy(
                target["ordered_link_arguments"]
            ),
            "ordered_link_occurrences": copy.deepcopy(
                target["ordered_link_occurrences"]
            ),
            "ordered_link_search_roots": copy.deepcopy(
                target["ordered_link_search_roots"]
            ),
        }
    return {
        "authority_dependencies": sorted(
            authority_dependencies, key=lambda item: item["dependency_id"],
        ),
        "resolution_dependencies": sorted(
            resolution_dependencies, key=lambda item: item["dependency_id"],
        ),
        "target_contracts": contracts,
        "unmaterialized_search_root_count": search_root_count,
    }


def _resolution_dependencies(
    target_id: str, rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        arguments = list(row["arguments"])
        ordinal = int(row["ordinal"])
        result.append({
            "dependency_id": stable_build_id("external", {
                "target": target_id, "ordinal": ordinal,
                "arguments": arguments,
            }),
            "kind": row["kind"],
            "name": " ".join(arguments),
            "consumer_target_ids": [target_id],
            "ordinal": ordinal,
            "arguments": arguments,
            "resolved": False,
            "provenance": {"raw_fact_role": MAKE_RAW_ROLE},
        })
    return result


__all__ = ["project_make_link_authority"]
