from __future__ import annotations

import hashlib
import math
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    canonical_json_metadata,
)


class ArtifactVerificationTests(unittest.TestCase):
    def test_streamed_canonical_metadata_matches_canonical_bytes(self) -> None:
        values = [
            None,
            True,
            0,
            -7,
            1.5,
            math.inf,
            "quoted\ntext\u2603",
            (),
            [1, {"b": "x", "a": [False, None]}],
            {2: "two", 1: "one"},
        ]

        for value in values:
            with self.subTest(value=value):
                encoded = canonical_json_bytes(value)
                self.assertEqual(
                    (hashlib.sha256(encoded).hexdigest(), len(encoded)),
                    canonical_json_metadata(value),
                )

    def test_streamed_metadata_chunks_large_strings_without_hash_drift(self) -> None:
        value = {"payload": "ab\\\"\n\u2603" * 100_000}
        encoded = canonical_json_bytes(value)

        self.assertEqual(
            (hashlib.sha256(encoded).hexdigest(), len(encoded)),
            canonical_json_metadata(value),
        )


if __name__ == "__main__":
    unittest.main()
