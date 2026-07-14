from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts import candidate_cache
from validation.tools.ai_candidate_cache_test_support import (
    CandidateCacheKeyMixin,
    context_pack,
    response,
)


class AiCandidateCacheExecutionTests(CandidateCacheKeyMixin, unittest.TestCase):
    def test_provider_failure_does_not_create_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-failure-") as tmp:
            root = Path(tmp)
            calls = 0

            def timeout_provider(
                _argv: list[str],
                _timeout: int,
            ) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(
                    124,
                    "",
                    "",
                    timed_out=True,
                )

            manifest = ai_candidate_harness.generate_candidate(
                context_pack(root, "cache-timeout"),
                out_dir=root / "out",
                cache_root=root / "cache",
                runner=timeout_provider,
            )

            self.assertEqual(1, calls)
            self.assertEqual("blocked", manifest["status"])
            self.assertEqual(1, manifest["provider_invocations"])
            self.assertEqual("miss", manifest["cache"]["status"])
            self.assertEqual([], list((root / "cache").rglob("entry.json")))

    def test_same_key_provider_generation_is_single_flight(self) -> None:
        with tempfile.TemporaryDirectory(prefix="candidate-cache-single-flight-") as tmp:
            root = Path(tmp)
            context = context_pack(root)
            calls = 0
            calls_lock = threading.Lock()

            def provider(
                _argv: list[str],
                _timeout: int,
            ) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                with calls_lock:
                    calls += 1
                time.sleep(0.05)
                return ai_candidate_harness.ProviderExecution(0, response(), "")

            def generate(index: int) -> dict[str, object]:
                return ai_candidate_harness.generate_candidate(
                    context,
                    out_dir=root / f"out-{index}",
                    cache_root=root / "cache",
                    runner=provider,
                )

            with ThreadPoolExecutor(max_workers=4) as executor:
                manifests = list(executor.map(generate, range(4)))

            self.assertEqual(1, calls)
            self.assertEqual(
                1,
                sum(item["provider_invocations"] for item in manifests),
            )
            self.assertEqual(
                3,
                sum(item["cache"]["status"] == "hit" for item in manifests),
            )

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
