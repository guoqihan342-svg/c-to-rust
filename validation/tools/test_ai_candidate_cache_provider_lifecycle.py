from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from validation.tools import _auto_migrate_ai_repair as ai_repair
from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.context_security import sha256_bytes
from validation.tools.ai_candidate_cache_test_support import (
    candidate_manifest_schema,
    context_pack,
    fresh_manifest_validation,
    repair_response,
    response,
)


class AiCandidateCacheProviderLifecycleTests(unittest.TestCase):
    def test_provider_miss_then_hit_uses_zero_new_calls_and_drift_reinvokes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-provider-") as tmp:
            root = Path(tmp)
            cache_root = root / "cache with spaces"
            context = context_pack(root)
            calls = 0

            def runner(
                _argv: list[str],
                _timeout: int,
            ) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(0, response(), "")

            first = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "first",
                agent="c2rust-migrator",
                cache_root=cache_root,
                runner=runner,
            )
            second = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "second",
                agent="c2rust-migrator",
                cache_root=cache_root,
                runner=lambda _argv, _timeout: self.fail("cache hit invoked provider"),
            )

            self.assertEqual(1, calls)
            self.assertEqual(
                {"status": "ready", "source_span_status": "inline_slice_spec"},
                first["provider_preflight"],
            )
            self.assertEqual(
                (1, "miss", True),
                (
                    first["provider_invocations"],
                    first["cache"]["status"],
                    first["cache"]["stored"],
                ),
            )
            self.assertEqual(
                (0, "hit"),
                (second["provider_invocations"], second["cache"]["status"]),
            )
            self.assertEqual(
                first["candidates"][0]["artifact"]["sha256"],
                second["candidates"][0]["artifact"]["sha256"],
            )
            self.assertEqual(
                [
                    "slice_spec",
                    "source_spans",
                    "generated_replay_api_contract",
                    "direct_caller_callee_facts",
                    "external_callee_source_blocks",
                ],
                second["candidates"][0]["prompt_scope"],
            )

            schema = candidate_manifest_schema()
            jsonschema.Draft7Validator(schema).validate(second)
            contradictory = json.loads(json.dumps(second))
            contradictory["cache"]["miss_reason"] = "entry_missing"
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft7Validator(schema).validate(contradictory)
            missing_entry = json.loads(json.dumps(second))
            missing_entry["cache"].pop("entry")
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft7Validator(schema).validate(missing_entry)

            malformed_miss = json.loads(json.dumps(first))
            malformed_miss["cache"].pop("miss_reason")
            malformed_miss["cache"].pop("stored")
            malformed_validation = fresh_manifest_validation(
                malformed_miss,
                manifest_path=root / "first" / "l3-cache-scale-ai-candidate-manifest.json",
                repo_root=root,
            )
            self.assertIn("ai_manifest_schema_invalid", malformed_validation["reasons"])
            validated = fresh_manifest_validation(
                second,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                repo_root=root,
            )
            self.assertEqual([], validated["reasons"])
            self.assertEqual((0, 1), (validated["invocations"], validated["cache_hits"]))

            key_drift = json.loads(json.dumps(second))
            key_drift["cache"]["key_sha256"] = "0" * 64
            drifted = fresh_manifest_validation(
                key_drift,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                repo_root=root,
            )
            self.assertIn("ai_manifest_cache_key_mismatch", drifted["reasons"])
            entry_drift = json.loads(json.dumps(second))
            entry_drift["cache"]["entry_sha256"] = "0" * 64
            drifted_entry = fresh_manifest_validation(
                entry_drift,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                repo_root=root,
            )
            self.assertIn("ai_manifest_cache_entry_sha_mismatch", drifted_entry["reasons"])

            prompt_path = root / "second" / "l3-cache-scale-ai-prompt.txt"
            original_prompt = prompt_path.read_bytes()
            prompt_path.write_text("changed prompt contract\n", encoding="utf-8")
            prompt_drift = json.loads(json.dumps(second))
            prompt_drift["bindings"]["prompt"]["sha256"] = sha256_bytes(
                prompt_path.read_bytes()
            )
            drifted_prompt = fresh_manifest_validation(
                prompt_drift,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                repo_root=root,
            )
            self.assertIn("ai_manifest_cache_key_mismatch", drifted_prompt["reasons"])
            prompt_path.write_bytes(original_prompt)

            second_dir = root / "second"
            canonical_draft = second_dir / "l3-cache-scale-rust-draft.rs"
            ai_candidate_harness.apply_generated_candidate(
                second,
                out_dir=second_dir,
                canonical_draft_path=canonical_draft,
            )
            repaired_source = (
                "pub fn scale(value: i32) -> i32 { value.saturating_mul(3) }\n"
            )
            repaired, report = ai_repair.repair_ai_candidate_after_validation(
                context,
                second,
                out_dir=second_dir,
                canonical_draft_path=canonical_draft,
                initial_failure_facts={
                    "schema_version": 1,
                    "status": "failed",
                    "failures": [
                        {
                            "gate": "schema_diff",
                            "kind": "value_mismatch",
                            "message": "candidate requires one bounded repair",
                        }
                    ],
                },
                validation_runner=lambda _candidate, _round: {
                    "schema_version": 1,
                    "status": "passed",
                    "failures": [],
                },
                max_rounds=1,
                opencode_command="opencode",
                resolved_model="zai/glm-5.1",
                agent="c2rust-migrator",
                variant="max",
                timeout_seconds=30,
                provider_runner=lambda _argv, _timeout: (
                    ai_candidate_harness.ProviderExecution(
                        0,
                        repair_response(repaired_source),
                        "",
                    )
                ),
            )
            self.assertEqual("candidate_ready_for_common_validation", report["status"])
            repaired_validation = fresh_manifest_validation(
                repaired,
                manifest_path=second_dir / "l3-cache-scale-ai-candidate-manifest.json",
                repo_root=root,
            )
            self.assertEqual([], repaired_validation["reasons"])
            self.assertEqual(
                (1, 1, 1),
                (
                    repaired_validation["invocations"],
                    repaired_validation["cache_hits"],
                    repaired_validation["repair_rounds"],
                ),
            )

            next(cache_root.rglob("candidate.rs")).write_text(
                "pub fn drift() {}\n",
                encoding="utf-8",
            )
            third = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "third",
                agent="c2rust-migrator",
                cache_root=cache_root,
                runner=runner,
            )
            self.assertEqual(2, calls)
            self.assertEqual(1, third["provider_invocations"])
            self.assertEqual("miss", third["cache"]["status"])
            self.assertEqual("entry_invalid", third["cache"]["miss_reason"])
            self.assertTrue(third["cache"]["stored"])
            fourth = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "fourth",
                agent="c2rust-migrator",
                cache_root=cache_root,
                runner=lambda _argv, _timeout: self.fail(
                    "recovered cache invoked provider"
                ),
            )
            self.assertEqual(2, calls)
            self.assertEqual(
                (0, "hit"),
                (fourth["provider_invocations"], fourth["cache"]["status"]),
            )


if __name__ == "__main__":
    unittest.main()
