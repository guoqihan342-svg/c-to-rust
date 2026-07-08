import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class ScalarDivRemContractL3EvidenceTests(unittest.TestCase):
    def test_scalar_div_rem_contract_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "scalar-div-rem-contract",
                "--slice-spec",
                "validation/slice-specs/demo-scalar-div-rem-contract.json",
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

    def test_scalar_div_rem_contract_binds_runtime_preconditions(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "scalar-div-rem-contract"
        )
        final_verification = self._load(evidence_dir / "l3-scalar-div-rem-contract-final-verification.json")
        rust_draft = (evidence_dir / "l3-scalar-div-rem-contract-rust-draft.rs").read_text(
            encoding="utf-8-sig"
        )

        self.assertTrue(final_verification["generated_draft_semantic_pass"])
        self.assertIn("checked_div", rust_draft)
        self.assertIn("checked_rem", rust_draft)
        self.assertIn("division by zero", rust_draft)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
