import json
import subprocess
import unittest
from pathlib import Path

from validation.tools.validate_l2_evidence_summary import validate_l2_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]


class ExternalDirectCalleeL3EvidenceTests(unittest.TestCase):
    def test_external_direct_callee_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "external-direct-callee",
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

    def test_external_direct_callee_records_plan_context_and_bindings(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "external-direct-callee"
        )
        plan = self._load(evidence_dir / "l3-external-direct-callee-auto-translation-plan.json")
        cfg = self._load(evidence_dir / "l3-external-direct-callee-cfg.json")
        context_pack = self._load(evidence_dir / "l3-external-direct-callee-context-pack.json")

        statement_kinds = {
            kind
            for block in cfg["functions"][0]["basic_blocks"]
            for kind in block["statement_kinds"]
        }
        call_expressions = plan["translation_summary"]["call_expressions"]
        contexts = {item["statement_context"] for item in call_expressions}
        external_callee = plan["translation_summary"]["external_direct_callees"][0]

        self.assertIn("call_expression", statement_kinds)
        self.assertIn("bounded-call-expression", plan["translation_summary"]["translation_rule_ids"])
        self.assertEqual(len(call_expressions), 3)
        self.assertEqual(contexts, {"declaration_initializer", "assignment", "return"})
        self.assertTrue(all(item["callee"] == "helper_add_one" for item in call_expressions))
        self.assertTrue(
            all(item["callee_signature_id"] == "sig-helper-add-one" for item in call_expressions)
        )
        self.assertEqual(external_callee["name"], "helper_add_one")
        self.assertEqual(external_callee["signature_ref"], "sig-helper-add-one")
        self.assertEqual(external_callee["stub_kind"], "compile_only")
        self.assertFalse(external_callee["semantics_verified"])
        self.assertEqual(context_pack["direct_call_edges"], call_expressions)
        self.assertEqual(context_pack["external_direct_callees"][0]["name"], "helper_add_one")
        self.assertEqual(context_pack["call_edge_to_callee_binding"][0]["callee"], "helper_add_one")

    def test_external_direct_callee_manifest_binds_required_l3_artifacts(self) -> None:
        manifest = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "external-direct-callee"
            / "l3-external-direct-callee-evidence-manifest.json"
        )
        evidence = manifest["evidence"]

        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(evidence["c_oracle"]["status"], "C_ORACLE_GENERATED")
        self.assertEqual(evidence["rust_report"]["status"], "passed")
        self.assertEqual(evidence["schema_diff"]["status"], "passed")
        self.assertTrue(evidence["negative_diff"]["mutation_detected"])
        self.assertEqual(evidence["unsafe_scan"]["status"], "passed")
        self.assertEqual(evidence["unsafe_ledger"]["status"], "passed")
        self.assertFalse(manifest["claim_boundary"]["external_callee_scope"]["semantics_verified"])
        self.assertEqual(manifest["claim_boundary"]["external_callee_scope"]["stub_kind"], "compile_only")
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

    def test_external_direct_callee_negative_diff_detects_binding_mutation(self) -> None:
        negative = self._load(
            REPO_ROOT / "validation" / "evidence" / "demo" / "l3-external-direct-callee-negative-diff.json"
        )

        self.assertTrue(negative["mutation_detected"])
        self.assertIn("external_callee_call_count", negative["mutated_fields"])
        self.assertIn("external_callee_bindings", negative["compared_fields"])

    def test_external_direct_callee_is_accepted_by_l2_summary_gate(self) -> None:
        report = validate_l2_evidence(REPO_ROOT / "validation" / "evidence")
        demo = next(item for item in report["slices"] if item["slice_id"] == "demo-external-direct-callee")

        self.assertEqual(demo["level"], "L3")
        self.assertEqual(
            demo["evidence"]["negative_diff"],
            "validation/evidence/demo/l3-external-direct-callee-negative-diff.json",
        )

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
