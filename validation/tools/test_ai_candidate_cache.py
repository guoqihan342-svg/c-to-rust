from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import jsonschema

from validation.tools import ai_candidate_harness
from validation.tools import validate_competition_run_summary as summary_validator
from validation.tools import _auto_migrate_ai_repair as ai_repair
from validation.tools._ai_candidate_harness_parts import candidate_cache
from validation.tools._ai_candidate_harness_parts.context_security import sha256_bytes


SOURCE = "pub fn scale(value: i32) -> i32 { value.wrapping_mul(3) }\n"


def response(source: str = SOURCE) -> str:
    payload = {
        "schema_version": 1,
        "candidate": {"language": "rust", "source": source},
        "assumptions": [],
    }
    return json.dumps(
        {"type": "message.part.updated", "part": {"type": "text", "text": json.dumps(payload)}}
    ) + "\n"


def repair_response(source: str) -> str:
    payload = {
        "schema_version": 1,
        "repair": {"kind": "candidate", "language": "rust", "source": source},
        "assumptions": [],
    }
    return json.dumps(
        {"type": "message.part.updated", "part": {"type": "text", "text": json.dumps(payload)}}
    ) + "\n"


def context_pack(slice_id: str = "cache-scale") -> dict[str, object]:
    c_source = "int scale(int value) { return value * 3; }"
    return {
        "schema_version": 2,
        "target_id": "generic-target",
        "slice_id": slice_id,
        "function_name": "scale",
        "source_root": {"status": "unavailable"},
        "source": {
            "span": {
                "status": "inline_slice_spec",
                "sha256": sha256_bytes(c_source.encode("utf-8")),
                "content": c_source,
            }
        },
        "c_boundary": {
            "payload": {
                "external_direct_callees": [
                    {"name": "helper", "definition_status": "real_source_bound"}
                ]
            }
        },
        "claim_boundary": {"semantic_gate": False},
    }


