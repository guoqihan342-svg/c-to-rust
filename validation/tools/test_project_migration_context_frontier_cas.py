from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
)
from validation.tools._project_migration_harness.context_frontier_cas import (
    read_frontier_cas_json, write_frontier_cas_json,
)


KIND = "context-frontier-state"


class ProjectMigrationContextFrontierCasTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontier-cas-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.harness = self.base / "harness"
        self.harness.mkdir()

    def test_round_trip_uses_canonical_content_address(self) -> None:
        payload = self.payload()
        encoded = canonical_json_bytes(payload)
        digest = hashlib.sha256(encoded).hexdigest()

        reference = write_frontier_cas_json(self.harness, KIND, payload)

        self.assertEqual({
            "path": (
                f"context/frontier-cas/{KIND}/sha256/{digest[:2]}/"
                f"{digest}.json"
            ),
            "sha256": digest,
            "size_bytes": len(encoded),
        }, reference)
        self.assertEqual(encoded, self.target(reference).read_bytes())
        self.assertEqual(
            payload,
            read_frontier_cas_json(self.harness, reference, KIND),
        )

    def test_same_content_is_idempotent(self) -> None:
        payload = self.payload()
        first = write_frontier_cas_json(self.harness, KIND, payload)
        before = self.target(first).read_bytes()

        second = write_frontier_cas_json(self.harness, KIND, payload)

        self.assertEqual(first, second)
        self.assertEqual(before, self.target(second).read_bytes())

    def test_existing_different_content_at_address_is_rejected(self) -> None:
        payload = self.payload()
        reference = write_frontier_cas_json(self.harness, KIND, payload)
        self.target(reference).write_bytes(canonical_json_bytes({
            "artifact_kind": KIND,
            "frontier": ["tampered"],
        }))

        with self.assertRaisesRegex(ValueError, "drifted"):
            write_frontier_cas_json(self.harness, KIND, payload)
        with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
            read_frontier_cas_json(self.harness, reference, KIND)

    def test_writer_rejects_invalid_kind_and_payload_binding(self) -> None:
        for kind in (
            "", ".", "..", "a/b", "a\\b", "/absolute", "C:drive",
            "a" * 97,
        ):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "kind"):
                    write_frontier_cas_json(
                        self.harness, kind, {"artifact_kind": kind},
                    )
        with self.assertRaisesRegex(ValueError, "artifact_kind"):
            write_frontier_cas_json(
                self.harness, KIND, {"artifact_kind": "other-kind"},
            )

    def test_reader_rejects_ref_sha_size_and_path_tampering(self) -> None:
        reference = write_frontier_cas_json(
            self.harness, KIND, self.payload(),
        )
        other_digest = "0" * 64
        cases = {
            "ref-sha": {**reference, "sha256": other_digest},
            "ref-size": {**reference, "size_bytes": reference["size_bytes"] + 1},
            "path-sha": {
                **reference,
                "path": reference["path"].replace(
                    reference["sha256"], other_digest,
                ),
            },
            "path-prefix": {
                **reference,
                "path": reference["path"].replace(
                    f"/{reference['sha256'][:2]}/", "/ff/",
                ),
            },
        }
        for name, changed in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    read_frontier_cas_json(self.harness, changed, KIND)

    def test_reader_rejects_unsafe_paths_before_opening(self) -> None:
        reference = write_frontier_cas_json(
            self.harness, KIND, self.payload(),
        )
        relative = reference["path"]
        unsafe = (
            f"/{relative}",
            relative.replace("/", "\\"),
            f"context/../{relative}",
            f"C:/{relative}",
        )
        for path in unsafe:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "path"):
                    read_frontier_cas_json(
                        self.harness, {**reference, "path": path}, KIND,
                    )

    def test_reader_rejects_noncanonical_json(self) -> None:
        data = b'{"artifact_kind":"context-frontier-state","frontier":[]}\n'
        reference = self.install_bytes(data)

        with self.assertRaisesRegex(ValueError, "canonical JSON"):
            read_frontier_cas_json(self.harness, reference, KIND)

    def test_reader_rejects_payload_artifact_kind_mismatch(self) -> None:
        data = canonical_json_bytes({
            "artifact_kind": "other-kind",
            "frontier": [],
        })
        reference = self.install_bytes(data)

        with self.assertRaisesRegex(ValueError, "artifact_kind"):
            read_frontier_cas_json(self.harness, reference, KIND)

    def test_reader_and_writer_reject_linked_cas_path(self) -> None:
        outside = self.base / "outside"
        reference = write_frontier_cas_json(outside, KIND, self.payload())
        linked_context = self.harness / "context"
        try:
            linked_context.symlink_to(
                outside / "context", target_is_directory=True,
            )
        except OSError as error:
            if os.name != "nt":
                self.skipTest(f"directory symlinks unavailable: {error}")
            completed = subprocess.run(
                [
                    "cmd.exe", "/d", "/c", "mklink", "/J",
                    str(linked_context), str(outside / "context"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                self.skipTest("directory links are unavailable")
        self.addCleanup(linked_context.rmdir)

        with self.assertRaisesRegex(ValueError, "link"):
            read_frontier_cas_json(self.harness, reference, KIND)
        with self.assertRaisesRegex(ValueError, "link"):
            write_frontier_cas_json(self.harness, KIND, self.payload())

    @staticmethod
    def payload() -> dict:
        return {
            "schema_version": 1,
            "artifact_kind": KIND,
            "frontier": ["unit-a", "unit-b"],
        }

    def install_bytes(self, data: bytes) -> dict:
        digest = hashlib.sha256(data).hexdigest()
        relative = (
            f"context/frontier-cas/{KIND}/sha256/{digest[:2]}/"
            f"{digest}.json"
        )
        target = self.harness.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {
            "path": relative,
            "sha256": digest,
            "size_bytes": len(data),
        }

    def target(self, reference: dict) -> Path:
        return self.harness.joinpath(
            *PurePosixPath(reference["path"]).parts
        )


if __name__ == "__main__":
    unittest.main()
