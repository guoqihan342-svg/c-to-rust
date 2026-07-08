import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class TargetAbiUlongL3EvidenceTests(unittest.TestCase):
    def test_target_abi_ulong_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "target-abi-ulong-identity",
                "--slice-spec",
                "validation/slice-specs/demo-target-abi-ulong-identity.json",
                "--require-semantic-pass",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["semantic_pass"])

    def test_target_abi_ulong_binds_lp64_width_in_generated_rust(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "target-abi-ulong-identity"
        )
        final_verification = self._load(
            evidence_dir / "l3-target-abi-ulong-identity-final-verification.json"
        )
        rust_draft = (
            evidence_dir / "l3-target-abi-ulong-identity-rust-draft.rs"
        ).read_text(encoding="utf-8-sig")

        self.assertTrue(final_verification["generated_draft_semantic_pass"])
        self.assertIn("pub fn target_abi_ulong_identity(value: u64) -> u64", rust_draft)
        self.assertIn("value", rust_draft)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
