from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools.replay_negative_mutation import mutate_key_replay_assertion
from validation.tools import test_replay_runtime_assertion as replay_support


class ReplayNegativeMutationTests(unittest.TestCase):
    def test_opaque_observable_guard_is_mutated_before_metadata_assertion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-negative-opaque-") as tmp:
            _plan, inventory, source = (
                replay_support.ReplayRuntimeAssertionTests().build_plan(Path(tmp))
            )
        first_id = inventory["assertions"][0]["assertion_id"]
        marker = f"C2R_REPLAY_ASSERT:{first_id}"

        mutated = mutate_key_replay_assertion(source)

        self.assertIsNotNone(mutated)
        original_line = next(line for line in source.splitlines() if marker in line)
        mutated_line = next(line for line in mutated.splitlines() if marker in line)
        self.assertIn(" != ", original_line)
        self.assertIn(" == ", mutated_line)
        self.assertEqual(source.count("assert_eq!"), mutated.count("assert_eq!"))
        self.assertEqual(source.count(marker), mutated.count(marker))

    def test_legacy_assertion_fallback_and_missing_assertion_fail_closed(self) -> None:
        source = "#[test]\nfn replay() { assert_eq!(candidate(), 7); }\n"
        self.assertEqual(
            mutate_key_replay_assertion(source),
            "#[test]\nfn replay() { assert_ne!(candidate(), 7); }\n",
        )
        self.assertIsNone(mutate_key_replay_assertion("fn replay() {}\n"))


if __name__ == "__main__":
    unittest.main()
