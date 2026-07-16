from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .project_test_oracle_snapshot import copy_bounded_repository_snapshot
from .rust_project_cargo_v3_toml import package_root, render_cargo_lock


def materialize_project_oracle_workspace(
    *, generation_root: Path, workspace_root: Path,
    rust_project_ir: Mapping[str, Any], inventory: Mapping[str, Any],
    mapping: Mapping[str, Any], completeness: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(workspace_root)
    if root.exists():
        if root.is_symlink() or not root.is_dir() or any(root.iterdir()):
            raise ValueError("project_test_oracle_workspace_not_empty")
    else:
        root.mkdir(parents=True, mode=0o700)
    packages_source = Path(generation_root).resolve(strict=True) / "packages"
    packages_target = root / "packages"
    copied = copy_bounded_repository_snapshot(packages_source, packages_target)
    packages = [dict(item) for item in rust_project_ir["packages"]]
    members = sorted(package_root(str(item["package_id"])) for item in packages)
    workspace_toml = _workspace_toml(members)
    cargo_lock = render_cargo_lock(packages)
    (root / "Cargo.toml").write_bytes(workspace_toml)
    (root / "Cargo.lock").write_bytes(cargo_lock)
    evidence = {
        "schema_version": 1,
        "artifact_kind": "project-test-candidate-workspace",
        "inventory_sha256": str(inventory["inventory_sha256"]),
        "mapping_sha256": str(mapping["mapping_sha256"]),
        "completeness_sha256": str(completeness["completeness_sha256"]),
        "rust_project_ir_sha256": str(rust_project_ir["ir_sha256"]),
        "package_snapshot": copied,
        "members": members,
        "workspace_toml_sha256": content_sha256(workspace_toml.decode("utf-8")),
        "cargo_lock_sha256": content_sha256(cargo_lock.decode("utf-8")),
    }
    evidence["workspace_sha256"] = content_sha256(evidence)
    return evidence


def _workspace_toml(members: list[str]) -> bytes:
    quoted = "\n".join(f"  {json.dumps(item)}," for item in members)
    return (
        "[workspace]\nresolver = \"2\"\nmembers = [\n" + quoted
        + "\n]\ndefault-members = [\n" + quoted + "\n]\n"
    ).encode("utf-8")


__all__ = ["materialize_project_oracle_workspace"]
