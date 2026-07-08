import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class ImplicitIntegerNoopCastL3EvidenceTests(unittest.TestCase):
    def test_implicit_integer_noop_cast_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "implicit-integer-noop-cast",
                "--slice-spec",
                "validation/slice-specs/demo-implicit-integer-noop-cast.json",
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
        self.assertTrue(payload["generated_draft_semantic_pass"])

    def test_implicit_integer_noop_cast_generated_rust_keeps_explicit_cast(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "implicit-integer-noop-cast"
        )
        final_verification = self._load(
            evidence_dir / "l3-implicit-integer-noop-cast-final-verification.json"
        )
        rust_draft = (
            evidence_dir / "l3-implicit-integer-noop-cast-rust-draft.rs"
        ).read_text(encoding="utf-8-sig")

        self.assertTrue(final_verification["generated_draft_semantic_pass"])
        self.assertIn("pub fn identity_noop(value: i32) -> i32", rust_draft)
        self.assertIn("return (value as i32);", rust_draft)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
