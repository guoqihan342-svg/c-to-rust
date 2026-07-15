from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline import (
    reopen_c2rust_project_baseline, run_c2rust_project_baseline,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_compile_db import (
    normalize_compilation_database,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_repair import (
    repair_module_static_parameter_collisions,
)
from validation.tools._project_migration_harness.project_migration_cli import parse_args
from validation.tools.project_migration_c2rust_baseline_test_support import FakeRunner


class C2RustProjectBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="c2rust-project-baseline-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.out = self.root / "out"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "include").mkdir()
        (self.repo / "src/unit.c").write_text(
            "int main(void) { return 0; }\n", encoding="utf-8",
        )
        (self.repo / "src/second-unit.c").write_text(
            "int main(void) { return 0; }\n", encoding="utf-8",
        )
        self.database = self.repo / "compile_commands.json"
        self._write_database_entries([
            self._valid_entry(), self._valid_entry("src/second-unit.c"),
        ])
        self.tools = {}
        for name in ("c2rust-transpile", "cargo", "rustc"):
            path = self.root / "tools" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((name + "\n").encode())
            self.tools[name] = path

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_cli_exposes_the_whole_project_baseline(self) -> None:
        args = parse_args([
            "c2rust-baseline", "--repo-root", str(self.repo),
            "--compile-database", str(self.database),
            "--c2rust-transpile", str(self.tools["c2rust-transpile"]),
            "--cargo", str(self.tools["cargo"]),
            "--rustc", str(self.tools["rustc"]),
            "--cargo-toolchain", "stable", "--rustc-bootstrap",
        ])
        self.assertEqual("c2rust-baseline", args.command)
        self.assertEqual("stable", args.cargo_toolchain)
        self.assertTrue(args.rustc_bootstrap)

    def test_rejects_directory_file_argv_and_output_path_escape(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "other.c").write_text("int other;\n", encoding="utf-8")
        cases = {
            "directory": {**self._valid_entry(), "directory": str(outside)},
            "file": {**self._valid_entry(), "file": "../outside/other.c"},
            "argv": {
                **self._valid_entry(),
                "arguments": ["cc", "-I", "../outside", "-c", "src/unit.c"],
            },
            "output": {**self._valid_entry(), "output": "../outside/unit.o"},
        }
        for label, entry in cases.items():
            with self.subTest(label=label):
                self._write_database(entry)
                with self.assertRaisesRegex(ValueError, "escapes"):
                    normalize_compilation_database(self.repo, self.database)

    def test_nonzero_transpiler_is_hash_bound_and_fail_closed(self) -> None:
        runner = FakeRunner(transpile_returncode=7)
        result = self._run(runner)
        self.assertEqual("blocked", result.report["status"])
        self.assertEqual(
            ["c2rust_transpile_execution_failed"], result.report["blockers"],
        )
        self.assertEqual(7, result.report["executions"][0]["returncode"])
        self.assertFalse(result.report["semantic_gate"])
        self.assertEqual(
            result.report,
            reopen_c2rust_project_baseline(self.out, result.report_ref),
        )

    def test_static_collision_repair_avoids_text_parameters_and_locals(self) -> None:
        source = """pub static mut value: i32 = 4;
// value remains in a comment
const LABEL: &str = "value";
pub unsafe fn by_parameter(value: i32) -> i32 { value }
pub unsafe fn by_static() -> i32 { value }
pub unsafe fn by_raw_static() -> *const i32 { &raw const value }
pub unsafe fn by_local() -> i32 { let value = 9; value }
pub unsafe fn qualified(value: i32) -> i32 { crate::value + value }
"""
        repaired = repair_module_static_parameter_collisions(source)
        self.assertIn("static mut __c2rust_static_value", repaired.source)
        self.assertIn("fn by_parameter(value: i32)", repaired.source)
        self.assertIn("let value = 9; value", repaired.source)
        self.assertIn("// value remains in a comment", repaired.source)
        self.assertIn('"value"', repaired.source)
        self.assertIn("by_static() -> i32 { __c2rust_static_value }", repaired.source)
        self.assertIn("&raw const __c2rust_static_value", repaired.source)
        self.assertIn("crate::__c2rust_static_value + value", repaired.source)
        self.assertEqual(3, repaired.rewritten_reference_count)

    def test_two_public_mains_create_and_execute_two_wrappers(self) -> None:
        runner = FakeRunner(self._two_main_sources())
        result = self._run(runner)
        self.assertEqual("passed", result.report["status"])
        wrappers = result.report["generated"]["wrappers"]
        self.assertEqual(2, len(wrappers))
        run_names = self._run_names(runner.calls)
        self.assertEqual({item["name"] for item in wrappers}, set(run_names))
        self.assertEqual(2, len(run_names))
        manifest = next(self.out.glob("workspaces/*/generated-output/Cargo.toml"))
        text = manifest.read_text(encoding="utf-8")
        self.assertEqual(2, text.count("[[bin]]"))
        self.assertIn("autobins = false", text)

    def test_wrapper_runs_from_its_original_compile_working_directory(self) -> None:
        build_directory = self.repo / "target/native-build/tests"
        build_directory.mkdir(parents=True)
        self._write_database_entries([
            self._valid_entry(
                "src/unit.c", directory=build_directory,
            ),
        ])
        runner = FakeRunner({
            "src/src/unit.rs": "pub unsafe extern \"C\" fn main() -> i32 { 0 }\n",
        })

        result = self._run(runner)

        self.assertEqual("passed", result.report["status"])
        self.assertEqual(build_directory.resolve(), runner.working_directories[-1])
        wrapper = result.report["generated"]["wrappers"][0]
        self.assertEqual(
            "target/native-build/tests", wrapper["source_working_directory"],
        )
        run_execution = next(
            item for item in result.report["executions"]
            if item["purpose"].startswith("cargo-run-wrapper-")
        )
        self.assertEqual(
            "repository/target/native-build/tests",
            run_execution["working_directory"],
        )

    def test_rejects_c2rust_normalized_source_path_collisions(self) -> None:
        for name in ("a-b.c", "a_b.c"):
            (self.repo / "src" / name).write_text(
                "int main(void) { return 0; }\n", encoding="utf-8",
            )
        self._write_database_entries([
            self._valid_entry("src/a-b.c"), self._valid_entry("src/a_b.c"),
        ])
        runner = FakeRunner({
            "src/src/a_b.rs": "pub unsafe extern \"C\" fn main() -> i32 { 0 }\n",
        })

        result = self._run(runner)

        self.assertEqual("blocked", result.report["status"])
        self.assertEqual(
            ["c2rust_translated_source_path_ambiguous"],
            result.report["blockers"],
        )
        self.assertEqual(1, len(runner.calls))

    def test_zero_public_main_blocks_before_cargo(self) -> None:
        runner = FakeRunner({"src/helper.rs": "pub fn helper() -> i32 { 0 }\n"})
        result = self._run(runner)
        self.assertEqual("blocked", result.report["status"])
        self.assertIn("c2rust_no_public_main", result.report["blockers"])
        self.assertEqual(1, len(runner.calls))

    def test_explicit_cargo_toolchain_and_environment_are_bound(self) -> None:
        cargo_home = self.root / "cargo-home"
        rustup_home = self.root / "rustup-home"
        cargo_home.mkdir()
        rustup_home.mkdir()
        runner = FakeRunner(self._two_main_sources())
        result = self._run(
            runner, cargo_toolchain="stable",
            environment_overrides={
                "CARGO_HOME": str(cargo_home),
                "RUSTUP_HOME": str(rustup_home),
                "RUSTC_BOOTSTRAP": "1",
            },
        )
        self.assertEqual("passed", result.report["status"])
        cargo_calls = [command for command in runner.calls if "--offline" in command]
        self.assertTrue(cargo_calls)
        self.assertTrue(all(command[1] == "+stable" for command in cargo_calls))
        self.assertTrue(all(
            environment["RUSTC_BOOTSTRAP"] == "1"
            and environment["CARGO_HOME"] == cargo_home.resolve().as_posix()
            and environment["RUSTUP_HOME"] == rustup_home.resolve().as_posix()
            for environment in runner.environments
        ))
        published = json.dumps(result.report, sort_keys=True)
        private_paths = [
            self.repo.resolve(), cargo_home.resolve(), rustup_home.resolve(),
            *(path.resolve() for path in self.tools.values()),
        ]
        for path in private_paths:
            with self.subTest(private_path=path.name):
                self.assertNotIn(path.as_posix(), published)
                self.assertNotIn(str(path), published)
        self.assertEqual(
            "portable-summary-only",
            result.report["claims"]["publication_scope"],
        )
        self.assertTrue(all(
            item["visibility"] == "private-local"
            for item in result.report["artifact_refs"]
        ))

    def test_every_wrapper_runs_even_when_one_fails(self) -> None:
        runner = FakeRunner(self._two_main_sources())
        first = self._run(runner)
        failing_name = first.report["generated"]["wrappers"][0]["name"]
        second_runner = FakeRunner(
            self._two_main_sources(), failing_bin=failing_name,
        )
        second = self._run(second_runner)
        self.assertEqual("blocked", second.report["status"])
        self.assertIn("c2rust_wrapper_execution_failed", second.report["blockers"])
        self.assertEqual(2, len(self._run_names(second_runner.calls)))

    def _run(self, runner: FakeRunner, **options):
        return run_c2rust_project_baseline(
            repo_root=self.repo, compile_commands=self.database,
            c2rust_transpile=self.tools["c2rust-transpile"], out_root=self.out,
            cargo=self.tools["cargo"], rustc=self.tools["rustc"],
            timeout_seconds=30, runner=runner,
            **options,
        )

    def _valid_entry(
        self, source: str = "src/unit.c", *, directory: Path | None = None,
    ) -> dict:
        selected_directory = directory or self.repo
        output = f"build/{Path(source).stem}.o" if directory is None else f"{Path(source).stem}.o"
        return {
            "directory": str(selected_directory), "file": str(self.repo / source),
            "arguments": [
                "cc", "-I", str(self.repo / "include"), "-c", str(self.repo / source),
                "-o", output,
            ],
            "output": output,
        }

    def _write_database(self, entry: dict) -> None:
        self.database.write_text(json.dumps([entry]), encoding="utf-8")

    def _write_database_entries(self, entries: list[dict]) -> None:
        self.database.write_text(json.dumps(entries), encoding="utf-8")

    @staticmethod
    def _two_main_sources() -> dict[str, str]:
        return {
            "src/src/unit.rs": (
                "pub static mut code: i32 = 0;\n"
                "pub unsafe extern \"C\" fn main(code: i32) -> i32 { code }\n"
            ),
            "src/src/second_unit.rs": (
                "pub unsafe extern \"C\" fn main() -> i32 { 0 }\n"
            ),
        }

    @staticmethod
    def _run_names(calls: list[list[str]]) -> list[str]:
        return [
            command[command.index("--bin") + 1]
            for command in calls if "run" in command and "--bin" in command
        ]


if __name__ == "__main__":
    unittest.main()
