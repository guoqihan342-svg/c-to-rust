from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any


_BLOCKING_BOUNDARIES = {
    "make_command_graph_incomplete",
    "make_generated_output_graph_incomplete",
    "make_external_dependency_resolution_unverified",
    "make_link_argument_classification_incomplete",
    "make_repository_input_closure_incomplete",
    "make_repository_input_snapshot_missing",
    "make_repository_input_snapshot_unverified",
}


def project_make_closure_artifacts(
    build_ir: Mapping[str, Any], build_ir_reference: Mapping[str, Any],
    report_reference: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    claim = build_ir["claim_boundary"]
    blockers = _closure_blockers(build_ir["boundaries"])
    build_ir_verified = verification.get("status") == "verified"
    closure_claimed = claim.get("closure_complete") is True
    resolution_complete = (
        claim.get("external_dependency_resolution_complete") is True
    )
    unresolved_count = claim.get("unresolved_external_dependency_count")
    if not resolution_complete and not any(
        item.get("kind") == "make_external_dependency_resolution_unverified"
        for item in blockers
    ):
        blockers.append({"kind": "make_external_dependency_resolution_unverified"})
    if resolution_complete and unresolved_count != 0:
        blockers.append({"kind": "make_external_dependency_resolution_claim_invalid"})
    if not build_ir_verified:
        blockers.append({"kind": "make_build_ir_verification_blocked"})
    if not closure_claimed and not blockers:
        blockers.append({"kind": "make_closure_claim_inconsistent"})
    closure_ready = (
        closure_claimed and resolution_complete and build_ir_verified
        and not blockers
    )
    closure = {
        "schema_version": 1,
        "artifact_kind": "project-migration-make-target-closure",
        "status": (
            "ready" if closure_ready else
            "ready_with_boundaries" if build_ir_verified else "blocked"
        ),
        "report": dict(report_reference),
        "build_ir": dict(build_ir_reference),
        "target_closure": list(build_ir["target_closure"]),
        "blockers": blockers,
        "command_graph_complete": claim["command_graph_complete"],
        "generated_output_graph_complete": claim[
            "generated_output_graph_complete"
        ],
        "repository_input_closure_complete": claim[
            "repository_input_closure_complete"
        ],
        "external_dependencies_complete": claim[
            "external_dependencies_complete"
        ],
        "generated_outputs_materialized": claim[
            "generated_outputs_materialized"
        ],
        "external_dependency_resolution_complete": claim[
            "external_dependency_resolution_complete"
        ],
        "external_dependency_resolution_kind": claim[
            "external_dependency_resolution_kind"
        ],
        "external_dependency_resolution_records": copy.deepcopy(claim[
            "external_dependency_resolution_records"
        ]),
        "boundaries": [dict(item) for item in build_ir["boundaries"]],
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    closure_verification = {
        "schema_version": 1,
        "artifact_kind": "project-migration-make-target-closure-verification",
        "status": (
            "verified" if closure_ready else
            "verified_with_boundaries" if build_ir_verified else "blocked"
        ),
        "report_sha256": report_reference["sha256"],
        "build_ir_sha256": build_ir_reference["sha256"],
        "blockers": _verification_blockers(
            blockers, verification, build_ir_verified,
        ),
        "command_graph_verified": (
            build_ir_verified and claim["command_graph_complete"]
        ),
        "generated_output_graph_complete": claim[
            "generated_output_graph_complete"
        ],
        "repository_input_closure_complete": claim[
            "repository_input_closure_complete"
        ],
        "external_dependencies_complete": claim[
            "external_dependencies_complete"
        ],
        "generated_outputs_materialized": claim[
            "generated_outputs_materialized"
        ],
        "external_dependency_resolution_complete": resolution_complete,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return closure, closure_verification, closure_ready


def _closure_blockers(
    boundaries: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(dict(boundary))
        for boundary in boundaries
        if boundary.get("kind") in _BLOCKING_BOUNDARIES
    ]


def _verification_blockers(
    closure_blockers: list[dict[str, Any]], verification: Mapping[str, Any],
    build_ir_verified: bool,
) -> list[dict[str, Any]]:
    combined = [copy.deepcopy(item) for item in closure_blockers]
    if not build_ir_verified:
        combined.extend(
            copy.deepcopy(dict(item))
            for item in verification.get("blockers", [])
            if isinstance(item, Mapping)
        )
    unique = {}
    for item in combined:
        key = repr(sorted(item.items()))
        unique[key] = item
    return [unique[key] for key in sorted(unique)]


__all__ = ["project_make_closure_artifacts"]
