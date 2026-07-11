from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness


INITIAL_SOURCE = "pub fn add_one(value: i32) -> i32 {\n    value + 2\n}\n"


def context_pack() -> dict[str, object]:
    return {
        "schema_version": 1,
        "target_id": "generic-target",
        "slice_id": "generic-add-one",
        "function_name": "add_one",
        "claim_boundary": {"semantic_gate": False},
    }


def failed_result(message: str = "return value differs") -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "failed",
        "failures": [
            {
                "gate": "schema_diff",
                "kind": "value_mismatch",
                "message": message,
                "location": {"function": "add_one"},
                "expected": 2,
                "actual": 3,
                "details": {"case_id": "bounded-1"},
            }
        ],
    }


def passed_result() -> dict[str, object]:
    return {"schema_version": 1, "status": "passed", "failures": []}


def repair_jsonl(repair: dict[str, object]) -> str:
    payload = {"schema_version": 1, "repair": repair, "assumptions": []}
    return json.dumps(
        {"type": "message.part.updated", "part": {"type": "text", "text": json.dumps(payload)}}
    ) + "\n"


def candidate_response(source: str) -> str:
    return repair_jsonl({"kind": "candidate", "language": "rust", "source": source})


def write_candidate(root: Path, source: str = INITIAL_SOURCE) -> Path:
    path = root / "initial.rs"
    path.write_text(source, encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AiCandidateRepairTests(unittest.TestCase):
    def test_candidate_repair_is_hash_bound_and_never_semantic_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-candidate-") as tmp:
            root = Path(tmp)
            initial = write_candidate(root)
            repaired = "pub fn add_one(value: i32) -> i32 {\n    value.wrapping_add(1)\n}\n"
            observed_argv: list[str] = []

            def provider(argv: list[str], timeout: int) -> ai_candidate_harness.ProviderExecution:
                observed_argv.extend(argv)
                self.assertEqual(timeout, 30)
                return ai_candidate_harness.ProviderExecution(0, candidate_response(repaired), "")

            def validator(candidate: Path, round_number: int) -> dict[str, object]:
                self.assertEqual(round_number, 1)
                self.assertEqual(candidate.read_text(encoding="utf-8"), repaired)
                return passed_result()

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=initial,
                initial_failure_facts=failed_result(),
                out_dir=root / "out",
                validation_runner=validator,
                timeout_seconds=30,
                runner=provider,
            )

            self.assertEqual(report["status"], "candidate_ready_for_common_validation")
            self.assertEqual(report["policy"]["effective_max_rounds"], 3)
            self.assertEqual(report["policy"]["hard_max_rounds"], 5)
            self.assertFalse(report["claim_boundary"]["semantic_pass"])
            self.assertEqual(report["claim_boundary"]["translation_coverage_numerator"], 0)
            self.assertNotIn('"semantic_pass": true', json.dumps(report).lower())
            self.assertEqual(initial.read_text(encoding="utf-8"), INITIAL_SOURCE)
            self.assertEqual(observed_argv[-1].splitlines()[0], "Task mode: generate-candidate")
            self.assertIn("Oracle, fixture, validator, and gate configuration are immutable", observed_argv[-1])
            round_record = report["rounds"][0]
            self.assertEqual(round_record["repair_kind"], "candidate")
            self.assertEqual(round_record["bindings"]["previous_candidate_sha256"], sha256(initial))
            self.assertEqual(len(round_record["repair_input_sha256"]), 64)
            for name in ("failure_facts", "prompt", "raw_response", "repair_artifact", "candidate"):
                binding = round_record["bindings"][name]
                self.assertEqual(binding["sha256"], sha256(root / "out" / binding["path"]))

    def test_single_file_patch_repairs_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-patch-") as tmp:
            root = Path(tmp)
            initial = write_candidate(root)
            patch = (
                "--- a/candidate.rs\n"
                "+++ b/candidate.rs\n"
                "@@ -1,3 +1,3 @@\n"
                " pub fn add_one(value: i32) -> i32 {\n"
                "-    value + 2\n"
                "+    value.wrapping_add(1)\n"
                " }\n"
            )

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=initial,
                initial_failure_facts=failed_result(),
                out_dir=root / "out",
                validation_runner=lambda candidate, _round: (
                    passed_result()
                    if "wrapping_add(1)" in candidate.read_text(encoding="utf-8")
                    else failed_result()
                ),
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    repair_jsonl({"kind": "patch", "format": "unified_diff", "content": patch}),
                    "",
                ),
            )

            self.assertEqual(report["status"], "candidate_ready_for_common_validation")
            self.assertEqual(report["rounds"][0]["repair_kind"], "patch")
            final_path = root / "out" / report["final_candidate"]["path"]
            self.assertIn("wrapping_add(1)", final_path.read_text(encoding="utf-8"))

    def test_unchanged_candidate_and_failure_stop_without_second_provider_call(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-unchanged-") as tmp:
            root = Path(tmp)
            initial = write_candidate(root)
            calls = 0

            def provider(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(0, candidate_response(INITIAL_SOURCE), "")

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=initial,
                initial_failure_facts=failed_result(),
                out_dir=root / "out",
                validation_runner=lambda _candidate, _round: failed_result(),
                runner=provider,
            )

            self.assertEqual(calls, 1)
            self.assertEqual(report["status"], "stopped")
            self.assertEqual(report["stop_reason"], "unchanged_input_and_failure")

    def test_five_round_hard_cap_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-cap-") as tmp:
            root = Path(tmp)
            initial = write_candidate(root)
            calls = 0

            def provider(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(
                    0,
                    candidate_response(f"{INITIAL_SOURCE}// repair round {calls}\n"),
                    "",
                )

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=initial,
                initial_failure_facts=failed_result("initial"),
                out_dir=root / "out",
                validation_runner=lambda _candidate, round_number: failed_result(f"round-{round_number}"),
                max_rounds=5,
                runner=provider,
            )

            self.assertEqual(calls, 5)
            self.assertEqual(report["status"], "exhausted")
            self.assertEqual(report["stop_reason"], "repair_round_limit_reached")
            with self.assertRaisesRegex(ValueError, "between 1 and 5"):
                ai_candidate_harness.coordinate_repairs(
                    context_pack(),
                    candidate_path=initial,
                    initial_failure_facts=failed_result(),
                    out_dir=root / "invalid",
                    validation_runner=lambda _candidate, _round: passed_result(),
                    max_rounds=6,
                    runner=provider,
                )
            self.assertEqual(calls, 5)

    def test_default_round_cap_stops_after_three_attempts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-default-cap-") as tmp:
            root = Path(tmp)
            calls = 0

            def provider(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(
                    0,
                    candidate_response(f"{INITIAL_SOURCE}// default repair round {calls}\n"),
                    "",
                )

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=write_candidate(root),
                initial_failure_facts=failed_result("initial"),
                out_dir=root / "out",
                validation_runner=lambda _candidate, round_number: failed_result(f"round-{round_number}"),
                runner=provider,
            )

            self.assertEqual(calls, 3)
            self.assertEqual(report["status"], "exhausted")
            self.assertEqual(len(report["rounds"]), 3)

    def test_unstructured_failure_facts_block_before_provider(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-facts-") as tmp:
            root = Path(tmp)
            calls = 0

            def provider(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(0, candidate_response(INITIAL_SOURCE), "")

            malformed = {"schema_version": 1, "status": "failed", "failures": ["rustc failed"]}
            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=write_candidate(root),
                initial_failure_facts=malformed,
                out_dir=root / "out",
                validation_runner=lambda _candidate, _round: passed_result(),
                runner=provider,
            )

            self.assertEqual(calls, 0)
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["failure"]["kind"], "invalid_repair_input")

    def test_sensitive_failure_fact_is_not_sent_to_provider(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-sensitive-") as tmp:
            root = Path(tmp)
            calls = 0
            failures = failed_result()
            failures["failures"][0]["details"]["api_key"] = "must-not-leak"

            def provider(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(0, candidate_response(INITIAL_SOURCE), "")

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=write_candidate(root),
                initial_failure_facts=failures,
                out_dir=root / "out",
                validation_runner=lambda _candidate, _round: passed_result(),
                runner=provider,
            )

            self.assertEqual(calls, 0)
            self.assertEqual(report["status"], "blocked")
            self.assertNotIn("must-not-leak", json.dumps(report))

    def test_provider_failure_is_structured_and_skips_validator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-provider-") as tmp:
            root = Path(tmp)
            validator_calls = 0

            def validator(_candidate: Path, _round: int) -> dict[str, object]:
                nonlocal validator_calls
                validator_calls += 1
                return passed_result()

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=write_candidate(root),
                initial_failure_facts=failed_result(),
                out_dir=root / "out",
                validation_runner=validator,
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    1,
                    "",
                    "invalid api key",
                ),
            )

            self.assertEqual(validator_calls, 0)
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["failure"]["kind"], "provider_authentication_failed")
            self.assertEqual(report["rounds"][0]["status"], "blocked")

    def test_response_cannot_include_gate_configuration_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-protected-") as tmp:
            root = Path(tmp)
            payload = {
                "schema_version": 1,
                "repair": {
                    "kind": "candidate",
                    "language": "rust",
                    "source": INITIAL_SOURCE,
                    "gate_configuration": {"disable": True},
                },
                "assumptions": [],
            }
            stdout = json.dumps({"type": "text", "text": json.dumps(payload)}) + "\n"

            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=write_candidate(root),
                initial_failure_facts=failed_result(),
                out_dir=root / "out",
                validation_runner=lambda _candidate, _round: passed_result(),
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(0, stdout, ""),
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["failure"]["kind"], "invalid_repair_response")
            self.assertIn("requires only", report["failure"]["message"])

    def test_patch_targeting_oracle_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-oracle-") as tmp:
            root = Path(tmp)
            patch = "--- a/oracle.json\n+++ b/oracle.json\n@@ -1 +1 @@\n-{}\n+{\"accept\":true}\n"
            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=write_candidate(root),
                initial_failure_facts=failed_result(),
                out_dir=root / "out",
                validation_runner=lambda _candidate, _round: passed_result(),
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    repair_jsonl({"kind": "patch", "format": "unified_diff", "content": patch}),
                    "",
                ),
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["failure"]["kind"], "invalid_repair_response")
            self.assertIn("candidate.rs", report["failure"]["message"])

    def test_validator_contract_error_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-repair-validator-") as tmp:
            root = Path(tmp)
            repaired = "pub fn add_one(value: i32) -> i32 { value.wrapping_add(1) }\n"
            report = ai_candidate_harness.coordinate_repairs(
                context_pack(),
                candidate_path=write_candidate(root),
                initial_failure_facts=failed_result(),
                out_dir=root / "out",
                validation_runner=lambda _candidate, _round: {"status": "green"},
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    candidate_response(repaired),
                    "",
                ),
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["failure"]["kind"], "invalid_validation_result")
            self.assertFalse(report["rounds"][0]["semantic_pass"])


if __name__ == "__main__":
    unittest.main()
