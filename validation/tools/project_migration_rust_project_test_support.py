from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.build_ir import (
    BUILD_IR_EXTRACTOR, BUILD_IR_KIND, BUILD_IR_SCHEMA_VERSION, finalize_build_ir,
)
from validation.tools._project_migration_harness.rust_candidate_facts import (
    derive_rust_metadata,
)
from validation.tools._project_migration_harness.rust_project_ir_derivation import (
    derive_rust_project_ir_from_candidates,
)


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def valid_build_ir() -> dict[str, Any]:
    provenance = {"raw_fact_role": "discovery"}
    source = {
        "path": "src/input.c", "kind": "file", "materialized": True,
        "sha256": sha_text("source"), "size_bytes": 6,
    }
    metadata = {
        "path": "build/compile_commands.json", "kind": "file",
        "materialized": True, "sha256": sha_text("compile-db"),
        "size_bytes": 10,
    }
    unit = {
        "unit_id": "translation-unit", "variant_index": 0, "variant_count": 1,
        "source": source, "working_directory": ".", "compiler": "clang",
        "compiler_wrappers": [], "language": "c", "toolchain_id": "clang-host",
        "includes": [], "defines": [], "redacted_define_count": 0,
        "compile_arguments": {
            "semantic_flags": [], "expanded_argv_sha256": sha_text("argv"),
            "response_files": [],
        },
        "output": {"path": "build/input.o", "kind": "file", "materialized": False},
        "provenance": provenance,
    }
    raw_refs = [{
        "role": role, "path": f"facts/{index}.json", "sha256": sha_text(role),
        "size_bytes": index + 1,
    } for index, role in enumerate((
        "discovery", "generated-build-closure",
        "generated-build-closure-verification",
    ))]
    return finalize_build_ir({
        "schema_version": BUILD_IR_SCHEMA_VERSION, "artifact_kind": BUILD_IR_KIND,
        "status": "ready", "extractor": dict(BUILD_IR_EXTRACTOR),
        "raw_fact_refs": raw_refs, "build_metadata": [metadata],
        "translation_units": [unit], "source_inputs": [source],
        "generated_inputs": [], "targets": [], "target_closure": [],
        "toolchains": [], "external_dependencies": [],
        "abi_facts": [{"unit_id": "translation-unit", "provenance": provenance}],
        "boundaries": [], "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    })


def descriptor(
    root: Path, unit_id: str, source: str, *, filename: str | None = None,
) -> dict[str, Any]:
    relative = f"candidates/{filename or unit_id + '.rs'}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    data = source.encode("utf-8")
    path.write_bytes(data)
    metadata = derive_rust_metadata(source)
    return {
        "unit_id": unit_id, "artifact_id": f"candidate-{unit_id}",
        "group_id": unit_id, "status": "accepted", "source_path": relative,
        "sha256": hashlib.sha256(data).hexdigest(), **metadata,
    }


def bound_ir(
    root: Path, descriptors: list[dict[str, Any]],
    dependencies: dict[str, list[str]], *, unsafe_policy: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    order = _topological_order(dependencies)
    build_ref = write_json_artifact(root, "plan/build-ir.json", valid_build_ir())
    manifest = {
        "schema_version": 1,
        "dag": {key: sorted(values) for key, values in sorted(dependencies.items())},
        "dag_order": order,
        "unsafe_policy": unsafe_policy or {
            "allow_unsafe": True, "max_total": None, "max_per_group": None,
        },
        "build_ir": {
            "status": "bound", "artifact": build_ref,
            "verification": {"path": "plan/build-verify.json", "sha256": sha_text("verify"),
                             "size_bytes": 1},
            "worker_admission": {"path": "plan/build-admit.json", "sha256": sha_text("admit"),
                                 "size_bytes": 1},
        },
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }
    dag_ref = write_json_artifact(root, "plan/integration-manifest.json", manifest)
    ir = derive_rust_project_ir_from_candidates(
        migration_manifest=manifest, migration_dag_ref=dag_ref,
        build_ir_refs=[build_ref], candidate_descriptors=descriptors,
        artifact_root=root,
    )
    return ir, manifest


def _topological_order(dependencies: dict[str, list[str]]) -> list[str]:
    remaining = {key: set(values) for key, values in dependencies.items()}
    order = []
    while remaining:
        ready = sorted(key for key, values in remaining.items() if not values)
        if not ready:
            raise ValueError("test DAG contains a cycle")
        for key in ready:
            order.append(key)
            remaining.pop(key)
        for values in remaining.values():
            values.difference_update(ready)
    return order


__all__ = ["bound_ir", "descriptor", "sha_text", "valid_build_ir"]
