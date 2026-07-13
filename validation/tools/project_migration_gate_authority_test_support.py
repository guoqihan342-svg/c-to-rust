from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.gate_authority import (
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    candidate_verdict_payload,
    project_authority,
    project_summary_payload,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ProjectMigrationGateAuthorityCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-gate-authority-")
        self.addCleanup(temporary.cleanup)
        self.harness = Path(temporary.name) / "harness"
        self.out_root = self.harness / "target" / "run"
        self.out_root.mkdir(parents=True)
        self.database = self.out_root / "project-ledger.sqlite3"
        self.ledger = ProjectLedger(self.database)
        self.ledger.create_run(
            run_id="run",
            project_key="project",
            source_commit="commit",
            dag_sha256=digest("dag"),
            units=[{
                "unit_id": "unit",
                "group_id": "group",
                "wave_index": 0,
                "content_sha256": digest("unit"),
            }],
            assignments=[{
                "unit_id": "unit",
                "worker_id": "translator",
                "role": "translator",
                "out_root": "target/run/workers/translator/out",
                "max_attempts": 4,
            }],
            max_concurrency=1,
            max_attempts=4,
        )
        self.candidate_id, self.candidate_sha = self.make_candidate("candidate-one")

    def make_candidate(self, label: str) -> tuple[str, str]:
        candidate_sha = digest(label)
        candidate_id = label
        with self.ledger.connect() as connection:
            ordinal = int(connection.execute(
                "select count(*)+1 from attempts where run_id='run' and unit_id='unit'"
            ).fetchone()[0])
            attempt = f"run:unit:translator:{ordinal}"
            now = f"2026-01-01T00:00:0{ordinal}Z"
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,worker_id,status,
                   fencing_token,input_sha256,output_sha256,error_key,started_at,finished_at,
                   metadata_json) values (?,?,?,?,?,?,'completed',?,?,?,null,?,?,?)""",
                (attempt, "run", "unit", "translator", ordinal, "translator", ordinal,
                 digest(f"input-{label}"), candidate_sha, now, now, "{}"),
            )
            connection.execute(
                """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,worker_id,
                   fencing_token,kind,repo_rel_path,content_sha256,status,created_at,metadata_json)
                   values (?,?,?,?,?,?,?,?,?,'candidate',?,?)""",
                ("run", candidate_id, "unit", attempt, "translator", ordinal,
                 "rust-candidate", f"target/run/workers/translator/out/{label}.rs",
                 candidate_sha, now, "{}"),
            )
            connection.execute(
                """update migration_units set status='gate-pending',
                   resumable_status='awaiting_gate',updated_at=?
                   where run_id='run' and unit_id='unit'""",
                (now,),
            )
        return candidate_id, candidate_sha

    def record_candidate_host_gate(
        self, family: str, status: str, record_id: str,
    ) -> dict[str, str | int]:
        payload = candidate_verdict_payload(
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            candidate_sha256=self.candidate_sha,
            gate_family=family,
            status=status,
            diagnostics=[] if status == "passed" else [{"code": "host-failed", "stage": family}],
        )
        reference = write_content_addressed_json(
            self.out_root, f"candidate/{family}", payload
        )
        full_path = f"target/run/{reference['path']}"
        self.ledger.record_host_verification(
            record_id=record_id,
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            kind=candidate_kind(family),
            status=status,
            verifier_id=candidate_authority(family),
            evidence_path=full_path,
            evidence_sha256=str(reference["sha256"]),
            gate_family=family,
        )
        return {**reference, "path": full_path}

    def promote_current_candidate(self) -> None:
        records = {}
        for family in sorted(CANDIDATE_REQUIRED_GATES):
            record_id = f"{self.candidate_id}-{family}"
            self.record_candidate_host_gate(family, "passed", record_id)
            records[family] = record_id
        final_id = f"{self.candidate_id}-final"
        self.record_candidate_host_gate("final-verification", "passed", final_id)
        self.ledger.promote_last_good_from_verification(
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            verifier_record_id=records["compile"],
            gate_record_id=final_id,
        )

    def record_project_host_gate(
        self, kind: str, status: str, record_id: str, candidate_set: str,
        sources: list[dict] | None = None,
    ) -> None:
        if kind != "final-verification" and sources is None:
            sources = [self.project_observation(kind, status, candidate_set)]
        payload = project_summary_payload(
            run_id="run",
            gate_kind=kind,
            status=status,
            candidate_set_sha256=candidate_set,
            source_evidence=sources or [],
        )
        reference = write_content_addressed_json(
            self.out_root, f"project/{kind}", payload
        )
        self.ledger.record_project_gate(
            record_id=record_id,
            run_id="run",
            gate_kind=kind,
            status=status,
            candidate_set_sha256=candidate_set,
            verifier_id=project_authority(kind),
            evidence_path=f"target/run/{reference['path']}",
            evidence_sha256=str(reference["sha256"]),
        )

    def project_observation(
        self, kind: str, status: str, candidate_set: str,
    ) -> dict[str, str | int]:
        passed = status == "passed"
        if kind == "integration":
            observation = {
                "managed_project_unchanged": passed,
                "candidate_count": 1,
                "manifest_sha256": digest("manifest"),
                "project_sha256": digest("project"),
            }
        elif kind in {"cargo-check", "cargo-test"}:
            observation = {
                "executed": True,
                "returncode": 0 if passed else 1,
                "timed_out": False,
                "sandbox_profile": "os-isolated-v1",
            }
        elif kind == "oracle-replay":
            observation = {
                "case_count": 1,
                "mismatch_count": 0 if passed else 1,
                "crash_count": 0,
                "oracle_sha256": digest("oracle"),
                "candidate_sha256": digest("candidate-project"),
            }
        elif kind == "negative":
            observation = {
                "case_count": 1,
                "unexpected_accept_count": 0 if passed else 1,
            }
        elif kind == "unsafe-alias-abi":
            observation = {
                "check_count": 1,
                "violation_count": 0 if passed else 1,
            }
        else:
            raise ValueError("unsupported raw project observation")
        payload = {
            "schema_version": 1,
            "artifact_kind": "host-project-gate-observation",
            "authority_id": project_authority(kind),
            "run_id": "run",
            "gate_kind": kind,
            "candidate_set_sha256": candidate_set,
            "observation": observation,
        }
        reference = write_content_addressed_json(
            self.out_root, f"raw/{kind}", payload
        )
        return {**reference, "path": f"target/run/{reference['path']}"}

    def record_project_final(self, record_id: str, candidate_set: str) -> None:
        sources = self.ledger.project_gate_bundle_sources(
            run_id="run", candidate_set_sha256=candidate_set
        )
        self.record_project_host_gate(
            "final-verification", "passed", record_id, candidate_set, sources
        )


__all__ = ["ProjectMigrationGateAuthorityCase", "digest"]
