from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import ProviderExecution
from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.controller import (
    dispatch_project_workers,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.project_preflight_runner import (
    run_project_worker_preflight,
)


LOGICAL_MODEL = "DeepSeek-V4-Flash"
RESOLVED_MODEL = "opencode/deepseek-v4-flash-free"


class RuntimeHarnessCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-runtime-security-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.harness = self.root / "harness"
        self.source.mkdir()
        self.harness.mkdir()
        agent_source = (
            Path(__file__).resolve().parents[2]
            / ".opencode/agents/c2rust-candidate.md"
        )
        agent_target = self.harness / ".opencode/agents/c2rust-candidate.md"
        agent_target.parent.mkdir(parents=True)
        agent_target.write_bytes(agent_source.read_bytes())

    @property
    def out_root(self) -> Path:
        return self.harness / "target/run"

    def plan(self, source: str = "int unit(void) { return 1; }\n") -> dict:
        (self.source / "unit.c").write_text(source, encoding="utf-8")
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
            run_id="runtime-security-run",
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

    def load(self, reference: dict) -> dict:
        return json.loads(
            (self.harness / Path(*reference["path"].split("/"))).read_text(
                encoding="utf-8"
            )
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

    def preflight(self, run_id: str, *, agent: str = "c2rust-candidate") -> dict:
        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(0, f"{RESOLVED_MODEL}\n", ""),
        ):
            generated = run_project_worker_preflight(
                harness_root=self.harness,
                out_root_rel="target/preflight",
                run_id=run_id,
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        report_ref = generated["report"]
        if agent == "c2rust-candidate":
            return report_ref
        report = self.load(report_ref)
        report["launch_policy"]["opencode_agent"] = agent
        return write_json_artifact(
            self.harness, "target/preflight/forged-agent-report.json", report
        )


__all__ = ["LOGICAL_MODEL", "RESOLVED_MODEL", "RuntimeHarnessCase"]
