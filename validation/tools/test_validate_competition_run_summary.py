import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_competition_run_summary.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_competition_run_summary_under_test", VALIDATOR)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load validate_competition_run_summary module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_summary() -> dict:
    return {
        "schema_version": 1,
        "run_id": "run-2026-06-28T120000Z",
        "proof_class": "wsl-local-simulation",
        "profile_id": "huawei-competition-ubuntu-24.04",
        "profile_sha256": "a" * 64,
        "clang_source": "vendored",
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": 17,
        "translator_version": "0.1.0",
        "slices": {
            "attempted": 2,
            "typed_ir_generated": 1,
            "compiled": 1,
            "semantic_pass": 1,
            "refused": 1,
            "blocked": 0,
            "failed": 0,
        },
        "unsafe_budget": {
            "status": "passed",
            "total_first_party_non_test_unsafe": 0,
            "ratio": 0.0,
        },
        "artifact_roots": [
            "target/competition-out/evidence",
            "target/competition-out/summary",
            "target/competition-out/logs",
        ],
        "final_gate": {
            "status": "passed",
            "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
        },
    }


def workflow_metrics_for(summary: dict) -> dict:
    slices = summary["slices"]
    per_unit_statuses = []
    for index in range(slices["semantic_pass"]):
        per_unit_statuses.append(
            {
                "unit_id": f"demo/unit-{index + 1}",
                "source": "slice-spec",
                "status": "converged",
                "compiled": True,
                "semantic_pass": True,
                "refused": False,
                "blocked": False,
                "failed": False,
            }
        )
    for index in range(slices["refused"]):
        per_unit_statuses.append(
            {
                "unit_id": f"demo/refused-{index + 1}",
                "source": "slice-spec",
                "status": "refused",
                "compiled": False,
                "semantic_pass": False,
                "refused": True,
                "blocked": False,
                "failed": False,
            }
        )
    for index in range(slices["blocked"]):
        per_unit_statuses.append(
            {
                "unit_id": f"demo/blocked-{index + 1}",
                "source": "slice-spec",
                "status": "blocked",
                "compiled": False,
                "semantic_pass": False,
                "refused": False,
                "blocked": True,
                "failed": False,
            }
        )
    for index in range(slices["failed"]):
        per_unit_statuses.append(
            {
                "unit_id": f"demo/failed-{index + 1}",
                "source": "slice-spec",
                "status": "failed",
                "compiled": False,
                "semantic_pass": False,
                "refused": False,
                "blocked": False,
                "failed": True,
            }
        )
    while len(per_unit_statuses) < slices["attempted"]:
        per_unit_statuses.append(
            {
                "unit_id": f"demo/unclassified-{len(per_unit_statuses) + 1}",
                "source": "slice-spec",
                "status": "unclassified",
                "compiled": False,
                "semantic_pass": False,
                "refused": False,
                "blocked": False,
                "failed": False,
            }
        )
    return {
        "schema_version": 1,
        "run_id": summary["run_id"],
        "proof_class": summary["proof_class"],
        "units_total": slices["attempted"],
        "units_converged": slices["semantic_pass"],
        "units_baseline_only": max(0, slices["compiled"] - slices["semantic_pass"]),
        "unsafe_reduction": {
            "status": "not_measured",
            "baseline_total_unsafe": None,
            "current_total_unsafe": summary["unsafe_budget"]["total_first_party_non_test_unsafe"],
            "reduced_by": None,
            "ratio": summary["unsafe_budget"]["ratio"],
        },
        "translation_before_after": {
            "status": "not_provided",
            "unit_count": 0,
            "measured_unsafe_unit_count": 0,
            "accepted_patch_unit_count": 0,
            "units": [],
        },
        "avg_repair_rounds": 0.0,
        "auto_recovery_rate": 0.0,
        "human_interventions": 0,
        "always_compiles": False,
        "always_equivalent": False,
        "fail_closed_count": slices["refused"] + slices["blocked"],
        "root_cause_counts": {},
        "wall_clock_seconds": summary["elapsed_seconds"],
        "llm_calls": 0,
        "per_unit_statuses": per_unit_statuses,
    }


