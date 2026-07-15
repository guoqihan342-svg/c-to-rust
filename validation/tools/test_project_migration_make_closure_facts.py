from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir import stable_build_id
from validation.tools._project_migration_harness.build_ir_host_toolchains import (
    HostToolchainProjection,
)
from validation.tools._project_migration_harness.make_build_ir_adapter import (
    MakeReportSelection,
)
from validation.tools._project_migration_harness.make_build_ir_closure import (
    project_make_closure,
)
from validation.tools._project_migration_harness.make_build_ir_closure_resolution import (
    WITNESS_KIND, create_toolchain_argument_resolution_record,
)
from validation.tools._project_migration_harness.make_dry_run_collect import (
    collect_make_facts,
)
from validation.tools._project_migration_harness.make_dry_run_contract import (
    MakeDryRunContractError, validate_make_dry_run_report,
)
from validation.tools._project_migration_harness.make_dry_run_linux import (
    MakeDryRunBackendDiscovery, canonical_make_toolchain_evidence_bytes,
    create_make_toolchain_evidence,
)
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.make_dry_run_report_io import (
    reopen_make_dry_run_report,
)
from validation.tools.test_project_migration_make_support import (
    ControlledCollectorBackend,
)
from validation.tools.project_migration_build_ir_host_test_support import (
    BuildIRHostBindingTestCase,
)


class MakeClosureFactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="make-closure-facts-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.harness = self.base / "harness"
        self.root.mkdir()
        self.harness.mkdir()
        self.write("src/unit.c", "int unit(void) { return 7; }\n")
        self.write("config/link.map", "{ global: unit; local: *; };\n")
        self.write(
            "Makefile",
            "all: build/app\n"
            "build/unit.o: src/unit.c\n"
            "\tgcc -c src/unit.c -o build/unit.o\n"
            "build/app: build/unit.o\n"
            "\tgcc build/unit.o -Wl,--version-script=config/link.map "
            "-o build/app\n",
        )

    def test_unbound_forwarded_link_input_keeps_required_closure_deferred(self) -> None:
        stdout = (
            "gcc -c src/unit.c -o build/unit.o\n"
            "gcc build/unit.o -Wl,--version-script=config/link.map "
            "-o build/app\n"
        ).encode("utf-8")
        toolchain = create_make_toolchain_evidence(
            backend_version="test-1", launcher_sha256="1" * 64,
            launcher_size_bytes=10, make_version="4.4",
            make_sha256="2" * 64, make_size_bytes=20,
        )
        toolchain_sha = hashlib.sha256(
            canonical_make_toolchain_evidence_bytes(toolchain)
        ).hexdigest()
        backend = ControlledCollectorBackend(toolchain_sha, stdout)
        result = collect_make_facts(
            self.root, working_directory=".", makefile="Makefile",
            targets=["all"], out_root="target/make-facts", timeout_seconds=30,
            discovery=MakeDryRunBackendDiscovery(
                backend, Path("make"), toolchain, None,
            ),
        )
        self.assertEqual("ready", result["status"], result)
        report_ref = result["make_report"]
        report = reopen_make_dry_run_report(self.root, report_ref)
        non_cas = copy.deepcopy(report)
        non_cas["repository_snapshot_ref"]["path"] = "evidence/snapshot.json"
        with self.assertRaisesRegex(
            MakeDryRunContractError, "repository_snapshot_ref_not_cas",
        ):
            validate_make_dry_run_report(non_cas)
        selection = MakeReportSelection(
            self.root / Path(*report_ref["path"].split("/")),
            report_ref["sha256"], report_ref["size_bytes"],
        )
        plan = plan_project(
            self.root, harness_root=self.harness, out_root="target/run",
            make_report=selection, require_build_closure=True,
        )
        self.assertEqual("planned", plan["status"], plan)
        self.assertFalse(plan["execution"]["build_closure_ready"])
        self.assertEqual([], plan["scheduler"]["ready_worker_ids"])
        build_ir = self.read("target/run/plan/build-ir.json")
        claim = build_ir["claim_boundary"]
        self.assertTrue(claim["command_graph_complete"])
        self.assertTrue(claim["repository_input_closure_complete"])
        self.assertFalse(claim["external_dependencies_complete"])
        self.assertFalse(claim["closure_complete"])
        self.assertGreater(claim["link_argument_classification_error_count"], 0)
        broken_targets = copy.deepcopy(build_ir["targets"])
        link = next(item for item in broken_targets if item["kind"] == "link")
        link["ordered_inputs"][0]["dependency_target_id"] = None
        broken = project_make_closure(
            report, broken_targets, [], link_classification_error_count=0,
            report_inputs_verified=True,
        )
        self.assertFalse(broken["claim_boundary"]["command_graph_complete"])
        self.assertFalse(
            broken["claim_boundary"]["generated_output_graph_complete"]
        )
        self.assertIn(
            "make_generated_output_graph_incomplete",
            {item["kind"] for item in broken["boundaries"]},
        )
        closure = self.read("target/run/plan/make-target-closure.json")
        self.assertEqual("ready_with_boundaries", closure["status"])
        self.assertIn(
            "make_link_argument_classification_incomplete",
            {item["kind"] for item in closure["blockers"]},
        )
    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    def read(self, relative: str) -> dict:
        return json.loads((self.harness / relative).read_text(encoding="utf-8"))
