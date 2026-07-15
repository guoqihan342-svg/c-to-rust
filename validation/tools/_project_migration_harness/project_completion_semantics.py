from __future__ import annotations

from typing import Any

from .candidate_semantic_evidence import revalidate_candidate_semantic_verdict
from .candidate_semantic_runners import (
    run_abi_layout_candidate, run_negative_candidate,
    run_oracle_replay_diff_candidate, run_unsafe_alias_candidate,
)
from .gate_authority import CANDIDATE_REQUIRED_GATES
from .gate_evidence import read_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .ledger_candidate_state import latest_candidate_records


SEMANTIC_RUNNERS = (
    "oracle-replay-diff", "negative", "unsafe-alias", "abi-layout",
)


def missing_candidate_semantic_gates(
    ledger: ProjectLedger, run_id: str, candidate_set: str,
    members: list[dict[str, str]],
) -> list[str]:
    missing = []
    with ledger.connect() as connection:
        for member in members:
            rows = latest_candidate_records(
                connection, run_id, member["unit_id"], member["artifact_id"],
            )
            by_family = {str(row["gate_family"]): row for row in rows}
            for family in sorted(CANDIDATE_REQUIRED_GATES - {"compile"}):
                row = by_family.get(family)
                if row is None or row["status"] != "passed":
                    missing.append(f"{member['unit_id']}:{family}:missing-pass")
                    continue
                payload = read_content_addressed_json(
                    ledger.path, str(row["evidence_path"]),
                    str(row["evidence_sha256"]),
                )
                if payload.get("candidate_set_sha256") != candidate_set:
                    missing.append(f"{member['unit_id']}:{family}:cohort-drift")
                    continue
                try:
                    strict = revalidate_candidate_semantic_verdict(ledger, payload)
                except LedgerError:
                    strict = False
                if not strict:
                    missing.append(f"{member['unit_id']}:{family}:untrusted-evidence")
    return missing


def semantic_runner(family: str) -> Any:
    return {
        "oracle-replay-diff": run_oracle_replay_diff_candidate,
        "negative": run_negative_candidate,
        "unsafe-alias": run_unsafe_alias_candidate,
        "abi-layout": run_abi_layout_candidate,
    }[family]


__all__ = [
    "SEMANTIC_RUNNERS", "missing_candidate_semantic_gates", "semantic_runner",
]
