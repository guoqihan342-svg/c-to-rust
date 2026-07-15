from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import (
    write_json_artifact,
)
from validation.tools._project_migration_harness.build_ir_projection import (
    project_build_ir,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    verify_build_ir_artifact,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_evidence import (
    reopen_c2rust_project_baseline,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_unit_transpile import (
    run_c2rust_build_ir_unit_baseline,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)
from validation.tools._project_migration_harness.project_migration_cli import (
    parse_args,
)
from validation.tools.project_migration_c2rust_baseline_test_support import (
    FakeRunner,
)


class FailFirstTranspileRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.transpile_count = 0

    def __call__(self, *args, **kwargs):
        self.transpile_count += 1
        self.transpile_returncode = 9 if self.transpile_count == 1 else 0
        return super().__call__(*args, **kwargs)


class C2RustBuildIRUnitTranspileTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="c2rust-unit-transpile-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.artifacts = self.root / "artifacts"
        self.out = self.root / "out"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "include").mkdir()
        (self.repo / "build").mkdir()
        self._write("CMakeLists.txt", "add_library(program OBJECT src/unit.c)\n")
        self._write("src/unit.c", "int unit(void) { return MODE; }\n")
        self._write("include/config.h", "#define CONFIG 1\n")
        self._write("debug.rsp", "-Iinclude -DMODE=1 -std=c11 -O0\n")
        self._write("build/debug.o", b"debug-object")
        self._write("build/release.o", b"release-object")
        self.entries = [
            self._entry(
                ["clang", "@debug.rsp", "-c", "src/unit.c", "-o", "build/debug.o"],
                "build/debug.o",
            ),
            self._entry(
                [
                    "clang", "-Iinclude", "-DMODE=2", "-std=c17", "-O3",
                    "-c", "src/unit.c", "-o", "build/release.o",
                ],
                "build/release.o",
            ),
        ]
        self.database = self.repo / "build/compile_commands.json"
        self.database.write_text(json.dumps(self.entries), encoding="utf-8")
        self.reference = self._materialize()
        self.tools = {}
        for name in ("c2rust-transpile", "cargo", "rustc"):
            path = self.root / "tools" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((name + "\n").encode())
            self.tools[name] = path

    def test_variants_run_in_isolated_single_entry_databases(self) -> None:
        runner = FakeRunner()

        result = self._run(runner)

        self.assertEqual(3, result.report["schema_version"])
        self.assertEqual("blocked", result.report["status"])
        self.assertEqual(
            ["c2rust_target_cargo_assembly_pending"],
            result.report["blockers"],
        )
        self.assertFalse(result.report["semantic_gate"])
        self.assertEqual(0, result.report["translation_coverage_numerator"])
        self.assertEqual(2, len(runner.calls))
        self.assertTrue(all("--emit-build-files" in call for call in runner.calls))
        databases = [Path(call[1]) for call in runner.calls]
        self.assertEqual(2, len({path.parent.parent for path in databases}))
        payloads = [json.loads(path.read_text(encoding="utf-8")) for path in databases]
        self.assertEqual([1, 1], [len(value) for value in payloads])
        self.assertEqual({"build/debug.o", "build/release.o"}, {
            value[0]["output"] for value in payloads
        })
        units = result.report["unit_transpiles"]
        self.assertEqual(2, len(units))
        self.assertTrue(all(item["status"] == "passed" for item in units))
        self.assertTrue(all(item["generated_snapshot_ref"] for item in units))
        self.assertEqual("passed", result.report["target_exports"]["status"])
        self.assertIsNotNone(result.report["target_exports"]["ref"])
        self.assertEqual([], result.report["target_exports"]["blockers"])
        self.assertFalse(result.report["claims"]["cargo_executed"])
        self.assertEqual(
            result.report,
            reopen_c2rust_project_baseline(self.out, result.report_ref),
        )

    def test_failed_unit_does_not_suppress_later_units(self) -> None:
        runner = FailFirstTranspileRunner()

        result = self._run(runner)

        self.assertEqual(2, len(runner.calls))
        self.assertEqual(["failed", "passed"], [
            item["status"] for item in result.report["unit_transpiles"]
        ])
        self.assertIn(
            "c2rust_unit_transpile_execution_failed",
            result.report["blockers"],
        )
        self.assertIn(
            "c2rust_target_cargo_assembly_pending",
            result.report["blockers"],
        )
        self.assertIn(
            "c2rust_target_export_inventory_unavailable",
            result.report["blockers"],
        )
        self.assertEqual("unavailable", result.report["target_exports"]["status"])

    def test_database_drift_is_rejected_before_process_execution(self) -> None:
        self.database.write_bytes(self.database.read_bytes() + b"\n")
        runner = FakeRunner()

        with self.assertRaises(ValueError):
            self._run(runner)

        self.assertEqual([], runner.calls)

    def test_cli_exposes_build_ir_pair_and_rejects_partial_pair(self) -> None:
        common = [
            "c2rust-baseline", "--repo-root", str(self.repo),
            "--compile-database", str(self.database),
            "--c2rust-transpile", str(self.tools["c2rust-transpile"]),
            "--cargo", str(self.tools["cargo"]),
            "--rustc", str(self.tools["rustc"]),
        ]
        args = parse_args([
            *common, "--build-ir", str(self.artifacts / self.reference["path"]),
            "--build-ir-artifact-root", str(self.artifacts),
        ])
        self.assertEqual(self.artifacts, args.build_ir_artifact_root)
        partial = parse_args([
            *common, "--build-ir", str(self.artifacts / self.reference["path"]),
        ])
        from validation.tools._project_migration_harness.c2rust_project_baseline_cli import (
            run_c2rust_baseline_command,
        )
        with self.assertRaisesRegex(ValueError, "arguments_incomplete"):
            run_c2rust_baseline_command(partial, harness_root=self.root)

    def _run(self, runner: FakeRunner):
        return run_c2rust_build_ir_unit_baseline(
            repo_root=self.repo,
            compile_commands=self.database,
            build_ir_artifact_root=self.artifacts,
            build_ir_reference=self.reference,
            c2rust_transpile=self.tools["c2rust-transpile"],
            out_root=self.out,
            cargo=self.tools["cargo"],
            rustc=self.tools["rustc"],
            timeout_seconds=30,
            runner=runner,
        )

    def _materialize(self) -> dict:
        discovery = discover_project(self.repo, compile_database=self.database)
        self.assertEqual("ready", discovery["status"], discovery)
        closure = discovery["generated_build_closure"]
        closure_verification = verify_generated_build_closure(self.repo, closure)
        references = []
        for role, relative, payload in (
            ("discovery", "plan/discovery.json", discovery),
            ("generated-build-closure", "plan/closure.json", closure),
            (
                "generated-build-closure-verification",
                "plan/closure-verification.json",
                closure_verification,
            ),
        ):
            references.append({
                "role": role,
                **write_json_artifact(self.artifacts, relative, payload),
            })
        build_ir = project_build_ir(
            discovery, closure, closure_verification, references,
        )
        reference = write_json_artifact(
            self.artifacts, "plan/build-ir.json", build_ir,
        )
        verified = verify_build_ir_artifact(self.repo, self.artifacts, reference)
        self.assertEqual("verified", verified["status"], verified)
        return reference

    def _entry(self, arguments: list[str], output: str) -> dict:
        return {
            "directory": str(self.repo),
            "file": str(self.repo / "src/unit.c"),
            "arguments": arguments,
            "output": output,
        }

    def _write(self, relative: str, value: str | bytes) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
