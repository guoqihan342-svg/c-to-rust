from __future__ import annotations

import unittest

from validation.tools import ai_candidate_harness


CANDIDATE_SHA = "a" * 64


def passing_payloads() -> dict[str, dict[str, object]]:
    common = {"candidate_sha256": CANDIDATE_SHA, "status": "passed"}
    return {
        "rustc": {**common, "returncode": 0},
        "generated_replay": {
            **common,
            "generated_draft_replay_pass": True,
            "replay_execution": {"status": "passed"},
        },
        "schema_diff": {**common, "first_mismatch": None},
        "negative_mutation": {**common, "mutation_detected": True},
        "unsafe_scan": dict(common),
        "unsafe_ledger": dict(common),
        "alias_contract": dict(common),
        "abi_contract": dict(common),
        "oracle_contract": dict(common),
        "final_verification": {**common, "semantic_pass": True},
    }


class AiGateFeedbackTests(unittest.TestCase):
    def extract(self, payloads: object) -> dict[str, object]:
        return ai_candidate_harness.extract_gate_failure_facts(
            payloads,
            selected_candidate_sha256=CANDIDATE_SHA,
        )

    def test_all_validator_owned_common_gates_produce_passed_repair_contract(self) -> None:
        result = self.extract(passing_payloads())

        self.assertEqual(result, {"schema_version": 1, "status": "passed", "failures": []})
        self.assertNotIn("semantic_pass", result)

    def test_missing_required_artifacts_fail_closed(self) -> None:
        result = self.extract({})

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["failures"]), 10)
        self.assertTrue(all(fact["kind"] == "artifact_missing" for fact in result["failures"]))

    def test_candidate_sha_binding_is_required_and_exact(self) -> None:
        payloads = passing_payloads()
        payloads["schema_diff"]["candidate_sha256"] = "b" * 64
        payloads["unsafe_scan"].pop("candidate_sha256")

        result = self.extract(payloads)

        by_gate = {fact["gate"]: fact for fact in result["failures"]}
        self.assertEqual(by_gate["schema_diff"]["kind"], "candidate_sha256_mismatch")
        self.assertEqual(by_gate["unsafe_scan"]["kind"], "candidate_binding_missing")

    def test_invalid_selected_sha_fails_before_gate_payloads_are_trusted(self) -> None:
        result = ai_candidate_harness.extract_gate_failure_facts(
            passing_payloads(), selected_candidate_sha256="not-a-sha"
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failures"][0]["gate"], "candidate_binding")

    def test_gate_specific_invariants_cannot_be_weakened_by_passed_status(self) -> None:
        payloads = passing_payloads()
        payloads["generated_replay"]["replay_execution"] = {"status": "failed"}
        payloads["schema_diff"]["first_mismatch"] = {"field": "return", "actual": 3}
        payloads["negative_mutation"]["mutation_detected"] = False
        payloads["final_verification"]["semantic_pass"] = False

        result = self.extract(payloads)

        kinds = {fact["gate"]: fact["kind"] for fact in result["failures"]}
        self.assertEqual(kinds["generated_replay"], "execution_not_passed")
        self.assertEqual(kinds["schema_diff"], "value_mismatch")
        self.assertEqual(kinds["negative_mutation"], "mutation_not_detected")
        self.assertEqual(kinds["final_verification"], "semantic_acceptance_missing")

    def test_structured_validator_failures_are_bounded_and_sanitized(self) -> None:
        payloads = passing_payloads()
        payloads["rustc"] = {
            "candidate_sha256": CANDIDATE_SHA,
            "status": "failed",
            "errors": [
                {
                    "code": {"code": "E0308"},
                    "message": "compile failed at C:\\Users\\Administrator\\secret\\candidate.rs " + "x" * 6_000,
                    "details": {
                        "api_key": "must-not-leak",
                        "source": "/home/runner/private/candidate.rs",
                    },
                }
                for _ in range(20)
            ],
        }

        result = self.extract(payloads)
        rustc = [fact for fact in result["failures"] if fact["gate"] == "rustc"]
        serialized = str(rustc)

        self.assertEqual(len(rustc), 2)
        self.assertTrue(all(fact["kind"] == "E0308" for fact in rustc))
        self.assertTrue(all(len(fact["message"].encode("utf-8")) <= 1_024 for fact in rustc))
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("Administrator", serialized)
        self.assertNotIn("/home/runner", serialized)
        self.assertIn("<host-path>", serialized)

    def test_passing_status_with_failure_entries_is_rejected(self) -> None:
        payloads = passing_payloads()
        payloads["unsafe_ledger"]["failures"] = [{"message": "unledgered unsafe"}]

        result = self.extract(payloads)

        failure = next(fact for fact in result["failures"] if fact["gate"] == "unsafe_ledger")
        self.assertEqual(failure["kind"], "contradictory_payload")

    def test_unknown_gate_and_malformed_payload_are_failures(self) -> None:
        payloads = passing_payloads()
        payloads["project_specific_bypass"] = {"status": "passed"}
        payloads["abi_contract"] = "passed"

        result = self.extract(payloads)
        kinds = {(fact["gate"], fact["kind"]) for fact in result["failures"]}

        self.assertIn(("common_gates", "unsupported_gate"), kinds)
        self.assertIn(("abi_contract", "malformed_payload"), kinds)


if __name__ == "__main__":
    unittest.main()
