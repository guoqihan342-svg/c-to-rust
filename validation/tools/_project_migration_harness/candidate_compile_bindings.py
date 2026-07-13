from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger_artifact_binding import read_ledger_artifact
from .ledger_run_contract import load_migration_contract
from .ledger_security import LedgerError


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
    if not isinstance(quarantine_ref, Mapping) or not isinstance(generation_ref, Mapping):
        raise LedgerError("candidate compile generation binding is invalid")
    candidate_data, root = read_ledger_artifact(ledger_path, source)
    quarantine_data, quarantine_root = read_ledger_artifact(
        ledger_path, quarantine_ref,
    )
    generation_data, generation_root = read_ledger_artifact(
        ledger_path, generation_ref,
    )
    if root != quarantine_root or root != generation_root or not candidate_data:
        raise LedgerError("candidate compile artifact roots are inconsistent")
    quarantine_payload = _json_object(quarantine_data)
    generation_payload = _json_object(generation_data)
    candidate_set = quarantine_payload.get("candidate_set")
    manifest = candidate_set.get("manifest") if isinstance(candidate_set, Mapping) else None
    members = manifest.get("members") if isinstance(manifest, Mapping) else None
    if (
        not isinstance(candidate_set, Mapping)
        or not isinstance(members, list)
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


def _json_object(data: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError("candidate compile generation evidence is invalid") from error
    if not isinstance(payload, Mapping):
        raise LedgerError("candidate compile generation evidence is invalid")
    return payload


__all__ = ["verify_compile_bindings"]
