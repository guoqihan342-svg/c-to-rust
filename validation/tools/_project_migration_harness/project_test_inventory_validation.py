from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .build_facts import is_linklike, resolve_repository_path
from .project_test_inventory_ctest import collect_ctest_json
from .project_test_inventory_make import (
    collect_make_test_dry_run, inventory_from_make_observation,
)
from .project_test_inventory_meson import collect_meson_test_introspection
from .project_test_inventory_meson_binding import MESON_TEST_ADAPTER
from .project_test_inventory_meson_parse import inventory_from_meson_observation
from .rust_project_ir_binding_domain import validate_bound_build_ir
from .rust_project_ir_binding_io import (
    artifact_identity, read_reference, strict_json,
)
from .project_test_inventory import inventory_from_ctest_observation


MAX_SOURCE_EXECUTABLE_BYTES = 1024 * 1024 * 1024
_INVENTORY_KEYS = {
    "schema_version", "artifact_kind", "status", "adapter",
    "source_observation", "build_directory", "tests", "blockers",
    "claim_boundary", "inventory_sha256",
}
_CLAIM_BOUNDARY = {
    "semantic_gate": False, "translation_coverage_numerator": 0,
}


def manifest_project_test_inventory_reference(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    binding = manifest.get("project_test_inventory")
    if (
        not isinstance(binding, Mapping)
        or set(binding) != {"status", "artifact"}
        or binding.get("status") != "bound"
    ):
        raise ValueError("project_test_inventory_manifest_binding_invalid")
    reference = binding.get("artifact")
    artifact_identity(reference)
    return dict(reference)


def reopen_manifest_project_test_inventory(
    *, repo_root: Path, artifact_root: Path,
    migration_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(repo_root).resolve(strict=True)
    artifacts = Path(artifact_root).resolve(strict=True)
    if not root.is_dir() or not artifacts.is_dir():
        raise ValueError("project_test_inventory_root_invalid")
    reference = manifest_project_test_inventory_reference(migration_manifest)
    raw = read_reference(artifacts, reference)
    inventory = strict_json(raw, "project test inventory")
    _validate_inventory_shape(inventory)

    if inventory["source_observation"] is None:
        if inventory["status"] != "blocked" or inventory["adapter"] is not None:
            raise ValueError("project_test_inventory_observation_missing")
        return inventory

    build_ir = _reopen_manifest_build_ir(artifacts, migration_manifest)
    observation_ref = inventory["source_observation"]
    observation = strict_json(
        read_reference(artifacts, observation_ref), "project test observation",
    )
    build_directory = resolve_repository_path(
        root, str(inventory["build_directory"]),
    )
    adapter = inventory["adapter"]
    if adapter == "ctest-json-v1":
        recollected = collect_ctest_json(root, build_directory)
        derive = inventory_from_ctest_observation
    elif adapter == "make-dry-run-v1":
        recollected = collect_make_test_dry_run(root, build_directory)
        derive = inventory_from_make_observation
    elif adapter == MESON_TEST_ADAPTER:
        binding = observation.get("build_binding")
        database = binding.get("compile_database") if isinstance(
            binding, Mapping,
        ) else None
        database_path = database.get("path") if isinstance(
            database, Mapping,
        ) else None
        if not isinstance(database_path, str):
            raise ValueError("project_test_meson_compile_database_invalid")
        recollected = collect_meson_test_introspection(
            root, build_directory,
            resolve_repository_path(root, database_path),
        )
        derive = inventory_from_meson_observation
    else:
        raise ValueError("project_test_inventory_adapter_invalid")
    current_observation = recollected.get("observation")
    if (
        recollected.get("status") != "collected"
        or not isinstance(current_observation, Mapping)
    ):
        raise ValueError("project_test_inventory_recollection_failed")
    if dict(current_observation) != observation:
        raise ValueError("project_test_inventory_observation_drifted")
    expected = derive(
        root, build_ir, observation, source_observation=observation_ref,
    )
    if expected != inventory:
        raise ValueError("project_test_inventory_derivation_drifted")
    for test in inventory["tests"]:
        _verify_source_executable(root, test.get("source_executable"))
    return inventory


def _reopen_manifest_build_ir(
    artifact_root: Path, manifest: Mapping[str, Any],
) -> dict[str, Any]:
    binding = manifest.get("build_ir")
    if not isinstance(binding, Mapping) or binding.get("status") != "bound":
        raise ValueError("project_test_build_ir_binding_invalid")
    reference = binding.get("artifact")
    data = read_reference(artifact_root, reference)
    payload = strict_json(data, "project test BuildIR")
    validate_bound_build_ir(payload, data)
    return payload


def _validate_inventory_shape(value: Mapping[str, Any]) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != _INVENTORY_KEYS
        or value.get("schema_version") != 1
        or value.get("artifact_kind") != "project-test-inventory"
        or value.get("status") not in {"ready", "blocked"}
        or not isinstance(value.get("tests"), list)
        or not isinstance(value.get("blockers"), list)
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
        or value.get("inventory_sha256") != content_sha256({
            key: item for key, item in value.items()
            if key != "inventory_sha256"
        })
    ):
        raise ValueError("project_test_inventory_schema_invalid")
    if value["status"] == "ready" and (
        value["adapter"] not in {
            "ctest-json-v1", "make-dry-run-v1", MESON_TEST_ADAPTER,
        }
        or not value["tests"] or value["blockers"]
        or not isinstance(value["source_observation"], Mapping)
    ):
        raise ValueError("project_test_inventory_ready_state_invalid")
    if value["status"] == "blocked" and not value["blockers"]:
        raise ValueError("project_test_inventory_blocked_state_invalid")
    source = value["source_observation"]
    if source is not None:
        artifact_identity(source)


def _verify_source_executable(root: Path, value: Any) -> None:
    required = {"path", "kind", "materialized", "sha256", "size_bytes"}
    if not isinstance(value, Mapping) or not required <= set(value):
        raise ValueError("project_test_source_executable_binding_invalid")
    size = value.get("size_bytes")
    digest = value.get("sha256")
    if (
        value.get("kind") != "file" or value.get("materialized") is not True
        or not isinstance(digest, str) or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        or isinstance(size, bool) or not isinstance(size, int)
        or not 0 <= size <= MAX_SOURCE_EXECUTABLE_BYTES
    ):
        raise ValueError("project_test_source_executable_binding_invalid")
    relative = checked_relative_path(value.get("path"))
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError("project_test_source_executable_link_forbidden")
    target = current.resolve(strict=True)
    target.relative_to(root)
    if not target.is_file() or target.stat().st_size != size:
        raise ValueError("project_test_source_executable_size_drifted")
    hasher = hashlib.sha256()
    observed = 0
    with target.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            observed += len(chunk)
            if observed > size:
                raise ValueError("project_test_source_executable_size_drifted")
            hasher.update(chunk)
    if observed != size or hasher.hexdigest() != digest:
        raise ValueError("project_test_source_executable_content_drifted")


__all__ = [
    "manifest_project_test_inventory_reference",
    "reopen_manifest_project_test_inventory",
]
