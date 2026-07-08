import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class SparseDesignatedArrayL3EvidenceTests(unittest.TestCase):
    def test_sparse_designated_array_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "sparse-designated-array-lookup",
                "--slice-spec",
                "validation/slice-specs/demo-sparse-designated-array-lookup.json",
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

    def test_sparse_designated_array_generated_rust_binds_sparse_initializer(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "sparse-designated-array-lookup"
        )
        final_verification = self._load(
            evidence_dir / "l3-sparse-designated-array-lookup-final-verification.json"
        )
        rust_draft = (
            evidence_dir / "l3-sparse-designated-array-lookup-rust-draft.rs"
        ).read_text(encoding="utf-8-sig")

        self.assertTrue(final_verification["generated_draft_semantic_pass"])
        self.assertIn("const TABLE: [i32; 4] = [0i32, 0i32, 7i32, 0i32];", rust_draft)
        self.assertIn("pub fn sparse_designated_array_lookup(index: i32) -> i32", rust_draft)
        self.assertIn("TABLE[index as usize]", rust_draft)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
