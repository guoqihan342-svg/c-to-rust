import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class WhileCountdownL3EvidenceTests(unittest.TestCase):
    def test_while_countdown_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "while-countdown-positive",
                "--slice-spec",
                "validation/slice-specs/demo-while-countdown-positive.json",
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

    def test_while_countdown_generated_rust_uses_loop_and_checked_decrement(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "while-countdown-positive"
        )
        final_verification = self._load(
            evidence_dir / "l3-while-countdown-positive-final-verification.json"
        )
        rust_draft = (
            evidence_dir / "l3-while-countdown-positive-rust-draft.rs"
        ).read_text(encoding="utf-8-sig")

        self.assertTrue(final_verification["generated_draft_semantic_pass"])
        self.assertIn("pub fn while_countdown_positive(mut value: i32) -> i32", rust_draft)
        self.assertIn("while", rust_draft)
        self.assertTrue(
            "checked_sub(1i32)" in rust_draft
            or "checked_add(!0i32)" in rust_draft
            or "checked_add(-1i32)" in rust_draft
        )

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