class MakeClosureResolutionTests(BuildIRHostBindingTestCase):
    def test_unresolved_dependency_blocks_required_closure(self) -> None:
        report, targets, dependency, toolchains, _record = self.fixture()
        dependency["resolved"] = False
        closure = self.project(report, targets, dependency, toolchains)
        claim = closure["claim_boundary"]
        self.assertFalse(claim["closure_complete"])
        self.assertFalse(claim["external_dependency_resolution_complete"])
        self.assertEqual(1, claim["unresolved_external_dependency_count"])
        blocker = next(
            item for item in closure["boundaries"]
            if item["kind"] == "make_external_dependency_resolution_unverified"
        )
        self.assertIn(
            "external_dependency_resolution_record_missing",
            blocker["reason_codes"],
        )
    def test_bound_toolchain_resolution_record_allows_closure(self) -> None:
        report, targets, dependency, toolchains, record = self.fixture()
        closure = self.project(
            report, targets, dependency, toolchains, records=[record],
        )
        claim = closure["claim_boundary"]
        self.assertTrue(claim["closure_complete"], closure)
        self.assertTrue(claim["external_dependency_resolution_complete"])
        self.assertEqual([record], claim["external_dependency_resolution_records"])
        self.assertNotIn(
            "make_external_dependency_resolution_unverified",
            {item["kind"] for item in closure["boundaries"]},
        )
    def test_classification_error_blocks_even_with_resolution(self) -> None:
        report, targets, dependency, toolchains, record = self.fixture()
        closure = project_make_closure(
            report, targets, [dependency], link_classification_error_count=1,
            report_inputs_verified=True,
            external_dependency_resolution_records=[record],
            toolchains=toolchains,
        )
        self.assertFalse(closure["claim_boundary"]["closure_complete"])
        self.assertIn(
            "make_link_argument_classification_incomplete",
            {item["kind"] for item in closure["boundaries"]},
        )
    def test_report_command_hash_drift_invalidates_resolution(self) -> None:
        report, targets, dependency, toolchains, record = self.fixture()
        report["commands"][1]["argv_sha256"] = "f" * 64
        closure = self.project(
            report, targets, dependency, toolchains, records=[record],
        )
        claim = closure["claim_boundary"]
        self.assertTrue(claim["command_graph_complete"])
        self.assertFalse(claim["external_dependency_resolution_complete"])
        blocker = next(
            item for item in closure["boundaries"]
            if item["kind"] == "make_external_dependency_resolution_unverified"
        )
        self.assertIn(
            "external_dependency_report_command_drift", blocker["reason_codes"],
        )
    @staticmethod
    def project(
        report: dict, targets: list[dict], dependency: dict,
        toolchains: list[dict], *, records: list[dict] | None = None,
    ) -> dict:
        return project_make_closure(
            report, targets, [dependency], link_classification_error_count=0,
            report_inputs_verified=True,
            external_dependency_resolution_records=records,
            toolchains=toolchains,
        )
    def fixture(self) -> tuple[dict, list[dict], dict, list[dict], dict]:
        projector = HostToolchainProjection(self.full_evidence())
        compile_toolchain = projector.compile("gcc", [], "c")
        link_toolchain = projector.command("gcc", "linker-driver")
        source = {
            "path": "src/unit.c", "kind": "file", "materialized": True,
            "sha256": "a" * 64, "size_bytes": 1,
        }
        object_output = {
            "path": "build/unit.o", "kind": "file", "materialized": False,
        }
        link_argv = ["gcc", "build/unit.o", "-pthread", "-o", "build/app"]
        commands = [
            _command(0, ["gcc", "-c", "src/unit.c", "-o", "build/unit.o"],
                     ["src/unit.c"], ["build/unit.o"], "compile"),
            _command(1, link_argv, ["build/unit.o"], ["build/app"], "link"),
        ]
        targets = [
            _target("object-target", "object", object_output, source, commands[0],
                    compile_toolchain),
            _target("link-target", "link",
                    {"path": "build/app", "kind": "file", "materialized": False},
                    object_output, commands[1], link_toolchain,
                    dependency="object-target"),
        ]
        identity = {
            "target": "link-target", "ordinal": 1, "arguments": ["-pthread"],
        }
        dependency = {
            "dependency_id": stable_build_id("external", identity),
            "kind": "library-name", "name": "-pthread",
            "consumer_target_ids": ["link-target"], "ordinal": 1,
            "arguments": ["-pthread"], "resolved": True,
            "provenance": {"raw_fact_role": "make-dry-run-report"},
        }
        toolchains = projector.records()
        link_record = next(
            item for item in toolchains if item["toolchain_id"] == link_toolchain
        )
        record = create_toolchain_argument_resolution_record(
            commands[1], targets[1], dependency, link_record,
            {
                "artifact_kind": WITNESS_KIND, "status": "verified",
                "path": "facts/link-argument-resolution.json",
                "sha256": "b" * 64, "size_bytes": 128,
            },
        )
        report = {"commands": commands, "input_refs": [source],
                  "repository_snapshot_ref": {"sha256": "c" * 64}}
        return report, targets, dependency, toolchains, record

