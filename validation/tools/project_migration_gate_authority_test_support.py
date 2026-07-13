from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.accepted_candidates import (
    accepted_candidate_descriptors,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_run_contract import (
    load_migration_contract,
)
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_repair_authoritative_ir import (
    persist_authoritative_project_ir,
)
from validation.tools._project_migration_harness.project_rust_ir import (
    derive_bound_project_ir,
)
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

    def register_project_interface_ready(self) -> None:
        with self.ledger.connect() as connection:
            contract, manifest = load_migration_contract(
                self.ledger.path, connection, "run",
            )
        descriptors = accepted_candidate_descriptors(
            self.ledger, run_id="run", out_root_rel="target/run",
        )
        rust_project_ir = derive_bound_project_ir(
            migration_contract=contract, migration_manifest=manifest,
            candidate_descriptors=descriptors, artifact_root=self.out_root,
        )
        receipt = coordinate_project_interfaces(rust_project_ir)
        if receipt["status"] != "candidate-ready":
            raise AssertionError("test candidate unexpectedly requires project repair")
        persist_authoritative_project_ir(
            rust_project_ir, out_root=self.out_root, out_root_rel="target/run",
        )
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=receipt, rust_project_ir=rust_project_ir,
        )


__all__ = ["ProjectMigrationGateAuthorityCase", "digest"]
