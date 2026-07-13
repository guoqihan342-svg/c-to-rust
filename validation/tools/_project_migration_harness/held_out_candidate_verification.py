from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .artifacts import canonical_json_bytes
from .execution_evidence import validate_provider_execution_evidence
from .gate_authority import (
    CANDIDATE_GATE_FAMILIES,
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    validate_candidate_verdict,
)
from .gate_evidence import read_content_addressed_json
from .held_out_ledger_support import (
    json_object as _json_object,
    require as _require,
)
from .ledger import ProjectLedger
from .ledger_verifier import _latest_candidate_records, _verify_candidate_sources
from .orchestration_facts import read_artifact_reference


def verify_candidate(
    ledger: ProjectLedger, connection: Any, harness_root: Path,
    run_id: str, member: Mapping[str, str], candidate_set_sha256: str,
) -> int:
    read_artifact_reference(harness_root, {
        "path": member["repo_rel_path"], "sha256": member["content_sha256"],
    })
    records = _latest_candidate_records(
        connection, run_id, member["unit_id"], member["artifact_id"],
    )
    by_family = {str(row["gate_family"]): row for row in records}
    _require(
        set(by_family) == CANDIDATE_GATE_FAMILIES,
        "candidate gate bundle is incomplete",
    )
    payloads = {}
    for family, row in by_family.items():
        _require(
            row["status"] == "passed"
            and row["kind"] == candidate_kind(family)
            and row["verifier_id"] == candidate_authority(family),
            "candidate gate is not a host-owned pass",
        )
        payload = read_content_addressed_json(
            ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"]),
        )
        validate_candidate_verdict(
            payload,
            run_id=run_id,
            unit_id=member["unit_id"],
            candidate_artifact_id=member["artifact_id"],
            candidate_sha256=member["content_sha256"],
            gate_family=family,
            candidate_set_sha256=candidate_set_sha256,
            status="passed",
            verifier_id=str(row["verifier_id"]),
            kind=str(row["kind"]),
        )
        _verify_candidate_sources(ledger, connection, payload, status="passed")
        payloads[family] = payload
    final = by_family["final-verification"]
    _require(
        int(final["ledger_rowid"]) > max(
            int(by_family[family]["ledger_rowid"])
            for family in CANDIDATE_REQUIRED_GATES
        ),
        "candidate final gate predates a prerequisite",
    )
    expected_sources = sorted(({
        "path": str(by_family[family]["evidence_path"]),
        "sha256": str(by_family[family]["evidence_sha256"]),
        "size_bytes": len(canonical_json_bytes(payloads[family])),
    } for family in CANDIDATE_REQUIRED_GATES), key=lambda item: item["path"])
    _require(
        sorted(
            payloads["final-verification"]["source_evidence"],
            key=lambda item: item["path"],
        ) == expected_sources,
        "candidate final gate prerequisite binding drifted",
    )
    return _verify_provider_execution(
        ledger, connection, run_id, member,
    )


def _verify_provider_execution(
    ledger: ProjectLedger, connection: Any, run_id: str,
    member: Mapping[str, str],
) -> int:
    attempt = connection.execute(
        "select worker_id,fencing_token,role,metadata_json from attempts where attempt_id=?",
        (member["attempt_id"],),
    ).fetchone()
    _require(attempt is not None, "candidate attempt is missing")
    metadata = _json_object(attempt["metadata_json"], "attempt metadata")
    executions = connection.execute(
        """select * from artifacts where run_id=? and unit_id=? and attempt_id=?
           and kind='provider-execution' and status='written' order by rowid""",
        (run_id, member["unit_id"], member["attempt_id"]),
    ).fetchall()
    if metadata.get("command_started") is True or executions:
        _require(
            len(executions) == 1,
            "candidate provider execution is missing or ambiguous",
        )
        validate_provider_execution_evidence(
            ledger.path,
            dict(executions[0]),
            run_id=run_id,
            unit_id=member["unit_id"],
            attempt_id=member["attempt_id"],
            worker_id=str(attempt["worker_id"]),
            fencing_token=int(attempt["fencing_token"]),
            role=str(attempt["role"]),
        )
        return 1
    return 0


__all__ = ["verify_candidate"]
