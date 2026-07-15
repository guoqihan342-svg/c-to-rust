from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.orchestrator_finalize import (
    _unique_blockers,
)


class OrchestratorFinalizeTests(unittest.TestCase):
    def test_closure_blockers_are_content_deduplicated_in_first_seen_order(self) -> None:
        shared = {"kind": "unresolved", "dependency_ids": ["a", "b"]}
        other = {"kind": "different"}

        self.assertEqual(
            _unique_blockers(
                [shared],
                [{"dependency_ids": ["a", "b"], "kind": "unresolved"}, other],
            ),
            [shared, other],
        )


if __name__ == "__main__":
    unittest.main()
