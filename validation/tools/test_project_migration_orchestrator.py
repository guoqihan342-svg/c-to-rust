from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.ledger_schema import SCHEMA_VERSION


class ProjectMigrationOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="project-orchestrator-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input"
        self.harness = self.root / "harness"
        self.source.mkdir()
        self.harness.mkdir()

    def write_project(self, source: str) -> Path:
        source_path = self.source / "src/unit.c"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(source, encoding="utf-8")
        database = self.source / "build/compile_commands.json"
        database.parent.mkdir(parents=True, exist_ok=True)
        database.write_text(json.dumps([{
            "directory": str(self.source),
            "file": "src/unit.c",
            "arguments": ["clang", "-std=c11", "-c", "src/unit.c", "-o", "build/unit.o"],
            "output": "build/unit.o",
        }]), encoding="utf-8")
        return database

    def test_repo_root_plan_builds_waves_contexts_portfolio_and_resumable_ledger(self) -> None:
        database = self.write_project(
            "static int seed(void) { return 3; }\n"
            "int combine(void) { return seed() + 1; }\n"
        )

        first = plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/run-one",
            compile_database=database,
            max_concurrency=2,
        )
        second = plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/run-one",
            compile_database=database,
            max_concurrency=2,
        )

        self.assertEqual("planned", first["status"])
        self.assertEqual("bound", first["ledger"]["status"])
        self.assertEqual(SCHEMA_VERSION, first["ledger"]["schema_version"])
        self.assertEqual("bound", second["ledger"]["status"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["plan_sha256"], second["plan_sha256"])
        returned = dict(first)
        returned_sha256 = returned.pop("plan_sha256")
        self.assertEqual(returned_sha256, content_sha256(returned))
        self.assertEqual(6, len(first["portfolio"]["assignments"]))
        self.assertEqual(2, len(first["portfolio"]["waves"]))
        self.assertTrue(all(
            assignment["authority"]["semantic_acceptance"] is False
            for assignment in first["portfolio"]["assignments"]
        ))
        self.assertFalse(first["execution"]["model_launched"])
        self.assertFalse((
            self.harness / "target/run-one/context/pages"
        ).exists())
        self.assertFalse((
            self.harness / "target/run-one/harness/assignments"
        ).exists())
        self.assertTrue((
            self.harness / "target/run-one/project-migration-plan.json"
        ).is_file())
        stored = json.loads((
            self.harness / "target/run-one/project-migration-plan.json"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("assignments", stored["portfolio"])
        self.assertEqual(
            first["artifacts"]["portfolio"], stored["portfolio"]["full_payload"],
        )
        claimed = stored.pop("plan_sha256")
        self.assertEqual(claimed, content_sha256(stored))

    def test_unknown_external_without_declaration_waits_without_model_launch(self) -> None:
        database = self.write_project(
            "int closed(void) { return 1; }\n"
            "int boundary(void) { return external_api(); }\n"
        )

        result = plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/boundary",
            compile_database=database,
        )

        self.assertEqual("planned", result["status"])
        boundary = [
            item
            for item in result["portfolio"]["assignments"]
            if item["role"] == "planner"
        ]
        self.assertEqual(1, len(boundary))
        self.assertEqual(7, len(result["portfolio"]["assignments"]))
        self.assertEqual([], result["portfolio"]["blocked_groups"])
        self.assertEqual(1, len(result["portfolio"]["pending_retrieval_groups"]))
        self.assertEqual(
            ["context_retrieval_not_ready"],
            result["portfolio"]["pending_retrieval_groups"][0]["reasons"],
        )
        self.assertNotIn(boundary[0]["worker_id"], result["scheduler"]["ready_worker_ids"])
        self.assertFalse(result["execution"]["model_launched"])

    def test_missing_compile_database_stops_before_model_and_ledger(self) -> None:
        (self.source / "unit.c").write_text("int unit(void) { return 1; }\n", encoding="utf-8")

        result = plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/blocked",
        )

        self.assertEqual("blocked", result["status"])
        self.assertEqual(["discovery_blocked"], result["blockers"])
        self.assertFalse(result["execution"]["model_launched"])
        self.assertFalse((
            self.harness / "target/blocked/state/project-migration.sqlite3"
        ).exists())


if __name__ == "__main__":
    unittest.main()
