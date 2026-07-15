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
from validation.tools._project_migration_harness.candidate_compile_evidence import (
    FIXED_CARGO_CHECK,
)
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    canonical_sha256,
)
from validation.tools.project_migration_semantic_test_support import (
    passed_strict_semantic_observation,
)
from validation.tools.project_migration_compile_test_support import (
    compile_observation_for_ledger,
)
from validation.tools.project_migration_candidate_generation_test_support import (
    materialize_candidate_generation,
)


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

    def load_out_artifact(self, relative: str) -> dict:
        path = self.out_root.joinpath(*relative.split("/"))
        return json.loads(path.read_text(encoding="utf-8"))

    def materialize_candidate_project(self, rust_project_ir: dict, target: Path) -> Path:
        return materialize_candidate_generation(
            rust_project_ir, self.out_root, target,
        )

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
        candidate_set = ledger.bind_verification_candidate_set(run_id=run_id)
        sources = self._candidate_sources(
            ledger, run_id, unit_id, candidate_id, family, candidate_set,
        )
        payload = candidate_verdict_payload(
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_id,
            candidate_sha256=candidate["content_sha256"],
            gate_family=family,
            status="passed",
            diagnostics=[],
            candidate_set_sha256=candidate_set,
            source_evidence=sources,
        )
        reference = write_content_addressed_json(
            self.out_root, f"candidate/{family}", payload
        )
        ledger._record_derived_verification(
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

    def _candidate_sources(
        self, ledger: ProjectLedger, run_id: str, unit_id: str,
        candidate_id: str, family: str, candidate_set: str,
    ) -> list[dict]:
        if family == "final-verification":
            with ledger.connect() as connection:
                rows = connection.execute(
                    """select evidence_path,evidence_sha256 from verifier_records v
                       where run_id=? and unit_id=? and candidate_artifact_id=?
                         and gate_family!='final-verification'
                         and gate_epoch=(select max(newer.gate_epoch) from verifier_records newer
                           where newer.run_id=v.run_id and newer.unit_id=v.unit_id
                             and newer.candidate_artifact_id=v.candidate_artifact_id
                             and newer.gate_family=v.gate_family)
                       order by gate_family""",
                    (run_id, unit_id, candidate_id),
                ).fetchall()
            return [{
                "path": str(row["evidence_path"]),
                "sha256": str(row["evidence_sha256"]),
                "size_bytes": self.harness.joinpath(
                    *Path(str(row["evidence_path"])).parts
                ).stat().st_size,
            } for row in rows]
        if family == "compile":
            raw = compile_observation_for_ledger(
                ledger, self.harness, run_id=run_id, unit_id=unit_id,
                candidate_artifact_id=candidate_id,
                candidate_set_sha256=candidate_set,
                execution=_compile_execution(),
            )
        else:
            candidate = next(
                item for item in ledger.orchestration_rows(run_id)["artifacts"]
                if item["artifact_id"] == candidate_id
            )
            raw = passed_strict_semantic_observation(
                family, ledger=ledger, run_id=run_id, unit_id=unit_id,
                candidate_artifact_id=candidate_id,
                candidate_sha256=str(candidate["content_sha256"]),
                candidate_set_sha256=candidate_set,
            )
        reference = write_content_addressed_json(
            self.out_root, f"raw/candidate/{family}", raw
        )
        return [{**reference, "path": f"target/run/{reference['path']}"}]

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


def _compile_execution() -> dict:
    digest = lambda value: content_sha256(value)
    sandbox_contract = SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256=digest("sandbox-launcher"),
        toolchain_sha256=digest("toolchain"),
    )
    contract = sandbox_contract.sha256
    return {
        "project_state_unchanged": True,
        "checks": [{
            "command": list(FIXED_CARGO_CHECK), "status": "passed",
            "cargo_executed": True, "returncode": 0, "timed_out": False,
            "stdout_sha256": digest("stdout"), "stderr_sha256": digest("stderr"),
            "sandbox_contract_sha256": contract,
            "sandbox_command_sha256": canonical_sha256(FIXED_CARGO_CHECK),
            "sandbox_launcher_argv_sha256": digest("launcher-argv"),
        }],
        "sandbox": {
            "contract_sha256": contract,
            "contract": sandbox_contract.payload(),
        },
    }
