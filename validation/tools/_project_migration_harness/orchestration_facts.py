from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .build_facts import is_linklike
from .candidate_strategy import select_candidate_strategy
from .gate_authority import (
    candidate_authority, candidate_kind, validate_candidate_verdict,
)
from .gate_diagnostics import (
    normalize_gate_evidence, validate_model_safe_gate_evidence,
)


MAX_FACT_ARTIFACT_BYTES = 2 * 1024 * 1024


def build_gate_facts(
    ledger: Any, *, run_id: str, harness_root: Path
) -> dict[str, dict[str, Any]]:
    states = {item["unit_id"]: item for item in ledger.unit_states(run_id)}
    rows = ledger.completed_orchestration_rows(run_id)
    artifacts = rows["artifacts"]
    verifications = rows["verifications"]
    with ledger.connect() as connection:
        attempt_counts = {
            str(row["unit_id"]): int(row["attempt_count"])
            for row in connection.execute(
                """select unit_id,count(*) as attempt_count from attempts
                   where run_id=? and role in ('translator','repairer')
                     and status<>'cancelled'
                   group by unit_id""",
                (run_id,),
            ).fetchall()
        }
    by_unit: dict[str, list[dict[str, Any]]] = {}
    by_id: dict[tuple[str, str], dict[str, Any]] = {}
    for artifact in artifacts:
        by_unit.setdefault(str(artifact["unit_id"]), []).append(artifact)
        by_id[(str(artifact["unit_id"]), str(artifact["artifact_id"]))] = artifact
    result: dict[str, dict[str, Any]] = {}
    for unit_id, state in states.items():
        facts: dict[str, Any] = {}
        failed_family: str | None = None
        unit_artifacts = by_unit.get(unit_id, [])
        planners = [item for item in unit_artifacts if item["kind"] == "planner-decision"]
        if planners:
            planner = planners[-1]
            payload = _read_json_binding(harness_root, planner)
            decision = payload.get("planner_decision")
            if not isinstance(decision, Mapping):
                raise ValueError("planner decision artifact is malformed")
            facts["planner_decision"] = dict(decision)
            facts["planner_decision_sha256"] = content_sha256(decision)
        candidates = [
            item
            for item in unit_artifacts
            if item["kind"] == "rust-candidate" and item["status"] == "candidate"
        ]
        if candidates:
            candidate = candidates[-1]
            facts.update(_artifact_facts("candidate_artifact", harness_root, candidate))
            candidate_records = [
                item
                for item in verifications
                if item["unit_id"] == unit_id
                and item["candidate_artifact_id"] == candidate["artifact_id"]
            ]
            latest_by_family: dict[str, dict[str, Any]] = {}
            for item in candidate_records:
                family = str(item.get("gate_family", ""))
                current = latest_by_family.get(family)
                if current is None or (
                    int(item.get("gate_epoch", 0)), int(item.get("sequence", 0))
                ) > (
                    int(current.get("gate_epoch", 0)), int(current.get("sequence", 0))
                ):
                    latest_by_family[family] = item
            failed = [
                item for item in latest_by_family.values()
                if item["status"] == "failed"
            ]
            if failed:
                record = max(failed, key=lambda item: int(item.get("sequence", 0)))
                evidence = _verification_ref(harness_root, record, candidate)
                facts["failed_gate_result"] = evidence
                facts["failed_gate_result_sha256"] = evidence["sha256"]
                failed_family = str(record["gate_family"])
        reviews = [item for item in unit_artifacts if item["kind"] == "structural-review"]
        candidate_sha = facts.get("candidate_artifact_sha256")
        for review in reversed(reviews):
            review_payload = _read_json_binding(harness_root, review)
            if review_payload.get("candidate_artifact_sha256") == candidate_sha:
                facts["review_artifact_sha256"] = review["content_sha256"]
                break
        last_good_id = state.get("last_good_artifact_id")
        if isinstance(last_good_id, str) and last_good_id:
            last_good = by_id.get((unit_id, last_good_id))
            if last_good is None:
                raise ValueError("last-good artifact is absent from the ledger")
            bound = _artifact_facts("last_good_artifact", harness_root, last_good)
            facts.update(bound)
        facts["candidate_strategy"] = select_candidate_strategy(
            gate_family=failed_family,
            attempt_count=attempt_counts.get(unit_id, 0),
            failure_fingerprint_sha256=(
                str(facts["failed_gate_result_sha256"])
                if failed_family is not None else None
            ),
        )
        result[unit_id] = facts
    return result


