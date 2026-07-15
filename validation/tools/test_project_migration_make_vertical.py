from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import validation.tools.project_migration_harness as project_migration_harness
from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.build_adapter import (
    BuildInputSelection, MAKE_REPORT_INPUT_KIND,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    verify_build_ir_artifact,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.make_build_ir_adapter import (
    materialize_selected_build_ir_stage,
)
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.project_migration_cli import parse_args
from validation.tools.test_project_migration_make_support import MakeBundleFactory


class MakeVerticalClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="make-vertical-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.factory = MakeBundleFactory(self.base)

    def bundle(self, name: str, *, compile_database: bool = False) -> dict:
        return self.factory.build(name, compile_database=compile_database)

    def materialize(self, name: str) -> tuple[dict, Path, dict]:
        bundle = self.bundle(name)
        discovery = discover_project(
            bundle["root"], make_report=bundle["selection"], max_units=16,
        )
        self.assertEqual("ready", discovery["status"], discovery)
        output = bundle["harness"] / "target/run"
        artifacts = {
            "discovery": write_json_artifact(output, "plan/discovery.json", discovery),
        }
        stage = materialize_selected_build_ir_stage(
            bundle["root"], output, discovery, artifacts, bundle["selection"],
        )
        self.assertEqual("verified", stage["verification"]["status"], stage)
        return bundle, output, artifacts

    def test_cli_report_to_build_ir_plan_and_worker_admission(self) -> None:
        bundle = self.bundle("vertical")
        selection = bundle["selection"]
        argv = [
            "plan", "--repo-root", str(bundle["root"]),
            "--profile", "development",
            "--out-root", "target/run",
            "--make-report", str(selection.path),
            "--make-report-sha256", selection.sha256,
            "--make-report-size-bytes", str(selection.size_bytes),
            "--build-closure-policy", "bounded-source",
        ]
        with patch.object(
            project_migration_harness, "REPO_ROOT", bundle["harness"],
        ), redirect_stdout(io.StringIO()):
            exit_code = project_migration_harness.main(argv)

        self.assertEqual(0, exit_code)
        output = bundle["harness"] / "target/run"
        plan = self.read(output / "project-migration-plan.json")
        self.assertEqual("planned", plan["status"], plan)
        self.assertTrue(plan["execution"]["build_ir_ready"])
        self.assertFalse(plan["execution"]["make_executed"])
        self.assertFalse(plan["execution"]["build_closure_ready"])
        self.assertEqual(
            "candidate-only", plan["execution"]["candidate_admission_scope"],
        )
        self.assertFalse(plan["execution"]["candidate_promotion_allowed"])
        self.assertTrue(plan["scheduler"]["ready_worker_ids"])
        build_ir = self.read(output / "plan/build-ir.json")
        admission = self.read(output / "plan/build-ir-worker-admission.json")
        self.assertEqual("verified", admission["status"], admission)
        self.assertEqual("ready_with_boundaries", build_ir["status"])
        self.assertEqual(["make-dry-run-report"], [
            item["role"] for item in build_ir["raw_fact_refs"]
        ])
        boundary = build_ir["claim_boundary"]
        self.assertFalse(boundary["closure_complete"])
        self.assertTrue(boundary["command_graph_complete"])
        self.assertTrue(boundary["selected_translation_units_complete"])
        self.assertFalse(boundary["repository_input_closure_complete"])
        self.assertTrue(boundary["external_dependencies_complete"])
        self.assertEqual(
            [["-Lbuild"], ["-lunit"]],
            sorted(item["arguments"] for item in build_ir["external_dependencies"]),
        )
        link = next(item for item in build_ir["targets"] if item["kind"] == "link")
        self.assertEqual(
            ["build/unit.o", "vendor/prebuilt.a", "-Lbuild", "-lunit",
             "-o", "build/program"],
            link["ordered_link_arguments"],
        )
        self.assertTrue(all(
            output_binding["materialized"] is False
            for target in build_ir["targets"]
            for output_binding in target["outputs"]
        ))
        self.assertTrue(all(
            item["binding"]["materialized"] is False
            for item in build_ir["generated_inputs"]
        ))
        for toolchain in build_ir["toolchains"]:
            self.assertEqual("hash-bound-make-toolchain-evidence", toolchain["identity"])
            self.assertTrue({"version", "target", "sysroot"}.isdisjoint(toolchain))
        self.assertFalse(boundary["semantic_gate"])
        self.assertEqual(0, boundary["translation_coverage_numerator"])

    def test_required_incomplete_closure_admits_candidate_only_frontier(self) -> None:
        bundle = self.bundle("required-closure")
        plan = plan_project(
            bundle["root"], harness_root=bundle["harness"],
            out_root="target/run", make_report=bundle["selection"],
            require_build_closure=True,
        )
        self.assertEqual("planned", plan["status"], plan)
        self.assertFalse(plan["execution"]["build_closure_ready"])
        self.assertTrue(plan["scheduler"]["ready_worker_ids"])
        self.assertEqual(
            "candidate-only", plan["portfolio"]["execution"]["build_closure_admission"],
        )
        self.assertTrue(plan["portfolio"]["initial_ready"]["selected_worker_ids"])
        self.assertFalse(plan["portfolio"]["execution"]["promotion_allowed"])

    def test_report_and_every_bound_input_drift_block_reopen(self) -> None:
        mutations = {
            "report": ("output", "plan/make-dry-run-report.json"),
            "stdout": ("root", "<stdout>"),
            "stderr": ("root", "<stderr>"),
            "plan": ("root", "evidence/make-plan.json"),
            "toolchain": ("root", "evidence/toolchain.json"),
            "preflight": ("root", "evidence/sandbox.json"),
            "source": ("root", "src/unit.c"),
            "input": ("root", "vendor/prebuilt.a"),
            "makefile": ("root", "Makefile"),
        }
        for name, (location, relative) in mutations.items():
            with self.subTest(name=name):
                bundle, output, artifacts = self.materialize(f"drift-{name}")
                base = output if location == "output" else bundle["root"]
                if relative == "<stdout>":
                    relative = bundle["stdout_relative"]
                elif relative == "<stderr>":
                    relative = bundle["stderr_relative"]
                path = base / relative
                path.write_bytes(path.read_bytes() + b"drift")
                verification = verify_build_ir_artifact(
                    bundle["root"], output, artifacts["build_ir"],
                )
                self.assertEqual("blocked", verification["status"], verification)

    def test_selected_report_hash_drift_blocks_discovery(self) -> None:
        bundle = self.bundle("selection-drift")
        report_path = bundle["selection"].path
        report_path.write_bytes(report_path.read_bytes() + b"drift")
        discovery = discover_project(
            bundle["root"], make_report=bundle["selection"],
        )
        self.assertEqual("blocked", discovery["status"], discovery)
        self.assertIn("make_report_reopen_blocked", discovery["blockers"])

    def test_worker_admission_reopens_report_after_initial_projection(self) -> None:
        bundle = self.bundle("admission-drift")
        real_verify = verify_build_ir_artifact

        def drift_before_admission(repo_root, artifact_root, reference):
            raw = bundle["root"] / bundle["stdout_relative"]
            raw.write_bytes(raw.read_bytes() + b"drift")
            return real_verify(repo_root, artifact_root, reference)

        with patch(
            "validation.tools._project_migration_harness.orchestrator."
            "verify_build_ir_artifact",
            side_effect=drift_before_admission,
        ):
            plan = plan_project(
                bundle["root"], harness_root=bundle["harness"],
                out_root="target/run", make_report=bundle["selection"],
                require_build_closure=False,
            )

        self.assertEqual("blocked", plan["status"], plan)
        self.assertEqual(
            ["build_ir_worker_admission_blocked"], plan["blockers"],
        )
        admission = self.read(
            bundle["harness"] / "target/run/plan/build-ir-worker-admission.json"
        )
        self.assertEqual("blocked", admission["status"], admission)
        self.assertNotIn("portfolio_dag", plan["artifacts"])
        self.assertNotIn("migration_graph", plan["artifacts"])
        self.assertFalse(
            (bundle["harness"] / "target/run/state/project-migration.sqlite3")
            .exists()
        )

    def test_root_rename_is_semantically_equivalent(self) -> None:
        projections = []
        for name in ("identity-a", "identity-b"):
            bundle, output, _artifacts = self.materialize(name)
            projections.append(self.read(output / "plan/build-ir.json"))
        first, second = projections
        self.assertEqual(first["semantic_sha256"], second["semantic_sha256"])
        self.assertEqual(first["target_closure"], second["target_closure"])
        self.assertEqual(
            [item["unit_id"] for item in first["translation_units"]],
            [item["unit_id"] for item in second["translation_units"]],
        )

    def test_compile_database_never_selects_make_implicitly(self) -> None:
        bundle = self.bundle("selection", compile_database=True)
        automatic = discover_project(bundle["root"])
        explicit = discover_project(
            bundle["root"], make_report=bundle["selection"],
        )
        conflict = discover_project(
            bundle["root"],
            compile_database=bundle["root"] / "compile_commands.json",
            make_report=bundle["selection"],
        )
        self.assertEqual("bound", automatic["compile_database"]["status"])
        self.assertNotIn("input_kind", automatic)
        self.assertEqual("explicit-make-dry-run-report", explicit["input_kind"])
        self.assertEqual("blocked", conflict["status"])
        self.assertIn("build_input_selection_conflict", conflict["blockers"])
        parsed = parse_args([
            "plan", "--repo-root", str(bundle["root"]),
            "--make-report", str(bundle["selection"].path),
            "--make-report-sha256", bundle["selection"].sha256,
            "--make-report-size-bytes", str(bundle["selection"].size_bytes),
        ])
        self.assertIsNone(parsed.compile_database)
        self.assertIsInstance(parsed.make_report, BuildInputSelection)
        self.assertEqual(MAKE_REPORT_INPUT_KIND, parsed.make_report.kind)
        self.assertEqual(bundle["selection"].path, parsed.make_report.path)
        self.assertEqual(bundle["selection"].sha256, parsed.make_report.sha256)
        self.assertEqual(
            bundle["selection"].size_bytes, parsed.make_report.size_bytes,
        )
        self.assertEqual(
            {
                "path": bundle["selection"].path,
                "sha256": bundle["selection"].sha256,
                "size_bytes": bundle["selection"].size_bytes,
            },
            parsed.make_report.binding,
        )
        blocked = plan_project(
            bundle["root"], harness_root=bundle["harness"],
            out_root="target/conflict",
            compile_database=bundle["root"] / "compile_commands.json",
            make_report=bundle["selection"],
        )
        self.assertEqual("blocked", blocked["status"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args([
                "plan", "--repo-root", str(bundle["root"]),
                "--compile-database", str(bundle["root"] / "compile_commands.json"),
                "--make-report", str(bundle["selection"].path),
                "--make-report-sha256", bundle["selection"].sha256,
                "--make-report-size-bytes", str(bundle["selection"].size_bytes),
            ])

    @staticmethod
    def read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
