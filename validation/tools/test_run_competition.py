import contextlib
import hashlib
import io
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "validation" / "tools" / "run_competition.py"
SUMMARY_VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_competition_run_summary.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("run_competition_under_test", RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load run_competition module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_summary_validator_module():
    spec = importlib.util.spec_from_file_location("validate_competition_run_summary_under_test", SUMMARY_VALIDATOR)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load validate_competition_run_summary module")
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
                "source_repository": "https://gitcode.com/xwxf/FlashDB.git",
                "source_branch": "competition",
                "source_commit": "abc123",
                "require_source_commit": "abc123",
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


def write_patch_events(evidence_root: Path, target_id: str, slice_id: str, events: list[dict]) -> None:
    evidence_dir = evidence_root / target_id / "auto-translation" / slice_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"l3-{slice_id}-patch-events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


def write_worker_summary(
    root: Path,
    worker_id: str,
    *,
    attempted: int,
    semantic_pass: int,
    failed: int = 0,
    final_gate_status: str = "passed",
    workflow_metrics: dict | None = None,
) -> Path:
    path = root / worker_id / "summary" / "competition-run-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "run_id": f"run-{worker_id}",
        "proof_class": "local-simulation",
        "profile_id": "huawei-competition-ubuntu-24.04",
        "profile_sha256": "a" * 64,
        "clang_source": "missing",
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": 1,
        "translator_version": "0.1.0",
        "slices": {
            "attempted": attempted,
            "typed_ir_generated": semantic_pass,
            "compiled": semantic_pass,
            "semantic_pass": semantic_pass,
            "refused": 0,
            "blocked": 0,
            "failed": failed,
        },
        "unsafe_budget": {
            "status": "passed",
            "total_first_party_non_test_unsafe": 0,
            "ratio": 0.0,
        },
        "artifact_roots": [
            f"target/competition-out/{worker_id}/evidence",
            f"target/competition-out/{worker_id}/summary",
            f"target/competition-out/{worker_id}/logs",
        ],
        "final_gate": {
            "status": final_gate_status,
            "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
        },
    }
    if workflow_metrics is not None:
        metrics_path = path.parent / "workflow-metrics.json"
        metrics_path.write_text(json.dumps(workflow_metrics, sort_keys=True), encoding="utf-8")
        summary["workflow_metrics"] = {
            "path": "workflow-metrics.json",
            "sha256": hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
        }
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path


