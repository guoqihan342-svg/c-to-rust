from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any, Mapping

from .ledger_schema import (
    _json, _now_text, _require_repo_path, _require_sha256, atomic,
)
from .ledger_project_repair_core import require_identity
from .ledger_security import (
    LedgerError, assert_no_secrets, assert_no_semantic_claims,
)


_STATUSES = {"written", "candidate", "diagnostic", "failed"}


class ProjectRepairArtifactMixin:
    def record_project_repair_artifact(
        self, *, attempt_id: str, artifact_id: str, kind: str,
        repo_rel_path: str, content_sha256: str, status: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if status not in _STATUSES:
            raise ValueError("project repair artifact identity/status is invalid")
        artifact_id = require_identity(artifact_id, "artifact_id")
        kind = require_identity(kind, "artifact kind")
        assert_no_semantic_claims({"kind": kind, "metadata": metadata or {}})
        path = _require_repo_path(repo_rel_path, "repo_rel_path")
        assert_no_secrets(path, "project_repair_artifact.repo_rel_path")
        digest = _require_sha256(content_sha256, "content_sha256")
        with self.connect() as connection, atomic(connection):
            attempt = connection.execute(
                """select * from project_repair_attempts
                   where attempt_id=?""", (attempt_id,),
            ).fetchone()
            if attempt is None or attempt["status"] != "running":
                raise LedgerError("project repair artifact requires a running attempt")
            try:
                attempt_metadata = json.loads(attempt["metadata_json"])
            except (TypeError, json.JSONDecodeError) as error:
                raise LedgerError("project repair attempt metadata is invalid") from error
            root_value = attempt_metadata.get("artifact_root")
            if not isinstance(root_value, str):
                raise LedgerError("project repair artifact root is unavailable")
            root = PurePosixPath(_require_repo_path(root_value, "artifact_root"))
            if root not in PurePosixPath(path).parents:
                raise LedgerError("project repair artifact escaped its bound root")
            values = (
                str(attempt["run_id"]), artifact_id,
                str(attempt["project_repair_queue_sha256"]),
                str(attempt["repair_id"]), attempt_id, kind, path, digest,
                status, _now_text(), _json(metadata),
            )
            existing = connection.execute(
                """select run_id,artifact_id,project_repair_queue_sha256,repair_id,
                   attempt_id,kind,repo_rel_path,content_sha256,status,created_at,
                   metadata_json from project_repair_artifacts
                   where run_id=? and attempt_id=? and artifact_id=?""",
                (attempt["run_id"], attempt_id, artifact_id),
            ).fetchone()
            if existing is not None:
                comparable = tuple(existing)
                if comparable[:9] != values[:9] or comparable[10] != values[10]:
                    raise LedgerError("project repair artifact replay changed its binding")
                return
            connection.execute(
                """insert into project_repair_artifacts(
                   run_id,artifact_id,project_repair_queue_sha256,repair_id,
                   attempt_id,kind,repo_rel_path,content_sha256,status,created_at,
                   metadata_json) values (?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )


__all__ = ["ProjectRepairArtifactMixin"]
