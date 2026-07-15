from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.controller import dispatch_project_workers
from validation.tools._project_migration_harness.ledger import ProjectLedger


class GeneratedBuildClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="generated-closure-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.harness = Path(self.temporary.name) / "harness"
        self.root.mkdir()
        self.harness.mkdir()

    def write(self, relative: str, data: str | bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
        return path

    def project(
        self,
        *,
        include: str = "build/generated",
        materialize_include: bool = True,
        materialize_output: bool = True,
        materialize_target: bool = True,
        link_input: str = "unit.o",
        link_format: str = "link-txt",
    ) -> Path:
        self.write("CMakeLists.txt", "add_executable(sample src/unit.c)\n")
        self.write("src/unit.c", "int unit(void) { return 1; }\n")
        if materialize_include:
            self.write(f"{include}/config.h", "#define VALUE 1\n")
        if materialize_output:
            self.write("build/unit.o", b"object-v1")
        if materialize_target:
            self.write("build/program.bin", b"target-v1")
        if link_format == "link-txt":
            self.write(
                "build/CMakeFiles/generated.dir/link.txt",
                f"clang {link_input} -o program.bin -lm\n",
            )
        elif link_format == "ninja":
            self.write(
                "build/CMakeFiles/rules.ninja",
                "rule C_LINKER\n"
                "  command = $PRE_LINK && clang $in -o $TARGET_FILE "
                "$LINK_LIBRARIES && $POST_BUILD\n",
            )
            self.write(
                "build/build.ninja",
                "ninja_required_version = 1.8\n"
                "include CMakeFiles/rules.ninja\n"
                f"build program.bin: C_LINKER {link_input}\n"
                "  LINK_LIBRARIES = -lm\n"
                "  PRE_LINK = :\n"
                "  POST_BUILD = :\n"
                "  TARGET_FILE = program.bin\n"
                "build all: phony program.bin\n"
                "default all\n",
            )
        else:
            raise ValueError("unsupported test link format")
        database = self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root),
            "file": "src/unit.c",
            "arguments": [
                "clang", f"-I{include}", "-c", "src/unit.c",
                "-o", "build/unit.o",
            ],
            "output": "build/unit.o",
        }]))
        return database

    def test_binds_generated_include_object_target_and_link_inputs(self) -> None:
        database = self.project()

        result = discover_project(self.root, compile_database=database)

        self.assertEqual("ready", result["status"])
        closure = result["generated_build_closure"]
        self.assertEqual("ready", closure["status"], closure)
        self.assertEqual([], closure["blockers"])
        include = closure["generated_include_roots"][0]
        self.assertEqual("build/generated", include["path"])
        self.assertEqual("directory", include["kind"])
        output = closure["compile_outputs"][0]
        self.assertEqual("build/unit.o", output["path"])
        self.assertEqual(
            hashlib.sha256(b"object-v1").hexdigest(), output["sha256"]
        )
        link = closure["target_link_closure"]
        self.assertEqual("ready", link["status"])
        self.assertEqual("build/program.bin", link["targets"][0]["output"]["path"])
        self.assertEqual(
            ["build/unit.o"],
            [item["path"] for item in link["targets"][0]["inputs"]],
        )
        self.assertFalse(closure["claim_boundary"]["parameters_guessed"])

    def test_missing_generated_artifacts_are_explicit_blockers(self) -> None:
        database = self.project(
            materialize_include=False,
            materialize_output=False,
            materialize_target=False,
        )

        result = discover_project(self.root, compile_database=database)

        closure = result["generated_build_closure"]
        self.assertEqual("blocked", closure["status"])
        kinds = {item["kind"] for item in closure["blockers"]}
        self.assertTrue({
            "generated_include_missing",
            "compile_output_missing",
            "link_input_missing",
            "link_target_missing",
        } <= kinds)
        self.assertEqual([], closure["target_link_closure"]["targets"][0]["inputs"])

    def test_binds_ninja_link_edge_and_included_rule_without_execution(self) -> None:
        database = self.project(link_format="ninja")

        closure = discover_project(
            self.root, compile_database=database
        )["generated_build_closure"]

        self.assertEqual("ready", closure["status"], closure)
        link = closure["target_link_closure"]
        self.assertEqual("ready", link["status"], link)
        self.assertEqual("build/program.bin", link["targets"][0]["output"]["path"])
        self.assertEqual(
            ["build/unit.o"],
            [item["path"] for item in link["targets"][0]["inputs"]],
        )
        self.assertEqual(
            ["build/CMakeFiles/rules.ninja", "build/build.ninja"],
            [item["path"] for item in link["support_files"]],
        )
        self.assertFalse(link["parameters_guessed"])

    def test_ninja_included_rule_drift_is_rejected_on_reopen(self) -> None:
        database = self.project(link_format="ninja")
        closure = discover_project(
            self.root, compile_database=database
        )["generated_build_closure"]
        self.write("build/CMakeFiles/rules.ninja", "rule changed\n  command = false\n")

        verification = verify_generated_build_closure(self.root, closure)

        self.assertEqual("blocked", verification["status"])
        self.assertIn(
            {
                "kind": "artifact_sha256_drift",
                "path": "build/CMakeFiles/rules.ninja",
            },
            verification["blockers"],
        )

    def test_external_include_and_object_input_are_blockers(self) -> None:
        external = Path(self.temporary.name) / "external.o"
        external.write_bytes(b"external")
        database = self.project(
            include=external.parent.as_posix(),
            link_input=external.as_posix(),
        )

        closure = discover_project(
            self.root, compile_database=database
        )["generated_build_closure"]

        kinds = {item["kind"] for item in closure["blockers"]}
        self.assertIn("external_include_path", kinds)
        self.assertIn("link_input_path_outside_repository", kinds)
        self.assertNotIn(
            external.as_posix(),
            {item.get("path") for item in closure["blockers"]},
        )
        self.assertEqual("blocked", closure["status"])

    def test_reopen_verifier_detects_hash_drift(self) -> None:
        database = self.project()
        closure = discover_project(
            self.root, compile_database=database
        )["generated_build_closure"]
        self.write("build/unit.o", b"object-v2")

        verification = verify_generated_build_closure(self.root, closure)

        self.assertEqual("blocked", verification["status"])
        self.assertIn(
            {"kind": "artifact_sha256_drift", "path": "build/unit.o"},
            verification["blockers"],
        )

    def test_reopen_requires_complete_link_replay_inputs(self) -> None:
        database = self.project()
        closure = discover_project(
            self.root, compile_database=database,
        )["generated_build_closure"]
        missing = {
            "compile_database": "compile_database_replay_binding_missing",
            "generated_stage_facts": "generated_stage_facts_replay_missing",
            "target_link_closure": "target_link_closure_replay_missing",
        }
        for field, reason in missing.items():
            with self.subTest(field=field):
                altered = copy.deepcopy(closure)
                del altered[field]
                verification = verify_generated_build_closure(self.root, altered)
                self.assertEqual("blocked", verification["status"])
                self.assertIn(reason, {
                    item["kind"] for item in verification["blockers"]
                })

    def test_orchestrator_materializes_hash_bound_closure_artifact(self) -> None:
        database = self.project()

        plan = plan_project(
            self.root,
            harness_root=self.harness,
            out_root="target/closure-run",
            compile_database=database,
        )

        self.assertEqual("planned", plan["status"])
        self.assertTrue(plan["execution"]["build_closure_ready"])
        binding = plan["artifacts"]["generated_build_closure"]
        artifact = self.harness / "target/closure-run/plan/generated-build-closure.json"
        self.assertTrue(artifact.is_file())
        self.assertEqual(
            hashlib.sha256(artifact.read_bytes()).hexdigest(), binding["sha256"]
        )
        verification = plan["artifacts"]["generated_build_closure_verification"]
        self.assertEqual(64, len(verification["sha256"]))

    def test_orchestrator_admits_only_candidate_frontier_without_closure(self) -> None:
        database = self.project(
            materialize_include=False,
            materialize_output=False,
            materialize_target=False,
        )

        plan = plan_project(
            self.root,
            harness_root=self.harness,
            out_root="target/blocked-closure",
            compile_database=database,
            require_build_closure=True,
        )

        self.assertEqual("planned", plan["status"])
        self.assertFalse(plan["execution"]["build_closure_ready"])
        self.assertFalse(plan["execution"]["model_launched"])
        self.assertEqual(
            "dispatch_candidate_only_workers",
            plan["execution"]["next_action"],
        )
        self.assertTrue(plan["scheduler"]["ready_worker_ids"])
        self.assertEqual(
            "candidate-only", plan["portfolio"]["execution"]["build_closure_admission"],
        )
        self.assertFalse(
            plan["claim_boundary"]["generated_build_closure_complete"]
        )
        ledger = ProjectLedger(
            self.harness / "target/blocked-closure/state/project-migration.sqlite3"
        )
        dispatch = dispatch_project_workers(
            plan["portfolio"],
            ledger=ledger,
            harness_root=self.harness,
            out_root=self.harness / "target/blocked-closure",
            out_root_rel="target/blocked-closure",
        )
        self.assertTrue(dispatch["launches"])


if __name__ == "__main__":
    unittest.main()
