from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from validation.tools import _ai_auxiliary_repair_metrics as repair_metrics
from validation.tools import run_ai_auxiliary_cross_project_suite as runner


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class AuxiliaryRepairMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ai-aux-repair-")
        self.root = Path(self.temporary.name)
        self.item = {
            "id": "project-a-one",
            "project_id": "project-a",
            "slice_id": "one",
            "construct_family": "loop",
            "slice_spec": {"path": "validation/one.json", "sha256": ""},
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initial_empty_completion_retry_counts_both_provider_invocations(self) -> None:
        self.assertEqual(2, repair_metrics.manifest_invocation_count({"provider_invocations": 2}))

    def test_runner_failure_round_is_not_a_proven_provider_invocation(self) -> None:
        report = self.repair_report("blocked", "provider_runner_failed", 1)
        report["rounds"][0]["bindings"].pop("raw_response")
        rounds, invocations = repair_metrics._validate_repair_rounds(report)
        self.assertEqual(1, rounds)
        self.assertEqual(0, invocations)

    def run_unit_with_repair(
        self,
        *,
        report_status: str,
        stop_reason: str,
        round_count: int,
        binding_mode: str = "valid",
        fresh_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        spec_path = self.root / "validation" / "one.json"
        write_json(spec_path, {"target_id": "project-a", "slice_id": "one"})
        self.item["slice_spec"]["sha256"] = runner.sha256_path(spec_path)
        evidence_root = self.root / "target" / binding_mode / "evidence"
        evidence_dir = evidence_root / "project-a" / "auto-translation" / "one"
        repair_path = evidence_dir / "l3-one-ai-repair-report.json"
        repair_report = self.repair_report(report_status, stop_reason, round_count)
        if binding_mode == "synthetic":
            repair_report["rounds"][0]["bindings"].pop("raw_response")
            repair_report["rounds"][0]["failure"]["kind"] = "invalid_repair_response"

        def fake_command(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            bound_path = repair_path
            bound_name = repair_path.name
            if binding_mode == "escaped":
                bound_path = evidence_dir.parent / "outside-repair-report.json"
                bound_name = "../outside-repair-report.json"
            if binding_mode != "missing":
                write_json(bound_path, repair_report)
            expected_sha = runner.sha256_path(bound_path) if bound_path.is_file() else "c" * 64
            if binding_mode == "drifted":
                expected_sha = "d" * 64
            write_json(
                evidence_dir / "l3-one-ai-candidate-manifest.json",
                {
                    "schema_version": 8,
                    "target_id": "project-a",
                    "slice_id": "one",
                    "status": "generated",
                    "provider_invocations": 1,
                    "generator": {},
                    "candidates": [],
                    "repair": {
                        "path": bound_name,
                        "sha256": expected_sha,
                        "status": report_status,
                        "semantic_pass": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

        reasons = fresh_reasons or ["ai_candidate_not_competition_eligible"]
        with (
            mock.patch.object(
                repair_metrics.summary_validator,
                "validate_bound_ai_repair_report",
                return_value=(round_count, []),
            ),
            mock.patch.object(
                runner.summary_validator,
                "validate_fresh_ai_manifest",
                return_value={"reasons": reasons},
            ),
        ):
            return runner.run_unit(
                item=self.item,
                index=0,
                repo_root=self.root,
                evidence_root=evidence_root,
                logs_root=self.root / "target" / binding_mode / "logs",
                report_path=self.root / "target" / binding_mode / "summary" / "report.json",
                model=runner.DEFAULT_MODEL,
                agent=runner.DEFAULT_AGENT,
                variant=runner.DEFAULT_VARIANT,
                timeout_seconds=30,
                repair_rounds=max(1, round_count),
                opencode_command="opencode",
                command_runner=fake_command,
            )

    @staticmethod
    def repair_report(status: str, stop_reason: str, round_count: int) -> dict[str, object]:
        rounds = []
        for round_number in range(1, round_count + 1):
            blocked = status == "blocked"
            bindings = {
                "previous_candidate_sha256": f"{round_number + 10:064x}",
                "failure_facts": {"path": f"failure-{round_number}.json", "sha256": "a" * 64},
                "prompt": {"path": f"prompt-{round_number}.txt", "sha256": "b" * 64},
                "raw_response": {"path": f"response-{round_number}.jsonl", "sha256": "c" * 64},
            }
            if not blocked:
                bindings.update(
                    {
                        "repair_artifact": {"path": f"repair-{round_number}.rs", "sha256": "d" * 64},
                        "candidate": {"path": f"candidate-{round_number}.rs", "sha256": "e" * 64},
                        "validation_result": {"path": f"validation-{round_number}.json", "sha256": "f" * 64},
                    }
                )
            rounds.append(
                {
                    "round": round_number,
                    "status": "blocked" if blocked else "candidate_generated",
                    "repair_input_sha256": f"{round_number:064x}",
                    "bindings": bindings,
                    **(
                        {"failure": {"kind": stop_reason, "message": "provider call failed"}}
                        if blocked
                        else {}
                    ),
                    "semantic_pass": False,
                }
            )
        return {
            "schema_version": 3,
            "target_id": "project-a",
            "slice_id": "one",
            "artifact_label": "ai-repair",
            "input_source": "opencode-ai",
            "status": status,
            "stop_reason": stop_reason,
            "policy": {"effective_max_rounds": max(1, round_count)},
            "generator": {},
            "claim_boundary": {
                "semantic_gate": False,
                "semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "rounds": rounds,
        }

    def test_exhausted_report_counts_all_verified_rounds(self) -> None:
        unit = self.run_unit_with_repair(
            report_status="exhausted",
            stop_reason="repair_round_limit_reached",
            round_count=2,
        )
        self.assertEqual(1, unit["initial_candidate_provider_invocations"])
        self.assertEqual(2, unit["repair_provider_invocations"])
        self.assertEqual(3, unit["provider_invocations"])
        self.assertEqual(3, unit["provider_invocations_total"])
        self.assertEqual("exhausted", unit["repair_status"])
        self.assertIn("repair_report", unit["artifacts"])

    def test_blocked_timeout_and_invalid_response_rounds_are_counted(self) -> None:
        for stop_reason in ("provider_timeout", "invalid_repair_response"):
            with self.subTest(stop_reason=stop_reason):
                unit = self.run_unit_with_repair(
                    report_status="blocked",
                    stop_reason=stop_reason,
                    round_count=1,
                )
                self.assertEqual(1, unit["repair_provider_invocations"])
                self.assertEqual(2, unit["provider_invocations_total"])
                self.assertEqual(stop_reason, unit["repair_stop_reason"])

    def test_verified_metrics_remain_visible_when_fresh_manifest_fails(self) -> None:
        unit = self.run_unit_with_repair(
            report_status="exhausted",
            stop_reason="repair_round_limit_reached",
            round_count=2,
            fresh_reasons=[
                "ai_candidate_not_competition_eligible",
                "ai_manifest_prompt_context_mismatch",
            ],
        )
        self.assertEqual("contract_failed", unit["status"])
        self.assertIn("ai_manifest_prompt_context_mismatch", unit["reason"])
        self.assertEqual(2, unit["repair_provider_invocations"])
        self.assertEqual(3, unit["provider_invocations_total"])
        self.assertEqual("exhausted", unit["repair_status"])
        self.assertIn("repair_report", unit["artifacts"])

    def test_missing_drifted_or_escaped_binding_is_not_counted(self) -> None:
        for binding_mode, expected_reason in (
            ("missing", "repair_report_missing"),
            ("drifted", "repair_report_sha256_mismatch"),
            ("escaped", "repair_report_path_invalid"),
        ):
            with self.subTest(binding_mode=binding_mode):
                unit = self.run_unit_with_repair(
                    report_status="blocked",
                    stop_reason="invalid_repair_response",
                    round_count=1,
                    binding_mode=binding_mode,
                )
                self.assertEqual("contract_failed", unit["status"])
                self.assertEqual(expected_reason, unit["reason"])
                self.assertEqual(0, unit["repair_provider_invocations"])
                self.assertEqual(1, unit["provider_invocations_total"])
                self.assertNotIn("repair_report", unit["artifacts"])

    def test_synthetic_round_without_provider_evidence_is_not_counted(self) -> None:
        unit = self.run_unit_with_repair(
            report_status="blocked",
            stop_reason="invalid_repair_response",
            round_count=1,
            binding_mode="synthetic",
        )
        self.assertEqual("contract_failed", unit["status"])
        self.assertEqual("repair_report_round_has_no_provider_evidence", unit["reason"])
        self.assertEqual(0, unit["repair_provider_invocations"])
        self.assertEqual(1, unit["provider_invocations_total"])


if __name__ == "__main__":
    unittest.main()
