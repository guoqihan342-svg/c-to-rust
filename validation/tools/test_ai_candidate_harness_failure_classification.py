from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts import provider
from validation.tools.ai_candidate_harness_test_support import (
    ManifestSchemaAssertions,
    build_provider_context,
    minimal_spec,
)


class AiCandidateHarnessFailureClassificationTests(
    ManifestSchemaAssertions,
    unittest.TestCase,
):
    def test_oversized_provider_output_is_blocked_and_capture_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-output-bound-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = build_provider_context(spec_path)
            oversized = "x" * (ai_candidate_harness.MAX_PROVIDER_STDOUT_BYTES + 1)

            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(0, oversized, ""),
            )

            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["failure"]["kind"], "provider_output_too_large")
            response_path = root / "out" / "l3-generic-scale-ai-response.jsonl"
            self.assertEqual(response_path.stat().st_size, ai_candidate_harness.MAX_PROVIDER_STDOUT_BYTES)

    def test_provider_balance_failure_is_structured_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-balance-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = build_provider_context(spec_path)

            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    1,
                    "",
                    "Insufficient balance or no resource package. Please recharge.",
                ),
            )

            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["failure"]["kind"], "provider_insufficient_balance")
            self.assertEqual(manifest["candidates"], [])
            self.assert_manifest_schema(manifest)

    def test_timeout_is_not_retried_inside_candidate_generator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-timeout-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = build_provider_context(spec_path)
            calls = 0

            def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(124, "", "", timed_out=True)

            manifest = ai_candidate_harness.generate_candidate(context, out_dir=root / "out", runner=runner)

            self.assertEqual(calls, 1)
            self.assertEqual(manifest["failure"]["kind"], "provider_timeout")

    def test_timeout_with_provider_balance_diagnostic_uses_actionable_classification(self) -> None:
        execution = provider.ProviderExecution(
            124,
            "",
            provider.PROVIDER_BALANCE_SENTINEL,
            timed_out=True,
        )

        failure = provider.classify_provider_failure(execution)

        self.assertEqual("provider_insufficient_balance", failure["kind"])


if __name__ == "__main__":
    unittest.main()