def _command(
    ordinal: int, argv: list[str], inputs: list[str], outputs: list[str], kind: str,
) -> dict:
    return {
        "ordinal": ordinal, "kind": kind, "tool": argv[0], "argv": argv,
        "argv_sha256": content_sha256(argv), "inputs": inputs, "outputs": outputs,
    }
def _target(
    identifier: str, kind: str, output: dict, input_binding: dict,
    command: dict, toolchain_id: str, dependency: str | None = None,
) -> dict:
    canonical_kind = "object" if kind == "object" else kind
    return {
        "target_id": identifier, "kind": canonical_kind, "outputs": [output],
        "ordered_inputs": [{
            "ordinal": 0, "role": "source" if dependency is None else "link-input",
            "binding": input_binding, "dependency_target_id": dependency,
        }],
        "dependency_target_ids": [] if dependency is None else [dependency],
        "compile_argument_sets": [] if kind == "link" else [{
            "kind": command["kind"], "command_ordinal": command["ordinal"],
            "arguments": command["argv"][1:],
            "argv_sha256": command["argv_sha256"],
        }],
        "ordered_link_arguments": command["argv"][1:] if kind == "link" else [],
        "provenance": {
            "raw_fact_role": "make-dry-run-report",
            "command_ordinal": command["ordinal"],
        },
        "toolchain_id": toolchain_id,
    }


if __name__ == "__main__":
    unittest.main()
