import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "validation" / "tools" / "run_competition.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("run_competition_under_test", RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load run_competition module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_slice_spec(root: Path, target_id: str, slice_id: str) -> Path:
    path = root / f"{target_id}-{slice_id}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_id": target_id,
                "slice_id": slice_id,
                "function_name": slice_id.replace("-", "_"),
            }
        ),
        encoding="utf-8",
    )
    return path


def write_extract_spec(root: Path, target_id: str, slice_id: str) -> Path:
    path = root / f"{target_id}-{slice_id}-extract.json"
    path.write_text(
        json.dumps(
            {
                "repo_root": str(root / "source-repo"),
                "source_file": "src/demo.c",
                "function": slice_id.replace("-", "_"),
                "target_id": target_id,
                "slice_id": slice_id,
                "source_commit": "abc123",
                "compiler_command_source": "compile_commands.json",
                "include_paths": ["include"],
                "defines": ["DEMO=1"],
            }
        ),
        encoding="utf-8",
    )
    return path


def write_final_verification(
    evidence_root: Path,
    target_id: str,
    slice_id: str,
    *,
    semantic_pass: bool,
    status: str | None = None,
) -> None:
    evidence_dir = evidence_root / target_id / "auto-translation" / slice_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"l3-{slice_id}-final-verification.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": status or ("passed" if semantic_pass else "failed"),
                "semantic_pass": semantic_pass,
                "rust_check_status": "passed" if semantic_pass else "failed",
            }
        ),
        encoding="utf-8",
    )


class FakeCommandRunner:
    def __init__(
        self,
        *,
        fail_auto_migrate_for: set[str] | None = None,
        fail_commands_containing: set[str] | None = None,
        stdout_by_command_marker: dict[str, str] | None = None,
    ) -> None:
        self.commands: list[list[str]] = []
        self.fail_auto_migrate_for = fail_auto_migrate_for or set()
        self.fail_commands_containing = fail_commands_containing or set()
        self.stdout_by_command_marker = stdout_by_command_marker or {}

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        command_text = " ".join(command)
        for marker in self.fail_commands_containing:
            if marker in command_text:
                return subprocess.CompletedProcess(command, 1, "", f"failed {marker}")
        if "extract_source_slice.py" in command_text:
            cwd = Path(kwargs.get("cwd", REPO_ROOT))
            self.write_extracted_slice_spec(command, cwd)
        for slice_id in self.fail_auto_migrate_for:
            if "auto_migrate.py" in command_text and slice_id in command_text:
                return subprocess.CompletedProcess(command, 1, "", f"failed {slice_id}")
        for marker, stdout in self.stdout_by_command_marker.items():
            if marker in command_text:
                return subprocess.CompletedProcess(command, 0, stdout, "")
        if "unsafe_budget.py" in command_text:
            stdout = json.dumps(
                {
                    "schema_version": 1,
                    "status": "passed",
                    "first_party_non_test_unsafe_count": 0,
                    "unsafe_ratio": 0.0,
                }
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    def write_extracted_slice_spec(self, command: list[str], cwd: Path) -> None:
        def arg_value(name: str) -> str:
            return command[command.index(name) + 1]

        out_path = Path(arg_value("--out"))
        if not out_path.is_absolute():
            out_path = cwd / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        target_id = arg_value("--target-id")
        slice_id = arg_value("--slice-id")
        function_name = arg_value("--function")
        out_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "target_id": target_id,
                    "slice_id": slice_id,
                    "function_name": function_name,
                }
            ),
            encoding="utf-8",
        )


