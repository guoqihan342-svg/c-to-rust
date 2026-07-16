from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_security import LedgerError


AUTHORITY = "host-candidate-pool-v1"


def load_candidate_pool(
    connection: Any, run_id: str, unit_id: str,
) -> dict[str, Any]:
    policy = connection.execute(
        """select max(case when role='translator' then max_attempts end) as max_attempts,
                  max(case when role='planner' then 1 else 0 end) as has_planner
           from assignments where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    if policy is None or policy["max_attempts"] is None:
        raise LedgerError("candidate pool requires a translator assignment")
    maximum = int(policy["max_attempts"])
    target = min(maximum, 2 if int(policy["has_planner"] or 0) else 1)
    attempt_count = int(connection.execute(
        """select count(*) from attempts where run_id=? and unit_id=?
           and role='translator' and status<>'cancelled'""",
        (run_id, unit_id),
    ).fetchone()[0])
    rows = connection.execute(
        """select a.rowid as sequence,a.* from artifacts a join attempts t
             on t.attempt_id=a.attempt_id and t.fencing_token=a.fencing_token
           where a.run_id=? and a.unit_id=? and a.kind='rust-candidate'
             and a.status='candidate' and t.status='completed'
             and t.role in ('translator','repairer') order by a.rowid""",
        (run_id, unit_id),
    ).fetchall()
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate = dict(row)
        unique.setdefault(str(candidate["content_sha256"]), candidate)
    candidates = list(unique.values())
    latest = _latest_verifier_records(connection, run_id, unit_id)
    scored = [_candidate_score(item, latest) for item in candidates]
    selected_score, reason = _select_candidate_score(scored)
    selected = None
    if selected_score is not None:
        selected = next(
            item for item in candidates
            if item["artifact_id"] == selected_score["artifact_id"]
        )
    exhausted = attempt_count >= maximum
    ready = bool(candidates) and (len(candidates) >= target or exhausted)
    core = {
        "schema_version": 1,
        "authority": AUTHORITY,
        "target_unique_candidates": target,
        "unique_candidate_count": len(candidates),
        "duplicate_candidate_count": len(rows) - len(candidates),
        "translator_attempt_count": attempt_count,
        "translator_max_attempts": maximum,
        "attempt_budget_exhausted": exhausted,
        "pool_ready": ready,
        "needs_additional_candidate": not ready and not exhausted,
        "candidate_sha256s": sorted(unique),
        "selected_candidate_artifact_id": (
            str(selected["artifact_id"]) if selected is not None else None
        ),
        "selected_candidate_sha256": (
            str(selected["content_sha256"]) if selected is not None else None
        ),
        "selection_reason": reason,
    }
    summary = {**core, "pool_sha256": content_sha256(core)}
    return {
        "summary": summary,
        "selected_candidate": selected,
        "candidate_scores": scored,
    }


def validate_candidate_pool_summary(value: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "authority", "target_unique_candidates",
        "unique_candidate_count", "duplicate_candidate_count",
        "translator_attempt_count", "translator_max_attempts",
        "attempt_budget_exhausted", "pool_ready",
        "needs_additional_candidate", "candidate_sha256s",
        "selected_candidate_artifact_id", "selected_candidate_sha256",
        "selection_reason", "pool_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("candidate pool summary fields are invalid")
    integers = (
        "target_unique_candidates", "unique_candidate_count",
        "duplicate_candidate_count", "translator_attempt_count",
        "translator_max_attempts",
    )
    if any(
        isinstance(value[key], bool) or not isinstance(value[key], int)
        or int(value[key]) < (1 if key in {
            "target_unique_candidates", "translator_max_attempts",
        } else 0)
        for key in integers
    ):
        raise ValueError("candidate pool summary counts are invalid")
    hashes = value.get("candidate_sha256s")
    selected_id = value.get("selected_candidate_artifact_id")
    selected_sha = value.get("selected_candidate_sha256")
    if (
        value.get("schema_version") != 1 or value.get("authority") != AUTHORITY
        or not isinstance(hashes, list) or hashes != sorted(set(hashes))
        or any(not _sha(item) for item in hashes)
        or value["unique_candidate_count"] != len(hashes)
        or (selected_id is None) != (selected_sha is None)
        or (selected_id is not None and (
            not isinstance(selected_id, str) or not selected_id
            or not _sha(selected_sha) or selected_sha not in hashes
        ))
        or not isinstance(value.get("selection_reason"), str)
        or any(not isinstance(value.get(key), bool) for key in (
            "attempt_budget_exhausted", "pool_ready",
            "needs_additional_candidate",
        ))
    ):
        raise ValueError("candidate pool summary binding is invalid")
    exhausted = value["translator_attempt_count"] >= value["translator_max_attempts"]
    ready = bool(hashes) and (
        len(hashes) >= value["target_unique_candidates"] or exhausted
    )
    if (
        value["target_unique_candidates"] > value["translator_max_attempts"]
        or value["translator_attempt_count"] > value["translator_max_attempts"]
        or value["attempt_budget_exhausted"] != exhausted
        or value["pool_ready"] != ready
        or value["needs_additional_candidate"] != (not ready and not exhausted)
        or (selected_sha is None) != (not hashes)
        or (value["selection_reason"] == "candidate-missing") != (not hashes)
        or value["selection_reason"] not in {
            "candidate-missing", "latest-unfailed-candidate",
            "best-host-gated-repair-base",
        }
    ):
        raise ValueError("candidate pool summary policy is inconsistent")
    core = {key: value[key] for key in fields if key != "pool_sha256"}
    if value.get("pool_sha256") != content_sha256(core):
        raise ValueError("candidate pool summary SHA-256 is invalid")
    return dict(value)


def _latest_verifier_records(
    connection: Any, run_id: str, unit_id: str,
) -> dict[str, dict[str, Mapping[str, Any]]]:
    rows = connection.execute(
        """select rowid as sequence,* from verifier_records
           where run_id=? and unit_id=? order by rowid""",
        (run_id, unit_id),
    ).fetchall()
    result: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        artifact_id = str(row["candidate_artifact_id"])
        family = str(row["gate_family"])
        current = result.setdefault(artifact_id, {}).get(family)
        if current is None or (
            int(row["gate_epoch"]), int(row["sequence"])
        ) > (
            int(current["gate_epoch"]), int(current["sequence"])
        ):
            result[artifact_id][family] = row
    return result


def _candidate_score(
    candidate: Mapping[str, Any],
    latest: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    records = latest.get(str(candidate["artifact_id"]), {})
    return {
        "artifact_id": str(candidate["artifact_id"]),
        "content_sha256": str(candidate["content_sha256"]),
        "sequence": int(candidate["sequence"]),
        "passed_gate_count": sum(
            item["status"] == "passed" for item in records.values()
        ),
        "failed_gate_count": sum(
            item["status"] == "failed" for item in records.values()
        ),
    }


def _select_candidate_score(
    scores: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    unfailed = [item for item in scores if item["failed_gate_count"] == 0]
    if unfailed:
        return (
            max(unfailed, key=lambda item: int(item["sequence"])),
            "latest-unfailed-candidate",
        )
    if scores:
        return (
            min(scores, key=lambda item: (
                -int(item["passed_gate_count"]),
                int(item["failed_gate_count"]),
                str(item["content_sha256"]),
            )),
            "best-host-gated-repair-base",
        )
    return None, "candidate-missing"


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


__all__ = [
    "AUTHORITY", "load_candidate_pool", "validate_candidate_pool_summary",
]
