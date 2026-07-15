from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness import (
    clang_raw_output_evidence as subject,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError

PLAN = "a" * 64
UNIT = "translation-unit"


class ProjectMigrationClangRawOutputEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="clang-raw-output-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out_root = self.root / "target" / "run"
        self.database = self.out_root / "state" / "project.sqlite3"
        self.database.parent.mkdir(parents=True)

    def test_ast_and_layout_raw_bytes_round_trip_after_ledger_reopen(self) -> None:
        cases = (
            ("clang-ast", b'{"kind":"TranslationUnitDecl"}\xff\x00', b"warning\r\n"),
            ("clang-record-layout", b"layout\r\n", b"diagnostic\xff\x00"),
        )
        for gate_kind, stdout, stderr in cases:
            with self.subTest(gate_kind=gate_kind):
                references = subject.write_clang_raw_outputs(
                    self.out_root, "target/run", gate_kind=gate_kind,
                    plan_sha256=PLAN, unit_id=UNIT,
                    stdout=stdout, stderr=stderr,
                )
                reopened = subject.read_clang_raw_outputs(
                    self.database, references, gate_kind=gate_kind,
                    plan_sha256=PLAN, unit_id=UNIT,
                )
                self.assertEqual({"stdout": stdout, "stderr": stderr}, reopened)
                for stream, data in reopened.items():
                    reference = references[f"{stream}_ref"]
                    self.assertEqual(hashlib.sha256(data).hexdigest(), reference["sha256"])
                    self.assertIn(f"/{gate_kind}/{stream}/", reference["path"])

    def test_gate_stream_and_reference_schema_are_strict(self) -> None:
        reference = self._write("clang-ast", "stdout", b"ast")
        with self.assertRaisesRegex(ValueError, "gate"):
            self._write("cargo-check", "stdout", b"bad")
        with self.assertRaisesRegex(ValueError, "stream"):
            self._write("clang-ast", "combined", b"bad")
        for mutation in (
            {**reference, "authority": "caller"},
            {**reference, "size_bytes": True},
            {**reference, "sha256": {"digest": reference["sha256"]}},
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    subject.validate_clang_raw_output_reference(
                        mutation, gate_kind="clang-ast", stream="stdout",
                        plan_sha256=PLAN, unit_id=UNIT,
                        expected_sha256=reference["sha256"],
                    )

    def test_plan_and_translation_unit_exchange_are_rejected(self) -> None:
        pair = subject.write_clang_raw_outputs(
            self.out_root, "target/run", gate_kind="clang-ast",
            plan_sha256=PLAN, unit_id=UNIT, stdout=b"ast", stderr=b"",
        )
        for plan, unit in (("b" * 64, UNIT), (PLAN, "other-unit")):
            with self.subTest(plan=plan, unit=unit):
                with self.assertRaisesRegex(ValueError, "execution binding"):
                    subject.validate_clang_raw_output_references(
                        pair, gate_kind="clang-ast",
                        plan_sha256=plan, unit_id=unit,
                    )

    def test_path_gate_stream_hash_and_size_drift_are_rejected(self) -> None:
        data = b"original"
        reference = self._write("clang-ast", "stderr", data)
        mutations = (
            {**reference, "path": "../" + reference["path"]},
            {**reference, "path": "/" + reference["path"]},
            {**reference, "path": reference["path"].replace(
                "/clang-ast/", "/clang-record-layout/",
            )},
            {**reference, "path": reference["path"].replace(
                "/stderr/", "/stdout/",
            )},
        )
        for mutation in mutations:
            with self.subTest(path=mutation["path"]):
                with self.assertRaises(ValueError):
                    subject.validate_clang_raw_output_reference(
                        mutation, gate_kind="clang-ast", stream="stderr",
                        plan_sha256=PLAN, unit_id=UNIT,
                        expected_sha256=reference["sha256"],
                    )
        with self.assertRaisesRegex(ValueError, "binding"):
            subject.validate_clang_raw_output_reference(
                reference, gate_kind="clang-ast", stream="stderr",
                plan_sha256=PLAN, unit_id=UNIT,
                expected_sha256="a" * 64,
            )
        with self.assertRaisesRegex(LedgerError, "content binding"):
            subject.read_clang_raw_output(
                self.database, {**reference, "size_bytes": len(data) + 1},
                gate_kind="clang-ast", stream="stderr",
                plan_sha256=PLAN, unit_id=UNIT,
                expected_sha256=reference["sha256"],
            )

    def test_reference_cannot_escape_or_rebind_the_ledger_out_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "root binding"):
            subject.write_clang_raw_output(
                self.out_root, "target/another-run", gate_kind="clang-ast",
                stream="stdout", plan_sha256=PLAN, unit_id=UNIT,
                data=b"misbound",
            )
        data = b"outside"
        digest = hashlib.sha256(data).hexdigest()
        relative = Path(
            f"outside/verification/raw-output/clang/{PLAN}/"
            f"{subject.clang_raw_output_identity(PLAN, UNIT)[1]}/clang-ast/stdout"
        ) / f"{digest}.bin"
        target = self.root / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        reference = {
            "path": relative.as_posix(), "sha256": digest,
            "size_bytes": len(data),
        }
        with self.assertRaisesRegex(LedgerError, "root binding"):
            subject.read_clang_raw_output(
                self.database, reference, gate_kind="clang-ast",
                stream="stdout", plan_sha256=PLAN, unit_id=UNIT,
                expected_sha256=digest,
            )
        wrong_database = self.out_root / "other-state" / "project.sqlite3"
        with self.assertRaisesRegex(LedgerError, "fixed ledger state root"):
            subject.read_clang_raw_output(
                wrong_database, reference, gate_kind="clang-ast",
                stream="stdout", plan_sha256=PLAN, unit_id=UNIT,
                expected_sha256=digest,
            )

    def test_link_escape_or_equivalent_path_escape_is_rejected(self) -> None:
        data = b"inside"
        reference = self._write("clang-ast", "stdout", data)
        target = self._target(reference)
        outside = self.root.parent / f"{self.root.name}-outside.bin"
        outside.write_bytes(data)
        self.addCleanup(outside.unlink, missing_ok=True)
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError:
            if os.name != "nt":
                raise
            escaped = {**reference, "path": reference["path"].replace(
                "target/run/", "outside/", 1,
            )}
            with self.assertRaisesRegex(LedgerError, "root binding"):
                subject.read_clang_raw_output(
                    self.database, escaped, gate_kind="clang-ast",
                    stream="stdout", plan_sha256=PLAN, unit_id=UNIT,
                    expected_sha256=reference["sha256"],
                )
            return
        with self.assertRaisesRegex(LedgerError, "safely readable"):
            subject.read_clang_raw_output(
                self.database, reference, gate_kind="clang-ast",
                stream="stdout", plan_sha256=PLAN, unit_id=UNIT,
                expected_sha256=reference["sha256"],
            )

    def test_content_hash_tamper_and_nonimmutable_rewrite_are_rejected(self) -> None:
        data = b"original"
        reference = self._write("clang-record-layout", "stderr", data)
        self._target(reference).write_bytes(b"tampered")
        with self.assertRaisesRegex(LedgerError, "content binding"):
            subject.read_clang_raw_output(
                self.database, reference, gate_kind="clang-record-layout",
                stream="stderr", plan_sha256=PLAN, unit_id=UNIT,
                expected_sha256=reference["sha256"],
            )
        with self.assertRaisesRegex(LedgerError, "immutable"):
            self._write("clang-record-layout", "stderr", data)

    def test_ast_stream_and_record_layout_pair_limits_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "bounded byte"):
            self._write(
                "clang-ast", "stdout",
                b"x" * (subject.MAX_CLANG_AST_RAW_OUTPUT_BYTES + 1),
            )
        half = subject.MAX_CLANG_RECORD_LAYOUT_RAW_OUTPUT_BYTES // 2
        with self.assertRaisesRegex(ValueError, "parser byte"):
            subject.write_clang_raw_outputs(
                self.out_root, "target/run", gate_kind="clang-record-layout",
                plan_sha256=PLAN, unit_id=UNIT,
                stdout=b"x" * (half + 1), stderr=b"y" * half,
            )
        stdout = self._write("clang-record-layout", "stdout", b"x" * (half + 1))
        stderr = self._write("clang-record-layout", "stderr", b"y" * half)
        pair = {
            "schema_version": 1, "gate_kind": "clang-record-layout",
            "plan_sha256": PLAN, "unit_id": UNIT,
            "unit_id_sha256": subject.clang_raw_output_identity(PLAN, UNIT)[1],
            "stdout_ref": stdout, "stdout_sha256": stdout["sha256"],
            "stderr_ref": stderr, "stderr_sha256": stderr["sha256"],
        }
        with self.assertRaisesRegex(ValueError, "parser byte"):
            subject.validate_clang_raw_output_references(
                pair, gate_kind="clang-record-layout",
                plan_sha256=PLAN, unit_id=UNIT,
            )
        with self.assertRaisesRegex(LedgerError, "reference pair"):
            subject.read_clang_raw_outputs(
                self.database, pair, gate_kind="clang-record-layout",
                plan_sha256=PLAN, unit_id=UNIT,
            )

    def test_oversized_file_is_rejected_before_reopen(self) -> None:
        data = b"x" * (subject.MAX_CLANG_RECORD_LAYOUT_RAW_OUTPUT_BYTES + 1)
        digest = hashlib.sha256(data).hexdigest()
        relative = Path(
            f"target/run/verification/raw-output/clang/{PLAN}/"
            f"{subject.clang_raw_output_identity(PLAN, UNIT)[1]}/"
            "clang-record-layout/stdout"
        ) / f"{digest}.bin"
        target = self.root / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        reference = {
            "path": relative.as_posix(), "sha256": digest, "size_bytes": 1,
        }
        with self.assertRaisesRegex(LedgerError, "safely readable"):
            subject.read_clang_raw_output(
                self.database, reference, gate_kind="clang-record-layout",
                stream="stdout", plan_sha256=PLAN, unit_id=UNIT,
                expected_sha256=digest,
            )

    def test_production_module_stays_within_line_budget(self) -> None:
        source = subject.__file__
        self.assertIsNotNone(source)
        with open(source, encoding="utf-8") as handle:
            self.assertLessEqual(sum(1 for _ in handle), 300)

    def _write(self, gate_kind: str, stream: str, data: bytes) -> dict:
        return subject.write_clang_raw_output(
            self.out_root, "target/run", gate_kind=gate_kind,
            stream=stream, plan_sha256=PLAN, unit_id=UNIT, data=data,
        )

    def _target(self, reference: dict) -> Path:
        return self.root.joinpath(*Path(reference["path"]).parts)


if __name__ == "__main__":
    unittest.main()
