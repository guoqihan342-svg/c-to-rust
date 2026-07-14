from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools import validate_competition_run_summary as summary_validator
from validation.tools._ai_candidate_harness_parts import provider
from validation.tools.ai_candidate_harness_manifest_test_support import (
    assert_generated_manifest_contract,
)
from validation.tools.ai_candidate_harness_test_support import (
    ManifestSchemaAssertions,
    build_provider_context,
    empty_completion_response,
    jsonl_response,
    minimal_spec,
)


class AiCandidateHarnessProviderGenerationTests(
    ManifestSchemaAssertions,
    unittest.TestCase,
):
    def test_generate_candidate_writes_hash_bound_nonsemantic_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-candidate-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec = minimal_spec(str(root))
            spec["c_source"] = (
                "int scale_value(int value) { /*"
                + ("context" * 2_500)
                + "*/ return value * 3; }"
            )
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            context = build_provider_context(spec_path)
            observed_argv: list[str] = []

            def runner(argv: list[str], timeout: int) -> ai_candidate_harness.ProviderExecution:
                observed_argv.extend(argv)
                self.assertEqual(timeout, 30)
                return ai_candidate_harness.ProviderExecution(
                    0,
                    jsonl_response("pub fn scale_value(value: i32) -> i32 { value.wrapping_mul(3) }\n"),
                    "",
                )

            out_dir = root / "out with spaces"
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=out_dir,
                timeout_seconds=30,
                runner=runner,
            )

            assert_generated_manifest_contract(
                self,
                manifest,
                observed_argv,
                out_dir,
                root,
            )

    def test_empty_completion_retries_once_with_same_prompt_and_binds_both_attempts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-empty-retry-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = build_provider_context(spec_path)
            calls: list[list[str]] = []
            valid_event = json.loads(
                jsonl_response(
                    "pub fn scale_value(value: i32) -> i32 { value.wrapping_mul(3) }\n"
                )
            )
            valid_event["sessionID"] = "ses_valid_second"
            valid_response = json.dumps(valid_event) + "\n"
            executions = iter(
                (
                    ai_candidate_harness.ProviderExecution(
                        0,
                        empty_completion_response("ses_empty_first"),
                        "",
                        identity_receipt={
                            "source": "opencode-session-export",
                            "session_id": "ses_empty_first",
                            "provider_id": "zai",
                            "model_id": "glm-5.1",
                            "agent": "c2rust-candidate",
                            "variant": "max",
                            "opencode_version": "1.0.0",
                            "session_export_sha256": "a" * 64,
                        },
                    ),
                    ai_candidate_harness.ProviderExecution(
                        0,
                        valid_response,
                        "",
                        identity_receipt={
                            "source": "opencode-session-export",
                            "session_id": "ses_valid_second",
                            "provider_id": "zai",
                            "model_id": "glm-5.1",
                            "agent": "c2rust-candidate",
                            "variant": "max",
                            "opencode_version": "1.0.0",
                            "session_export_sha256": "b" * 64,
                        },
                    ),
                )
            )

            def runner(argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                calls.append(list(argv))
                return next(executions)

            out_dir = root / "out"
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=out_dir,
                runner=runner,
            )

            self.assertEqual(2, len(calls))
            self.assertEqual(calls[0], calls[1])
            self.assertEqual("generated", manifest["status"])
            self.assertEqual(2, manifest["provider_invocations"])
            self.assertEqual(2, len(manifest["provider_attempts"]))
            self.assertEqual(
                "provider_empty_completion_retry",
                manifest["provider_attempts"][1]["reason"],
            )
            self.assertEqual("generated", manifest["provider_retry"]["result"])
            self.assertFalse(manifest["provider_retry"]["semantic_gate"])
            self.assertFalse(manifest["claim_boundary"]["semantic_gate"])
            self.assertEqual(
                manifest["provider_attempts"][-1]["raw_response"],
                manifest["bindings"]["raw_response"],
            )
            self.assertEqual(
                manifest["provider_attempts"][-1]["invocation_receipt"],
                manifest["bindings"]["invocation_receipt"],
            )
            for attempt in manifest["provider_attempts"]:
                self.assertIn("session_export_identity", attempt)
                for key in ("raw_response", "invocation_receipt"):
                    ref = attempt[key]
                    self.assertEqual(ref["sha256"], provider.sha256_path(out_dir / ref["path"]))
            self.assert_manifest_schema(manifest)
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
            self.assertEqual(2, validation["invocations"])
            drifted = json.loads(json.dumps(manifest))
            drifted["provider_attempts"][0]["raw_response"]["sha256"] = "0" * 64
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
                "ai_manifest_provider_attempt_response_binding_invalid",
                rejected["reasons"],
            )
            malformed = json.loads(json.dumps(manifest))
            malformed["provider_attempts"][0] = None
            rejected = summary_validator.validate_fresh_ai_manifest(
                malformed,
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
                "ai_manifest_provider_attempt_identity_invalid",
                rejected["reasons"],
            )

    def test_empty_completion_second_empty_or_invalid_remains_blocked(self) -> None:
        for label, second, expected_kind in (
            (
                "empty",
                ai_candidate_harness.ProviderExecution(
                    0, empty_completion_response("ses_empty_second"), ""
                ),
                "provider_empty_completion",
            ),
            (
                "invalid",
                ai_candidate_harness.ProviderExecution(
                    0, json.dumps({"type": "text", "text": "not-json"}) + "\n", ""
                ),
                "invalid_ai_response",
            ),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"ai-empty-{label}-"
            ) as tmp:
                root = Path(tmp)
                spec_path = root / "slice.json"
                spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
                context = build_provider_context(spec_path)
                calls = 0

                def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                    nonlocal calls
                    calls += 1
                    return (
                        ai_candidate_harness.ProviderExecution(
                            0, empty_completion_response("ses_empty_first"), ""
                        )
                        if calls == 1
                        else second
                    )

                manifest = ai_candidate_harness.generate_candidate(
                    context,
                    out_dir=root / "out",
                    runner=runner,
                )

                self.assertEqual(2, calls)
                self.assertEqual("blocked", manifest["status"])
                self.assertEqual([], manifest["candidates"])
                self.assertEqual(expected_kind, manifest["failure"]["kind"])
                self.assertEqual("blocked", manifest["provider_retry"]["result"])
                self.assert_manifest_schema(manifest)

    def test_only_exact_empty_completion_fingerprint_retries(self) -> None:
        cases = {
            "malformed": ai_candidate_harness.ProviderExecution(0, "not-json\n", ""),
            "tool": ai_candidate_harness.ProviderExecution(
                0, json.dumps({"type": "tool_use", "tool": "read"}) + "\n", ""
            ),
            "auth": ai_candidate_harness.ProviderExecution(1, "", "invalid api key"),
            "balance": ai_candidate_harness.ProviderExecution(1, "", "insufficient balance"),
            "timeout": ai_candidate_harness.ProviderExecution(124, "", "", timed_out=True),
            "nonzero": ai_candidate_harness.ProviderExecution(7, "", "failed"),
            "assistant_text": ai_candidate_harness.ProviderExecution(
                0, json.dumps({"type": "text", "text": ""}) + "\n", ""
            ),
        }
        for label, execution in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"ai-no-retry-{label}-"
            ) as tmp:
                root = Path(tmp)
                spec_path = root / "slice.json"
                spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
                context = build_provider_context(spec_path)
                calls = 0

                def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                    nonlocal calls
                    calls += 1
                    return execution

                manifest = ai_candidate_harness.generate_candidate(
                    context,
                    out_dir=root / "out",
                    runner=runner,
                )

                self.assertEqual(1, calls)
                self.assertEqual(1, manifest["provider_invocations"])
                self.assertNotIn("provider_retry", manifest)


if __name__ == "__main__":
    unittest.main()
