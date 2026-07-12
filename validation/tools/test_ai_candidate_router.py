from __future__ import annotations

import copy
import unittest

from validation.tools import ai_candidate_harness as router


def passing_gates(candidate_sha: str) -> dict[str, dict[str, str]]:
    return {
        gate: {"status": "passed", "candidate_sha256": candidate_sha}
        for gate in router.REQUIRED_GATES
    }


def candidate(candidate_id: str, source: str, candidate_sha: str, **metadata: object) -> dict[str, object]:
    value = {
        "candidate_id": candidate_id,
        "source": source,
        "artifact": {"sha256": candidate_sha},
        "gate_results": passing_gates(candidate_sha),
        **metadata,
    }
    if source == "opencode-ai":
        value.update(
            {
                "provider": "zai",
                "logical_model": "GLM-5.1",
                "resolved_model": "zai/glm-5.1",
                "competition_eligible": True,
                "evaluation_scope": "competition-primary",
                "agent": "c2rust-candidate",
                "variant": "max",
            }
        )
    return value


class AiCandidateRouterTests(unittest.TestCase):
    def test_ai_is_selected_before_deterministic_candidates_without_self_scoring(self) -> None:
        ai = candidate(
            "ai",
            "opencode-ai",
            "d" * 64,
            target="target-z",
            project="project-z",
            function="function-z",
            slice="slice-z",
            model="model-z",
            self_score=-1000,
        )
        typed_ir = candidate("typed", "typed-ir", "a" * 64, self_score=999999)

        result = router.route_candidates([typed_ir, ai], provider_invocations=1)

        self.assertEqual(result["selected_candidate_id"], "ai")
        self.assertEqual([item["source"] for item in result["candidate_set"]], ["opencode-ai", "typed-ir"])
        self.assertEqual(result["candidate_set"][0]["accepted_gates"], list(router.REQUIRED_GATES))
        self.assertEqual(result["selection_policy"]["ignored_ranking_fields"][-1], "self_score")

    def test_project_model_and_input_order_cannot_change_route(self) -> None:
        base = [
            candidate("baseline", "c2rust-baseline", "c" * 64),
            candidate("ai", "opencode-ai", "b" * 64),
            candidate("typed", "typed-ir", "a" * 64),
        ]
        altered = copy.deepcopy(list(reversed(base)))
        for index, item in enumerate(altered):
            item.update(
                target=f"other-{index}",
                project=f"project-{index}",
                function=f"function-{index}",
                slice=f"slice-{index}",
                model=f"model-{index}",
                self_score=10_000 - index,
            )

        first = router.route_candidates(base)
        second = router.route_candidates(altered)

        self.assertEqual(first, second)

    def test_failed_ai_retains_gate_fact_and_falls_back_to_typed_ir(self) -> None:
        ai = candidate("ai", "opencode-ai", "a" * 64)
        ai["gate_results"]["oracle"] = {
            "status": "failed",
            "candidate_sha256": "a" * 64,
        }
        typed_ir = candidate("typed", "typed-ir", "b" * 64)

        result = router.route_candidates([typed_ir, ai])

        self.assertEqual(result["selected_candidate_id"], "typed")
        rejected_ai = result["candidate_set"][0]
        self.assertEqual(rejected_ai["decision"], "rejected")
        self.assertIn(
            {"gate": "oracle", "reason": "gate_not_passed", "actual": "failed"},
            rejected_ai["rejection_facts"],
        )
        self.assertNotIn("oracle", rejected_ai["accepted_gates"])
        self.assertEqual(result["metrics"]["fallbacks_attempted"], 1)

    def test_every_gate_must_pass_and_bind_the_exact_artifact_sha(self) -> None:
        missing_alias = candidate("missing", "opencode-ai", "a" * 64)
        del missing_alias["gate_results"]["alias_abi"]
        mismatched_final = candidate("mismatch", "typed-ir", "b" * 64)
        mismatched_final["gate_results"]["final_verification"]["candidate_sha256"] = "c" * 64

        result = router.route_candidates([mismatched_final, missing_alias])

        self.assertIsNone(result["selected_candidate_id"])
        reasons = {
            (fact["gate"], fact["reason"])
            for item in result["candidate_set"]
            for fact in item["rejection_facts"]
        }
        self.assertIn(("alias_abi", "missing_or_invalid_gate_result"), reasons)
        self.assertIn(("final_verification", "gate_candidate_sha256_mismatch"), reasons)

    def test_artifact_sha_dedup_keeps_fixed_priority_source(self) -> None:
        shared_sha = "e" * 64
        result = router.route_candidates(
            [
                candidate("typed", "typed-ir", shared_sha),
                candidate("ai", "opencode-ai", shared_sha),
            ]
        )

        self.assertEqual(result["selected_candidate_id"], "ai")
        self.assertEqual(len(result["candidate_set"]), 1)
        self.assertEqual(result["deduplicated_candidates"][0]["candidate_id"], "typed")
        self.assertEqual(result["deduplicated_candidates"][0]["duplicate_of"], "ai")
        self.assertEqual(result["metrics"]["deduplicated_candidates"], 1)

    def test_legacy_handwritten_and_accepted_evidence_are_never_candidates(self) -> None:
        result = router.route_candidates(
            [
                candidate("legacy", "legacy", "a" * 64),
                candidate("hand", "handwritten", "b" * 64),
                candidate("history", "accepted-evidence", "c" * 64),
            ]
        )

        self.assertIsNone(result["selected_candidate_id"])
        self.assertTrue(all(item["decision"] == "rejected" for item in result["candidate_set"]))
        self.assertTrue(
            all(
                item["rejection_facts"][0]["reason"] == "forbidden_or_unsupported_source"
                for item in result["candidate_set"]
            )
        )
        self.assertEqual(result["metrics"]["source_rejected_candidates"], 3)

    def test_all_four_allowed_sources_have_a_fixed_schedule(self) -> None:
        inputs = [
            candidate("baseline", "c2rust-baseline", "d" * 64),
            candidate("repair", "c2rust-repair", "c" * 64),
            candidate("typed", "typed-ir", "b" * 64),
            candidate("ai", "opencode-ai", "a" * 64),
        ]
        result = router.route_candidates(inputs)

        self.assertEqual(
            [item["source"] for item in result["candidate_set"]],
            ["opencode-ai", "typed-ir", "c2rust-repair", "c2rust-baseline"],
        )

    def test_candidate_count_is_hard_bounded(self) -> None:
        inputs = [candidate(str(index), "typed-ir", f"{index + 1:064x}") for index in range(5)]
        with self.assertRaisesRegex(ValueError, "hard maximum of 4"):
            router.route_candidates(inputs)

    def test_unbounded_candidate_identity_is_rejected_without_copying_input(self) -> None:
        oversized = candidate("x" * (router.MAX_CANDIDATE_ID_BYTES + 1), "typed-ir", "a" * 64)
        with self.assertRaisesRegex(ValueError, "non-empty candidate_id"):
            router.route_candidates([oversized])

        unknown = candidate("unknown", "sensitive-" + "x" * 10_000, "b" * 64)
        result = router.route_candidates([unknown])
        encoded = repr(result)
        self.assertNotIn("sensitive-", encoded)
        self.assertLess(len(encoded), 5_000)

    def test_provider_invocation_budget_defaults_to_one_and_caps_at_two(self) -> None:
        default = router.route_candidates([], provider_invocations=1)
        self.assertEqual(default["metrics"]["provider_invocations_remaining"], 0)
        self.assertEqual(
            default["selection_policy"]["provider_invocation_budget"]["scope"],
            "initial_candidate_generation_only",
        )
        self.assertEqual(default["provider_invocations"], 1)

        expanded = router.route_candidates(
            [], provider_invocation_budget=2, provider_invocations=2
        )
        self.assertEqual(expanded["metrics"]["provider_invocation_budget"], 2)
        with self.assertRaisesRegex(ValueError, "effective invocation budget"):
            router.route_candidates([], provider_invocations=2)
        with self.assertRaisesRegex(ValueError, "hard maximum of 2"):
            router.route_candidates([], provider_invocation_budget=3)

    def test_provider_invocation_scope_policy_drift_is_rejected(self) -> None:
        result = router.route_candidates([], provider_invocations=1)
        result["selection_policy"]["provider_invocation_budget"]["scope"] = (
            "initial_generation_and_repair"
        )
        result["selection_policy_sha256"] = router.selection_policy_sha256(
            result["selection_policy"]
        )

        with self.assertRaisesRegex(ValueError, "selection policy drift"):
            router.recompute_router_metrics(result)

    def test_metrics_and_policy_hash_are_recomputable(self) -> None:
        result = router.route_candidates(
            [candidate("ai", "opencode-ai", "a" * 64)],
            provider_invocations=1,
        )

        self.assertEqual(result["metrics"], router.recompute_router_metrics(result))
        self.assertEqual(
            result["selection_policy_sha256"],
            router.selection_policy_sha256(result["selection_policy"]),
        )
        self.assertEqual(
            result["metrics"]["selection_policy_sha256"],
            result["selection_policy_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
