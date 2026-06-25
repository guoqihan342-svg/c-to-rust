import json
import subprocess
import unittest
from pathlib import Path

from validation.tools.validate_l2_evidence_summary import validate_l2_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]


class StoreAddOneL3EvidenceTests(unittest.TestCase):
    def test_store_add_one_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "store-add-one",
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

    def test_store_add_one_records_bounded_pointer_lvalue_decisions(self) -> None:
        evidence_dir = REPO_ROOT / "validation" / "evidence" / "demo" / "auto-translation" / "store-add-one"
        cfg = self._load(evidence_dir / "l3-store-add-one-cfg.json")
        pointer_graph = self._load(evidence_dir / "l3-store-add-one-pointer-graph.json")
        plan = self._load(evidence_dir / "l3-store-add-one-auto-translation-plan.json")
        block = cfg["functions"][0]["basic_blocks"][0]

        self.assertIn("pointer_write", block["statement_kinds"])
        self.assertIn("bounded_pointer_index", block["lvalue_kinds"])
        self.assertTrue(
            any(decision["decision"] == "bounded_pointer_index" for decision in block["lvalue_decisions"])
        )
        self.assertTrue(
            any(
                decision["decision"] == "bounded_pointer_index"
                for decision in pointer_graph["pointer_decisions"]
            )
        )
        out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
        self.assertEqual(out_node["ownership_role"], "out_param")
        self.assertEqual(out_node["mutability"], "write_only")
        self.assertIn("out[0]", out_node["write_effects"])
        self.assertIn("bounded_pointer_index", out_node["boundary_decisions"])
        self.assertIn("bounded-pointer-index-write", plan["translation_summary"]["translation_rule_ids"])
        self.assertEqual(plan["translation_summary"]["unsafe_candidate_count"], 0)
        self.assertEqual(plan["translation_summary"]["unsupported_lvalue_count"], 0)
        self.assertEqual(plan["translation_summary"]["lvalue_decision_counts"]["bounded_pointer_index"], 1)
        self.assertEqual(plan["translation_summary"]["pointer_boundary_decision_counts"]["bounded_pointer_index"], 1)

    def test_store_add_one_manifest_binds_required_l3_artifacts(self) -> None:
        manifest = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "store-add-one"
            / "l3-store-add-one-evidence-manifest.json"
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
            "pointer_dependency_graph",
            "test_translation",
            "final_verification",
            "summary",
            "version_or_config_binding",
        ]:
            path = REPO_ROOT / evidence[key]["path"]
            self.assertTrue(path.exists(), f"missing {key}: {path}")

    def test_store_add_one_is_accepted_by_l2_summary_gate(self) -> None:
        report = validate_l2_evidence(REPO_ROOT / "validation" / "evidence")
        demo = next(item for item in report["slices"] if item["slice_id"] == "demo-store-add-one")

        self.assertEqual(demo["level"], "L3")
        self.assertEqual(
            demo["evidence"]["negative_diff"],
            "validation/evidence/demo/l3-store-add-one-negative-diff.json",
        )

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