class RunCompetitionTests(unittest.TestCase):
    def test_core_ci_runs_competition_runner_tests(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "core-translator-validation-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("validation.tools.test_run_competition", workflow)

    def test_runner_invokes_common_gates_and_writes_valid_summary(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(out_root / "evidence", "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            self.assertTrue(any("config/competition-env/env.sh" in text for text in command_texts))
            self.assertTrue(any("toolchain-check.sh" in text for text in command_texts))
            self.assertTrue(any("auto_migrate.py" in text and "--competition-clang-lane" in text for text in command_texts))
            self.assertTrue(any("validate_auto_translation_evidence.py" in text for text in command_texts))
            self.assertTrue(any("unsafe_budget.py" in text for text in command_texts))
            self.assertTrue(any("openspec validate --all --strict" in text for text in command_texts))
            self.assertTrue(any("validate_competition_run_summary.py" in text for text in command_texts))

            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["proof_class"], "local-simulation")
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)
            self.assertEqual(summary["final_gate"]["status"], "passed")

    def test_runner_extracts_slice_spec_before_auto_migrate(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            extract_spec = write_extract_spec(tmp_path, "demo", "extracted-slice")
            write_final_verification(out_root / "evidence", "demo", "extracted-slice", semantic_pass=True)
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[extract_spec],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            extract_command = next(text for text in command_texts if "extract_source_slice.py" in text)
            self.assertIn("--repo-root", extract_command)
            self.assertIn("--source-file src/demo.c", extract_command)
            self.assertIn("--function extracted_slice", extract_command)
            self.assertIn("--include-path include", extract_command)
            self.assertIn("--define DEMO=1", extract_command)
            auto_migrate_command = next(text for text in command_texts if "auto_migrate.py" in text)
            self.assertIn(
                "slice-specs/demo-extracted-slice.json",
                auto_migrate_command.replace("\\", "/"),
            )
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)

    def test_runner_counts_extract_failure_as_slice_failure_and_logs_it(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            extract_spec = write_extract_spec(tmp_path, "demo", "bad-extract")
            fake_runner = FakeCommandRunner(fail_commands_containing={"extract_source_slice.py"})

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[extract_spec],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["failed"], 1)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            self.assertFalse(any("auto_migrate.py" in text for text in command_texts))
            entries = [
                json.loads(line)
                for line in (out_root / "logs" / "commands.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            extract_entries = [entry for entry in entries if entry["step"] == "extract-slice-bad-extract"]
            self.assertEqual(len(extract_entries), 1)
            self.assertEqual(extract_entries[0]["returncode"], 1)
            self.assertIn("failed extract_source_slice.py", extract_entries[0]["stderr"])

    def test_runner_combines_existing_and_extracted_slice_specs(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            existing_spec = write_slice_spec(tmp_path, "demo", "existing-slice")
            extract_spec = write_extract_spec(tmp_path, "demo", "extracted-slice")
            write_final_verification(out_root / "evidence", "demo", "existing-slice", semantic_pass=True)
            write_final_verification(out_root / "evidence", "demo", "extracted-slice", semantic_pass=True)
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[existing_spec],
                extraction_specs=[extract_spec],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            auto_migrate_commands = [text for text in command_texts if "auto_migrate.py" in text]
            self.assertEqual(len(auto_migrate_commands), 2)
            self.assertTrue(any("existing-slice" in text for text in auto_migrate_commands))
            self.assertTrue(any("extracted-slice" in text for text in auto_migrate_commands))
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 2)
            self.assertEqual(summary["slices"]["semantic_pass"], 2)

    def test_runner_requires_slice_spec_or_extract_spec(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            with self.assertRaises(SystemExit) as raised:
                module.run_competition(
                    slice_specs=[],
                    extraction_specs=[],
                    out_root=Path(tmp) / "competition-out",
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="run-test",
                )

        self.assertIn("--slice-spec or --extract-spec", str(raised.exception))

    def test_runner_archives_command_logs_with_exit_code_and_output(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(out_root / "evidence", "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            log_path = out_root / "logs" / "commands.jsonl"
            self.assertTrue(log_path.exists())
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertGreaterEqual(len(entries), 6)
            self.assertEqual(entries[0]["step"], "environment-check")
            self.assertIn("config/competition-env/env.sh", " ".join(entries[0]["command"]))
            self.assertEqual(entries[0]["returncode"], 0)
            self.assertEqual(entries[0]["stdout"], "ok")
            self.assertEqual(entries[0]["stderr"], "")
            self.assertTrue(all(not Path(entry["log_path"]).is_absolute() for entry in entries))
            self.assertTrue(all("\\" not in entry["log_path"] for entry in entries))

    def test_runner_archives_failed_slice_command_without_unexecuted_validator_log(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "bad-slice")
            fake_runner = FakeCommandRunner(fail_auto_migrate_for={"bad-slice"})

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            entries = [
                json.loads(line)
                for line in (out_root / "logs" / "commands.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            auto_migrate_entries = [entry for entry in entries if entry["step"] == "auto-migrate-bad-slice"]
            self.assertEqual(len(auto_migrate_entries), 1)
            self.assertEqual(auto_migrate_entries[0]["returncode"], 1)
            self.assertIn("failed bad-slice", auto_migrate_entries[0]["stderr"])
            self.assertFalse(any(entry["step"] == "validate-evidence-bad-slice" for entry in entries))

    def test_runner_continues_after_slice_failure_and_marks_summary_failed(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            bad_spec = write_slice_spec(tmp_path, "demo", "bad-slice")
            good_spec = write_slice_spec(tmp_path, "demo", "good-slice")
            write_final_verification(out_root / "evidence", "demo", "good-slice", semantic_pass=True)
            fake_runner = FakeCommandRunner(fail_auto_migrate_for={"bad-slice"})

            result = module.run_competition(
                slice_specs=[bad_spec, good_spec],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            auto_migrate_commands = [
                command for command in fake_runner.commands if any("auto_migrate.py" in item for item in command)
            ]
            self.assertEqual(len(auto_migrate_commands), 2)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 2)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)
            self.assertEqual(summary["slices"]["failed"], 1)
            self.assertEqual(summary["final_gate"]["status"], "failed")

    def test_runner_keeps_global_gate_failure_out_of_slice_failure_counts(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(out_root / "evidence", "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner(fail_commands_containing={"unsafe_budget.py"})

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)
            self.assertEqual(summary["slices"]["failed"], 0)
            self.assertEqual(summary["unsafe_budget"]["status"], "failed")
            self.assertEqual(summary["unsafe_budget"]["total_first_party_non_test_unsafe"], 0)
            self.assertEqual(summary["unsafe_budget"]["ratio"], 0.0)
            self.assertEqual(summary["final_gate"]["status"], "failed")

    def test_runner_summary_uses_unsafe_budget_json_stdout(self) -> None:
        module = load_runner_module()
        unsafe_stdout = json.dumps(
            {
                "schema_version": 1,
                "status": "passed",
                "first_party_non_test_unsafe_count": 7,
                "unsafe_ratio": 0.03125,
            }
        )
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(out_root / "evidence", "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner(stdout_by_command_marker={"unsafe_budget.py": unsafe_stdout})

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["unsafe_budget"]["total_first_party_non_test_unsafe"], 7)
            self.assertEqual(summary["unsafe_budget"]["ratio"], 0.03125)
            self.assertEqual(summary["unsafe_budget"]["status"], "passed")

    def test_runner_marks_invalid_unsafe_budget_json_stdout_as_gate_failure(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(out_root / "evidence", "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner(stdout_by_command_marker={"unsafe_budget.py": "not-json"})

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["unsafe_budget"]["status"], "failed")
            self.assertEqual(summary["unsafe_budget"]["total_first_party_non_test_unsafe"], 0)
            self.assertEqual(summary["unsafe_budget"]["ratio"], 0.0)
            self.assertEqual(summary["final_gate"]["status"], "failed")

    def test_unsafe_budget_summary_rejects_non_object_json_stdout(self) -> None:
        module = load_runner_module()

        for stdout in ["null", "[]", '"text"', "123", "true"]:
            with self.subTest(stdout=stdout):
                summary = module.unsafe_budget_summary(
                    subprocess.CompletedProcess(["unsafe_budget.py"], 0, stdout, "")
                )

                self.assertEqual(summary["status"], "failed")
                self.assertEqual(summary["total_first_party_non_test_unsafe"], 0)
                self.assertEqual(summary["ratio"], 0.0)

    def test_runner_keeps_evidence_validator_failure_out_of_terminal_slice_counts(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(out_root / "evidence", "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner(fail_commands_containing={"validate_auto_translation_evidence.py"})

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)
            self.assertEqual(summary["slices"]["refused"], 0)
            self.assertEqual(summary["slices"]["blocked"], 0)
            self.assertEqual(summary["slices"]["failed"], 0)
            self.assertEqual(summary["final_gate"]["status"], "failed")

    def test_runner_counts_refused_and_blocked_slices_separately(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            refused_spec = write_slice_spec(tmp_path, "demo", "refused-slice")
            blocked_spec = write_slice_spec(tmp_path, "demo", "blocked-slice")
            write_final_verification(
                out_root / "evidence",
                "demo",
                "refused-slice",
                semantic_pass=False,
                status="refused",
            )
            write_final_verification(
                out_root / "evidence",
                "demo",
                "blocked-slice",
                semantic_pass=False,
                status="blocked",
            )
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[refused_spec, blocked_spec],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 2)
            self.assertEqual(summary["slices"]["refused"], 1)
            self.assertEqual(summary["slices"]["blocked"], 1)
            self.assertEqual(summary["slices"]["failed"], 0)
            self.assertEqual(summary["final_gate"]["status"], "failed")

    def test_runner_marks_environment_check_failure_as_global_gate_failure(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(out_root / "evidence", "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner(fail_commands_containing={"toolchain-check.sh"})

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)
            self.assertEqual(summary["slices"]["failed"], 0)
            self.assertEqual(summary["final_gate"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
