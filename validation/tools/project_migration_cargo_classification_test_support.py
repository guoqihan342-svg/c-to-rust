from __future__ import annotations

from collections.abc import Sequence

from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    module_id_for_candidate,
)


def classification_ir(
    member: dict[str, str], *, rust_path: str,
    public_symbols: Sequence[str] = (),
) -> dict:
    candidate_sha = member["content_sha256"]
    build_sha = "f" * 64
    module_id = module_id_for_candidate(candidate_sha)
    evidence = {
        "build_ir_sha256s": [build_sha],
        "dag_unit_ids": [member["unit_id"]],
        "candidate_sha256s": [candidate_sha],
    }
    return build_rust_project_ir(
        migration_dag_ref={
            "path": "facts/migration-dag.json", "sha256": "e" * 64,
            "size_bytes": 1,
        },
        build_ir_refs=[{
            "path": "facts/build-ir.json", "sha256": build_sha,
            "size_bytes": 1,
        }],
        candidate_refs=[{
            "unit_id": member["unit_id"],
            "artifact_id": member["artifact_id"],
            "source": {
                "path": f"candidates/{member['artifact_id']}.rs",
                "sha256": candidate_sha, "size_bytes": 1,
            },
        }],
        crate={
            "crate_id": "classification-crate", "edition": "2021",
            "crate_types": ["rlib"], "root_module_id": module_id,
            "targets": ["library"], "evidence": evidence,
        },
        modules=[{
            "module_id": module_id, "parent_module_id": None,
            "rust_path": rust_path, "unit_id": member["unit_id"],
            "candidate_sha256": candidate_sha, "visibility": "crate",
            "evidence": evidence,
        }],
        public_api=[{
            "declaration_id": f"api-{index}", "module_id": module_id,
            "symbol": symbol, "kind": "function", "signature": "fn()",
            "visibility": "public", "evidence": evidence,
        } for index, symbol in enumerate(public_symbols)],
    )


__all__ = ["classification_ir"]
