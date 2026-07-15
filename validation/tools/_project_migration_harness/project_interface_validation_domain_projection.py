from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .clang_fact_commands import (
    build_clang_fact_plans,
    validate_clang_fact_plan,
)
from .project_candidate_domain import (
    candidate_domain_context_sha256,
    validate_candidate_project_domain,
)
from .project_interface_validation_domain_contract import CLAIM_BOUNDARY, DOMAIN_KIND


def bind_contract_dag(
    contract: Mapping[str, Any], source_domain: Mapping[str, Any],
) -> None:
    dag = source_domain["dag"]
    parent = dag["parent"]
    bound = dag["child"]["artifact"] if parent is None else parent["artifact"]
    if bound != contract["integration_manifest"]:
        raise ValueError("interface validation contract DAG drifted")
    if parent is None and (
        dag["child"]["edge_set_sha256"]
        != content_sha256(contract["dependency_edges"])
        or dag["child"]["order_sha256"] != content_sha256(contract["dag_order"])
    ):
        raise ValueError("interface validation contract DAG projection drifted")


def candidate_domain(
    run_id: str, contract: Mapping[str, Any], ir: Mapping[str, Any],
    source_domain: Mapping[str, Any], digest: str, manifest: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    if source_domain["dag"]["parent"] is None:
        return validate_candidate_project_domain(
            run_id=run_id, migration_contract=contract, rust_project_ir=ir,
            rust_project_binding_sha256=source_domain[
                "rust_project_binding_sha256"
            ], candidate_set_sha256=digest, candidate_set_manifest=manifest,
            artifact_root=artifact_root,
        )
    members = [{
        "unit_id": item["unit_id"], "artifact_id": item["artifact_id"],
        "content_sha256": item["source"]["sha256"],
    } for item in ir["bindings"]["candidates"]]
    compact = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    if (
        hashlib.sha256(compact.encode("utf-8")).hexdigest() != digest
        or manifest.get("members") != members
        or manifest.get("run_context_sha256") != contract["context_sha256"]
        or manifest.get("dag_sha256") != contract["dag_sha256"]
        or manifest.get("integration_manifest_sha256")
        != contract["integration_manifest"]["sha256"]
        or manifest.get("roots") != [item["unit_id"] for item in members]
    ):
        raise ValueError("interface validation cohort candidate set drifted")
    projection = {
        "run_id": run_id, "run_context_sha256": contract["context_sha256"],
        "dag_sha256": contract["dag_sha256"],
        "integration_manifest": dict(contract["integration_manifest"]),
        "candidate_set_sha256": digest,
        "candidate_set_manifest_sha256": content_sha256(manifest),
        "rust_project_ir_sha256": ir["ir_sha256"],
        "rust_project_interface_sha256": ir["interface_sha256"],
        "rust_project_binding_sha256": source_domain[
            "rust_project_binding_sha256"
        ],
    }
    return {**projection, "candidate_domain_context_sha256": (
        candidate_domain_context_sha256(projection)
    )}


def clang_plan_projection(
    build_irs: list[dict[str, Any]], portable: Mapping[str, Any],
) -> dict[str, Any]:
    projections = []
    translation_units = 0
    for build_ir in build_irs:
        translation_units += len(build_ir["translation_units"])
        for plan in build_clang_fact_plans(build_ir, portable):
            checked = validate_clang_fact_plan(plan, build_ir, portable)
            projections.append({
                "build_ir_semantic_sha256": checked["build_ir_semantic_sha256"],
                "unit_id": checked["unit_id"], "gate": checked["gate"],
                "plan_sha256": checked["plan_sha256"],
                "target_context_sha256": checked["target_context_sha256"],
            })
    projections.sort(key=lambda item: (
        item["build_ir_semantic_sha256"], item["unit_id"], item["gate"],
    ))
    if len(projections) != translation_units * 2 or len({
        item["plan_sha256"] for item in projections
    }) != len(projections):
        raise ValueError("interface validation Clang plan coverage invalid")
    targets = sorted({item["target_context_sha256"] for item in projections})
    return {
        "plan_count": len(projections),
        "translation_unit_count": translation_units,
        "plan_set_sha256": content_sha256(projections),
        "target_context_set_sha256": content_sha256(targets),
    }


def domain_payload(
    contract: Mapping[str, Any], ir_ref: Mapping[str, Any], ir: Mapping[str, Any],
    sources: Mapping[str, Any], manifest: Mapping[str, Any], candidate_sha: str,
    b2a_ref: Mapping[str, Any], b2a: Mapping[str, Any],
    toolchain: Mapping[str, Any], plans: Mapping[str, Any],
) -> dict[str, Any]:
    portable = toolchain["portable_binding"]
    core = {
        "schema_version": 1, "artifact_kind": DOMAIN_KIND, "status": "ready",
        "run": {
            "run_id": contract["run_id"],
            "run_context_sha256": contract["context_sha256"],
            "dag_sha256": contract["dag_sha256"],
            "integration_manifest": dict(contract["integration_manifest"]),
        },
        "rust_project_ir": {
            "reference": dict(ir_ref), "ir_sha256": ir["ir_sha256"],
            "interface_sha256": ir["interface_sha256"],
            "binding_sha256": sources["rust_project_binding_sha256"],
        },
        "source_domain": {
            "domain_sha256": sources["domain_sha256"],
            "source_repository_binding_sha256": sources[
                "source_repository_binding_sha256"
            ], "dag_sha256": content_sha256(sources["dag"]),
            "build_ir_set_sha256": sources["build_ir_set_sha256"],
            "build_ir_count": len(sources["build_ir_set"]),
            "translation_unit_count": plans["translation_unit_count"],
            "candidate_source_set_sha256": sources[
                "candidate_source_set_sha256"
            ], "candidate_count": len(sources["candidate_sources"]),
        },
        "candidate_set": {
            "sha256": candidate_sha,
            "manifest_sha256": content_sha256(manifest),
            "scope": manifest["scope"], "member_count": len(manifest["members"]),
        },
        "candidate_project_verification": {
            "reference": dict(b2a_ref), "status": b2a["status"],
            "verification_context_sha256": b2a["verification_context_sha256"],
            "generation_sha256": b2a["materialization"]["generation"]["sha256"],
            "cargo_fact_binding_sha256": b2a["cargo_fact_evidence"][
                "binding_sha256"
            ],
        },
        "clang_toolchain": {
            "receipt": dict(toolchain),
            "receipt_sha256": toolchain["receipt_sha256"],
            "portable_binding_sha256": portable["binding_sha256"],
            "target": portable["target"]["value"],
            "binary_sha256": portable["binary"]["sha256"],
        },
        "clang_fact_plans": dict(plans), "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    return {**core, "domain_sha256": content_sha256(core)}


__all__ = [
    "bind_contract_dag", "candidate_domain", "clang_plan_projection",
    "domain_payload",
]
