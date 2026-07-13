from __future__ import annotations

from typing import Any

from .ledger import LedgerError, ProjectLedger


RECORDED_RESULT_ARTIFACT_STATUSES = {
    "project-repair-request": "written",
    "provider-prompt": "written",
    "provider-raw_response": "written",
    "provider-invocation_receipt": "diagnostic",
    "provider-parsed_response": "written",
    "provider-execution_report": "diagnostic",
}


def load_recorded_project_repair_result(
    ledger: ProjectLedger, *, attempt_id: str,
) -> dict[str, Any] | None:
    with ledger.connect() as connection:
        rows = connection.execute(
            """select kind,repo_rel_path,content_sha256,status
               from project_repair_artifacts where attempt_id=?
               and kind in ('project-repair-request','provider-prompt',
               'provider-raw_response','provider-invocation_receipt',
               'provider-parsed_response','provider-execution_report')
               order by kind,artifact_id""",
            (attempt_id,),
        ).fetchall()
    by_kind: dict[str, list[Any]] = {}
    for row in rows:
        by_kind.setdefault(str(row["kind"]), []).append(row)
    if set(by_kind) != set(RECORDED_RESULT_ARTIFACT_STATUSES):
        return None
    if any(len(values) != 1 for values in by_kind.values()):
        raise LedgerError("project repair recorded result is ambiguous")
    for kind, expected_status in RECORDED_RESULT_ARTIFACT_STATUSES.items():
        if by_kind[kind][0]["status"] != expected_status:
            raise LedgerError("project repair recorded result status drifted")
    return {
        "request": _reference(by_kind["project-repair-request"][0]),
        "response": _reference(by_kind["provider-parsed_response"][0]),
        "result_artifact_sha256s": {
            kind: str(values[0]["content_sha256"])
            for kind, values in sorted(by_kind.items())
        },
    }


def _reference(row: Any) -> dict[str, str]:
    return {
        "path": str(row["repo_rel_path"]),
        "sha256": str(row["content_sha256"]),
    }


__all__ = [
    "RECORDED_RESULT_ARTIFACT_STATUSES", "load_recorded_project_repair_result",
]
