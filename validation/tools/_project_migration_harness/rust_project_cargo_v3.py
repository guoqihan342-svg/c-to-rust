from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import cargo_project
from .artifacts import canonical_json_bytes, content_sha256
from .orchestration_facts import read_artifact_reference
from .rust_project_cargo import V3_GENERATOR
from .rust_project_cargo_v3_inputs import (
    accepted_groups, load_v3_candidate_sources, unsafe_policy,
)
from .rust_project_cargo_v3_projection import (
    derive_rust_project_cargo_v3_projection,
)
from .rust_project_cargo_v3_render import (
    EDITION, render_rust_project_cargo_v3_files,
)
from .rust_project_cargo_v3_source_layout import (
    derive_rust_project_cargo_v3_source_layout,
)
from .rust_project_ir_cohort import PARENT_DAG_KEY
from .rust_project_ir_validation import reopen_rust_project_ir_bindings


def reconstruct_cargo_project_v3(
    rust_project_ir: Mapping[str, Any], artifact_root: Path, *,
    max_source_bytes: int = cargo_project.MAX_SOURCE_BYTES,
) -> cargo_project.CargoProjectPlan:
    """Reconstruct a v3 workspace only through reopened, fail-closed facts."""
    try:
        root = Path(artifact_root).resolve(strict=True)
        binding = reopen_rust_project_ir_bindings(rust_project_ir, root)
    except (OSError, TypeError, ValueError) as error:
        _fail("rust_project_ir_binding_invalid", "rust_project_ir", detail=error)
    if rust_project_ir.get("topology_status") != "ready":
        blockers = rust_project_ir.get("topology_blockers")
        code, entity = _first_blocker(blockers, "rust_project_ir_topology_blocked")
        _fail(code, "rust_project_ir", entity)
    candidates = load_v3_candidate_sources(
        rust_project_ir, root, max_source_bytes=max_source_bytes,
    )
    sources = {unit_id: item["source"] for unit_id, item in candidates.items()}
    try:
        layout = derive_rust_project_cargo_v3_source_layout(
            rust_project_ir, sources,
        )
    except (TypeError, ValueError) as error:
        _fail("rust_project_cargo_v3_source_layout_invalid", "cargo_projection",
              detail=error)
    if layout["status"] != "ready":
        blocker = layout["blockers"][0]
        _fail(str(blocker["code"]), "cargo_projection", str(blocker["unit_id"]))
    try:
        projection = derive_rust_project_cargo_v3_projection(
            rust_project_ir, layout,
        )
    except (TypeError, ValueError) as error:
        _fail("rust_project_cargo_v3_projection_invalid", "cargo_projection",
              detail=error)
    if projection["status"] != "ready":
        blocker = projection["blockers"][0]
        _fail(
            str(blocker["code"]), "cargo_projection",
            str(blocker["entity_id"]),
        )
    try:
        files = render_rust_project_cargo_v3_files(
            rust_project_ir, projection, sources,
        )
        dag = _dag_payload(rust_project_ir, root)
        dependencies, order = cargo_project._migration_dag(dag)
        policy = unsafe_policy(candidates, dag.get("unsafe_policy"))
    except cargo_project.ProjectInputError:
        raise
    except (OSError, TypeError, ValueError) as error:
        _fail(str(error), "cargo_render", detail=error)
    if set(order) != set(candidates):
        _fail("rust_project_cargo_v3_dag_candidate_drift", "cargo_render")
    manifest = _manifest(
        rust_project_ir, binding, projection, files,
        accepted_groups(candidates, dependencies), policy,
        "verification-cohort" if PARENT_DAG_KEY in dag else "full-project",
        dependencies, order,
    )
    result = dict(files)
    result[cargo_project.LAST_GOOD_MANIFEST] = cargo_project.canonical_json_bytes(
        manifest,
    )
    return cargo_project.CargoProjectPlan(
        files=result, last_good_manifest=manifest,
    )


def _manifest(
    ir, binding, projection, files, groups, policy, scope, dependencies, order,
) -> dict[str, Any]:
    refs = [_ref(path, data) for path, data in sorted(files.items())]
    targets = [dict(item) for item in projection["targets"]]
    packages = [dict(item) for item in projection["packages"]]
    dag_projection = {
        "dependencies": {
            key: list(dependencies[key]) for key in sorted(dependencies)
        },
        "order": list(order),
    }
    return {
        "schema_version": cargo_project.SCHEMA_VERSION,
        "generator": V3_GENERATOR,
        "generator_policy": {"edition": EDITION, "network": "offline"},
        "rust_project_ir_scope": scope,
        "rust_project_ir_sha256": ir["ir_sha256"],
        "rust_project_interface_sha256": ir["interface_sha256"],
        "rust_project_ir_completeness": dict(ir["interface_completeness"]),
        "domain_binding_sha256": content_sha256(binding),
        "cargo_projection_sha256": projection["projection_sha256"],
        "dag_sha256": hashlib.sha256(
            cargo_project.canonical_json_bytes(dag_projection)
        ).hexdigest(),
        "native_link": {
            "status": "not-required", "requirement_count": 0,
            "resolution_gate": False,
        },
        "c_compilation_facts": binding.get("c_compilation_facts"),
        "cargo_workspace": dict(projection["workspace"]),
        "cargo_packages": packages,
        "cargo_targets": targets,
        "cargo_target_topology_sha256": content_sha256(targets),
        "accepted_groups": groups,
        "unsafe_policy": dict(policy),
        "cargo_executed": False,
        "semantic_gate": False,
        "semantic_pass": False,
        "translation_coverage_numerator": 0,
        "files": refs,
    }


def _dag_payload(ir: Mapping[str, Any], root: Path) -> dict[str, Any]:
    try:
        raw = read_artifact_reference(root, ir["bindings"]["migration_dag"])
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, KeyError) as error:
        _fail("rust_project_ir_dag_unreadable", "rust_project_ir", detail=error)
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail("rust_project_ir_dag_noncanonical", "rust_project_ir")
    return value


def _first_blocker(value: Any, fallback: str) -> tuple[str, str | None]:
    if isinstance(value, list) and value and isinstance(value[0], Mapping):
        return str(value[0].get("code") or fallback), str(
            value[0].get("entity_id") or "",
        ) or None
    return fallback, None


def _ref(path: str, data: bytes) -> dict[str, Any]:
    return {
        "path": path, "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _fail(
    code: str, stage: str, group_id: str | None = None,
    detail: Exception | None = None,
) -> None:
    del detail
    raise cargo_project.ProjectInputError(code[:96], stage, group_id)


__all__ = ["reconstruct_cargo_project_v3"]
