from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools.project_migration_gate_authority_candidate_test_support import (
    CandidateGateAuthoritySupportMixin,
    _compile_execution,
    digest,
)
from validation.tools.project_migration_gate_authority_project_test_support import (
    ProjectGateAuthoritySupportMixin,
)
from validation.tools.project_migration_run_contract_test_support import (
    migration_run_metadata,
)


class ProjectMigrationGateAuthorityCase(
    CandidateGateAuthoritySupportMixin,
    ProjectGateAuthoritySupportMixin,
    unittest.TestCase,
):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-gate-authority-")
        self.addCleanup(temporary.cleanup)
        self.harness = Path(temporary.name) / "harness"
        self.out_root = self.harness / "target" / "run"
        self.out_root.mkdir(parents=True)
        self.database = self.out_root / "state" / "project-migration.sqlite3"
        self.ledger = ProjectLedger(self.database)
        units = [{
            "unit_id": "unit",
            "group_id": "unit",
            "wave_index": 0,
            "content_sha256": digest("unit"),
        }]
        dag_sha256 = digest("dag")
        self.ledger.create_run(
            run_id="run",
            project_key="project",
            source_commit="commit",
            dag_sha256=dag_sha256,
            units=units,
            assignments=[{
                "unit_id": "unit",
                "worker_id": "translator",
                "role": "translator",
                "out_root": "target/run/workers/translator/out",
                "max_attempts": 4,
            }],
            max_concurrency=1,
            max_attempts=4,
            metadata=migration_run_metadata(
                self.out_root,
                self.database,
                run_id="run",
                dag_sha256=dag_sha256,
                units=units,
                dependencies={"unit": []},
            ),
        )
        self.candidate_id, self.candidate_sha = self.make_candidate("candidate-one")


__all__ = ["ProjectMigrationGateAuthorityCase", "digest"]
