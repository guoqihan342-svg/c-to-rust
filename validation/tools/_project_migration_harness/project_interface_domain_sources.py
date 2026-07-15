from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import canonical_build_ir_bytes
from .build_ir_validation import validate_build_ir, verify_build_ir_artifact
from .orchestration_facts import read_artifact_reference
from .rust_project_ir_cohort import PARENT_DAG_KEY
from .rust_project_ir_validation import reopen_rust_project_ir_bindings


def reopen_project_interface_source_domain(
    rust_project_ir: Mapping[str, Any], *, repo_root: Path, artifact_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reopen every C, DAG, BuildIR, and candidate source bound by IR v2."""
    repository = Path(repo_root).resolve(strict=True)
    artifacts = Path(artifact_root).resolve(strict=True)
    if not repository.is_dir() or not artifacts.is_dir():
        raise ValueError("interface_validation_source_root_invalid")
    binding = reopen_rust_project_ir_bindings(rust_project_ir, artifacts)
    ir_bindings = rust_project_ir["bindings"]
    dag = _read_object(
        artifacts, ir_bindings["migration_dag"], "interface_validation_dag",
    )
    build_irs, build_set = _build_irs(
        ir_bindings["build_ir"], repository, artifacts,
    )
    candidates = [
        {
            "unit_id": item["unit_id"],
            "artifact_id": item["artifact_id"],
            "source": _reference(item["source"]),
        }
        for item in ir_bindings["candidates"]
    ]
    dag_domain = _dag_domain(dag, ir_bindings["migration_dag"])
    source_domain = {
        "schema_version": 1,
        "artifact_kind": "project-interface-source-domain",
        "rust_project_binding_sha256": binding["bindings_sha256"],
        "dag": dag_domain,
        "build_ir_set": build_set,
        "build_ir_set_sha256": content_sha256(build_set),
        "candidate_sources": candidates,
        "candidate_source_set_sha256": content_sha256(candidates),
        "source_repository_binding_sha256": content_sha256({
            "dag": dag_domain,
            "build_ir_set": build_set,
            "candidate_sources": candidates,
        }),
        "claim_boundary": {
            "interface_closure": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    source_domain["domain_sha256"] = content_sha256(source_domain)
    return source_domain, build_irs


def _build_irs(
    references: Any, repo_root: Path, artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(references, list) or not references:
        raise ValueError("interface_validation_build_ir_set_invalid")
    payloads = []
    projections = []
    for raw_reference in references:
        reference = _reference(raw_reference)
        payload = _read_object(
            artifact_root, reference, "interface_validation_build_ir",
        )
        try:
            validate_build_ir(payload)
        except (TypeError, ValueError) as error:
            raise ValueError("interface_validation_build_ir_invalid") from error
        data = read_artifact_reference(artifact_root, reference)
        if canonical_build_ir_bytes(payload) != data:
            raise ValueError("interface_validation_build_ir_noncanonical")
        verification = verify_build_ir_artifact(
            repo_root, artifact_root, reference,
        )
        if verification.get("status") != "verified":
            raise ValueError("interface_validation_c_repository_drifted")
        projection = {
            "reference": reference,
            "semantic_sha256": payload["semantic_sha256"],
            "toolchain_profile": verification.get("toolchain_profile"),
            "verified_binding_count": verification.get("verified_binding_count"),
            "native_link_config_resolved": verification.get(
                "native_link_config_resolved"
            ),
            "unresolved_native_dependency_count": verification.get(
                "unresolved_native_dependency_count"
            ),
        }
        payloads.append(payload)
        projections.append(projection)
    if projections != sorted(
        projections, key=lambda item: (
            item["reference"]["path"], item["reference"]["sha256"],
        ),
    ):
        raise ValueError("interface_validation_build_ir_order_invalid")
    return payloads, projections


def _dag_domain(
    dag: Mapping[str, Any], child_reference: Mapping[str, Any],
) -> dict[str, Any]:
    graph, order = dag.get("dag"), dag.get("dag_order")
    if not isinstance(graph, Mapping) or not isinstance(order, list):
        raise ValueError("interface_validation_child_dag_invalid")
    child = {
        "artifact": _reference(child_reference),
        "unit_set_sha256": content_sha256(sorted(graph)),
        "edge_set_sha256": content_sha256([
            {"unit_id": key, "dependencies": graph[key]}
            for key in sorted(graph)
        ]),
        "order_sha256": content_sha256(order),
    }
    parent = dag.get(PARENT_DAG_KEY)
    if parent is None:
        parent_projection = None
    else:
        if not isinstance(parent, Mapping):
            raise ValueError("interface_validation_parent_dag_invalid")
        selected = parent.get("selected_unit_ids")
        if not isinstance(selected, list):
            raise ValueError("interface_validation_parent_dag_invalid")
        parent_projection = {
            "scope": parent.get("scope"),
            "artifact": _reference(parent.get("artifact")),
            "selected_unit_set_sha256": content_sha256(selected),
        }
    return {"parent": parent_projection, "child": child}


def _read_object(root: Path, reference: Any, code: str) -> dict[str, Any]:
    bound = _reference(reference)
    try:
        data = read_artifact_reference(root, bound)
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{code}_unreadable") from error
    if (
        len(data) != bound["size_bytes"]
        or not isinstance(value, dict)
        or canonical_json_bytes(value) != data
    ):
        raise ValueError(f"{code}_noncanonical")
    return value


def _reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not {
        "path", "sha256", "size_bytes",
    } <= set(value):
        raise ValueError("interface_validation_artifact_reference_invalid")
    reference = {
        key: value[key] for key in ("path", "sha256", "size_bytes")
    }
    path, digest, size = (
        reference["path"], reference["sha256"], reference["size_bytes"],
    )
    if (
        not isinstance(path, str) or not path
        or not isinstance(digest, str) or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or type(size) is not int or size < 0
    ):
        raise ValueError("interface_validation_artifact_reference_invalid")
    return reference


__all__ = ["reopen_project_interface_source_domain"]
