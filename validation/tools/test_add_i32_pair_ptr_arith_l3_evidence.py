import json
import subprocess
import unittest
from pathlib import Path

from validation.tools.validate_l2_evidence_summary import validate_l2_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]


class AddI32PairPtrArithL3EvidenceTests(unittest.TestCase):
    def test_add_i32_pair_ptr_arith_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "add-i32-pair-ptr-arith",
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

    def test_add_i32_pair_ptr_arith_records_alias_gate_and_matrix(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "add-i32-pair-ptr-arith"
        )
        pointer_graph = self._load(evidence_dir / "l3-add-i32-pair-ptr-arith-pointer-graph.json")
        plan = self._load(evidence_dir / "l3-add-i32-pair-ptr-arith-auto-translation-plan.json")
        rust_report = self._load(REPO_ROOT / "validation/evidence/demo/l3-add-i32-pair-ptr-arith-rust-report.json")
        direct_diff = self._load(REPO_ROOT / "validation/evidence/demo/l3-add-i32-pair-ptr-arith-diff.json")
        negative_diff = self._load(REPO_ROOT / "validation/evidence/demo/l3-add-i32-pair-ptr-arith-negative-diff.json")

        self.assertIn("alias_sensitive_state", pointer_graph["applicability"]["triggers"])
        self.assertEqual(pointer_graph["alias_contract"]["decision"], "requires_noalias_contract")
        self.assertFalse(pointer_graph["alias_contract"]["complete_alias_safety"])
        self.assertGreaterEqual(len(pointer_graph["alias_sets"]), 2)
        self.assertTrue(
            any(set(item["members"]) == {"lhs", "out"} for item in pointer_graph["alias_sets"])
        )
        self.assertTrue(
            any(set(item["members"]) == {"rhs", "out"} for item in pointer_graph["alias_sets"])
        )
        self.assertTrue(
            any(
                item["kind"] == "noalias" and set(item["applies_to"]) == {"lhs", "out"}
                for item in pointer_graph["safe_boundary_preconditions"]
            )
        )
        self.assertTrue(
            any(
                item["kind"] == "noalias" and set(item["applies_to"]) == {"rhs", "out"}
                for item in pointer_graph["safe_boundary_preconditions"]
            )
        )
        self.assertEqual(
            plan["translation_summary"]["alias_gate"]["decision"],
            "requires_noalias_contract",
        )
        self.assertFalse(plan["translation_summary"]["alias_gate"]["complete_alias_safety"])
        self.assertIn("alias_matrix", direct_diff["compared_fields"])
        self.assertIn("safe_noalias_precondition", direct_diff["compared_fields"])
        self.assertTrue(negative_diff["mutation_detected"])
        self.assertIn(
            negative_diff["first_mismatch"]["field"],
            {"out_values", "alias_case", "alias_matrix", "safe_noalias_precondition"},
        )
        self.assertTrue(
            any(case["alias_case"] == "lhs_rhs_read_alias" for case in rust_report["cases"])
        )
        self.assertTrue(
            any(case["status"] == "rejected_overlap_risk" for case in rust_report["cases"])
        )

    def test_add_i32_pair_ptr_arith_manifest_binds_alias_claim_boundary(self) -> None:
        manifest = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "add-i32-pair-ptr-arith"
            / "l3-add-i32-pair-ptr-arith-evidence-manifest.json"
        )
        evidence = manifest["evidence"]
        alias_gate = manifest["claim_boundary"]["alias_gate"]

        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(alias_gate["decision"], "requires_noalias_contract")
        self.assertFalse(alias_gate["complete_alias_safety"])
        self.assertGreaterEqual(alias_gate["risk_count"], 2)
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
            "pointer_dependency_graph",
            "test_translation",
            "final_verification",
            "summary",
            "version_or_config_binding",
        ]:
            path = REPO_ROOT / evidence[key]["path"]
            self.assertTrue(path.exists(), f"missing {key}: {path}")

    def test_add_i32_pair_ptr_arith_is_accepted_by_l2_summary_gate(self) -> None:
        report = validate_l2_evidence(REPO_ROOT / "validation" / "evidence")
        demo = next(
            item for item in report["slices"] if item["slice_id"] == "demo-add-i32-pair-ptr-arith"
        )

        self.assertEqual(demo["level"], "L3")
        self.assertEqual(
            demo["evidence"]["negative_diff"],
            "validation/evidence/demo/l3-add-i32-pair-ptr-arith-negative-diff.json",
        )

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
