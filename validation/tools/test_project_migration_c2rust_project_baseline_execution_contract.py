from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline import (
    reopen_c2rust_project_baseline, run_c2rust_project_baseline,
)
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.c2rust_project_baseline_evidence import (
    C2RustBaselineEvidenceError, write_baseline_report,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_schema import (
    validate_c2rust_baseline_report,
)
from validation.tools._project_migration_harness.project_migration_cli import parse_args
from validation.tools.project_migration_c2rust_baseline_test_support import FakeRunner


class BaselineExecutionContractIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="c2rust-contract-run-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.out = self.root / "out"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "build/tests").mkdir(parents=True)
        (self.repo / "fixtures").mkdir()
        (self.repo / "fixtures/input.xml").write_text("<root/>\n", encoding="utf-8")
        for name in ("unit.c", "second-unit.c"):
            (self.repo / "src" / name).write_text(
                "int main(void) { return 0; }\n", encoding="utf-8",
            )
        self.database = self.repo / "compile_commands.json"
        self.database.write_text(json.dumps([
            self._entry("src/unit.c"), self._entry("src/second-unit.c"),
        ]), encoding="utf-8")
        self.contract = self.repo / "build/execution-contract.json"
        self.tools = {}
        for name in ("c2rust-transpile", "cargo", "rustc"):
            path = self.root / "tools" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name, encoding="utf-8")
            self.tools[name] = path

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_declared_scenarios_execute_exact_inputs_and_compile_only_does_not_run(self) -> None:
        self._write_contract(self._contract_payload())
        runner = FakeRunner(
            self._generated_sources(), returncode_by_token={"--expect-seven": 7},
        )

        result = self._run(runner)

        self.assertEqual("passed", result.report["status"])
        plan = result.report["generated"]["execution_plan"]
        self.assertEqual("declared-scenarios", plan["mode"])
        self.assertEqual(2, plan["scenario_count"])
        self.assertEqual(1, plan["compile_only_wrapper_count"])
        scenario_executions = [
            item for item in result.report["executions"]
            if item["purpose"].startswith("cargo-run-scenario-")
        ]
        self.assertEqual(
            ["cargo-run-scenario-case-input", "cargo-run-scenario-case-seven"],
            [item["purpose"] for item in scenario_executions],
        )
        self.assertFalse(any(
            item["purpose"].startswith("cargo-run-wrapper-")
            for item in result.report["executions"]
        ))
        self.assertEqual([0], scenario_executions[0]["expected_returncodes"])
        self.assertEqual([7], scenario_executions[1]["expected_returncodes"])
        self.assertEqual(b"<stdin/>\n", runner.stdins[-2])
        self.assertEqual(b"", runner.stdins[-1])
        self.assertEqual("strict", runner.environments[-2]["CASE_MODE"])
        self.assertEqual((self.repo / "build/tests").resolve(), runner.working_directories[-2])
        self.assertEqual(
            result.report,
            reopen_c2rust_project_baseline(self.out, result.report_ref),
        )

    def test_incomplete_mapping_blocks_before_any_cargo_command(self) -> None:
        payload = self._contract_payload()
        payload["wrappers"].pop()
        self._write_contract(payload)
        runner = FakeRunner(self._generated_sources())

        result = self._run(runner)

        self.assertEqual("blocked", result.report["status"])
        self.assertIn(
            "c2rust_scenario_wrapper_mapping_incomplete",
            result.report["blockers"],
        )
        self.assertEqual(1, len(runner.calls))
        self.assertEqual("source-bound", result.report["inputs"]["execution_contract"]["status"])

    def test_scenario_timeout_above_run_policy_blocks_before_cargo(self) -> None:
        payload = self._contract_payload()
        payload["wrappers"][0]["scenarios"][0]["timeout_seconds"] = 31
        self._write_contract(payload)
        runner = FakeRunner(self._generated_sources())

        result = self._run(runner, timeout_seconds=30)

        self.assertEqual("blocked", result.report["status"])
        self.assertEqual(
            ["c2rust_scenario_timeout_exceeds_policy"],
            result.report["blockers"],
        )
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(
            "validated", result.report["inputs"]["execution_contract"]["status"],
        )

    def test_contract_binding_drift_is_rejected_by_schema_and_reopener(self) -> None:
        self._write_contract(self._contract_payload())
        result = self._run(FakeRunner(self._generated_sources()))
        forged = copy.deepcopy(result.report)
        forged["generated"]["execution_plan"]["contract_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "mode_binding_invalid"):
            validate_c2rust_baseline_report(forged)
        normalized = result.report["inputs"]["execution_contract"]["normalized_ref"]
        target = self.out.joinpath(*Path(normalized["path"]).parts)
        target.write_bytes(b"{}\n")
        with self.assertRaisesRegex(ValueError, "content_drifted"):
            reopen_c2rust_project_baseline(self.out, result.report_ref)

    def test_report_reopen_cross_binds_each_scenario_input_to_contract(self) -> None:
        self._write_contract(self._contract_payload())
        result = self._run(FakeRunner(self._generated_sources()))
        scenario_indexes = [
            index for index, item in enumerate(result.report["executions"])
            if item["purpose"].startswith("cargo-run-scenario-")
        ]
        first, second = scenario_indexes

        forged_argv = copy.deepcopy(result.report)
        execution = forged_argv["executions"][first]
        execution["argv"][-1] = "../../fixtures/other.xml"
        execution["argv_sha256"] = content_sha256(execution["argv"])

        forged_timeout = copy.deepcopy(result.report)
        forged_timeout["executions"][first]["timeout_seconds"] = 29

        forged_environment = copy.deepcopy(result.report)
        keys = forged_environment["executions"][first]["environment_keys"]
        forged_environment["executions"][first]["environment_keys"] = sorted(
            [*keys, "FORGED_MODE"],
        )

        forged_stdin = copy.deepcopy(result.report)
        replacement = forged_stdin["executions"][second]["stdin_ref"]
        forged_stdin["executions"][first]["stdin_ref"] = replacement
        forged_stdin["executions"][first]["stdin_sha256"] = replacement["sha256"]

        for label, forged in (
            ("argv", forged_argv), ("timeout", forged_timeout),
            ("environment", forged_environment), ("stdin", forged_stdin),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(
                C2RustBaselineEvidenceError,
                "execution_input_mismatch|stdin_mismatch",
            ):
                write_baseline_report(self.out, forged)

    def test_cli_accepts_execution_contract(self) -> None:
        args = parse_args([
            "c2rust-baseline", "--repo-root", str(self.repo),
            "--compile-database", str(self.database),
            "--execution-contract", str(self.contract),
            "--c2rust-transpile", str(self.tools["c2rust-transpile"]),
            "--cargo", str(self.tools["cargo"]),
            "--rustc", str(self.tools["rustc"]),
        ])
        self.assertEqual(self.contract, args.execution_contract)

    def _run(self, runner: FakeRunner, *, timeout_seconds: int = 30):
        return run_c2rust_project_baseline(
            repo_root=self.repo, compile_commands=self.database,
            execution_contract=self.contract,
            c2rust_transpile=self.tools["c2rust-transpile"],
            cargo=self.tools["cargo"], rustc=self.tools["rustc"],
            out_root=self.out, timeout_seconds=timeout_seconds, runner=runner,
        )

    def _entry(self, source: str) -> dict:
        return {
            "directory": str(self.repo), "file": str(self.repo / source),
            "arguments": ["cc", "-c", str(self.repo / source)],
        }

    @staticmethod
    def _generated_sources() -> dict[str, str]:
        return {
            "src/src/unit.rs": "pub unsafe extern \"C\" fn main() -> i32 { 0 }\n",
            "src/src/second_unit.rs": "pub unsafe extern \"C\" fn main() -> i32 { 0 }\n",
        }

    @staticmethod
    def _scenario(identifier: str, argv: list[str], expected_exit: int) -> dict:
        return {
            "id": identifier, "argv": argv,
            "working_directory": "build/tests",
            "environment": {"CASE_MODE": "strict"},
            "stdin_utf8": "<stdin/>\n" if identifier == "case-input" else "",
            "expected_exit": expected_exit, "timeout_seconds": 30,
        }

    def _contract_payload(self) -> dict:
        return {
            "schema_version": 1,
            "wrappers": [
                {
                    "translated_module_path": "src/src/unit.rs",
                    "execution_mode": "scenarios",
                    "scenarios": [
                        self._scenario("case-input", ["../../fixtures/input.xml"], 0),
                        self._scenario("case-seven", ["--expect-seven"], 7),
                    ],
                },
                {
                    "translated_module_path": "src/src/second_unit.rs",
                    "execution_mode": "compile_only",
                },
            ],
        }

    def _write_contract(self, payload: dict) -> None:
        self.contract.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
