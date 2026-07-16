from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .build_ir import is_sha256
from .gate_authority import project_authority, project_summary_payload
from .gate_evidence import require_content_addressed_reference
from .ledger import LedgerError, ProjectLedger
from .project_test_completeness import validate_project_test_completeness
from .project_test_semantic_oracle import validate_passed_project_test_oracle
from .rust_project_ir_binding_io import artifact_identity, read_reference, strict_json


def reopen_project_test_semantic_evidence(
    *, ledger: ProjectLedger, artifact_root: Path, out_root_rel: str,
    run_id: str, candidate_set_sha256: str,
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    if verification.get("status") != "passed" or verification.get("semantic_gate") is not False:
        raise LedgerError("project_test_semantic_verification_not_passed")
    inventory_ref = _reference(verification.get("inventory"), "inventory")
    mapping_ref = _reference(verification.get("mapping"), "mapping")
    completeness_ref = _reference(
        verification.get("completeness"), "completeness",
    )
    oracle_ref = _reference(verification.get("oracle"), "oracle")
    require_content_addressed_reference(oracle_ref)
    if PurePosixPath(oracle_ref["path"]).parts != (
        "verification", "project-test", "oracle", f"{oracle_ref['sha256']}.json",
    ):
        raise LedgerError("project_test_oracle_artifact_scope_invalid")
    inventory = _read_json(artifact_root, inventory_ref, "inventory")
    mapping = _read_json(artifact_root, mapping_ref, "mapping")
    completeness = _read_json(
        artifact_root, completeness_ref, "completeness",
    )
    oracle = _read_json(artifact_root, oracle_ref, "oracle")
    _validate_inventory(inventory)
    _validate_mapping(mapping, inventory)
    try:
        validate_project_test_completeness(completeness, inventory, mapping)
    except (TypeError, ValueError) as error:
        raise LedgerError("project_test_completeness_summary_invalid") from error
    oracle_observation = validate_passed_project_test_oracle(
        oracle, inventory, mapping, completeness,
    )
    expected_observation = bound_project_test_gate_observation(
        oracle_observation, oracle_ref,
    )
    if verification.get("gate_observation") != expected_observation:
        raise LedgerError("project_test_gate_observation_binding_drifted")
    record = verification.get("project_gate_record")
    if not isinstance(record, Mapping):
        raise LedgerError("project_test_gate_record_missing")
    _validate_gate_record(
        ledger=ledger, artifact_root=artifact_root, out_root_rel=out_root_rel,
        run_id=run_id, candidate_set_sha256=candidate_set_sha256,
        record=record, expected_observation=expected_observation,
    )
    summary = {
        "case_count": expected_observation["case_count"],
        "mismatch_count": expected_observation["mismatch_count"],
        "crash_count": expected_observation["crash_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "mapping_sha256": mapping["mapping_sha256"],
        "completeness_sha256": completeness["completeness_sha256"],
        "oracle_artifact_sha256": oracle_ref["sha256"],
        "candidate_sha256": expected_observation["candidate_sha256"],
    }
    summary["summary_sha256"] = content_sha256(summary)
    return {
        "schema_version": 1,
        "artifact_kind": "project-test-semantic-evidence-binding",
        "status": "verified", "inventory": inventory_ref,
        "mapping": mapping_ref, "completeness": completeness_ref,
        "oracle": oracle_ref, "summary": summary,
        "project_gate_record_id": str(record["record_id"]),
        "semantic_gate": False,
    }


def bound_project_test_gate_observation(
    observation: Mapping[str, Any], oracle_ref: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "case_count", "mismatch_count", "crash_count",
        "oracle_sha256", "candidate_sha256",
    }
    v2 = required | {
        "evidence_sha256", "input_snapshot_sha256", "execution_isolation",
    }
    v3 = v2 | {"completeness_sha256"}
    if frozenset(observation) not in {
        frozenset(required), frozenset(v2), frozenset(v3),
    }:
        raise LedgerError("project_test_oracle_observation_schema_invalid")
    return {
        "case_count": observation["case_count"],
        "mismatch_count": observation["mismatch_count"],
        "crash_count": observation["crash_count"],
        "oracle_sha256": str(oracle_ref["sha256"]),
        "candidate_sha256": observation["candidate_sha256"],
    }


def _validate_inventory(inventory: Mapping[str, Any]) -> None:
    tests = inventory.get("tests")
    if (
        inventory.get("artifact_kind") != "project-test-inventory"
        or inventory.get("status") != "ready"
        or not isinstance(tests, list) or not tests
        or inventory.get("inventory_sha256") != content_sha256({
            key: value for key, value in inventory.items() if key != "inventory_sha256"
        })
    ):
        raise LedgerError("project_test_inventory_summary_invalid")


def _validate_mapping(
    mapping: Mapping[str, Any], inventory: Mapping[str, Any],
) -> None:
    mappings = mapping.get("mappings")
    if (
        mapping.get("artifact_kind") != "project-test-mapping"
        or mapping.get("status") != "ready"
        or not isinstance(mappings, list) or not mappings
        or not is_sha256(mapping.get("rust_project_ir_sha256"))
        or mapping.get("inventory_sha256") != inventory.get("inventory_sha256")
        or mapping.get("mapping_sha256") != content_sha256({
            key: value for key, value in mapping.items() if key != "mapping_sha256"
        })
    ):
        raise LedgerError("project_test_mapping_summary_invalid")


def _validate_gate_record(
    *, ledger: ProjectLedger, artifact_root: Path, out_root_rel: str,
    run_id: str, candidate_set_sha256: str, record: Mapping[str, Any],
    expected_observation: Mapping[str, Any],
) -> None:
    record_id = record.get("record_id")
    raw_ref = _full_reference(record.get("raw_observation"), "raw_observation")
    evidence_ref = _full_reference(record.get("evidence"), "gate_evidence")
    harness_root = _harness_root(artifact_root, out_root_rel)
    raw = _read_json(harness_root, raw_ref, "raw_observation")
    evidence = _read_json(harness_root, evidence_ref, "gate_evidence")
    expected_raw = {
        "schema_version": 1, "artifact_kind": "host-project-gate-observation",
        "authority_id": project_authority("oracle-replay"),
        "run_id": run_id, "gate_kind": "oracle-replay",
        "candidate_set_sha256": candidate_set_sha256,
        "observation": dict(expected_observation),
    }
    expected_evidence = project_summary_payload(
        run_id=run_id, gate_kind="oracle-replay", status="passed",
        candidate_set_sha256=candidate_set_sha256,
        source_evidence=[raw_ref], diagnostic_codes=[],
    )
    if raw != expected_raw or evidence != expected_evidence:
        raise LedgerError("project_test_gate_evidence_binding_drifted")
    if (
        record.get("gate_kind") != "oracle-replay" or record.get("gate_status") != "passed"
        or record.get("candidate_set_sha256") != candidate_set_sha256
        or record.get("raw_observation") != raw_ref or record.get("evidence") != evidence_ref
    ):
        raise LedgerError("project_test_gate_record_binding_invalid")
    with ledger.connect() as connection:
        row = connection.execute(
            """select run_id,gate_kind,status,candidate_set_sha256,verifier_id,
                      evidence_path,evidence_sha256 from project_gate_records
               where record_id=?""",
            (record_id,),
        ).fetchone()
    if (
        row is None or str(row["run_id"]) != run_id
        or str(row["gate_kind"]) != "oracle-replay" or str(row["status"]) != "passed"
        or str(row["candidate_set_sha256"]) != candidate_set_sha256
        or str(row["verifier_id"]) != project_authority("oracle-replay")
        or str(row["evidence_path"]) != evidence_ref["path"]
        or str(row["evidence_sha256"]) != evidence_ref["sha256"]
    ):
        raise LedgerError("project_test_gate_ledger_binding_drifted")


def _reference(value: Any, label: str) -> dict[str, Any]:
    try:
        path, digest, size = artifact_identity(value)
    except (TypeError, ValueError) as error:
        raise LedgerError(f"project_test_{label}_reference_invalid") from error
    return {"path": path, "sha256": digest, "size_bytes": size}


def _full_reference(value: Any, label: str) -> dict[str, Any]:
    reference = _reference(value, label)
    require_content_addressed_reference(reference)
    return reference


def _read_json(root: Path, reference: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        data = read_reference(root, reference)
        payload = strict_json(data, f"project test {label}")
    except (OSError, TypeError, ValueError) as error:
        raise LedgerError(f"project_test_{label}_artifact_drifted") from error
    if len(data) != reference["size_bytes"]:
        raise LedgerError(f"project_test_{label}_artifact_size_drifted")
    return payload


def _harness_root(artifact_root: Path, out_root_rel: str) -> Path:
    relative = PurePosixPath(checked_relative_path(out_root_rel))
    root = artifact_root.resolve(strict=True)
    for _ in relative.parts:
        root = root.parent
    if root.joinpath(*relative.parts).resolve(strict=True) != artifact_root.resolve(strict=True):
        raise LedgerError("project_test_artifact_root_binding_invalid")
    return root


__all__ = [
    "bound_project_test_gate_observation", "reopen_project_test_semantic_evidence",
]
