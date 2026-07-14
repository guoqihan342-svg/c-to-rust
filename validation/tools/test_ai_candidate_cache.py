from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts import candidate_cache
from validation.tools.ai_candidate_cache_test_support import (
    CandidateCacheKeyMixin,
    SOURCE,
    response,
)


class AiCandidateCacheTests(CandidateCacheKeyMixin, unittest.TestCase):
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
        with mock.patch.object(
            candidate_cache,
            "PROMPT_SCHEMA_VERSION",
            candidate_cache.PROMPT_SCHEMA_VERSION + 1,
        ):
            prompt_version_key = candidate_cache.cache_key_sha256(self.key_payload())
        with mock.patch.object(
            candidate_cache,
            "PARSE_CONTRACT_VERSION",
            candidate_cache.PARSE_CONTRACT_VERSION + 1,
        ):
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


if __name__ == "__main__":
    unittest.main()
