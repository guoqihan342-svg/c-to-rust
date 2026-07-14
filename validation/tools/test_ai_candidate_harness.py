from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools import validate_competition_run_summary as summary_validator
from validation.tools._ai_candidate_harness_parts import provider_runtime
from validation.tools.ai_candidate_harness_test_support import (
    ManifestSchemaAssertions,
    build_provider_context,
    empty_completion_response,
    minimal_spec,
)


class AiCandidateHarnessContractResponseTests(
    ManifestSchemaAssertions,
    unittest.TestCase,
):
    def test_context_pack_redacts_source_root_and_sensitive_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-context-") as tmp:
            root = Path(tmp)
            source_root = "/mnt/c/external/project"
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(source_root)), encoding="utf-8")

            context = build_provider_context(spec_path)

            encoded = json.dumps(context)
            self.assertNotIn(source_root, encoded)
            self.assertNotIn("must-not-leak", encoded)
            self.assertIn("<host-path>", encoded)
            self.assertFalse(context["claim_boundary"]["semantic_gate"])

    def test_missing_replay_contract_blocks_before_provider_invocation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-replay-missing-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)
            calls = 0

            def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                raise AssertionError("provider must not run without a replay API contract")

            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=runner,
            )

            self.assertEqual(0, calls)
            self.assertEqual("blocked", manifest["status"])
            self.assertEqual(0, manifest["provider_invocations"])
            self.assertEqual(
                "missing",
                manifest["provider_preflight"]["replay_api_contract_status"],
            )

    def test_invalid_ai_response_is_blocked_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-invalid-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = build_provider_context(spec_path)

            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    json.dumps({"type": "text", "text": "```rust\nfn bad() {}\n```"}) + "\n",
                    "",
                ),
            )

            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["failure"]["kind"], "invalid_ai_response")
            self.assertEqual(manifest["candidates"], [])
            self.assert_manifest_schema(manifest)
            self.assertFalse(any((root / "out").glob("*-ai-rust-candidate.rs")))

    def test_empty_completion_fingerprint_requires_terminal_zero_token_finish(self) -> None:
        valid = empty_completion_response()
        self.assertTrue(provider_runtime.is_retryable_empty_completion(valid))
        for drifted in (
            valid + json.dumps({"type": "step_start", "part": {"type": "step-start"}}),
            valid.replace('"output": 0', '"output": 1'),
            valid.replace('"reasoning": 0', '"reasoning": 1'),
            valid + "not-json\n",
        ):
            self.assertFalse(provider_runtime.is_retryable_empty_completion(drifted))

    def test_response_with_extra_fields_is_blocked(self) -> None:
        payload = {
            "schema_version": 1,
            "candidate": {"language": "rust", "source": "fn value() {}", "bypass": True},
            "assumptions": [],
        }
        with self.assertRaisesRegex(ValueError, "exactly language and source"):
            ai_candidate_harness.parse_candidate_response(
                json.dumps({"type": "text", "text": json.dumps(payload)}) + "\n"
            )

    def test_source_context_failure_blocks_without_provider_invocation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-context-preflight-") as tmp:
            root = Path(tmp)
            spec = minimal_spec(str(root))
            spec.pop("c_source")
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            context = build_provider_context(spec_path)
            calls = 0

            def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                raise AssertionError("provider runner must not be called")

            out_dir = root / "out"
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=out_dir,
                runner=runner,
            )

            self.assertEqual(0, calls)
            self.assertEqual("blocked", manifest["status"])
            self.assertEqual(0, manifest["provider_invocations"])
            self.assertEqual(
                {"status": "blocked", "source_span_status": "source_span_unavailable"},
                manifest["provider_preflight"],
            )
            self.assertEqual("context_not_provider_ready", manifest["failure"]["kind"])
            self.assertEqual(b"", (out_dir / "l3-generic-scale-ai-response.jsonl").read_bytes())
            self.assert_manifest_schema(manifest)
            external_context_blocked = json.loads(json.dumps(manifest))
            external_context_blocked["provider_preflight"]["context_boundary_status"] = (
                "external_callee_source_context_incomplete"
            )
            self.assert_manifest_schema(external_context_blocked)

            validation = summary_validator.validate_fresh_ai_manifest(
                manifest,
                manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-candidate",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertEqual([], validation["reasons"])
            self.assertEqual(0, validation["invocations"])

            drifted = json.loads(json.dumps(manifest))
            drifted["provider_invocations"] = 1
            rejected = summary_validator.validate_fresh_ai_manifest(
                drifted,
                manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-candidate",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn(
                "ai_manifest_invoked_preflight_not_ready",
                rejected["reasons"],
            )

            source_status_drift = json.loads(json.dumps(manifest))
            source_status_drift["provider_preflight"]["source_span_status"] = "real_source_bound"
            source_status_rejected = summary_validator.validate_fresh_ai_manifest(
                source_status_drift,
                manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-migrator",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn(
                "ai_manifest_provider_preflight_source_status_mismatch",
                source_status_rejected["reasons"],
            )

    def test_rejected_declared_source_root_cannot_fall_back_to_inline_ready(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-rejected-root-") as tmp:
            root = Path(tmp)
            spec = minimal_spec(str(root))
            spec["source_root"] = "../outside"
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            context = build_provider_context(spec_path)
            calls = 0

            def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                raise AssertionError("provider runner must not be called")

            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=runner,
            )

            self.assertEqual(0, calls)
            self.assertEqual("rejected_untrusted_absolute_or_parent_path", context["source_root"]["status"])
            self.assertEqual("source_root_not_ready", manifest["provider_preflight"]["source_span_status"])


if __name__ == "__main__":
    unittest.main()
