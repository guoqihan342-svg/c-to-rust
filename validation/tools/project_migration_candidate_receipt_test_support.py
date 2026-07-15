from __future__ import annotations

import json
from pathlib import Path

from validation.tools._project_migration_harness import cargo_project
from validation.tools._project_migration_harness.integration_validation import (
    digest,
)
from validation.tools._project_migration_harness.quarantine_manifest import (
    QUARANTINE_MANIFEST,
)
from validation.tools._project_migration_harness.rust_project_cargo import (
    GENERATOR,
)


def materialize_test_quarantine(root: Path) -> dict:
    generation = Path(root) / "generations/current"
    generation.mkdir(parents=True)
    cargo = b"[package]\nname = \"candidate\"\nversion = \"0.1.0\"\n"
    members = [{
        "unit_id": f"unit-{index}",
        "artifact_id": f"artifact-{index}",
        "content_sha256": str(index) * 64,
    } for index in (1, 2)]
    candidate_manifest = {"schema_version": 2, "members": members}
    candidate_set_sha256 = digest(json.dumps(
        candidate_manifest, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    quarantine = cargo_project.canonical_json_bytes({
        "schema_version": 1,
        "kind": "detached-cargo-quarantine",
        "candidate_set": {
            "sha256": candidate_set_sha256, "manifest": candidate_manifest,
        },
        "candidate_bindings": [{
            **member, "group_id": member["unit_id"],
        } for member in members],
        "candidate_count": 2,
        "immutable": True,
        "last_good_updated": False,
        "cargo_executed": False,
    })
    files = {
        "Cargo.toml": cargo,
        QUARANTINE_MANIFEST: quarantine,
    }
    references = [{
        "path": path,
        "sha256": digest(data),
        "size_bytes": len(data),
    } for path, data in sorted(files.items())]
    quarantine_reference = next(
        item for item in references if item["path"] == QUARANTINE_MANIFEST
    )
    manifest = cargo_project.canonical_json_bytes({
        "schema_version": cargo_project.SCHEMA_VERSION,
        "generator": GENERATOR,
        "rust_project_ir_scope": "full-project",
        "rust_project_ir_sha256": "a" * 64,
        "rust_project_interface_sha256": "b" * 64,
        "generation_kind": "detached-quarantine",
        "immutable": True,
        "last_good_updated": False,
        "cargo_executed": False,
        "quarantine_manifest": {
            "path": QUARANTINE_MANIFEST,
            "sha256": quarantine_reference["sha256"],
        },
        "files": references,
    })
    for relative, data in files.items():
        (generation / relative).write_bytes(data)
    (generation / cargo_project.LAST_GOOD_MANIFEST).write_bytes(manifest)
    relative = "generations/current"
    return {
        "generator": GENERATOR,
        "candidate_set_sha256": candidate_set_sha256,
        "generation": {
            "path": relative,
            "sha256": digest(manifest),
            "immutable": True,
        },
        "manifest_ref": {
            "path": f"{relative}/{QUARANTINE_MANIFEST}",
            "sha256": digest(quarantine),
            "size_bytes": len(quarantine),
        },
        "generation_manifest_ref": {
            "path": f"{relative}/{cargo_project.LAST_GOOD_MANIFEST}",
            "sha256": digest(manifest),
            "size_bytes": len(manifest),
        },
    }


__all__ = ["materialize_test_quarantine"]