def _artifact_facts(
    prefix: str, root: Path, artifact: Mapping[str, Any]
) -> dict[str, Any]:
    data = _read_binding(root, artifact)
    reference = {
        "artifact_id": str(artifact["artifact_id"]),
        "path": str(artifact["repo_rel_path"]),
        "sha256": str(artifact["content_sha256"]),
        "size_bytes": len(data),
    }
    return {
        prefix: reference,
        f"{prefix}_id": reference["artifact_id"],
        f"{prefix}_sha256": reference["sha256"],
    }


def _verification_ref(
    root: Path, record: Mapping[str, Any], candidate: Mapping[str, Any],
) -> dict[str, Any]:
    pseudo = {
        "repo_rel_path": record["evidence_path"],
        "content_sha256": record["evidence_sha256"],
    }
    data = _read_binding(root, pseudo)
    try:
        raw = json.loads(data.decode("utf-8"))
        evidence = project_model_safe_gate_evidence(raw)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("failed gate evidence is not a model-safe projection") from error
    if (
        evidence["status"] != "failed"
        or evidence["candidate_artifact_id"] != record["candidate_artifact_id"]
        or evidence["candidate_artifact_id"] != candidate["artifact_id"]
        or evidence["candidate_artifact_sha256"] != candidate["content_sha256"]
    ):
        raise ValueError("failed gate evidence candidate ID/SHA/status binding is invalid")
    if raw.get("artifact_kind") == "candidate-gate-verdict" and (
        raw.get("run_id") != record["run_id"]
        or raw.get("unit_id") != record["unit_id"]
        or raw.get("gate_family") != record["gate_family"]
        or raw.get("authority_id") != record["verifier_id"]
        or candidate_kind(str(raw.get("gate_family"))) != record["kind"]
    ):
        raise ValueError("failed gate verdict does not match its ledger record")
    return {
        "record_id": str(record["record_id"]),
        "kind": str(record["kind"]),
        "path": str(record["evidence_path"]),
        "sha256": str(record["evidence_sha256"]),
        "size_bytes": len(data),
    }


def project_model_safe_gate_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("gate evidence must be a JSON object")
    if value.get("artifact_kind") == "model-safe-gate-evidence":
        return validate_model_safe_gate_evidence(value)
    if value.get("artifact_kind") != "candidate-gate-verdict":
        raise ValueError("gate evidence artifact kind is invalid")
    gate_family = str(value.get("gate_family"))
    validate_candidate_verdict(
        value,
        run_id=str(value.get("run_id")),
        unit_id=str(value.get("unit_id")),
        candidate_artifact_id=str(value.get("candidate_artifact_id")),
        candidate_sha256=str(value.get("candidate_sha256")),
        gate_family=gate_family,
        candidate_set_sha256=(
            str(value.get("candidate_set_sha256"))
            if value.get("candidate_set_sha256") is not None else None
        ),
        status=str(value.get("status")),
        verifier_id=candidate_authority(gate_family),
        kind=candidate_kind(gate_family),
    )
    return validate_model_safe_gate_evidence(normalize_gate_evidence(
        gate_family=gate_family,
        status=str(value.get("status")),
        candidate_artifact_id=str(value.get("candidate_artifact_id")),
        candidate_sha256=str(value.get("candidate_sha256")),
        diagnostics=value.get("diagnostics"),
    ))


def _read_json_binding(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    data = _read_binding(root, reference)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("bound orchestration artifact is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("bound orchestration artifact must be a JSON object")
    return value


def read_artifact_reference(root: Path, reference: Mapping[str, Any]) -> bytes:
    return _read_binding(root, {
        "repo_rel_path": reference.get("path"),
        "content_sha256": reference.get("sha256"),
    })


def _read_binding(root: Path, reference: Mapping[str, Any]) -> bytes:
    relative = reference.get("repo_rel_path")
    expected = reference.get("content_sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ValueError("artifact binding is incomplete")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("artifact binding path is unsafe")
    base = root.resolve(strict=True)
    current = base
    for part in path.parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError("artifact binding contains a link")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as error:
        raise ValueError("artifact binding escapes the harness root") from error
    if resolved.stat().st_size > MAX_FACT_ARTIFACT_BYTES:
        raise ValueError("artifact binding exceeds the read limit")
    with resolved.open("rb") as stream:
        data = stream.read(MAX_FACT_ARTIFACT_BYTES + 1)
    if len(data) > MAX_FACT_ARTIFACT_BYTES:
        raise ValueError("artifact binding exceeds the read limit")
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("artifact binding SHA-256 drifted")
    return data


__all__ = [
    "MAX_FACT_ARTIFACT_BYTES",
    "build_gate_facts",
    "project_model_safe_gate_evidence",
    "read_artifact_reference",
]
