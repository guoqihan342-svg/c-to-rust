from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    persist_captured_cargo_outputs,
    read_cargo_raw_output,
    validate_cargo_raw_output_reference,
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError


class ProjectMigrationCargoRawOutputEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cargo-raw-output-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out_root = self.root / "target" / "run"
        self.database = self.out_root / "state" / "project.sqlite3"
        self.database.parent.mkdir(parents=True)

    def test_empty_output_is_content_addressed_and_reopenable(self) -> None:
        reference = self._write("stdout", b"")
        self.assertEqual(0, reference["size_bytes"])
        self.assertEqual(
            b"",
            read_cargo_raw_output(
                self.database, reference, gate_kind="cargo-check",
                stream="stdout", expected_sha256=hashlib.sha256(b"").hexdigest(),
            ),
        )

    def test_stream_path_swap_is_rejected(self) -> None:
        reference = self._write("stdout", b"bounded")
        swapped = dict(reference)
        swapped["path"] = swapped["path"].replace("/stdout/", "/stderr/")
        with self.assertRaisesRegex(ValueError, "path binding"):
            validate_cargo_raw_output_reference(
                swapped, gate_kind="cargo-check", stream="stdout",
                expected_sha256=reference["sha256"],
            )

    def test_size_and_content_tamper_are_rejected(self) -> None:
        reference = self._write("stderr", b"original")
        wrong_size = {**reference, "size_bytes": reference["size_bytes"] + 1}
        with self.assertRaisesRegex(LedgerError, "content binding"):
            read_cargo_raw_output(
                self.database, wrong_size, gate_kind="cargo-check",
                stream="stderr", expected_sha256=reference["sha256"],
            )
        target = self.root.joinpath(*Path(reference["path"]).parts)
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(LedgerError, "content binding"):
            read_cargo_raw_output(
                self.database, reference, gate_kind="cargo-check",
                stream="stderr", expected_sha256=reference["sha256"],
            )

    def test_reference_cannot_escape_to_an_ancestor_sibling(self) -> None:
        data = b"outside-only"
        digest = hashlib.sha256(data).hexdigest()
        relative = Path(
            "outside/verification/raw-output/cargo-check/stdout"
        ) / f"{digest}.bin"
        target = self.root / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        reference = {
            "path": relative.as_posix(), "sha256": digest,
            "size_bytes": len(data),
        }
        with self.assertRaisesRegex(LedgerError, "root binding"):
            read_cargo_raw_output(
                self.database, reference, gate_kind="cargo-check",
                stream="stdout", expected_sha256=digest,
            )

    def test_oversized_file_is_rejected_before_reading(self) -> None:
        data = b"x" * (1024 * 1024 + 1)
        digest = hashlib.sha256(data).hexdigest()
        relative = Path(
            "target/run/verification/raw-output/cargo-check/stdout"
        ) / f"{digest}.bin"
        target = self.root / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        reference = {
            "path": relative.as_posix(), "sha256": digest,
            "size_bytes": 1,
        }
        with self.assertRaisesRegex(LedgerError, "safely readable"):
            read_cargo_raw_output(
                self.database, reference, gate_kind="cargo-check",
                stream="stdout", expected_sha256=digest,
            )

    def test_captured_outputs_are_removed_after_persistence(self) -> None:
        stdout, stderr = "compiler-json\n", "linker-note\n"
        execution = {
            "status": "failed", "diagnostics": [],
            "checks": [{
                "command": ["cargo", "check"], "status": "failed",
                "cargo_executed": True,
                "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
                "stdout_ref": None, "stderr_ref": None,
                "_captured_stdout": stdout, "_captured_stderr": stderr,
            }],
        }
        persisted = persist_captured_cargo_outputs(
            execution, out_root=self.out_root, out_root_rel="target/run",
        )
        check = persisted["checks"][0]
        self.assertNotIn("_captured_stdout", check)
        self.assertNotIn("_captured_stderr", check)
        self.assertEqual("failed", persisted["status"])
        for stream, expected in (("stdout", stdout), ("stderr", stderr)):
            self.assertEqual(
                expected.encode(),
                read_cargo_raw_output(
                    self.database, check[f"{stream}_ref"],
                    gate_kind="cargo-check", stream=stream,
                    expected_sha256=check[f"{stream}_sha256"],
                ),
            )

    def test_missing_capture_turns_execution_into_environment_blocker(self) -> None:
        execution = {
            "status": "passed", "diagnostics": [],
            "checks": [{
                "command": ["cargo", "check"], "status": "passed",
                "cargo_executed": True, "stdout_sha256": "a" * 64,
                "stderr_sha256": "b" * 64,
            }],
        }
        persisted = persist_captured_cargo_outputs(
            execution, out_root=self.out_root, out_root_rel="target/run",
        )
        self.assertEqual("blocked", persisted["status"])
        self.assertEqual("cargo_raw_output_unavailable", persisted[
            "diagnostics"
        ][0]["code"])
        self.assertIsNone(persisted["checks"][0]["stdout_ref"])

    def _write(self, stream: str, data: bytes) -> dict:
        return write_cargo_raw_output(
            self.out_root, "target/run", gate_kind="cargo-check",
            stream=stream, data=data,
        )


if __name__ == "__main__":
    unittest.main()
