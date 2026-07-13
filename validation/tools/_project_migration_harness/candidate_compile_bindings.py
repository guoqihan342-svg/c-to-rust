from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .ledger_artifact_binding import read_ledger_artifact
from .ledger_run_contract import load_migration_contract
from .ledger_security import LedgerError
from .quarantine_manifest import QUARANTINE_MANIFEST, generation_files
from .rust_project_cargo import GENERATOR, reconstruct_cargo_project_from_ir
from .rust_project_ir import canonical_rust_project_ir_bytes
from .rust_project_ir_validation import reopen_rust_project_ir_bindings


def verify_compile_bindings(
    payload: Mapping[str, Any], *, ledger_path: Path, connection: Any,
) -> None:
    if not isinstance(payload, Mapping):
        raise LedgerError("candidate compile observation schema is invalid")
    contract, _manifest = load_migration_contract(
        ledger_path, connection, str(payload.get("run_id")),
    )
    expected_contract = {
        "context_sha256": contract["context_sha256"],
        "dag_sha256": contract["dag_sha256"],
        "integration_manifest": contract["integration_manifest"],
    }
    if payload.get("run_contract") != expected_contract:
        raise LedgerError("candidate compile run contract drifted")
    source = payload.get("candidate_source")
    quarantine = payload.get("quarantine")
    if not isinstance(source, Mapping) or not isinstance(quarantine, Mapping):
        raise LedgerError("candidate compile artifact binding is invalid")
    quarantine_ref = quarantine.get("quarantine_manifest")
    generation_ref = quarantine.get("generation_manifest")
    ir_ref = quarantine.get("rust_project_ir")
    if (
        not isinstance(quarantine_ref, Mapping)
        or not isinstance(generation_ref, Mapping)
        or not isinstance(ir_ref, Mapping)
    ):
        raise LedgerError("candidate compile generation binding is invalid")
    candidate_data, root = read_ledger_artifact(ledger_path, source)
    quarantine_data, quarantine_root = read_ledger_artifact(
        ledger_path, quarantine_ref,
    )
    generation_data, generation_root = read_ledger_artifact(
        ledger_path, generation_ref,
    )
    ir_data, ir_root = read_ledger_artifact(ledger_path, ir_ref)
    if (
        root != quarantine_root or root != generation_root or root != ir_root
        or not candidate_data
    ):
        raise LedgerError("candidate compile artifact roots are inconsistent")
    artifact_root = ledger_path.parent.parent.resolve(strict=True)
    _require_inside_artifact_root(root, ir_ref, artifact_root)
    quarantine_payload = _json_object(quarantine_data)
    generation_payload = _json_object(generation_data)
    ir = _json_object(ir_data)
    try:
        if canonical_rust_project_ir_bytes(ir) != ir_data:
            raise ValueError("RustProjectIR is not canonical")
        reopen_rust_project_ir_bindings(ir, artifact_root)
        plan = reconstruct_cargo_project_from_ir(ir, artifact_root)
    except (OSError, TypeError, ValueError) as error:
        raise LedgerError("candidate compile RustProjectIR cannot be replayed") from error
    if (
        quarantine.get("generator") != GENERATOR
        or quarantine.get("rust_project_ir_sha256") != ir.get("ir_sha256")
        or quarantine.get("rust_project_interface_sha256") != ir.get("interface_sha256")
        or quarantine.get("rust_project_ir_scope")
        != plan.last_good_manifest.get("rust_project_ir_scope")
    ):
        raise LedgerError("candidate compile RustProjectIR binding drifted")
    candidate_set = quarantine_payload.get("candidate_set")
    manifest = candidate_set.get("manifest") if isinstance(candidate_set, Mapping) else None
    members = manifest.get("members") if isinstance(manifest, Mapping) else None
    bindings = quarantine_payload.get("candidate_bindings")
    expected_bindings = sorted(({
        "unit_id": str(item["unit_id"]),
        "artifact_id": str(item["artifact_id"]),
        "group_id": str(item["unit_id"]),
        "content_sha256": str(item["source"]["sha256"]),
    } for item in ir["bindings"]["candidates"]), key=lambda item: item["unit_id"])
    expected_members = [{
        "unit_id": item["unit_id"],
        "artifact_id": item["artifact_id"],
        "content_sha256": item["content_sha256"],
    } for item in expected_bindings]
    if (
        not isinstance(candidate_set, Mapping)
        or not isinstance(members, list)
        or members != expected_members
        or bindings != expected_bindings
        or candidate_set.get("sha256") != payload.get("candidate_set_sha256")
        or not any(
            item.get("artifact_id") == payload.get("candidate_artifact_id")
            and item.get("content_sha256") == source.get("sha256")
            for item in members if isinstance(item, Mapping)
        )
        or generation_payload.get("quarantine_manifest") != {
            "path": "migration-quarantine.json",
            "sha256": quarantine_ref.get("sha256"),
        }
    ):
        raise LedgerError("candidate compile quarantine binding is invalid")
    expected_files = generation_files(
        plan, str(candidate_set["sha256"]), manifest, members, expected_bindings,
    )
    if (
        expected_files[QUARANTINE_MANIFEST] != quarantine_data
        or expected_files["migration-last-good.json"] != generation_data
        or generation_payload.get("generator") != GENERATOR
        or generation_payload.get("rust_project_ir_sha256") != ir.get("ir_sha256")
    ):
        raise LedgerError("candidate compile generation cannot be deterministically replayed")
    _verify_generation_files(
        ledger_path, generation_ref, expected_files, root,
    )


def _require_inside_artifact_root(
    repository_root: Path, reference: Mapping[str, Any], artifact_root: Path,
) -> None:
    try:
        path = repository_root.joinpath(*PurePosixPath(str(reference["path"])).parts)
        path.resolve(strict=True).relative_to(artifact_root)
    except (OSError, KeyError, ValueError) as error:
        raise LedgerError("candidate compile RustProjectIR is outside the run output") from error


def _verify_generation_files(
    ledger_path: Path, generation_ref: Mapping[str, Any],
    files: Mapping[str, bytes], repository_root: Path,
) -> None:
    base = PurePosixPath(str(generation_ref["path"])).parent
    for relative, expected in files.items():
        reference = {
            "path": (base / PurePosixPath(relative)).as_posix(),
            "sha256": hashlib.sha256(expected).hexdigest(),
            "size_bytes": len(expected),
        }
        actual, root = read_ledger_artifact(ledger_path, reference)
        if root != repository_root or actual != expected:
            raise LedgerError("candidate compile generation file drifted")


def _json_object(data: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("candidate compile generation evidence is invalid") from error
    if not isinstance(payload, Mapping):
        raise LedgerError("candidate compile generation evidence is invalid")
    return payload


__all__ = ["verify_compile_bindings"]
