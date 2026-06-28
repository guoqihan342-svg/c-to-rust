import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_RUNNER = REPO_ROOT / "validation" / "tools" / "run_competition_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("run_competition_smoke_under_test", SMOKE_RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load competition smoke module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCommandRunner:
    def __init__(self, *, fail_commands_containing: set[str] | None = None) -> None:
        self.commands: list[list[str]] = []
        self.fail_commands_containing = fail_commands_containing or set()

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        command_text = " ".join(command)
        for marker in self.fail_commands_containing:
            if marker in command_text:
                return subprocess.CompletedProcess(command, 1, "", f"failed {marker}")
        return subprocess.CompletedProcess(command, 0, "ok", "")


class RunCompetitionSmokeTests(unittest.TestCase):
    def test_smoke_runner_records_proof_class_deviations_and_common_gates(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            fake_runner = FakeCommandRunner()

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="ci-approximation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            self.assertTrue(any("config/competition-env/env.sh" in text for text in command_texts))
            self.assertTrue(any("toolchain-check.sh" in text for text in command_texts))
            self.assertTrue(any("validate_auto_translation_evidence.py" in text for text in command_texts))
            self.assertTrue(any("verify_vendored_clang.py" in text for text in command_texts))
            self.assertTrue(any("evidence_governance.py" in text for text in command_texts))
            self.assertTrue(any("translator_coverage_matrix.py" in text for text in command_texts))
            self.assertTrue(any("-m unittest" in text for text in command_texts))

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["proof_class"], "ci-approximation")
            self.assertEqual(summary["profile_id"], "huawei-competition-ubuntu-24.04")
            self.assertEqual(summary["final_gate"]["status"], "passed")
            self.assertGreaterEqual(len(summary["environment_deviations"]), 3)
            self.assertIn("os.kernel", {item["field"] for item in summary["environment_deviations"]})
            self.assertTrue(all(not Path(entry["log_path"]).is_absolute() for entry in summary["steps"]))
            self.assertTrue(all(entry["status"] == "passed" for entry in summary["steps"]))
            self.assertEqual(
                summary["vendored_clang_verification"]["path"],
                "summary/vendored-clang-verification.json",
            )

    def test_smoke_runner_requires_explicit_confirmation_for_competition_exact(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            with self.assertRaises(SystemExit) as raised:
                module.run_competition_smoke(
                    out_root=Path(tmp) / "competition-smoke",
                    proof_class="competition-exact",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-test",
                )

        self.assertIn("--confirm-competition-exact", str(raised.exception))

    def test_smoke_runner_marks_gate_failure_without_slice_count_claims(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(fail_commands_containing={"evidence_governance.py"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertNotIn("slices", summary)
            failed_steps = [step for step in summary["steps"] if step["status"] == "failed"]
            self.assertEqual([step["step"] for step in failed_steps], ["evidence-governance"])

    def test_non_exact_smoke_degrades_environment_drift_without_failing_gate(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="ci-approximation",
                command_runner=FakeCommandRunner(fail_commands_containing={"toolchain-check.sh"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 0)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "passed")
            environment_step = next(step for step in summary["steps"] if step["step"] == "environment-check")
            self.assertEqual(environment_step["status"], "degraded")
            self.assertEqual(environment_step["proof_class_effect"], "exactness_blocker")

    def test_failed_vendored_clang_verification_keeps_clang_lane_unverified(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            original_clang_source = module.clang_source
            try:
                module.clang_source = lambda _: "vendored"
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(fail_commands_containing={"verify_vendored_clang.py"}),
                    repo_root=REPO_ROOT,
                    run_id="smoke-test",
                )
            finally:
                module.clang_source = original_clang_source

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(summary["clang_source"], "vendored")
            self.assertFalse(summary["clang_lane_verified"])
            self.assertFalse(summary["competition_profile_match"]["clang_lane_verified"])

    def test_competition_exact_fails_on_environment_drift_even_when_confirmed(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="competition-exact",
                confirm_competition_exact=True,
                command_runner=FakeCommandRunner(fail_commands_containing={"toolchain-check.sh"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "failed")
            environment_step = next(step for step in summary["steps"] if step["step"] == "environment-check")
            self.assertEqual(environment_step["status"], "failed")

    def test_competition_exact_requires_vendored_clang_verification(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="competition-exact",
                confirm_competition_exact=True,
                command_runner=FakeCommandRunner(fail_commands_containing={"--require-clang"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(result.exit_code, 1)
            failed_steps = [step for step in summary["steps"] if step["status"] == "failed"]
            self.assertIn("vendored-clang-verification", [step["step"] for step in failed_steps])

    def test_competition_exact_fails_when_detected_environment_has_limiting_deviations(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            original_detect = module.detect_execution_environment
            try:
                module.detect_execution_environment = lambda: {
                    "kind": "windows-local",
                    "detected_ci": False,
                    "detected_wsl": False,
                    "system": "Windows",
                    "release": "11",
                    "version": "10.0.26220",
                    "machine": "AMD64",
                    "kernel": "11",
                    "python_version": "3.14.2",
                    "runner_name": "local",
                }
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="competition-exact",
                    confirm_competition_exact=True,
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-test",
                )
            finally:
                module.detect_execution_environment = original_detect

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            limiting_deviations = [
                item for item in summary["environment_deviations"] if item["severity"] == "proof-class-limiting"
            ]
            self.assertTrue(limiting_deviations)
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("proof_class_limited_by_environment", summary["final_gate"]["reasons"])

    def test_main_accepts_smoke_cli_args(self) -> None:
        module = load_smoke_module()
        calls: dict[str, object] = {}

        def fake_run_competition_smoke(**kwargs: object) -> object:
            calls.update(kwargs)
            return module.CompetitionSmokeResult(
                exit_code=0,
                summary_path=Path("summary.json"),
                summary={"status": "fake"},
            )

        original_argv = sys.argv
        original_runner = module.run_competition_smoke
        try:
            module.run_competition_smoke = fake_run_competition_smoke
            sys.argv = [
                "run_competition_smoke.py",
                "--proof-class",
                "wsl-local-simulation",
                "--out-root",
                "target/competition-smoke",
                "--run-id",
                "smoke-cli",
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 0)
        finally:
            sys.argv = original_argv
            module.run_competition_smoke = original_runner

        self.assertEqual(calls["proof_class"], "wsl-local-simulation")
        self.assertEqual(calls["out_root"], Path("target/competition-smoke"))
        self.assertEqual(calls["run_id"], "smoke-cli")

    def test_core_ci_runs_competition_smoke_tests_and_gate(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "core-translator-validation-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("validation.tools.test_run_competition_smoke", workflow)
        self.assertIn("validation.tools.test_verify_vendored_clang", workflow)
        self.assertIn("python validation/tools/run_competition_smoke.py", workflow)

    def test_clang_source_detects_windows_project_local_clang_exe(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            repo_root = Path(tmp)
            clang = repo_root / "tools" / "llvm" / "bin" / "clang.exe"
            clang.parent.mkdir(parents=True)
            clang.write_text("", encoding="utf-8")

            self.assertEqual(module.clang_source(repo_root), "vendored")


if __name__ == "__main__":
    unittest.main()
