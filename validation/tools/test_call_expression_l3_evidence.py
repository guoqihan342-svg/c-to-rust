import json
import subprocess
import unittest
from pathlib import Path

from validation.tools.validate_l2_evidence_summary import validate_l2_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]


class CallExpressionL3EvidenceTests(unittest.TestCase):
    def test_call_expression_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "call-expression",
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

    def test_call_expression_records_plan_and_context_edges(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "call-expression"
        )
        plan = self._load(evidence_dir / "l3-call-expression-auto-translation-plan.json")
        cfg = self._load(evidence_dir / "l3-call-expression-cfg.json")
        context_pack = self._load(evidence_dir / "l3-call-expression-context-pack.json")

        statement_kinds = {
            kind
            for block in cfg["functions"][0]["basic_blocks"]
            for kind in block["statement_kinds"]
        }
        call_expressions = plan["translation_summary"]["call_expressions"]
        contexts = {item["statement_context"] for item in call_expressions}

        self.assertIn("call_expression", statement_kinds)
        self.assertIn("bounded-call-expression", plan["translation_summary"]["translation_rule_ids"])
        self.assertEqual(len(call_expressions), 3)
        self.assertEqual(contexts, {"declaration_initializer", "assignment", "return"})
        self.assertEqual(context_pack["direct_call_edges"], call_expressions)
        self.assertTrue(all(item["callee"] == "call_expression_chain" for item in call_expressions))

    def test_call_expression_manifest_binds_required_l3_artifacts(self) -> None:
        manifest = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "call-expression"
            / "l3-call-expression-evidence-manifest.json"
        )
        evidence = manifest["evidence"]

        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(evidence["c_oracle"]["status"], "C_ORACLE_GENERATED")
        self.assertEqual(evidence["rust_report"]["status"], "passed")
        self.assertEqual(evidence["schema_diff"]["status"], "passed")
        self.assertTrue(evidence["negative_diff"]["mutation_detected"])
        self.assertEqual(evidence["unsafe_scan"]["status"], "passed")
        self.assertEqual(evidence["unsafe_ledger"]["status"], "passed")
        for key in [
            "slice_contract",
            "context_pack",
            "cache_metadata",
            "config_profile",
            "test_translation",
            "final_verification",
            "summary",
            "version_or_config_binding",
        ]:
            path = REPO_ROOT / evidence[key]["path"]
            self.assertTrue(path.exists(), f"missing {key}: {path}")

    def test_call_expression_negative_diff_detects_metadata_mutation(self) -> None:
        negative = self._load(
            REPO_ROOT / "validation" / "evidence" / "demo" / "l3-call-expression-negative-diff.json"
        )

        self.assertTrue(negative["mutation_detected"])
        self.assertIn("call_expression_count", negative["mutated_fields"])
        self.assertIn("call_expression_contexts", negative["compared_fields"])

    def test_call_expression_is_accepted_by_l2_summary_gate(self) -> None:
        report = validate_l2_evidence(REPO_ROOT / "validation" / "evidence")
        demo = next(item for item in report["slices"] if item["slice_id"] == "demo-call-expression")

        self.assertEqual(demo["level"], "L3")
        self.assertEqual(
            demo["evidence"]["negative_diff"],
            "validation/evidence/demo/l3-call-expression-negative-diff.json",
        )

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
