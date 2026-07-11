from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from validation.tools import run_ai_finite_cross_project_suite as module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RunAiFiniteCrossProjectSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "validation" / "slice-specs").mkdir(parents=True)
        self.suite_path = self.root / "validation" / "suite.json"
        self.items = []
        for index in range(3):
            spec_path = self.root / "validation" / "slice-specs" / f"slice-{index}.json"
            spec_path.write_text(json.dumps({"target_id": f"project-{index}"}), encoding="utf-8")
            self.items.append(
                {
                    "id": f"item-{index}",
                    "project_id": f"project-{index}",
                    "slice_id": f"slice-{index}",
                    "slice_spec": {
                        "path": f"validation/slice-specs/slice-{index}.json",
                        "sha256": _sha256(spec_path),
                    },
                }
            )
        self._write_suite(self.items)

    def _write_suite(self, items: list[dict[str, object]]) -> None:
        self.suite_path.write_text(
            json.dumps({"schema_version": 1, "suite_id": "test-suite", "items": items}, indent=2) + "\n",
            encoding="utf-8",
        )

    def _ready_preflight(self, suite: Path | str, repo_root: Path | str | None) -> dict[str, object]:
        self.assertEqual(self.suite_path.resolve(), Path(suite).resolve())
        self.assertEqual(self.root.resolve(), Path(repo_root).resolve())
        return {
            "contract_status": "passed",
            "status": "ready",
            "summary": {
                "items_total": len(self.items),
                "ready": len(self.items),
                "blocked": 0,
                "model_invocations": 0,
                "translations_executed": 0,
            },
        }

    def _fake_result(
        self,
        kwargs: dict[str, object],
        *,
        exit_code: int = 0,
        final_status: str = "passed",
        returned_path: Path | None = None,
        returned_summary: dict[str, object] | None = None,
        attempted: int | None = None,
        circuit_skipped: int | None = None,
    ) -> SimpleNamespace:
        out_root = Path(kwargs["out_root"])
        summary_path = out_root / "summary" / "competition-run-summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        slice_count = len(kwargs["slice_specs"])
        attempted_count = slice_count if attempted is None else attempted
        summary = {
            "schema_version": 2,
            "slices": {
                "attempted": attempted_count,
                "typed_ir_generated": attempted_count,
                "compiled": attempted_count if final_status == "passed" else 0,
                "semantic_pass": attempted_count if final_status == "passed" else 0,
                "refused": 0,
                "blocked": 0,
                "failed": 0 if final_status == "passed" else attempted_count,
            },
            "ai_translation_metrics": {
                "schema_version": 1,
                "units_total": attempted_count,
                "units": [{"unit_id": f"unit-{index}"} for index in range(attempted_count)],
                "totals": {"model_invocations": attempted_count, "translations_executed": attempted_count},
            },
            "final_gate": {"status": final_status},
        }
        if circuit_skipped is not None:
            attempted_count = slice_count - circuit_skipped
            summary["provider_circuit_breaker"] = {
                "status": "open",
                "threshold": 2,
                "consecutive_failures": 2,
                "failure_kind": "provider_timeout",
                "requested_slice_specs": slice_count,
                "attempted_slice_specs": attempted_count,
                "skipped_slice_specs": circuit_skipped,
                "observations": [
                    {"unit_id": "project-0/slice-0", "failure_kind": "provider_timeout"},
                    {"unit_id": "project-1/slice-1", "failure_kind": "provider_timeout"},
                ],
            }
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=exit_code,
            summary_path=returned_path or summary_path,
            summary=summary if returned_summary is None else returned_summary,
            summary_validated=True,
        )

    def test_blocked_preflight_never_calls_competition_runner(self) -> None:
        calls = []

        def blocked_preflight(*args: object) -> dict[str, object]:
            return {"contract_status": "passed", "status": "blocked", "summary": {"blocked": 3}}

        def forbidden_runner(**kwargs: object) -> object:
            calls.append(kwargs)
            raise AssertionError("competition runner must not be called")

        exit_code, report, report_path = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=blocked_preflight,
            competition_runner=forbidden_runner,
        )

        self.assertEqual(2, exit_code)
        self.assertEqual("blocked", report["status"])
        self.assertEqual(["suite_preflight_not_ready"], report["blocked_reasons"])
        self.assertEqual([], calls)
        self.assertEqual(report, json.loads(report_path.read_text(encoding="utf-8")))

    def test_suite_is_passed_once_with_each_slice_spec_and_fresh_policy(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_runner(**kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return self._fake_result(kwargs)

        exit_code, report, _ = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            proof_class="ci-approximation",
            run_id="finite-run",
            ai_model="model-x",
            ai_agent="agent-x",
            ai_variant="variant-x",
            ai_timeout_seconds=321,
            ai_opencode_command="opencode-x",
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=fake_runner,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", report["status"])
        self.assertEqual(1, len(calls))
        self.assertEqual(
            [Path(item["slice_spec"]["path"]) for item in self.items],
            calls[0]["slice_specs"],
        )
        self.assertEqual(len(self.items), len(set(calls[0]["slice_specs"])))
        self.assertIs(calls[0]["reuse_accepted_evidence"], False)
        self.assertEqual(
            (self.root / "out" / "competition").resolve(),
            Path(calls[0]["out_root"]).resolve(),
        )
        for call in calls:
            self.assertEqual("ci-approximation", call["proof_class"])
            self.assertEqual("finite-run", call["run_id"])
            self.assertEqual("model-x", call["ai_model"])
            self.assertEqual("agent-x", call["ai_agent"])
            self.assertEqual("variant-x", call["ai_variant"])
            self.assertEqual(321, call["ai_timeout_seconds"])
            self.assertEqual("opencode-x", call["ai_opencode_command"])
        self.assertEqual(1, len(report["runs"]))
        self.assertEqual(1, report["runs"][0]["outer_attempts"])
        self.assertEqual(3, len(report["runs"][0]["suite_items"]))

    def test_dry_run_only_returns_sha_bound_plan_without_writes_or_success_claim(self) -> None:
        calls = []
        out_root = self.root / "dry-out"

        def forbidden_runner(**kwargs: object) -> object:
            calls.append(kwargs)
            raise AssertionError("dry-run must not execute")

        exit_code, plan, report_path = module.run_suite(
            suite=self.suite_path,
            out_root=out_root,
            dry_run=True,
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=forbidden_runner,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("planned", plan["status"])
        self.assertNotEqual("passed", plan["status"])
        self.assertEqual("validation/suite.json", plan["suite"]["path"])
        self.assertEqual(_sha256(self.suite_path), plan["suite"]["sha256"])
        self.assertEqual(0, plan["plan"]["model_invocations"])
        self.assertEqual(0, plan["plan"]["translations_executed"])
        self.assertFalse(plan["plan"]["success_claim_created"])
        self.assertIsNone(report_path)
        self.assertFalse(out_root.exists())
        self.assertEqual([], calls)

    def test_failure_copies_only_bound_competition_summary_values(self) -> None:
        expected: dict[str, object] = {}

        def fake_runner(**kwargs: object) -> SimpleNamespace:
            result = self._fake_result(
                kwargs,
                exit_code=1,
                final_status="failed",
            )
            expected.update(result.summary)
            return result

        exit_code, report, report_path = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=fake_runner,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", report["status"])
        self.assertEqual(["failed"], [run["status"] for run in report["runs"]])
        self.assertEqual([expected["slices"]], [entry["value"] for entry in report["slices"]])
        self.assertEqual([expected["ai_translation_metrics"]], [entry["value"] for entry in report["ai_translation_metrics"]])
        run = report["runs"][0]
        self.assertEqual(expected["slices"], run["slices"])
        self.assertEqual(expected["ai_translation_metrics"], run["ai_translation_metrics"])
        bound = self.root / "out" / run["competition_summary"]["path"]
        self.assertEqual(_sha256(bound), run["competition_summary"]["sha256"])
        self.assertEqual(report, json.loads(report_path.read_text(encoding="utf-8")))

    def test_suite_sha_drift_blocks_before_any_competition_call(self) -> None:
        calls = []

        def drifting_preflight(*args: object) -> dict[str, object]:
            self.suite_path.write_text(self.suite_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            return {"contract_status": "passed", "status": "ready", "summary": {"ready": 3}}

        def forbidden_runner(**kwargs: object) -> object:
            calls.append(kwargs)
            raise AssertionError("drifted suite must not execute")

        exit_code, report, _ = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=drifting_preflight,
            competition_runner=forbidden_runner,
        )

        self.assertEqual(2, exit_code)
        self.assertEqual(["suite_sha256_drift"], report["blocked_reasons"])
        self.assertEqual([], calls)

    def test_unexpected_summary_path_fails_closed_without_copying_semantic_numbers(self) -> None:
        def fake_runner(**kwargs: object) -> SimpleNamespace:
            wrong_path = Path(kwargs["out_root"]) / "summary" / "other.json"
            return self._fake_result(kwargs, returned_path=wrong_path)

        exit_code, report, _ = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=fake_runner,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("unexpected_competition_summary_path", report["runs"][0]["error"])
        self.assertEqual([], report["slices"])
        self.assertEqual([], report["ai_translation_metrics"])

    def test_summary_result_drift_fails_closed(self) -> None:
        def fake_runner(**kwargs: object) -> SimpleNamespace:
            return self._fake_result(kwargs, returned_summary={"drifted": True})

        exit_code, report, _ = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=fake_runner,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("competition_summary_result_mismatch", report["runs"][0]["error"])
        self.assertEqual([], report["slices"])

    def test_unvalidated_competition_summary_fails_closed(self) -> None:
        def fake_runner(**kwargs: object) -> SimpleNamespace:
            result = self._fake_result(kwargs)
            result.summary_validated = False
            return result

        exit_code, report, _ = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=fake_runner,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("competition_summary_validation_failed", report["runs"][0]["error"])
        self.assertEqual([], report["slices"])

    def test_attempted_count_mismatch_fails_closed_without_semantic_copy(self) -> None:
        def fake_runner(**kwargs: object) -> SimpleNamespace:
            return self._fake_result(kwargs, attempted=2)

        exit_code, report, _ = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=fake_runner,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("competition_summary_attempted_count_mismatch", report["runs"][0]["error"])
        self.assertEqual([], report["slices"])
        self.assertEqual([], report["ai_translation_metrics"])

    def test_provider_circuit_breaker_returns_bound_blocked_partial_report(self) -> None:
        def fake_runner(**kwargs: object) -> SimpleNamespace:
            return self._fake_result(
                kwargs,
                exit_code=1,
                final_status="failed",
                attempted=2,
                circuit_skipped=1,
            )

        exit_code, report, report_path = module.run_suite(
            suite=self.suite_path,
            out_root=self.root / "out",
            repo_root=self.root,
            preflight_validator=self._ready_preflight,
            competition_runner=fake_runner,
        )

        self.assertEqual(2, exit_code)
        self.assertEqual("blocked", report["status"])
        self.assertEqual("blocked", report["runs"][0]["status"])
        self.assertEqual("provider_circuit_breaker_open", report["runs"][0]["error"])
        self.assertEqual(1, report["runs"][0]["provider_circuit_breaker"]["skipped_slice_specs"])
        self.assertEqual(1, len(report["slices"]))
        self.assertEqual(1, len(report["ai_translation_metrics"]))
        self.assertEqual(report, json.loads(report_path.read_text(encoding="utf-8")))

    def test_main_forwards_cli_ai_options(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_runner(**kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return self._fake_result(kwargs)

        args = [
            "--suite",
            str(self.suite_path),
            "--out-root",
            str(self.root / "cli-out"),
            "--proof-class",
            "wsl-local-simulation",
            "--run-id",
            "cli-run",
            "--ai-model",
            "cli-model",
            "--ai-agent",
            "cli-agent",
            "--ai-variant",
            "cli-variant",
            "--ai-timeout-seconds",
            "77",
            "--ai-opencode-command",
            "cli-opencode",
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = module.main(
                args,
                repo_root=self.root,
                preflight_validator=self._ready_preflight,
                competition_runner=fake_runner,
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(calls))
        self.assertTrue(all(call["proof_class"] == "wsl-local-simulation" for call in calls))
        self.assertTrue(all(call["run_id"] == "cli-run" for call in calls))
        self.assertTrue(all(call["ai_model"] == "cli-model" for call in calls))
        self.assertTrue(all(call["ai_agent"] == "cli-agent" for call in calls))
        self.assertTrue(all(call["ai_variant"] == "cli-variant" for call in calls))
        self.assertTrue(all(call["ai_timeout_seconds"] == 77 for call in calls))
        self.assertTrue(all(call["ai_opencode_command"] == "cli-opencode" for call in calls))


if __name__ == "__main__":
    unittest.main()