def write_summary_with_workflow_metrics(summary_path: Path, summary: dict) -> None:
    metrics_path = summary_path.parent / "workflow-metrics.json"
    metrics_path.write_text(json.dumps(workflow_metrics_for(summary), sort_keys=True), encoding="utf-8")
    summary["workflow_metrics"] = {
        "path": "workflow-metrics.json",
        "sha256": hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")


class ValidateCompetitionRunSummaryTests(unittest.TestCase):
    def test_core_ci_runs_competition_run_summary_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "core-translator-validation-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("validation.tools.test_validate_competition_run_summary", workflow)

    def test_accepts_valid_competition_run_summary(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, valid_summary())

            result = module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["proof_class"], "wsl-local-simulation")

    def test_accepts_valid_competition_run_summary_with_worker_statuses(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 2,
            "summaries": [
                {
                    "path": "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
                    "status": "passed",
                    "proof_class": "wsl-local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                },
                {
                    "path": "target/competition-out/workers/worker-b/summary/competition-run-summary.json",
                    "status": "failed",
                    "proof_class": "wsl-local-simulation",
                    "attempted": 2,
                    "semantic_pass": 1,
                    "failed": 1,
                    "slices": {
                        "attempted": 2,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 1,
                    },
                },
            ],
        }
        summary["final_gate"]["status"] = "failed"
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            result = module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")

    def test_accepts_worker_summary_under_custom_run_out_root(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 1,
            "summaries": [
                {
                    "path": "target/opencode-real-smoke-20260630-003/workers/worker-a/summary/competition-run-summary.json",
                    "status": "passed",
                    "proof_class": "wsl-local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            result = module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")

    def test_rejects_unknown_proof_class(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["proof_class"] = "local"
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("proof_class", str(raised.exception))

    def test_rejects_missing_workflow_metrics_artifact_binding(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("workflow_metrics", str(raised.exception))

    def test_rejects_workflow_metrics_sha_mismatch(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)
            summary["workflow_metrics"]["sha256"] = "0" * 64
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("sha256", str(raised.exception))

    def test_rejects_repair_rounds_without_repair_history(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics["per_unit_statuses"] = [
                {
                    "unit_id": "demo/keyword-param",
                    "source": "slice-spec",
                    "status": "converged",
                    "compiled": True,
                    "semantic_pass": True,
                    "refused": False,
                    "blocked": False,
                    "failed": False,
                    "repair_rounds": 2,
                    "auto_recovered": True,
                },
                {
                    "unit_id": "demo/refused-1",
                    "source": "slice-spec",
                    "status": "refused",
                    "compiled": False,
                    "semantic_pass": False,
                    "refused": True,
                    "blocked": False,
                    "failed": False,
                },
            ]
            metrics_path.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
            summary["workflow_metrics"]["sha256"] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("repair_history", str(raised.exception))

    def test_accepts_translation_before_after_artifact_bindings(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["slices"] = {
            "attempted": 1,
            "typed_ir_generated": 1,
            "compiled": 1,
            "semantic_pass": 1,
            "refused": 0,
            "blocked": 0,
            "failed": 0,
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-run-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            artifacts = {
                "baseline": evidence_dir / "baseline.rs",
                "final": evidence_dir / "final.rs",
                "oracle_evidence": evidence_dir / "oracle-diff.json",
                "accepted_patch": evidence_dir / "accepted.patch",
                "patch_log": evidence_dir / "step-log.jsonl",
            }
            for name, path in artifacts.items():
                path.write_text(f"{name}\n", encoding="utf-8")
            write_summary_with_workflow_metrics(summary_path, summary)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            before_after = {
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
                    "baseline_total_unsafe": 4,
                    "current_total_unsafe": 1,
                    "reduced_by": 3,
                    "ratio": 0.25,
                },
            }
            metrics["translation_before_after"] = {
                "status": "bound",
                "unit_count": 1,
                "measured_unsafe_unit_count": 1,
                "accepted_patch_unit_count": 1,
                "units": [
                    {
                        "unit_id": "demo/unit-1",
                        "status": "bound",
                        "unsafe_reduction": before_after["unsafe_reduction"],
                    }
                ],
            }
            metrics["per_unit_statuses"][0]["translation_before_after"] = before_after
            metrics["unsafe_reduction"] = before_after["unsafe_reduction"]
            metrics_path.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
            summary["workflow_metrics"]["sha256"] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            result = module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")

    def test_rejects_root_unsafe_reduction_drift_from_translation_before_after_units(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["slices"] = {
            "attempted": 1,
            "typed_ir_generated": 1,
            "compiled": 1,
            "semantic_pass": 1,
            "refused": 0,
            "blocked": 0,
            "failed": 0,
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-run-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            artifacts = {
                "baseline": evidence_dir / "baseline.rs",
                "final": evidence_dir / "final.rs",
                "oracle_evidence": evidence_dir / "oracle-diff.json",
                "accepted_patch": evidence_dir / "accepted.patch",
            }
            for name, path in artifacts.items():
                path.write_text(f"{name}\n", encoding="utf-8")
            write_summary_with_workflow_metrics(summary_path, summary)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            unsafe_reduction = {
                "status": "measured",
                "baseline_total_unsafe": 4,
                "current_total_unsafe": 1,
                "reduced_by": 3,
                "ratio": 0.25,
            }
            before_after = {
                "schema_version": 1,
                "status": "bound",
                **{
                    name: {
                        "path": f"evidence/{path.name}",
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for name, path in artifacts.items()
                },
                "unsafe_reduction": unsafe_reduction,
            }
            metrics["translation_before_after"] = {
                "status": "bound",
                "unit_count": 1,
                "measured_unsafe_unit_count": 1,
                "accepted_patch_unit_count": 1,
                "units": [
                    {
                        "unit_id": "demo/unit-1",
                        "status": "bound",
                        "unsafe_reduction": unsafe_reduction,
                    }
                ],
            }
            metrics["per_unit_statuses"][0]["translation_before_after"] = before_after
            metrics["unsafe_reduction"] = {
                "status": "measured",
                "baseline_total_unsafe": 4,
                "current_total_unsafe": 2,
                "reduced_by": 2,
                "ratio": 0.5,
            }
            metrics_path.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
            summary["workflow_metrics"]["sha256"] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("workflow metrics unsafe_reduction does not match translation_before_after units", str(raised.exception))

    def test_rejects_translation_before_after_sha_mismatch(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["slices"] = {
            "attempted": 1,
            "typed_ir_generated": 1,
            "compiled": 1,
            "semantic_pass": 1,
            "refused": 0,
            "blocked": 0,
            "failed": 0,
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-run-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            artifact_paths = {}
            for name in ["baseline", "final", "oracle_evidence", "accepted_patch"]:
                path = evidence_dir / f"{name}.txt"
                path.write_text(name, encoding="utf-8")
                artifact_paths[name] = path
            write_summary_with_workflow_metrics(summary_path, summary)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            before_after = {
                "schema_version": 1,
                "status": "bound",
                **{
                    name: {
                        "path": f"evidence/{path.name}",
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for name, path in artifact_paths.items()
                },
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 4,
                    "current_total_unsafe": 1,
                    "reduced_by": 3,
                },
            }
            before_after["final"]["sha256"] = "0" * 64
            metrics["translation_before_after"] = {
                "status": "bound",
                "unit_count": 1,
                "measured_unsafe_unit_count": 1,
                "accepted_patch_unit_count": 1,
                "units": [
                    {
                        "unit_id": "demo/unit-1",
                        "status": "bound",
                        "unsafe_reduction": before_after["unsafe_reduction"],
                    }
                ],
            }
            metrics["per_unit_statuses"][0]["translation_before_after"] = before_after
            metrics_path.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
            summary["workflow_metrics"]["sha256"] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("translation_before_after.final.sha256", str(raised.exception))

    def test_rejects_workflow_root_cause_count_mismatch(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics["root_cause_counts"] = {}
            metrics["per_unit_statuses"] = [
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
                },
                {
                    "unit_id": "demo/demo-add-two",
                    "source": "slice-spec",
                    "status": "converged",
                    "compiled": True,
                    "semantic_pass": True,
                    "refused": False,
                    "blocked": False,
                    "failed": False,
                },
            ]
            metrics_path.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
            summary["workflow_metrics"]["sha256"] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("root_cause_counts", str(raised.exception))

    def test_rejects_workflow_per_unit_status_count_mismatch(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics["per_unit_statuses"] = [
                {
                    "unit_id": "demo/demo-add-one",
                    "source": "slice-spec",
                    "status": "converged",
                    "compiled": True,
                    "semantic_pass": True,
                    "refused": False,
                    "blocked": False,
                    "failed": False,
                }
            ]
            metrics_path.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
            summary["workflow_metrics"]["sha256"] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("per_unit_statuses count", str(raised.exception))

    def test_rejects_worker_summary_count_mismatch(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 2,
            "summaries": [
                {
                    "path": "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
                    "status": "passed",
                    "proof_class": "local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("workers.count", str(raised.exception))

    def test_rejects_worker_summary_proof_class_mismatch(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 1,
            "summaries": [
                {
                    "path": "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
                    "status": "passed",
                    "proof_class": "local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("proof_class", str(raised.exception))

    def test_rejects_worker_summary_absolute_path(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 1,
            "summaries": [
                {
                    "path": "F:/agent/crustpaper/0630/target/competition-out/workers/worker-a/summary/competition-run-summary.json",
                    "status": "passed",
                    "proof_class": "wsl-local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("worker summary path", str(raised.exception))

    def test_rejects_worker_summary_path_not_under_workers_summary(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["workers"] = {
            "count": 1,
            "summaries": [
                {
                    "path": "target/competition-out/misc/worker-a.json",
                    "status": "passed",
                    "proof_class": "wsl-local-simulation",
                    "attempted": 1,
                    "semantic_pass": 1,
                    "failed": 0,
                    "slices": {
                        "attempted": 1,
                        "typed_ir_generated": 1,
                        "compiled": 1,
                        "semantic_pass": 1,
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("workers/<worker-id>/summary/competition-run-summary.json", str(raised.exception))

    def test_rejects_duplicate_worker_summary_paths(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        worker = {
            "path": "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
            "status": "passed",
            "proof_class": "wsl-local-simulation",
            "attempted": 1,
            "semantic_pass": 1,
            "failed": 0,
            "slices": {
                "attempted": 1,
                "typed_ir_generated": 1,
                "compiled": 1,
                "semantic_pass": 1,
                "refused": 0,
                "blocked": 0,
                "failed": 0,
            },
        }
        summary["workers"] = {"count": 2, "summaries": [dict(worker), dict(worker)]}
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("duplicate worker summary path", str(raised.exception))

    def test_rejects_absolute_artifact_root(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["artifact_roots"][0] = "F:/agent/crustpaper/0625ctr/target/competition-out/evidence"
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("artifact_roots", str(raised.exception))

    def test_rejects_passed_final_gate_without_semantic_pass(self) -> None:
        module = load_validator_module()
        summary = valid_summary()
        summary["slices"]["semantic_pass"] = 0
        with tempfile.TemporaryDirectory(prefix="competition-summary-test-") as tmp:
            summary_path = Path(tmp) / "competition-run-summary.json"
            write_summary_with_workflow_metrics(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                module.validate_summary(summary_path, repo_root=REPO_ROOT)

        self.assertIn("semantic_pass", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