class AiCandidateCacheTests(unittest.TestCase):
    def key_payload(self, context_sha: str = "a" * 64) -> dict[str, object]:
        return candidate_cache.cache_key_payload(
            context_sha,
            prompt_sha256="b" * 64,
            resolved_model="zai/glm-5.1",
            agent="c2rust-migrator",
            agent_definition_sha256="c" * 64,
            variant="max",
        )

    def test_cache_round_trip_is_reparsed_and_first_writer_wins(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate cache ") as tmp:
            root = Path(tmp)
            payload = self.key_payload()
            first_response = response().encode("utf-8")
            self.assertTrue(
                candidate_cache.store_candidate_cache(
                    root,
                    payload,
                    first_response,
                    SOURCE.encode("utf-8"),
                    ai_candidate_harness.parse_candidate_response,
                )
            )
            replacement = "pub fn scale(value: i32) -> i32 { value }\n"
            self.assertFalse(
                candidate_cache.store_candidate_cache(
                    root,
                    payload,
                    response(replacement).encode("utf-8"),
                    replacement.encode("utf-8"),
                    ai_candidate_harness.parse_candidate_response,
                )
            )

            hit, reason = candidate_cache.load_candidate_cache(
                root,
                payload,
                ai_candidate_harness.parse_candidate_response,
            )

            self.assertEqual("hit", reason)
            self.assertIsNotNone(hit)
            self.assertEqual(SOURCE.encode("utf-8"), hit.candidate_bytes)
            self.assertEqual(64, len(hit.entry_sha256))

    def test_concurrent_publish_keeps_one_complete_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-concurrent-") as tmp:
            root = Path(tmp)
            payload = self.key_payload()

            def publish(_index: int) -> bool:
                return candidate_cache.store_candidate_cache(
                    root,
                    payload,
                    response().encode("utf-8"),
                    SOURCE.encode("utf-8"),
                    ai_candidate_harness.parse_candidate_response,
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(publish, range(16)))

            self.assertEqual(1, sum(results))
            hit, reason = candidate_cache.load_candidate_cache(
                root,
                payload,
                ai_candidate_harness.parse_candidate_response,
            )
            self.assertEqual("hit", reason)
            self.assertIsNotNone(hit)
            self.assertEqual(SOURCE.encode("utf-8"), hit.candidate_bytes)

    def test_prompt_and_parse_contract_versions_change_the_key(self) -> None:
        baseline = candidate_cache.cache_key_sha256(self.key_payload())
        with mock.patch.object(candidate_cache, "PROMPT_SCHEMA_VERSION", 2):
            prompt_version_key = candidate_cache.cache_key_sha256(self.key_payload())
        with mock.patch.object(candidate_cache, "PARSE_CONTRACT_VERSION", 2):
            parse_version_key = candidate_cache.cache_key_sha256(self.key_payload())

        self.assertNotEqual(baseline, prompt_version_key)
        self.assertNotEqual(baseline, parse_version_key)
        self.assertNotEqual(prompt_version_key, parse_version_key)

    def test_key_fields_and_artifact_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-drift-") as tmp:
            root = Path(tmp)
            payload = self.key_payload()
            baseline = candidate_cache.cache_key_sha256(payload)
            variants = []
            for key, value in (
                ("context_pack_sha256", "b" * 64),
                ("prompt_sha256", "d" * 64),
                ("resolved_model", "zai/glm-next"),
                ("agent", "other-agent"),
                ("agent_definition_sha256", "e" * 64),
                ("variant", "high"),
            ):
                changed = dict(payload)
                changed[key] = value
                variants.append(candidate_cache.cache_key_sha256(changed))
            self.assertTrue(all(value != baseline for value in variants))
            self.assertEqual(len(variants), len(set(variants)))

            self.assertTrue(
                candidate_cache.store_candidate_cache(
                    root,
                    payload,
                    response().encode("utf-8"),
                    SOURCE.encode("utf-8"),
                    ai_candidate_harness.parse_candidate_response,
                )
            )
            candidate_path = next(root.rglob("candidate.rs"))
            candidate_path.write_text("pub fn drift() {}\n", encoding="utf-8")
            hit, reason = candidate_cache.load_candidate_cache(
                root,
                payload,
                ai_candidate_harness.parse_candidate_response,
            )
            self.assertIsNone(hit)
            self.assertEqual("entry_invalid", reason)

    def test_invalid_response_is_never_stored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-invalid-") as tmp:
            root = Path(tmp)
            self.assertFalse(
                candidate_cache.store_candidate_cache(
                    root,
                    self.key_payload(),
                    b"not-json\n",
                    SOURCE.encode("utf-8"),
                    ai_candidate_harness.parse_candidate_response,
                )
            )
            self.assertEqual([], list(root.rglob("entry.json")))

    def test_provider_miss_then_hit_uses_zero_new_calls_and_drift_reinvokes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-provider-") as tmp:
            root = Path(tmp)
            cache_root = root / "cache with spaces"
            calls = 0

            def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(0, response(), "")

            first = ai_candidate_harness.generate_candidate(
                context_pack(),
                out_dir=root / "first",
                cache_root=cache_root,
                runner=runner,
            )
            second = ai_candidate_harness.generate_candidate(
                context_pack(),
                out_dir=root / "second",
                cache_root=cache_root,
                runner=lambda _argv, _timeout: self.fail("cache hit invoked provider"),
            )

            self.assertEqual(1, calls)
            self.assertEqual((1, "miss", True), (
                first["provider_invocations"], first["cache"]["status"], first["cache"]["stored"]
            ))
            self.assertEqual((0, "hit"), (
                second["provider_invocations"], second["cache"]["status"]
            ))
            self.assertEqual(first["candidates"][0]["artifact"]["sha256"], second["candidates"][0]["artifact"]["sha256"])
            self.assertEqual(
                ["slice_spec", "source_spans", "direct_caller_callee_facts"],
                second["candidates"][0]["prompt_scope"],
            )
            schema = json.loads(
                (
                    Path(__file__).resolve().parents[1]
                    / "auto-translation-template"
                    / "ai-candidate-manifest.schema.json"
                ).read_text(encoding="utf-8")
            )
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
            malformed_miss_validation = summary_validator.validate_fresh_ai_manifest(
                malformed_miss,
                manifest_path=root / "first" / "l3-cache-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-migrator",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn("ai_manifest_schema_invalid", malformed_miss_validation["reasons"])
            validated = summary_validator.validate_fresh_ai_manifest(
                second,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-migrator",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertEqual([], validated["reasons"])
            self.assertEqual((0, 1), (validated["invocations"], validated["cache_hits"]))

            key_drift = json.loads(json.dumps(second))
            key_drift["cache"]["key_sha256"] = "0" * 64
            drifted = summary_validator.validate_fresh_ai_manifest(
                key_drift,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-migrator",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn("ai_manifest_cache_key_mismatch", drifted["reasons"])
            entry_drift = json.loads(json.dumps(second))
            entry_drift["cache"]["entry_sha256"] = "0" * 64
            drifted_entry = summary_validator.validate_fresh_ai_manifest(
                entry_drift,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-migrator",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn("ai_manifest_cache_entry_sha_mismatch", drifted_entry["reasons"])
            prompt_path = root / "second" / "l3-cache-scale-ai-prompt.txt"
            original_prompt = prompt_path.read_bytes()
            prompt_path.write_text("changed prompt contract\n", encoding="utf-8")
            prompt_drift = json.loads(json.dumps(second))
            prompt_drift["bindings"]["prompt"]["sha256"] = sha256_bytes(prompt_path.read_bytes())
            drifted_prompt = summary_validator.validate_fresh_ai_manifest(
                prompt_drift,
                manifest_path=root / "second" / "l3-cache-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-migrator",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
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
            repaired_source = "pub fn scale(value: i32) -> i32 { value.saturating_mul(3) }\n"
            repaired, report = ai_repair.repair_ai_candidate_after_validation(
                context_pack(),
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
                provider_runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    repair_response(repaired_source),
                    "",
                ),
            )
            self.assertEqual("candidate_ready_for_common_validation", report["status"])
            repaired_validation = summary_validator.validate_fresh_ai_manifest(
                repaired,
                manifest_path=second_dir / "l3-cache-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-migrator",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
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

            next(cache_root.rglob("candidate.rs")).write_text("pub fn drift() {}\n", encoding="utf-8")
            third = ai_candidate_harness.generate_candidate(
                context_pack(),
                out_dir=root / "third",
                cache_root=cache_root,
                runner=runner,
            )
            self.assertEqual(2, calls)
            self.assertEqual(1, third["provider_invocations"])
            self.assertEqual("miss", third["cache"]["status"])
            self.assertEqual("entry_invalid", third["cache"]["miss_reason"])
            self.assertTrue(third["cache"]["stored"])
            fourth = ai_candidate_harness.generate_candidate(
                context_pack(),
                out_dir=root / "fourth",
                cache_root=cache_root,
                runner=lambda _argv, _timeout: self.fail("recovered cache invoked provider"),
            )
            self.assertEqual(2, calls)
            self.assertEqual((0, "hit"), (
                fourth["provider_invocations"], fourth["cache"]["status"]
            ))

    def test_provider_failure_does_not_create_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-failure-") as tmp:
            root = Path(tmp)
            manifest = ai_candidate_harness.generate_candidate(
                context_pack("cache-timeout"),
                out_dir=root / "out",
                cache_root=root / "cache",
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    124,
                    "",
                    "",
                    timed_out=True,
                ),
            )
            self.assertEqual("blocked", manifest["status"])
            self.assertEqual("miss", manifest["cache"]["status"])
            self.assertEqual([], list((root / "cache").rglob("entry.json")))

    def test_same_key_provider_generation_is_single_flight(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-single-flight-") as tmp:
            root = Path(tmp)
            calls = 0
            calls_lock = threading.Lock()

            def provider(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                with calls_lock:
                    calls += 1
                time.sleep(0.05)
                return ai_candidate_harness.ProviderExecution(0, response(), "")

            def generate(index: int) -> dict[str, object]:
                return ai_candidate_harness.generate_candidate(
                    context_pack(),
                    out_dir=root / f"out-{index}",
                    cache_root=root / "cache",
                    runner=provider,
                )

            with ThreadPoolExecutor(max_workers=4) as executor:
                manifests = list(executor.map(generate, range(4)))

            self.assertEqual(1, calls)
            self.assertEqual(1, sum(item["provider_invocations"] for item in manifests))
            self.assertEqual(3, sum(item["cache"]["status"] == "hit" for item in manifests))

    @unittest.skipUnless(os.name == "nt", "Windows lock retry contract")
    def test_windows_generation_lock_retries_resource_deadlock(self) -> None:
        import msvcrt

        with tempfile.TemporaryDirectory(prefix="candidate-cache-lock-retry-") as tmp:
            attempts = 0
            real_locking = msvcrt.locking

            def flaky_locking(descriptor: int, mode: int, size: int):
                nonlocal attempts
                if mode == msvcrt.LK_NBLCK and attempts < 3:
                    attempts += 1
                    raise OSError(36, "Resource deadlock avoided")
                return real_locking(descriptor, mode, size)

            with mock.patch.object(msvcrt, "locking", side_effect=flaky_locking):
                with candidate_cache.candidate_generation_lock(
                    Path(tmp),
                    self.key_payload(),
                    timeout_seconds=1.0,
                ):
                    pass

            self.assertEqual(3, attempts)


if __name__ == "__main__":
    unittest.main()
