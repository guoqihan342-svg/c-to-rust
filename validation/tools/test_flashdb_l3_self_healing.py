import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validation.tools import flashdb_l3_self_healing as self_healing
from validation.tools.flashdb_l3_self_healing import main


REPO_ROOT = Path(__file__).resolve().parents[2]
C2RUST_CRC32_OUTPUT = (
    REPO_ROOT
    / "validation"
    / "evidence"
    / "flashdb"
    / "auto-translation"
    / "real-fdb-calc-crc32"
    / "l3-real-fdb-calc-crc32-c2rust-baseline-output.rs"
)


class FlashDbL3SelfHealingTests(unittest.TestCase):
    def test_default_retry_limit_is_five_repair_rounds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-self-healing-test-") as tmp:
            root = Path(tmp)
            input_path = root / "rustc.jsonl"
            input_path.write_text(
                json.dumps({"reason": "build-finished", "success": True}) + "\n",
                encoding="utf-8",
            )
            rust_check = root / "rust-check.json"
            error_events = root / "error-events.jsonl"
            patches = root / "patch-events.jsonl"
            policy = root / "self-healing-policy.json"

            argv = [
                "flashdb_l3_self_healing.py",
                "--input",
                str(input_path),
                "--rust-check",
                str(rust_check),
                "--error-events",
                str(error_events),
                "--patches",
                str(patches),
                "--policy",
                str(policy),
                "--repo-commit",
                "repo123",
                "--source-commit",
                "source123",
                "--rollback-id",
                "rollback-default",
                "--cwd",
                str(root),
                "--exit-code",
                "0",
            ]

            with patch("sys.argv", argv):
                self.assertEqual(main(), 0)

            payload = json.loads(policy.read_text(encoding="utf-8"))
            self.assertEqual(payload["retry_limit_per_root_cause"], 5)

    def test_extracts_real_c2rust_crc32_function_with_two_bounded_unsafe_sites(self) -> None:
        extraction = self_healing.extract_c2rust_function_baseline(
            C2RUST_CRC32_OUTPUT,
            function_name="fdb_calc_crc32",
            readonly_static="crc32_table",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(
            extraction["source"],
            {
                "path": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/"
                "l3-real-fdb-calc-crc32-c2rust-baseline-output.rs",
                "sha256": "7ea393d1d09f0f4f91127247599b4d91c3be3c350e70cc384902e1c8db34b316",
            },
        )
        self.assertEqual(extraction["function_name"], "fdb_calc_crc32")
        self.assertEqual(extraction["source_spans"]["readonly_static"]["line_start"], 122)
        self.assertEqual(extraction["source_spans"]["function"]["line_start"], 380)
        self.assertIn("static mut crc32_table: [uint32_t; 256]", extraction["rust"])
        self.assertIn('pub unsafe extern "C" fn fdb_calc_crc32(', extraction["rust"])
        self.assertNotIn("pub unsafe extern \"C\" fn _fdb_set_status", extraction["rust"])
        self.assertEqual(
            [finding["kind"] for finding in extraction["unsafe_scan"]["findings"]],
            ["mutable_static", "raw_pointer_len_boundary"],
        )
        self.assertEqual(extraction["unsafe_scan"]["first_party_non_test_unsafe_count"], 2)

    def test_minimal_crc32_transform_preserves_table_algorithm_and_reduces_unsafe_to_zero(self) -> None:
        extraction = self_healing.extract_c2rust_function_baseline(
            C2RUST_CRC32_OUTPUT,
            function_name="fdb_calc_crc32",
            readonly_static="crc32_table",
            repo_root=REPO_ROOT,
        )
        transformed = self_healing.transform_c2rust_crc32_baseline(extraction)

        self.assertEqual(
            [item["transform"] for item in transformed["repair_round"]["changes"]],
            ["static_mut_to_immutable", "raw_pointer_len_to_slice"],
        )
        self.assertEqual(transformed["baseline"]["sha256"], extraction["rust_sha256"])
        self.assertEqual(transformed["source"], extraction["source"])
        self.assertEqual(transformed["unsafe_scan"]["first_party_non_test_unsafe_count"], 0)
        self.assertIn("static crc32_table: [uint32_t; 256]", transformed["rust"])
        self.assertIn("pub fn fdb_calc_crc32(mut crc: uint32_t, buf: &[uint8_t])", transformed["rust"])
        self.assertIn(
            "crc32_table[((crc ^ *byte as uint32_t) & 0xff as uint32_t) as usize]",
            transformed["rust"],
        )
        self.assertEqual(
            extraction["algorithm_invariants"]["table_initializer_sha256"],
            transformed["algorithm_invariants"]["table_initializer_sha256"],
        )
        self.assertNotIn("unsafe", transformed["rust"])
        self.assertNotIn("*const ::core::ffi::c_void", transformed["rust"])

    def test_real_extracted_and_transformed_crc32_candidates_compile(self) -> None:
        rustc = shutil.which("rustc")
        if rustc is None:
            self.skipTest("rustc is not available")
        extraction = self_healing.extract_c2rust_function_baseline(
            C2RUST_CRC32_OUTPUT,
            function_name="fdb_calc_crc32",
            readonly_static="crc32_table",
            repo_root=REPO_ROOT,
        )
        transformed = self_healing.transform_c2rust_crc32_baseline(extraction)

        with tempfile.TemporaryDirectory(prefix="crc32-c2rust-function-compile-") as tmp:
            for label, source in (("baseline", extraction["rust"]), ("final", transformed["rust"])):
                source_path = Path(tmp) / f"{label}.rs"
                source_path.write_text(source, encoding="utf-8")
                result = subprocess.run(
                    [
                        rustc,
                        "--edition=2021",
                        "--crate-type=lib",
                        "--error-format=short",
                        str(source_path),
                    ],
                    cwd=tmp,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{label} failed to compile:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
                )