def write_worker_assignment_request(
    out_root: Path,
    worker_id: str,
    *,
    target_id: str = "demo",
    slice_id: str = "demo-first",
    function: str = "first_unit",
    source_commit: str = "commit-one",
    source_sha256: str = "a" * 64,
    require_source_commit: str = "commit-one",
) -> Path:
    path = out_root / "harness" / "assignments" / f"{worker_id}-request.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": "run-test",
                "target_id": target_id,
                "slice_id": slice_id,
                "function": function,
                "source_repo_root": "sources/FlashDB",
                "source_repository": "https://gitcode.com/xwxf/FlashDB.git",
                "source_branch": "competition",
                "source_file": "src/fdb_utils.c",
                "source_commit": source_commit,
                "source_sha256": source_sha256,
                "require_source_commit": require_source_commit,
                "slice_specs": [f"validation/slice-specs/{slice_id}.json"],
                "out_root": f"target/competition-out/workers/{worker_id}",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_worker_before_after_artifacts(worker_root: Path, worker_id: str) -> dict:
    evidence_dir = worker_root / worker_id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "baseline": evidence_dir / "baseline-unsafe.rs",
        "final": evidence_dir / "final-safe.rs",
        "oracle_evidence": evidence_dir / "oracle-diff.json",
        "accepted_patch": evidence_dir / "accepted.patch",
        "patch_log": evidence_dir / "safety-step-log.jsonl",
        "baseline_verification": evidence_dir / "verified-baseline.json",
    }
    for name, path in artifacts.items():
        if name == "baseline_verification":
            path.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "semantic_pass": True,
                        "semantic_claim_source": "verified_unsafe_baseline_gates",
                        "generated_draft_semantic_pass": False,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(f"{name}\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "status": "bound",
        **{
            name: {
                "path": f"evidence/{path.name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in artifacts.items()
        },
        "unsafe_reduction": {
            "status": "measured",
            "baseline_total_unsafe": 6,
            "current_total_unsafe": 2,
            "reduced_by": 4,
            "ratio": 2 / 6,
        },
    }
    manifest["baseline_verification"].update(
        {
            "status": "passed",
            "semantic_pass": True,
            "semantic_claim_source": "verified_unsafe_baseline_gates",
            "generated_draft_semantic_pass": False,
        }
    )
    return manifest


def write_direct_before_after_manifest(out_root: Path, target_id: str, slice_id: str) -> dict:
    evidence_dir = out_root / "evidence" / target_id / "auto-translation" / slice_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "baseline": evidence_dir / "baseline-unsafe.rs",
        "final": evidence_dir / "final-safe.rs",
        "oracle_evidence": evidence_dir / "oracle-diff.json",
        "accepted_patch": evidence_dir / "accepted.patch",
        "patch_log": evidence_dir / "safety-step-log.jsonl",
        "baseline_verification": evidence_dir / "verified-baseline.json",
    }
    for name, path in artifacts.items():
        if name == "baseline_verification":
            path.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "semantic_pass": True,
                        "semantic_claim_source": "verified_unsafe_baseline_gates",
                        "generated_draft_semantic_pass": False,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(f"{name}\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "status": "bound",
        **{
            name: {
                "path": f"evidence/{target_id}/auto-translation/{slice_id}/{path.name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in artifacts.items()
        },
        "unsafe_reduction": {
            "status": "measured",
            "baseline_total_unsafe": 3,
            "current_total_unsafe": 0,
            "reduced_by": 3,
            "ratio": 0.0,
        },
    }
    manifest["baseline_verification"].update(
        {
            "status": "passed",
            "semantic_pass": True,
            "semantic_claim_source": "verified_unsafe_baseline_gates",
            "generated_draft_semantic_pass": False,
        }
    )
    (evidence_dir / f"l3-{slice_id}-translation-before-after.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


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

    def test_runner_writes_machine_readable_workflow_metrics_artifact(self) -> None:
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
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["workflow_metrics"]["path"], "summary/workflow-metrics.json")
            self.assertRegex(summary["workflow_metrics"]["sha256"], r"^[0-9a-f]{64}$")

            metrics_path = out_root / "summary" / "workflow-metrics.json"
            self.assertTrue(metrics_path.exists())
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(metrics["run_id"], "run-test")
            self.assertEqual(metrics["units_total"], 1)
            self.assertEqual(metrics["units_converged"], 1)
            self.assertEqual(metrics["units_baseline_only"], 0)
            self.assertEqual(metrics["fail_closed_count"], 0)
            self.assertEqual(metrics["avg_repair_rounds"], 0.0)
            self.assertEqual(metrics["auto_recovery_rate"], 0.0)
            self.assertEqual(metrics["human_interventions"], 0)
            self.assertTrue(metrics["always_compiles"])
            self.assertTrue(metrics["always_equivalent"])
            self.assertEqual(metrics["llm_calls"], 0)
            self.assertEqual(metrics["wall_clock_seconds"], summary["elapsed_seconds"])
            self.assertEqual(metrics["unsafe_reduction"]["status"], "not_measured")
            self.assertEqual(
                metrics["per_unit_statuses"],
                [
                    {
                        "unit_id": "demo/store-add-one",
                        "source": "slice-spec",
                        "status": "converged",
                        "compiled": True,
                        "semantic_pass": True,
                        "refused": False,
                        "blocked": False,
                        "failed": False,
                    }
                ],
            )

    def test_runner_counts_direct_slice_self_healing_repair_metrics(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "keyword-param")
            write_final_verification(out_root / "evidence", "demo", "keyword-param", semantic_pass=True)
            write_patch_events(
                out_root / "evidence",
                "demo",
                "keyword-param",
                [
                    {"round": 1, "status": "applied"},
                    {"round": 2, "status": "applied", "ai_usage": {"used": True, "candidate_id": "ai-repair-1"}},
                    {"round": 3, "status": "applied"},
                    {"round": 3, "status": "verified"},
                ],
            )
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
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["avg_repair_rounds"], 3.0)
            self.assertEqual(metrics["auto_recovery_rate"], 1.0)
            self.assertEqual(metrics["llm_calls"], 1)
            self.assertEqual(metrics["per_unit_statuses"][0]["repair_rounds"], 3)
            self.assertTrue(metrics["per_unit_statuses"][0]["auto_recovered"])
            self.assertEqual(metrics["per_unit_statuses"][0]["llm_calls"], 1)
            repair_history = metrics["per_unit_statuses"][0]["repair_history"]
            self.assertEqual(
                repair_history["patch_events_path"],
                "evidence/demo/auto-translation/keyword-param/l3-keyword-param-patch-events.jsonl",
            )
            self.assertRegex(repair_history["patch_events_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(repair_history["statuses"], ["applied", "applied", "applied", "verified"])
            self.assertEqual(repair_history["rollback_ids"], [])
            self.assertTrue(repair_history["verified"])

    def test_runner_binds_direct_slice_translation_before_after_manifest(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            spec_path = write_slice_spec(tmp_path, "demo", "keyword-param")
            write_final_verification(out_root / "evidence", "demo", "keyword-param", semantic_pass=True)
            before_after = write_direct_before_after_manifest(out_root, "demo", "keyword-param")

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            self.assertEqual(
                validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"],
                "passed",
            )
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["translation_before_after"]["status"], "bound")
            self.assertEqual(metrics["translation_before_after"]["unit_count"], 1)
            self.assertEqual(metrics["translation_before_after"]["measured_unsafe_unit_count"], 1)
            self.assertEqual(metrics["translation_before_after"]["accepted_patch_unit_count"], 1)
            self.assertEqual(
                metrics["translation_before_after"]["units"][0]["baseline_verification"],
                before_after["baseline_verification"],
            )
            self.assertEqual(metrics["unsafe_reduction"]["status"], "measured")
            self.assertEqual(metrics["unsafe_reduction"]["baseline_total_unsafe"], 3)
            self.assertEqual(metrics["unsafe_reduction"]["current_total_unsafe"], 0)
            self.assertEqual(metrics["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(metrics["unsafe_reduction"]["ratio"], 0.0)
            unit = metrics["per_unit_statuses"][0]
            self.assertEqual(unit["translation_before_after"], before_after)

    def test_runner_can_reuse_committed_accepted_evidence_without_regenerating_candidate(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            accepted_evidence_root = tmp_path / "accepted-evidence"
            spec_path = write_slice_spec(tmp_path, "demo", "store-add-one")
            write_final_verification(accepted_evidence_root, "demo", "store-add-one", semantic_pass=True)
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[spec_path],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
                reuse_accepted_evidence=True,
                accepted_evidence_root=accepted_evidence_root,
            )

            self.assertEqual(result.exit_code, 0)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            self.assertFalse(any("auto_migrate.py" in text for text in command_texts))
            validate_commands = [text for text in command_texts if "validate_auto_translation_evidence.py" in text]
            self.assertEqual(len(validate_commands), 1)
            self.assertIn("--evidence-root", validate_commands[0])
            self.assertIn(accepted_evidence_root.as_posix(), validate_commands[0])
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["compiled"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)
            self.assertEqual(summary["slices"]["failed"], 0)
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
            self.assertIn("--source-repository https://gitcode.com/xwxf/FlashDB.git", extract_command)
            self.assertIn("--source-branch competition", extract_command)
            self.assertIn("--source-commit abc123", extract_command)
            self.assertIn("--require-source-commit abc123", extract_command)
            self.assertIn("--compiler-command-source compile_commands.json", extract_command)
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

    def test_runner_extracts_inline_extraction_spec_before_auto_migrate(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            inline_spec = {
                "repo_root": str(tmp_path / "source-repo"),
                "source_file": "src/direct.c",
                "function": "direct_slice",
                "target_id": "demo",
                "slice_id": "direct-slice",
                "include_paths": ["include"],
                "defines": ["DIRECT=1"],
            }
            write_final_verification(out_root / "evidence", "demo", "direct-slice", semantic_pass=True)
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[inline_spec],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            extract_command = next(text for text in command_texts if "extract_source_slice.py" in text)
            self.assertIn("--source-file src/direct.c", extract_command)
            self.assertIn("--function direct_slice", extract_command)
            self.assertIn("--include-path include", extract_command)
            self.assertIn("--define DIRECT=1", extract_command)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)

    def test_main_accepts_direct_extraction_cli_args(self) -> None:
        module = load_runner_module()
        calls: dict[str, object] = {}

        def fake_run_competition(**kwargs: object) -> object:
            calls.update(kwargs)
            return module.CompetitionRunResult(
                exit_code=0,
                summary_path=Path("summary.json"),
                summary={"status": "fake"},
            )

        original_argv = sys.argv
        original_run_competition = module.run_competition
        try:
            module.run_competition = fake_run_competition
            sys.argv = [
                "run_competition.py",
                "--source-repo-root",
                str(REPO_ROOT / "source-repo"),
                "--source-file",
                "src/direct.c",
                "--function",
                "direct_slice",
                "--target-id",
                "demo",
                "--slice-id",
                "direct-slice",
                "--source-commit",
                "abc123",
                "--source-repository",
                "https://gitcode.com/xwxf/FlashDB.git",
                "--source-branch",
                "competition",
                "--require-source-commit",
                "abc123",
                "--compiler-command-source",
                "compile_commands.json",
                "--include-path",
                "include",
                "--define",
                "DIRECT=1",
            ]

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 0)
        finally:
            sys.argv = original_argv
            module.run_competition = original_run_competition

        extraction_specs = calls["extraction_specs"]
        self.assertEqual(len(extraction_specs), 1)
        extraction = extraction_specs[0]
        self.assertEqual(extraction["repo_root"], str(REPO_ROOT / "source-repo"))
        self.assertEqual(extraction["source_file"], "src/direct.c")
        self.assertEqual(extraction["function"], "direct_slice")
        self.assertEqual(extraction["target_id"], "demo")
        self.assertEqual(extraction["slice_id"], "direct-slice")
        self.assertEqual(extraction["source_commit"], "abc123")
        self.assertEqual(extraction["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(extraction["source_branch"], "competition")
        self.assertEqual(extraction["require_source_commit"], "abc123")
        self.assertEqual(extraction["compiler_command_source"], "compile_commands.json")
        self.assertEqual(extraction["include_paths"], ["include"])
        self.assertEqual(extraction["defines"], ["DIRECT=1"])

    def test_main_accepts_worker_summary_cli_args(self) -> None:
        module = load_runner_module()
        calls: dict[str, object] = {}

        def fake_run_competition(**kwargs: object) -> object:
            calls.update(kwargs)
            return module.CompetitionRunResult(
                exit_code=0,
                summary_path=Path("summary.json"),
                summary={"status": "fake"},
            )

        original_argv = sys.argv
        original_run_competition = module.run_competition
        try:
            module.run_competition = fake_run_competition
            sys.argv = [
                "run_competition.py",
                "--worker-summary",
                "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
            ]

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 0)
        finally:
            sys.argv = original_argv
            module.run_competition = original_run_competition

        self.assertEqual(
            calls["worker_summaries"],
            [Path("target/competition-out/workers/worker-a/summary/competition-run-summary.json")],
        )

    def test_main_rejects_incomplete_direct_extraction_cli_args(self) -> None:
        module = load_runner_module()
        original_argv = sys.argv
        try:
            sys.argv = [
                "run_competition.py",
                "--source-file",
                "src/direct.c",
                "--function",
                "direct_slice",
                "--target-id",
                "demo",
                "--slice-id",
                "direct-slice",
            ]

            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as raised:
                with contextlib.redirect_stderr(stderr):
                    module.main()
        finally:
            sys.argv = original_argv

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("direct extraction args require --source-repo-root", stderr.getvalue())

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

        self.assertIn("--slice-spec, --extract-spec, --worker-summary, or direct extraction argument group", str(raised.exception))

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

    def test_runner_merges_worker_summaries_without_reprocessing_slices(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            worker_a = write_worker_summary(worker_root, "worker-a", attempted=1, semantic_pass=1)
            write_worker_assignment_request(
                out_root,
                "worker-a",
                target_id="demo",
                slice_id="demo-first",
                function="first_unit",
                source_commit="commit-one",
                require_source_commit="commit-one",
            )
            worker_b = write_worker_summary(
                worker_root,
                "worker-b",
                attempted=2,
                semantic_pass=1,
                failed=1,
                final_gate_status="failed",
            )
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker_a, worker_b],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            self.assertFalse(any("auto_migrate.py" in text for text in command_texts))
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 3)
            self.assertEqual(summary["slices"]["semantic_pass"], 2)
            self.assertEqual(summary["slices"]["failed"], 1)
            self.assertEqual(summary["workers"]["count"], 2)
            self.assertEqual(summary["workers"]["summaries"][0]["status"], "passed")
            self.assertEqual(summary["workers"]["summaries"][0]["worker_id"], "worker-a")
            self.assertEqual(summary["workers"]["summaries"][0]["function"], "first_unit")
            self.assertEqual(summary["workers"]["summaries"][0]["source_file"], "src/fdb_utils.c")
            self.assertEqual(summary["workers"]["summaries"][0]["source_commit"], "commit-one")
            self.assertEqual(summary["workers"]["summaries"][0]["source_sha256"], "a" * 64)
            self.assertEqual(summary["workers"]["summaries"][0]["require_source_commit"], "commit-one")
            self.assertEqual(summary["workers"]["summaries"][0]["slice_specs"], ["validation/slice-specs/demo-first.json"])
            self.assertEqual(summary["workers"]["summaries"][1]["status"], "failed")
            self.assertEqual(summary["workers"]["summaries"][1]["worker_id"], "worker-b")
            self.assertNotIn("source_commit", summary["workers"]["summaries"][1])
            self.assertEqual(summary["final_gate"]["status"], "failed")

    def test_runner_aggregates_worker_workflow_metrics_into_parent_artifact(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            worker_a = write_worker_summary(
                worker_root,
                "worker-a",
                attempted=2,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 2,
                    "units_converged": 1,
                    "units_baseline_only": 1,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 1.5,
                    "auto_recovery_rate": 0.5,
                    "human_interventions": 1,
                    "always_compiles": True,
                    "always_equivalent": False,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 9,
                    "llm_calls": 3,
                    "per_unit_statuses": [],
                },
            )
            worker_b = write_worker_summary(
                worker_root,
                "worker-b",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-b",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 0.0,
                    "auto_recovery_rate": 0.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 4,
                    "llm_calls": 1,
                    "per_unit_statuses": [],
                },
            )
            fake_runner = FakeCommandRunner()

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker_a, worker_b],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            summary = json.loads(parent_summary_path.read_text(encoding="utf-8"))
            self.assertNotIn("workflow_metrics", summary["workers"]["summaries"][0])
            self.assertEqual(
                validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"],
                "passed",
            )
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["units_total"], 3)
            self.assertEqual(metrics["units_converged"], 2)
            self.assertEqual(metrics["units_baseline_only"], 0)
            self.assertEqual(metrics["avg_repair_rounds"], 1.0)
            self.assertAlmostEqual(metrics["auto_recovery_rate"], 1.0 / 3.0)
            self.assertEqual(metrics["human_interventions"], 1)
            self.assertEqual(metrics["llm_calls"], 4)

    def test_runner_expands_multi_unit_worker_per_unit_statuses_into_parent_workflow_metrics(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            worker = write_worker_summary(
                worker_root,
                "worker-a",
                attempted=2,
                semantic_pass=1,
                final_gate_status="blocked",
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 2,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 0.5,
                    "auto_recovery_rate": 0.0,
                    "human_interventions": 0,
                    "always_compiles": False,
                    "always_equivalent": False,
                    "fail_closed_count": 1,
                    "root_cause_counts": {"rustc_compile_error": 1},
                    "wall_clock_seconds": 6,
                    "llm_calls": 2,
                    "per_unit_statuses": [
                        {
                            "unit_id": "demo/unit-a",
                            "source": "worker-summary",
                            "status": "converged",
                            "compiled": True,
                            "semantic_pass": True,
                            "refused": False,
                            "blocked": False,
                            "failed": False,
                            "llm_calls": 1,
                        },
                        {
                            "unit_id": "demo/unit-b",
                            "source": "worker-summary",
                            "status": "blocked",
                            "compiled": False,
                            "semantic_pass": False,
                            "refused": False,
                            "blocked": True,
                            "failed": False,
                            "root_cause_key": "rustc_compile_error",
                            "llm_calls": 1,
                        },
                    ],
                },
            )
            worker_summary = json.loads(worker.read_text(encoding="utf-8"))
            worker_summary["slices"]["blocked"] = 1
            worker.write_text(json.dumps(worker_summary, sort_keys=True), encoding="utf-8")

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            self.assertEqual(validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"], "passed")
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual([unit["unit_id"] for unit in metrics["per_unit_statuses"]], ["demo/unit-a", "demo/unit-b"])
            self.assertEqual(metrics["root_cause_counts"], {"rustc_compile_error": 1})
            self.assertEqual(metrics["per_unit_statuses"][1]["root_cause_key"], "rustc_compile_error")
            self.assertEqual(metrics["per_unit_statuses"][0]["worker_summary_path"], "workers/worker-a/summary/competition-run-summary.json")
            self.assertEqual(metrics["llm_calls"], 2)

    def test_runner_preserves_worker_root_cause_metrics_for_opencode_contract_failure(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            worker = write_worker_summary(
                worker_root,
                "worker-a",
                attempted=1,
                semantic_pass=0,
                final_gate_status="blocked",
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 0,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 0.0,
                    "auto_recovery_rate": 0.0,
                    "human_interventions": 0,
                    "always_compiles": False,
                    "always_equivalent": False,
                    "fail_closed_count": 1,
                    "root_cause_counts": {"opencode_contract_not_executed": 1},
                    "wall_clock_seconds": 4,
                    "llm_calls": 1,
                    "per_unit_statuses": [
                        {
                            "unit_id": "demo/demo-add-one",
                            "source": "opencode-worker",
                            "status": "blocked",
                            "compiled": False,
                            "semantic_pass": False,
                            "refused": False,
                            "blocked": True,
                            "failed": False,
                            "root_cause_key": "opencode_contract_not_executed",
                            "opencode_contract_verification": {
                                "status": "not-executed",
                                "worker_command_seen": False,
                                "executed_shell_command_count": 1,
                            },
                        }
                    ],
                },
            )
            worker_summary = json.loads(worker.read_text(encoding="utf-8"))
            worker_summary["slices"]["blocked"] = 1
            worker.write_text(json.dumps(worker_summary, sort_keys=True), encoding="utf-8")

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 1)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            self.assertEqual(
                validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"],
                "passed",
            )
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["fail_closed_count"], 1)
            self.assertEqual(metrics["root_cause_counts"], {"opencode_contract_not_executed": 1})
            self.assertEqual(metrics["per_unit_statuses"][0]["root_cause_key"], "opencode_contract_not_executed")
            self.assertEqual(metrics["per_unit_statuses"][0]["opencode_contract_verification"]["status"], "not-executed")

    def test_runner_aggregates_measured_worker_unsafe_reduction_into_parent_artifact(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            worker_a = write_worker_summary(
                worker_root,
                "worker-a",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 8,
                        "current_total_unsafe": 5,
                        "reduced_by": 3,
                        "ratio": 0.625,
                    },
                    "avg_repair_rounds": 0.0,
                    "auto_recovery_rate": 0.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 3,
                    "llm_calls": 1,
                    "per_unit_statuses": [],
                },
            )
            worker_b = write_worker_summary(
                worker_root,
                "worker-b",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-b",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 4,
                        "current_total_unsafe": 2,
                        "reduced_by": 2,
                        "ratio": 0.5,
                    },
                    "avg_repair_rounds": 0.0,
                    "auto_recovery_rate": 0.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 2,
                    "llm_calls": 0,
                    "per_unit_statuses": [],
                },
            )

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker_a, worker_b],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            self.assertEqual(
                validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"],
                "passed",
            )
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["unsafe_reduction"]["status"], "measured")
            self.assertEqual(metrics["unsafe_reduction"]["baseline_total_unsafe"], 12)
            self.assertEqual(metrics["unsafe_reduction"]["current_total_unsafe"], 7)
            self.assertEqual(metrics["unsafe_reduction"]["reduced_by"], 5)
            self.assertAlmostEqual(metrics["unsafe_reduction"]["ratio"], 7 / 12)

    def test_runner_preserves_worker_translation_before_after_evidence(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            before_after = write_worker_before_after_artifacts(worker_root, "worker-a")
            worker = write_worker_summary(
                worker_root,
                "worker-a",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 6,
                        "current_total_unsafe": 2,
                        "reduced_by": 4,
                        "ratio": 2 / 6,
                    },
                    "translation_before_after": {
                        "status": "bound",
                        "unit_count": 1,
                        "measured_unsafe_unit_count": 1,
                        "accepted_patch_unit_count": 1,
                        "units": [
                            {
                                "unit_id": "flashdb/real-fdb-calc-crc32",
                                "status": "bound",
                                "unsafe_reduction": before_after["unsafe_reduction"],
                            }
                        ],
                    },
                    "avg_repair_rounds": 1.0,
                    "auto_recovery_rate": 1.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 5,
                    "llm_calls": 1,
                    "per_unit_statuses": [
                        {
                            "unit_id": "flashdb/real-fdb-calc-crc32",
                            "source": "opencode-worker",
                            "status": "converged",
                            "compiled": True,
                            "semantic_pass": True,
                            "refused": False,
                            "blocked": False,
                            "failed": False,
                            "translation_before_after": before_after,
                        }
                    ],
                },
            )

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            self.assertEqual(
                validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"],
                "passed",
            )
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["translation_before_after"]["status"], "bound")
            self.assertEqual(metrics["translation_before_after"]["unit_count"], 1)
            self.assertEqual(metrics["translation_before_after"]["measured_unsafe_unit_count"], 1)
            self.assertEqual(metrics["translation_before_after"]["accepted_patch_unit_count"], 1)
            unit = metrics["per_unit_statuses"][0]
            self.assertEqual(unit["worker_summary_path"], "workers/worker-a/summary/competition-run-summary.json")
            self.assertEqual(unit["translation_before_after"]["baseline"]["path"], "evidence/baseline-unsafe.rs")

    def test_unsafe_reduction_aggregation_requires_full_measured_worker_coverage(self) -> None:
        module = load_runner_module()
        unsafe_budget = {
            "status": "passed",
            "total_first_party_non_test_unsafe": 9,
            "ratio": 0.03,
        }

        partial = module.aggregate_unsafe_reduction(
            [
                {
                    "units_total": 1,
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 8,
                        "current_total_unsafe": 5,
                    },
                }
            ],
            unsafe_budget,
            attempted=2,
        )
        not_measured = module.aggregate_unsafe_reduction(
            [{"units_total": 1, "unsafe_reduction": {"status": "not_measured"}}],
            unsafe_budget,
            attempted=1,
        )

        for aggregate in [partial, not_measured]:
            self.assertEqual(
                aggregate,
                {
                    "status": "not_measured",
                    "baseline_total_unsafe": None,
                    "current_total_unsafe": 9,
                    "reduced_by": None,
                    "ratio": 0.03,
                },
            )

    def test_runner_preserves_worker_repair_history_in_parent_workflow_metrics(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            repair_history_path = worker_root / "worker-a" / "logs" / "repair-history.jsonl"
            repair_history_path.parent.mkdir(parents=True, exist_ok=True)
            repair_history_path.write_text(
                json.dumps({"round": 1, "status": "failed", "rollback_id": "rollback-1"}) + "\n"
                + json.dumps({"round": 2, "status": "verified"}) + "\n",
                encoding="utf-8",
            )
            worker = write_worker_summary(
                worker_root,
                "worker-a",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 2.0,
                    "auto_recovery_rate": 1.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 4,
                    "llm_calls": 2,
                    "per_unit_statuses": [
                        {
                            "unit_id": "demo/demo-add-one",
                            "source": "worker-summary",
                            "status": "converged",
                            "compiled": True,
                            "semantic_pass": True,
                            "refused": False,
                            "blocked": False,
                            "failed": False,
                            "repair_rounds": 2,
                            "auto_recovered": True,
                            "llm_calls": 2,
                            "repair_history": {
                                "patch_events_path": "workers/worker-a/logs/repair-history.jsonl",
                                "patch_events_sha256": hashlib.sha256(repair_history_path.read_bytes()).hexdigest(),
                                "statuses": ["failed", "verified"],
                                "rollback_ids": ["rollback-1"],
                                "verified": True,
                            },
                        }
                    ],
                },
            )

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            self.assertEqual(validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"], "passed")
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["per_unit_statuses"][0]["repair_rounds"], 2)
            self.assertTrue(metrics["per_unit_statuses"][0]["auto_recovered"])
            self.assertEqual(metrics["per_unit_statuses"][0]["llm_calls"], 2)
            self.assertEqual(metrics["per_unit_statuses"][0]["repair_history"]["rollback_ids"], ["rollback-1"])

    def test_runner_rewrites_worker_local_repair_history_path_for_parent_summary(self) -> None:
        module = load_runner_module()
        validator = load_summary_validator_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker_root = out_root / "workers"
            repair_history_path = worker_root / "worker-a" / "summary" / "retry-repair-history-worker-a.jsonl"
            repair_history_path.parent.mkdir(parents=True, exist_ok=True)
            repair_history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed"}) + "\n"
                + json.dumps({"attempt": 2, "status": "verified"}) + "\n",
                encoding="utf-8",
            )
            worker = write_worker_summary(
                worker_root,
                "worker-a",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 1.0,
                    "auto_recovery_rate": 1.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 3,
                    "llm_calls": 1,
                    "per_unit_statuses": [
                        {
                            "unit_id": "demo/demo-add-one",
                            "source": "worker-summary",
                            "status": "converged",
                            "compiled": True,
                            "semantic_pass": True,
                            "refused": False,
                            "blocked": False,
                            "failed": False,
                            "repair_rounds": 1,
                            "auto_recovered": True,
                            "repair_history": {
                                "patch_events_path": repair_history_path.name,
                                "patch_events_sha256": hashlib.sha256(repair_history_path.read_bytes()).hexdigest(),
                                "statuses": ["failed", "verified"],
                                "rollback_ids": [],
                                "verified": True,
                            },
                        }
                    ],
                },
            )

            result = module.run_competition(
                slice_specs=[],
                extraction_specs=[],
                worker_summaries=[worker],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="run-test",
            )

            self.assertEqual(result.exit_code, 0)
            parent_summary_path = out_root / "summary" / "competition-run-summary.json"
            self.assertEqual(validator.validate_summary(parent_summary_path, repo_root=REPO_ROOT)["status"], "passed")
            metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            repair_history = metrics["per_unit_statuses"][0]["repair_history"]
            self.assertEqual(
                repair_history["patch_events_path"],
                "workers/worker-a/summary/retry-repair-history-worker-a.jsonl",
            )
            self.assertTrue((out_root / repair_history["patch_events_path"]).exists())

    def test_runner_rejects_worker_summary_outside_out_root_workers(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            outside_worker = write_worker_summary(tmp_path / "elsewhere", "worker-a", attempted=1, semantic_pass=1)

            with self.assertRaises(SystemExit) as raised:
                module.run_competition(
                    slice_specs=[],
                    extraction_specs=[],
                    worker_summaries=[outside_worker],
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="run-test",
                )

            self.assertIn("worker summary", str(raised.exception))
            self.assertIn("out_root/workers", str(raised.exception))

    def test_runner_rejects_duplicate_worker_summary_path(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker = write_worker_summary(out_root / "workers", "worker-a", attempted=1, semantic_pass=1)

            with self.assertRaises(SystemExit) as raised:
                module.run_competition(
                    slice_specs=[],
                    extraction_specs=[],
                    worker_summaries=[worker, worker],
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="run-test",
                )

            self.assertIn("duplicate worker summary", str(raised.exception))

    def test_runner_rejects_worker_summary_proof_class_mismatch(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker = write_worker_summary(out_root / "workers", "worker-a", attempted=1, semantic_pass=1)
            worker_summary = json.loads(worker.read_text(encoding="utf-8"))
            worker_summary["proof_class"] = "ci-approximation"
            worker.write_text(json.dumps(worker_summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.run_competition(
                    slice_specs=[],
                    extraction_specs=[],
                    worker_summaries=[worker],
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="run-test",
                )

            self.assertIn("proof_class", str(raised.exception))

    def test_runner_rejects_worker_workflow_metrics_sha_mismatch(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker = write_worker_summary(
                out_root / "workers",
                "worker-a",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 0.0,
                    "auto_recovery_rate": 0.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 1,
                    "llm_calls": 0,
                    "per_unit_statuses": [],
                },
            )
            worker_summary = json.loads(worker.read_text(encoding="utf-8"))
            worker_summary["workflow_metrics"]["sha256"] = "0" * 64
            worker.write_text(json.dumps(worker_summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.run_competition(
                    slice_specs=[],
                    extraction_specs=[],
                    worker_summaries=[worker],
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="run-test",
                )

            self.assertIn("workflow_metrics.sha256", str(raised.exception))

    def test_runner_rejects_worker_workflow_metrics_malformed_binding(self) -> None:
        module = load_runner_module()
        with tempfile.TemporaryDirectory(prefix="run-competition-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "competition-out"
            worker = write_worker_summary(
                out_root / "workers",
                "worker-a",
                attempted=1,
                semantic_pass=1,
                workflow_metrics={
                    "schema_version": 1,
                    "run_id": "run-worker-a",
                    "proof_class": "local-simulation",
                    "units_total": 1,
                    "units_converged": 1,
                    "units_baseline_only": 0,
                    "unsafe_reduction": {"status": "not_measured"},
                    "avg_repair_rounds": 0.0,
                    "auto_recovery_rate": 0.0,
                    "human_interventions": 0,
                    "always_compiles": True,
                    "always_equivalent": True,
                    "fail_closed_count": 0,
                    "wall_clock_seconds": 1,
                    "llm_calls": 0,
                    "per_unit_statuses": [],
                },
            )
            worker_summary = json.loads(worker.read_text(encoding="utf-8"))
            worker_summary["workflow_metrics"] = {"path": "workflow-metrics.json"}
            worker.write_text(json.dumps(worker_summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.run_competition(
                    slice_specs=[],
                    extraction_specs=[],
                    worker_summaries=[worker],
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="run-test",
                )

            self.assertIn("workflow_metrics.path", str(raised.exception))
            self.assertIn("workflow_metrics.sha256", str(raised.exception))

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

    def test_runner_records_local_environment_check_failure_without_blocking_translation(self) -> None:
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

            self.assertEqual(result.exit_code, 0)
            summary = json.loads((out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["slices"]["attempted"], 1)
            self.assertEqual(summary["slices"]["semantic_pass"], 1)
            self.assertEqual(summary["slices"]["failed"], 0)
            self.assertEqual(summary["final_gate"]["status"], "passed")

    def test_runner_marks_exact_environment_check_failure_as_global_gate_failure(self) -> None:
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
                proof_class="competition-exact",
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
