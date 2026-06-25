import json
import subprocess
import unittest
from pathlib import Path

from validation.tools.validate_l2_evidence_summary import validate_l2_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]


class SumI32PtrArithL3EvidenceTests(unittest.TestCase):
    def test_sum_i32_ptr_arith_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "sum-i32-ptr-arith",
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

    def test_sum_i32_ptr_arith_records_raw_and_canonical_pointer_reads(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "sum-i32-ptr-arith"
        )
        cfg = self._load(evidence_dir / "l3-sum-i32-ptr-arith-cfg.json")
        pointer_graph = self._load(evidence_dir / "l3-sum-i32-ptr-arith-pointer-graph.json")
        type_map = self._load(evidence_dir / "l3-sum-i32-ptr-arith-type-map.json")
        plan = self._load(evidence_dir / "l3-sum-i32-ptr-arith-auto-translation-plan.json")
        blocks = cfg["functions"][0]["basic_blocks"]
        statement_kinds = {kind for block in blocks for kind in block["statement_kinds"]}
        lvalue_decisions = [
            decision
            for block in blocks
            for decision in block.get("lvalue_decisions", [])
        ]

        self.assertIn("bounded_input_buffer_read", statement_kinds)
        self.assertIn("bounded_pointer_arithmetic_input_read", statement_kinds)
        self.assertTrue(
            any(
                decision["decision"] == "bounded_pointer_arithmetic_input_read"
                and decision["translation_rule_id"] == "bounded-pointer-arithmetic-input-read"
                for decision in lvalue_decisions
            )
        )
        self.assertTrue(
            any(
                decision["decision"] == "bounded_pointer_arithmetic_input_read"
                and decision["translation_rule_id"] == "bounded-pointer-arithmetic-input-read"
                for decision in pointer_graph["pointer_decisions"]
            )
        )
        values_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "values")
        out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
        self.assertEqual(values_node["kind"], "buffer")
        self.assertEqual(values_node["buffer_role"], "input")
        self.assertEqual(values_node["length_companion"], "len")
        self.assertEqual(values_node["mutability"], "read_only")
        self.assertIn("values[i]", values_node["read_effects"])
        self.assertIn("*(values + i)", values_node["read_effects"])
        self.assertIn("bounded_input_buffer", values_node["boundary_decisions"])
        self.assertIn("bounded_pointer_arithmetic_input_read", values_node["boundary_decisions"])
        self.assertIn("out[0]", out_node["write_effects"])
        values_type = next(item for item in type_map["mappings"] if item["c_name"] == "values")
        self.assertEqual(values_type["rust_type"], "&[i32]")
        self.assertIn("bounded-input-buffer-read", plan["translation_summary"]["translation_rule_ids"])
        self.assertIn(
            "bounded-pointer-arithmetic-input-read",
            plan["translation_summary"]["translation_rule_ids"],
        )
        self.assertEqual(plan["translation_summary"]["unsafe_candidate_count"], 0)

    def test_sum_i32_ptr_arith_manifest_binds_required_l3_artifacts(self) -> None:
        manifest = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "sum-i32-ptr-arith"
            / "l3-sum-i32-ptr-arith-evidence-manifest.json"
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

    def test_sum_i32_ptr_arith_is_accepted_by_l2_summary_gate(self) -> None:
        report = validate_l2_evidence(REPO_ROOT / "validation" / "evidence")
        demo = next(item for item in report["slices"] if item["slice_id"] == "demo-sum-i32-ptr-arith")

        self.assertEqual(demo["level"], "L3")
        self.assertEqual(
            demo["evidence"]["negative_diff"],
            "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json",
        )

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
