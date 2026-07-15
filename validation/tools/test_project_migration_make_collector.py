from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.make_build_ir_adapter import (
    MakeReportSelection,
)
from validation.tools._project_migration_harness.make_dry_run_collect import (
    collect_make_facts,
)
from validation.tools._project_migration_harness.make_dry_run_host_evidence import MAKE_ENVIRONMENT
from validation.tools._project_migration_harness.make_dry_run_linux import (
    MakeDryRunBackendDiscovery, build_make_bubblewrap_argv,
    canonical_make_toolchain_evidence_bytes, create_make_toolchain_evidence,
    discover_make_dry_run_backend,
)
from validation.tools._project_migration_harness.make_dry_run_report_io import (
    MakeDryRunReopenError, reopen_make_dry_run_report,
)
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.project_migration_cli import (
    parse_args,
)
from validation.tools.test_project_migration_make_support import (
    ControlledCollectorBackend,
)


class MakeCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="make-collector-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.harness = self.base / "harness"
        self.root.mkdir()
        self.harness.mkdir()
        self.write("src/unit.c", "int unit(void) { return 7; }\n")
        self.write("include/config.h", "#define UNIT_VALUE 7\n")
        self.write_bytes("vendor/prebuilt.a", b"prebuilt-input\n")
        self.write(
            "build/Makefile",
            "all: app\n"
            "obj/unit.o: ../src/unit.c\n"
            "\tgcc -I../include -c ../src/unit.c -o obj/unit.o\n"
            "app: obj/unit.o ../vendor/prebuilt.a\n"
            "\tgcc obj/unit.o ../vendor/prebuilt.a -o app -lpthread\n",
        )
        self.stdout = (
            "gcc -I../include -c ../src/unit.c -o obj/unit.o\n"
            "gcc obj/unit.o ../vendor/prebuilt.a -o app -lpthread\n"
        ).encode("utf-8")
        self.toolchain = create_make_toolchain_evidence(
            backend_version="test-1",
            launcher_sha256="1" * 64,
            launcher_size_bytes=10,
            make_version="4.4",
            make_sha256="2" * 64,
            make_size_bytes=20,
        )
        toolchain_sha = hashlib.sha256(
            canonical_make_toolchain_evidence_bytes(self.toolchain)
        ).hexdigest()
        self.backend = ControlledCollectorBackend(toolchain_sha, self.stdout)
        self.discovery = MakeDryRunBackendDiscovery(
            self.backend, Path("make"), self.toolchain, None,
        )

    def collect(self) -> dict:
        return collect_make_facts(
            self.root,
            working_directory="build",
            makefile="Makefile",
            targets=["all"],
            out_root="target/make-facts",
            timeout_seconds=30,
            discovery=self.discovery,
        )

    def test_subdirectory_collection_reopens_and_plans(self) -> None:
        result = self.collect()
        self.assertEqual("ready", result["status"], result)
        self.assertEqual((1, 1), (
            self.backend.preflight_calls, self.backend.execute_calls,
        ))
        report_ref = result["make_report"]
        report = reopen_make_dry_run_report(self.root, report_ref)

        self.assertEqual("build", report["working_directory"])
        self.assertEqual(
            ["make", "-B", "-n", "-j1", "--no-print-directory",
             "-f", "Makefile", "--", "all"],
            report["make_argv"],
        )
        self.assertEqual(["src/unit.c"], [
            item["path"] for item in report["source_refs"]
        ])
        self.assertEqual(["src/unit.c", "vendor/prebuilt.a"], [
            item["path"] for item in report["input_refs"]
        ])
        self.assertEqual(
            ["build/obj/unit.o"], report["commands"][0]["outputs"],
        )
        self.assertEqual(
            ["build/obj/unit.o", "vendor/prebuilt.a"],
            report["commands"][1]["inputs"],
        )
        for stream in ("stdout", "stderr"):
            reference = report[f"raw_{stream}_ref"]
            self.assertTrue(reference["path"].endswith(
                f"/cas/raw-{stream}/{reference['sha256']}.bin"
            ))

        selection = MakeReportSelection(
            self.root / Path(*PurePathParts(report_ref["path"])),
            report_ref["sha256"], report_ref["size_bytes"],
        )
        plan = plan_project(
            self.root,
            harness_root=self.harness,
            out_root="target/run",
            make_report=selection,
            require_build_closure=True,
            profile="development",
        )
        self.assertEqual("planned", plan["status"], plan)
        self.assertFalse(plan["execution"]["build_closure_ready"])
        self.assertFalse(plan["claim_boundary"][
            "generated_build_closure_complete"
        ])
        self.assertTrue(plan["scheduler"]["ready_worker_ids"])
        self.assertEqual(
            "candidate-only", plan["execution"]["candidate_admission_scope"],
        )
        self.assertFalse(plan["execution"]["candidate_promotion_allowed"])
        build_ir = read_json(self.harness / "target/run/plan/build-ir.json")
        self.assertEqual("build", build_ir["translation_units"][0]["working_directory"])
        self.assertEqual("src/unit.c", build_ir["translation_units"][0]["source"]["path"])
        boundary = build_ir["claim_boundary"]
        self.assertFalse(boundary["closure_complete"])
        self.assertTrue(boundary["command_graph_complete"])
        self.assertTrue(boundary["generated_output_graph_complete"])
        self.assertTrue(boundary["repository_input_closure_complete"])
        self.assertTrue(boundary["external_dependencies_complete"])
        self.assertFalse(boundary["external_dependency_resolution_complete"])
        self.assertFalse(boundary["generated_outputs_materialized"])
        link = next(item for item in build_ir["targets"] if item["kind"] == "link")
        generated = {
            item["binding"]["path"]: item for item in build_ir["generated_inputs"]
        }
        self.assertEqual(
            [link["target_id"]], generated["build/obj/unit.o"]["consumer_target_ids"],
        )
        closure = read_json(
            self.harness / "target/run/plan/make-target-closure.json"
        )
        closure_verification = read_json(
            self.harness /
            "target/run/plan/make-target-closure-verification.json"
        )
        self.assertEqual("ready_with_boundaries", closure["status"])
        self.assertIn(
            "make_external_dependency_resolution_unverified",
            {item["kind"] for item in closure["blockers"]},
        )
        self.assertEqual(plan["artifacts"]["build_ir"], closure["build_ir"])
        self.assertEqual("verified_with_boundaries", closure_verification["status"])
        self.assertFalse(
            closure_verification["external_dependency_resolution_complete"]
        )
        self.assertEqual(
            plan["artifacts"]["build_ir"]["sha256"],
            closure_verification["build_ir_sha256"],
        )

    def test_raw_cas_drift_and_parent_escape_fail_closed(self) -> None:
        result = self.collect()
        self.assertEqual("ready", result["status"], result)
        report = reopen_make_dry_run_report(self.root, result["make_report"])
        header = self.root / "include/config.h"
        original_header = header.read_bytes()
        header.write_bytes(original_header + b"drift")
        with self.assertRaises(MakeDryRunReopenError):
            reopen_make_dry_run_report(self.root, result["make_report"])
        header.write_bytes(original_header)
        reopen_make_dry_run_report(self.root, result["make_report"])
        raw = self.root / Path(*PurePathParts(report["raw_stdout_ref"]["path"]))
        raw.write_bytes(raw.read_bytes() + b"drift")
        with self.assertRaises(MakeDryRunReopenError):
            reopen_make_dry_run_report(self.root, result["make_report"])

        blocked_backend = ControlledCollectorBackend(
            self.backend.toolchain_sha256, self.stdout,
        )
        blocked = collect_make_facts(
            self.root,
            working_directory="build",
            makefile="../../outside.mk",
            targets=["all"],
            out_root="target/escape",
            timeout_seconds=30,
            discovery=MakeDryRunBackendDiscovery(
                blocked_backend, Path("make"), self.toolchain, None,
            ),
        )
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual(0, blocked_backend.preflight_calls)

    def test_cli_contract_and_non_linux_discovery_are_explicit(self) -> None:
        parsed = parse_args([
            "collect-make-facts",
            "--repo-root", str(self.root),
            "--working-directory", "build",
            "--makefile", "Makefile",
            "--target", "all",
            "--out-root", "target/facts",
        ])
        self.assertEqual(["all"], parsed.targets)
        with mock.patch(
            "validation.tools._project_migration_harness.make_dry_run_linux."
            "platform.system",
            return_value="Windows",
        ):
            unavailable = discover_make_dry_run_backend()
        self.assertIsNone(unavailable.backend)
        self.assertEqual("make_dry_run_linux_required", unavailable.reason_code)

    def test_bubblewrap_argv_clears_environment_and_chdirs(self) -> None:
        tools = self.base / "tools"
        tools.mkdir()
        launcher = tools / "bwrap"
        make = tools / "make"
        launcher.write_bytes(b"launcher")
        make.write_bytes(b"make")
        workspace = self.base / "workspace"
        runtime = self.base / "runtime"
        (workspace / "build").mkdir(parents=True)
        runtime.mkdir()
        argv = build_make_bubblewrap_argv(
            launcher=launcher,
            make_binary=make,
            workspace=workspace,
            runtime=runtime,
            working_directory="build",
            make_args=("-B", "-n", "-j1", "--no-print-directory",
                       "-f", "Makefile", "--", "all"),
            marker_name=f"make-{'4' * 64}.started",
            plan_sha256="5" * 64,
            command_sha256="4" * 64,
        )
        self.assertIn("--clearenv", argv)
        self.assertIn("--unshare-all", argv)
        self.assertIn("--cap-drop", argv)
        self.assertEqual("/workspace/build", argv[argv.index("--chdir") + 1])
        environment = {
            argv[index + 1]: argv[index + 2]
            for index, item in enumerate(argv) if item == "--setenv"
        }
        self.assertEqual(dict(MAKE_ENVIRONMENT), environment)
        self.assertNotIn("USERPROFILE", environment)

    def write(self, relative: str, content: str) -> None:
        self.write_bytes(relative, content.encode("utf-8"))

    def write_bytes(self, relative: str, content: bytes) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def PurePathParts(value: str) -> tuple[str, ...]:
    return tuple(value.split("/"))


def read_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
