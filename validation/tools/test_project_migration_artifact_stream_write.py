from __future__ import annotations

import gc
import hashlib
from pathlib import Path
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    canonical_json_metadata,
    content_sha256,
    write_json_artifact,
)


def _measure_peak_bytes(callback) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        callback()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    gc.collect()
    return peak


class ProjectMigrationArtifactStreamWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-artifact-stream-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_content_sha256_and_stream_write_match_canonical_json_bytes(self) -> None:
        values = [
            None,
            True,
            0,
            -7,
            1.5,
            {"quoted": "line\n\"two\"\u2603", "items": [False, None, {2: "two", 1: "one"}]},
        ]

        for index, value in enumerate(values):
            with self.subTest(index=index):
                relative = f"artifacts/value-{index}.json"
                expected = canonical_json_bytes(value)
                reference = write_json_artifact(self.base, relative, value)

                self.assertEqual(expected, (self.base / relative).read_bytes())
                self.assertEqual(
                    hashlib.sha256(expected).hexdigest(),
                    canonical_json_metadata(value)[0],
                )
                self.assertEqual(
                    hashlib.sha256(expected).hexdigest(),
                    content_sha256(value),
                )
                self.assertEqual(reference["sha256"], content_sha256(value))
                self.assertEqual(reference["size_bytes"], len(expected))

    def test_stream_write_atomically_replaces_existing_file_contents(self) -> None:
        relative = "artifacts/replace.json"
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        old_payload = {"payload": "old-value" * 512}
        path.write_bytes(canonical_json_bytes(old_payload))

        new_payload = {"payload": "new"}
        expected = canonical_json_bytes(new_payload)
        reference = write_json_artifact(self.base, relative, new_payload)

        self.assertEqual(expected, path.read_bytes())
        self.assertEqual(reference["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(reference["size_bytes"], len(expected))

    def test_stream_write_failure_keeps_previous_file(self) -> None:
        relative = "artifacts/failure.json"
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = canonical_json_bytes({"status": "old"})
        path.write_bytes(previous)

        def fail_after_partial_write(handle, payload):
            handle.write(b"{\n")
            raise OSError("simulated stream write failure")

        with patch(
            "validation.tools._project_migration_harness.artifacts._write_canonical_json_stream",
            side_effect=fail_after_partial_write,
        ):
            with self.assertRaises(OSError):
                write_json_artifact(self.base, relative, {"status": "new"})

        self.assertEqual(previous, path.read_bytes())

    def test_stream_write_peak_memory_is_well_below_canonical_json_bytes_for_large_string(self) -> None:
        payload = {"payload": "x" * (8 * 1024 * 1024)}
        relative = "artifacts/large.json"

        bytes_peak = _measure_peak_bytes(lambda: canonical_json_bytes(payload))
        stream_peak = _measure_peak_bytes(
            lambda: write_json_artifact(self.base, relative, payload)
        )

        self.assertEqual(canonical_json_bytes(payload), (self.base / relative).read_bytes())
        self.assertEqual(content_sha256(payload), canonical_json_metadata(payload)[0])
        self.assertLess(stream_peak, 2 * 1024 * 1024)
        self.assertLess(stream_peak * 4, bytes_peak)


if __name__ == "__main__":
    unittest.main()
