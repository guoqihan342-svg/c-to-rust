from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from . import cargo_project
from . import integration_validation as validation


QUARANTINE_MANIFEST = "migration-quarantine.json"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def candidate_set(
    descriptors: Sequence[Mapping[str, Any]],
    expected: str,
    manifest: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not isinstance(expected, str) or _SHA256.fullmatch(expected) is None:
        _fail("candidate_set_sha256_invalid", "candidate_set")
    if (
        isinstance(descriptors, (str, bytes))
        or not isinstance(descriptors, Sequence)
        or not descriptors
    ):
        _fail("candidate_set_members_invalid", "candidate_set")
    members: list[dict[str, str]] = []
    bindings: list[dict[str, str]] = []
    seen: set[str] = set()
    for descriptor in descriptors:
        if not isinstance(descriptor, Mapping) or descriptor.get("status") != "accepted":
            _fail("candidate_set_member_invalid", "candidate_set")
        unit_id = _identifier(descriptor.get("unit_id"))
        artifact_id = _identifier(descriptor.get("artifact_id"))
        group_id = _identifier(descriptor.get("group_id"))
        digest = descriptor.get("sha256")
        if (
            unit_id in seen
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            _fail("candidate_set_member_invalid", "candidate_set")
        seen.add(unit_id)
        members.append({
            "unit_id": unit_id,
            "artifact_id": artifact_id,
            "content_sha256": digest,
        })
        bindings.append({
            "unit_id": unit_id,
            "artifact_id": artifact_id,
            "group_id": group_id,
            "content_sha256": digest,
        })
    members.sort(key=lambda item: item["unit_id"])
    bindings.sort(key=lambda item: item["unit_id"])
    if not isinstance(manifest, Mapping):
        _fail("candidate_set_manifest_invalid", "candidate_set")
    encoded = json.dumps(
        dict(manifest), sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if validation.digest(encoded) != expected or manifest.get("members") != members:
        _fail("candidate_set_sha256_mismatch", "candidate_set")
    return members, bindings


def generation_files(
    plan: cargo_project.CargoProjectPlan,
    candidate_set_sha256: str,
    candidate_set_manifest: Mapping[str, Any],
    members: list[dict[str, str]],
    bindings: list[dict[str, str]],
) -> dict[str, bytes]:
    quarantine = cargo_project.canonical_json_bytes({
        "schema_version": 1,
        "kind": "detached-cargo-quarantine",
        "candidate_set": {
            "sha256": candidate_set_sha256,
            "manifest": dict(candidate_set_manifest),
        },
        "candidate_bindings": bindings,
        "candidate_count": len(members),
        "immutable": True,
        "last_good_updated": False,
        "cargo_executed": False,
    })
    reference = {
        "path": QUARANTINE_MANIFEST,
        "sha256": validation.digest(quarantine),
        "size_bytes": len(quarantine),
    }
    manifest = dict(plan.last_good_manifest)
    manifest["files"] = sorted(
        [*manifest["files"], reference], key=lambda item: item["path"],
    )
    manifest.update({
        "generation_kind": "detached-quarantine",
        "immutable": True,
        "last_good_updated": False,
        "quarantine_manifest": {
            "path": reference["path"], "sha256": reference["sha256"],
        },
    })
    files = dict(plan.files)
    files[QUARANTINE_MANIFEST] = quarantine
    files[cargo_project.LAST_GOOD_MANIFEST] = cargo_project.canonical_json_bytes(
        manifest,
    )
    return files


def _identifier(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(ord(char) < 32 for char in value)
    ):
        _fail("candidate_set_member_invalid", "candidate_set")
    return value


def _fail(code: str, stage: str) -> None:
    raise cargo_project.ProjectInputError(code, stage)
