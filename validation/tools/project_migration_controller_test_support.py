from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.controller import (
    dispatch_project_workers,
)
from validation.tools._project_migration_harness.gate_authority import (
    candidate_authority,
    candidate_kind,
    candidate_verdict_payload,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.orchestrator import plan_project


class ProjectMigrationControllerCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-controller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.harness = self.root / "harness"
        self.source.mkdir()
        self.harness.mkdir()

    @property
    def out_root(self) -> Path:
        return self.harness / "target/run"

    def plan(self, source: str) -> dict:
        source_path = self.source / "unit.c"
        source_path.write_text(source, encoding="utf-8")
        database = self.source / "compile_commands.json"
        database.write_text(json.dumps([{
            "directory": ".",
            "file": "unit.c",
            "arguments": ["clang", "-c", "unit.c", "-o", "unit.o"],
            "output": "unit.o",
        }]), encoding="utf-8")
        return plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/run",
            compile_database=database,
            run_id="controller-run",
            max_concurrency=2,
        )

    def ledger(self) -> ProjectLedger:
        return ProjectLedger(self.out_root / "state/project-migration.sqlite3")

    def dispatch(self, plan: dict, ledger: ProjectLedger) -> dict:
        return dispatch_project_workers(
            plan["portfolio"],
            ledger=ledger,
            harness_root=self.harness,
            out_root=self.out_root,
            out_root_rel="target/run",
        )

    def request(self, launch: dict) -> dict:
        return self.load(launch["request"]["path"])

    def load(self, relative: str) -> dict:
        path = self.harness / Path(*relative.split("/"))
        return json.loads(path.read_text(encoding="utf-8"))

    def host_pass(
        self,
        ledger: ProjectLedger,
        run_id: str,
        unit_id: str,
        candidate_id: str,
        record_id: str,
        family: str,
    ) -> None:
        candidate = next(
            item for item in ledger.orchestration_rows(run_id)["artifacts"]
            if item["artifact_id"] == candidate_id
        )
        payload = candidate_verdict_payload(
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_id,
            candidate_sha256=candidate["content_sha256"],
            gate_family=family,
            status="passed",
            diagnostics=[],
        )
        reference = write_content_addressed_json(
            self.out_root, f"candidate/{family}", payload
        )
        ledger.record_host_verification(
            record_id=record_id,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_id,
            gate_family=family,
            kind=candidate_kind(family),
            status="passed",
            verifier_id=candidate_authority(family),
            evidence_path=f"target/run/{reference['path']}",
            evidence_sha256=reference["sha256"],
        )

    @staticmethod
    def common(request: dict) -> dict:
        return {
            "schema_version": 1,
            "run_id": request["run_id"],
            "worker_id": request["worker_id"],
            "group_id": request["group_id"],
            "role": request["role"],
            "effective_input_sha256": request["effective_input_sha256"],
        }


__all__ = ["ProjectMigrationControllerCase"]
