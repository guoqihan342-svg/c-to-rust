from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from validation.tools._project_migration_harness.host_verifier_contract import (
    HOST_VERIFIER_GATE_KINDS,
)
from validation.tools._project_migration_harness.host_verifier_raw_evidence import (
    MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES,
    read_host_verifier_raw_evidence,
    validate_host_verifier_raw_evidence_reference,
    write_host_verifier_raw_evidence,
)


class ProjectMigrationHostVerifierRawEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="host-verifier-raw-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.evidence_root = "target/host-verifier-run"

    def test_each_gate_and_stream_is_content_addressed_and_reopenable(self) -> None:
        for gate_kind in HOST_VERIFIER_GATE_KINDS:
            for stream in ("stdout", "stderr"):
                with self.subTest(gate_kind=gate_kind, stream=stream):
                    data = f"{gate_kind}:{stream}".encode("ascii")
                    reference = self._write(gate_kind, stream, data)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), reference["sha256"])
                    self.assertEqual(len(data), reference["size_bytes"])
                    self.assertEqual(
                        data,
                        read_host_verifier_raw_evidence(
                            self.root, reference, gate_kind=gate_kind,
                            stream=stream, evidence_root=self.evidence_root,
                        ),
                    )

    def test_empty_output_is_valid_but_oversized_input_is_rejected(self) -> None:
        reference = self._write("project-abi", "stdout", b"")
        self.assertEqual(0, reference["size_bytes"])
        with self.assertRaisesRegex(ValueError, "byte bound"):
            self._write(
                "project-abi", "stderr",
                b"x" * (MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES + 1),
            )

    def test_unknown_fields_gate_stream_and_replay_shapes_are_rejected(self) -> None:
        reference = self._write("project-feature-cfg", "stdout", b"cfg")
        cases = (
            ({**reference, "caller_authority": True}, "schema"),
            ({**reference, "sha256": {"digest": reference["sha256"]}}, "SHA-256"),
            ({**reference, "size_bytes": True}, "size"),
        )
        for value, message in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, message):
                    validate_host_verifier_raw_evidence_reference(
                        value, gate_kind="project-feature-cfg", stream="stdout",
                    )
        with self.assertRaisesRegex(ValueError, "gate kind"):
            validate_host_verifier_raw_evidence_reference(
                reference, gate_kind="project-final", stream="stdout",
            )
        with self.assertRaisesRegex(ValueError, "stream"):
            validate_host_verifier_raw_evidence_reference(
                reference, gate_kind="project-feature-cfg", stream="combined",
            )

    def test_path_sha_size_and_expected_root_drift_are_rejected(self) -> None:
        reference = self._write("project-initialization", "stderr", b"failed")
        mutations = (
            {**reference, "path": "../" + reference["path"]},
            {**reference, "path": "/" + reference["path"]},
            {**reference, "path": reference["path"].replace("/stderr/", "/stdout/")},
            {**reference, "path": reference["path"].replace(
                "/project-initialization/", "/project-abi/",
            )},
            {**reference, "sha256": "a" * 64},
            {**reference, "size_bytes": -1},
            {**reference, "size_bytes": MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES + 1},
        )
        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_host_verifier_raw_evidence_reference(
                        value, gate_kind="project-initialization", stream="stderr",
                        evidence_root=self.evidence_root,
                    )
        with self.assertRaisesRegex(ValueError, "root binding"):
            validate_host_verifier_raw_evidence_reference(
                reference, gate_kind="project-initialization", stream="stderr",
                evidence_root="target/another-run",
            )

    def test_size_content_and_immutable_rewrite_tamper_are_rejected(self) -> None:
        data = b"original"
        reference = self._write("project-abi", "stderr", data)
        with self.assertRaisesRegex(ValueError, "content binding"):
            read_host_verifier_raw_evidence(
                self.root, {**reference, "size_bytes": len(data) + 1},
                gate_kind="project-abi", stream="stderr",
                evidence_root=self.evidence_root,
            )
        target = self.root.joinpath(*Path(reference["path"]).parts)
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "content binding"):
            read_host_verifier_raw_evidence(
                self.root, reference, gate_kind="project-abi", stream="stderr",
                evidence_root=self.evidence_root,
            )
        with self.assertRaisesRegex(ValueError, "immutable"):
            self._write("project-abi", "stderr", data)

    def test_oversized_file_is_rejected_before_reopen(self) -> None:
        data = b"x" * (MAX_HOST_VERIFIER_RAW_EVIDENCE_BYTES + 1)
        digest = hashlib.sha256(data).hexdigest()
        relative = (
            f"{self.evidence_root}/verification/host-verifier/raw/"
            f"project-abi/stdout/{digest}.bin"
        )
        target = self.root.joinpath(*Path(relative).parts)
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        reference = {"path": relative, "sha256": digest, "size_bytes": 1}
        with self.assertRaisesRegex(ValueError, "safely readable"):
            read_host_verifier_raw_evidence(
                self.root, reference, gate_kind="project-abi", stream="stdout",
                evidence_root=self.evidence_root,
            )

    def test_symlink_file_and_escape_root_are_rejected(self) -> None:
        reference = self._write("project-abi", "stdout", b"inside")
        target = self.root.joinpath(*Path(reference["path"]).parts)
        outside = self.root.parent / f"{self.root.name}-outside.bin"
        outside.write_bytes(b"inside")
        self.addCleanup(outside.unlink, missing_ok=True)
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError as error:
            if os.name != "nt":
                self.skipTest(f"symbolic links unavailable: {error}")
            self._assert_windows_junction_escape_is_rejected()
            return
        with self.assertRaisesRegex(ValueError, "safely readable"):
            read_host_verifier_raw_evidence(
                self.root, reference, gate_kind="project-abi", stream="stdout",
                evidence_root=self.evidence_root,
            )

    def _assert_windows_junction_escape_is_rejected(self) -> None:
        data = b"junction-escape"
        digest = hashlib.sha256(data).hexdigest()
        outside = self.root.parent / f"{self.root.name}-outside-directory"
        suffix = Path(
            "verification/host-verifier/raw/project-abi/stdout"
        ) / f"{digest}.bin"
        target = outside / suffix
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        junction = self.root / "junction-evidence"
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        if completed.returncode != 0:
            self.skipTest("symbolic links and directory junctions are unavailable")
        self.addCleanup(junction.rmdir)
        relative = f"junction-evidence/{suffix.as_posix()}"
        reference = {
            "path": relative, "sha256": digest, "size_bytes": len(data),
        }
        with self.assertRaisesRegex(ValueError, "safely readable"):
            read_host_verifier_raw_evidence(
                self.root, reference, gate_kind="project-abi", stream="stdout",
                evidence_root="junction-evidence",
            )

    def _write(
        self, gate_kind: str, stream: str, data: bytes,
    ) -> dict[str, object]:
        return write_host_verifier_raw_evidence(
            self.root, self.evidence_root, gate_kind=gate_kind,
            stream=stream, data=data,
        )


if __name__ == "__main__":
    unittest.main()
