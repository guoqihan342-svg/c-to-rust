import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class EnumConstantL3EvidenceTests(unittest.TestCase):
    def test_enum_constant_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "enum-constant",
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

    def test_enum_constant_binds_clang_lowered_enum_literal(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "enum-constant"
        )
        clang_report = self._load(evidence_dir / "l3-enum-constant-clang-lowering-report.json")
        rust_draft = (evidence_dir / "l3-enum-constant-rust-draft.rs").read_text(
            encoding="utf-8-sig"
        )

        typed_ir = clang_report["typed_ir_candidate"]
        self.assertEqual(clang_report["lowering_report"]["status"], "lowered")
        self.assertEqual(typed_ir["status"], "generated")
        function_ir = clang_report["lowering_report"]["function_ir"]
        rhs = function_ir["body"][0]["Return"]["value"]["Binary"]["rhs"]["LitInt"]
        self.assertEqual(rhs["value"], 7)
        self.assertEqual(rhs["spelling"], "7")
        self.assertIn("return value.checked_add(7i32)", rust_draft)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
