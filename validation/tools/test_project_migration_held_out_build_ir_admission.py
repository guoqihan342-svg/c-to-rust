from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools.project_migration_held_out_build_ir_admission_test_support import (
    HeldOutBuildIRAdmissionTestSupport,
)


class ProjectMigrationHeldOutBuildIRAdmissionTests(
    HeldOutBuildIRAdmissionTestSupport,
    unittest.TestCase,
):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="project-held-out-build-ir-admission-",
        )
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.harness = self.base / "harness"
        self.harness.mkdir()

    def test_build_ir_checks_precede_index_and_dag_for_finite_projects(self) -> None:
        expected_order = [
            "build_ir_validation[1]", "build_ir_validation[2]", "c_index",
            "migration_graph", "context_pages", "context_portfolio", "ledger",
        ]
        for ordinal in range(2):
            with self.subTest(ordinal=ordinal):
                source, database, identity, _ = self.write_project(ordinal)
                out_root = f"target/held-out/{identity}"
                events: list[str] = []
                validator = self.validator(events)
                plan, stages = self.run_plan(
                    source, database, identity=identity, out_root=out_root,
                    events=events, validator=validator,
                )

                self.assertIn(
                    plan["status"], {"planned", "ready", "ready_with_boundaries"},
                )
                self.assertEqual(expected_order, events)
                self.assertEqual(2, validator.call_count)
                self.assertEqual(
                    validator.call_args_list[0].args[2],
                    validator.call_args_list[1].args[2],
                )
                for stage in stages.values():
                    stage.assert_called_once()
                initial = self.read_artifact(
                    out_root, plan["artifacts"]["build_ir_verification"],
                )
                admission = self.read_artifact(
                    out_root, plan["artifacts"]["build_ir_worker_admission"],
                )
                self.assertEqual("verified", initial["status"], initial)
                self.assertEqual("verified", admission["status"], admission)
                self.assertIn("portfolio_dag", plan["artifacts"])
                self.assertTrue(
                    (self.output(out_root) / "state/project-migration.sqlite3").is_file()
                )
                self.assert_nonsemantic_plan(plan)

    def test_initial_build_ir_failure_stops_before_all_downstream_work(self) -> None:
        source, database, identity, source_file = self.write_project(10)
        out_root = f"target/held-out/{identity}"
        events: list[str] = []
        validator = self.validator(events, drift_call=1, drift_path=source_file)
        plan, stages = self.run_plan(
            source, database, identity=identity, out_root=out_root,
            events=events, validator=validator,
        )

        self.assertEqual("blocked", plan["status"])
        self.assertEqual(["build_ir_validation[1]"], events)
        verification = self.read_artifact(
            out_root, plan["artifacts"]["build_ir_verification"],
        )
        self.assertEqual("blocked", verification["status"])
        self.assertNotIn("build_ir_worker_admission", plan["artifacts"])
        self.assert_no_downstream_effects(plan, stages, out_root)

    def test_worker_admission_drift_stops_before_all_downstream_work(self) -> None:
        source, database, identity, source_file = self.write_project(20)
        out_root = f"target/held-out/{identity}"
        events: list[str] = []
        validator = self.validator(events, drift_call=2, drift_path=source_file)
        plan, stages = self.run_plan(
            source, database, identity=identity, out_root=out_root,
            events=events, validator=validator,
        )

        self.assertEqual("blocked", plan["status"])
        self.assertEqual(
            ["build_ir_validation[1]", "build_ir_validation[2]"], events,
        )
        initial = self.read_artifact(
            out_root, plan["artifacts"]["build_ir_verification"],
        )
        admission = self.read_artifact(
            out_root, plan["artifacts"]["build_ir_worker_admission"],
        )
        self.assertEqual("verified", initial["status"], initial)
        self.assertEqual("blocked", admission["status"], admission)
        self.assertIn(
            "artifact_sha256_drift",
            {item["kind"] for item in admission["blockers"]},
        )
        self.assert_no_downstream_effects(plan, stages, out_root)


if __name__ == "__main__":
    unittest.main()
