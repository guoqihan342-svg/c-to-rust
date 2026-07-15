from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_symbol_model import (
    build_native_symbol_candidate,
    render_native_symbol_prompt,
    validate_native_symbol_candidate,
)
from validation.tools.project_migration_native_symbol_test_support import (
    NativeSymbolTestCase,
)


class NativeSymbolModelTests(NativeSymbolTestCase):
    def test_prompt_and_candidate_keep_ai_attribution_bounded(self) -> None:
        prompt = render_native_symbol_prompt(self.symbol_context)
        result = self.symbol_candidate()

        self.assertEqual(1, prompt.count('"link_name": "alpha_open"'))
        self.assertNotIn("/private", prompt)
        self.assertEqual("candidate", result["status"])
        self.assertEqual(2, result["native_assignment_count"])
        self.assertEqual(1, result["runtime_assignment_count"])
        self.assertEqual(0, result["defer_count"])
        self.assertFalse(result["claim_boundary"]["symbol_assignments_resolved"])
        self.assertFalse(result["claim_boundary"]["native_exports_verified"])
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertEqual(
            result, validate_native_symbol_candidate(result, self.symbol_context),
        )

    def test_missing_duplicate_and_unknown_symbol_assignments_block(self) -> None:
        base = self.response()
        cases = []
        missing = copy.deepcopy(base)
        missing["assignments"].pop()
        cases.append(("missing", missing))
        duplicate = copy.deepcopy(base)
        duplicate["assignments"][1] = copy.deepcopy(duplicate["assignments"][0])
        cases.append(("duplicate", duplicate))
        unknown = copy.deepcopy(base)
        unknown["assignments"][0]["symbol_id"] = "native-symbol-unknown"
        cases.append(("unknown", unknown))
        for name, response in cases:
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "coverage|symbol_invalid",
            ):
                build_native_symbol_candidate(self.symbol_context, response)

    def test_provider_kind_and_requirement_pairing_fail_closed(self) -> None:
        cases = []
        runtime_with_requirement = self.response()
        runtime_with_requirement["assignments"][2]["requirement_id"] = (
            self.symbol_context["providers"][0]["requirement_id"]
        )
        cases.append(("runtime-requirement", runtime_with_requirement))
        unknown_requirement = self.response()
        unknown_requirement["assignments"][0]["requirement_id"] = (
            "native-link-requirement-unknown"
        )
        cases.append(("unknown-requirement", unknown_requirement))
        for name, response in cases:
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "provider_invalid",
            ):
                build_native_symbol_candidate(self.symbol_context, response)

        deferred_context = copy.deepcopy(self.symbol_context)
        deferred_provider = deferred_context["providers"][0]
        deferred_provider.update({
            "strategy": "defer", "rustc_link_name": None,
            "rustc_link_kind": None,
        })
        deferred_context["context_sha256"] = content_sha256({
            key: item for key, item in deferred_context.items()
            if key != "context_sha256"
        })
        response = self.response()
        response["context_sha256"] = deferred_context["context_sha256"]
        assigned_id = deferred_provider["requirement_id"]
        assignment = next(
            item for item in response["assignments"]
            if item["requirement_id"] == assigned_id
        )
        with self.assertRaisesRegex(ValueError, "provider_invalid"):
            build_native_symbol_candidate(deferred_context, response)

    def test_defer_is_a_candidate_not_a_resolution_claim(self) -> None:
        result = build_native_symbol_candidate(
            self.symbol_context, self.response(beta_kind="defer"),
        )
        self.assertEqual(1, result["defer_count"])
        self.assertFalse(result["claim_boundary"]["symbol_assignments_resolved"])
        forged = self.response()
        forged["resolved"] = True
        with self.assertRaisesRegex(ValueError, "schema_invalid"):
            build_native_symbol_candidate(self.symbol_context, forged)

    def test_candidate_count_and_content_hash_tamper_block(self) -> None:
        candidate = self.symbol_candidate()
        count_tamper = copy.deepcopy(candidate)
        count_tamper["native_assignment_count"] += 1
        with self.assertRaisesRegex(ValueError, "summary_invalid"):
            validate_native_symbol_candidate(count_tamper, self.symbol_context)
        hash_tamper = copy.deepcopy(candidate)
        hash_tamper["candidate_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "sha256_drift"):
            validate_native_symbol_candidate(hash_tamper, self.symbol_context)


if __name__ == "__main__":
    unittest.main()
