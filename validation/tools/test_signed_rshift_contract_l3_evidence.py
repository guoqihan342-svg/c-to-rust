import json
import subprocess
import unittest
from pathlib import Path

from validation.tools.validate_l2_evidence_summary import validate_l2_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]


class SignedRshiftContractL3EvidenceTests(unittest.TestCase):
    def test_signed_rshift_contract_auto_translation_semantic_gate_passes(self) -> None:
        result = subprocess.run(
            [
                "python",
                "-B",
                "validation/tools/validate_auto_translation_evidence.py",
                "--target-id",
                "demo",
                "--slice-id",
                "signed-rshift-contract",
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

    def test_signed_rshift_contract_binds_explicit_scalar_contract(self) -> None:
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "signed-rshift-contract"
        )
        clang_report = self._load(evidence_dir / "l3-signed-rshift-contract-clang-lowering-report.json")
        route = self._load(evidence_dir / "l3-signed-rshift-contract-route-decision.json")
        profile = self._load(evidence_dir / "l3-signed-rshift-contract-validation-profile.json")
        rust_draft = (
            evidence_dir / "l3-signed-rshift-contract-rust-draft.rs"
        ).read_text(encoding="utf-8-sig")

        runtime_preconditions = {
            item["code"]
            for item in clang_report["typed_ir_candidate"]["runtime_preconditions"]
        }
        self.assertIn("shift_count_in_range", runtime_preconditions)
        self.assertIn(
            "signed_right_shift_implementation_defined",
            runtime_preconditions,
        )
        self.assertIn(".checked_shr(", rust_draft)

        route_typed_ir = route["candidate_generation"]["typed_ir"]
        profile_typed_ir = profile["candidate_generation"]["typed_ir"]
        self.assertEqual(route_typed_ir["scalar_admission"]["status"], "covered")
        self.assertEqual(profile_typed_ir["scalar_admission"]["status"], "covered")
        self.assertEqual(
            route["scalar_ub_contract"]["c_boundary"]["signed_right_shift"],
            "explicit_implementation_defined_contract",
        )
        self.assertEqual(
            profile["scalar_ub_contract"]["c_boundary"]["signed_right_shift"],
            "explicit_implementation_defined_contract",
        )

    def test_signed_rshift_contract_manifest_binds_required_l3_artifacts(self) -> None:
        manifest = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "signed-rshift-contract"
            / "l3-signed-rshift-contract-evidence-manifest.json"
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
            "clang_lowering_report",
            "route_decision",
            "validation_profile",
            "test_translation",
            "final_verification",
            "summary",
            "version_or_config_binding",
        ]:
            path = REPO_ROOT / evidence[key]["path"]
            self.assertTrue(path.exists(), f"missing {key}: {path}")

    def test_signed_rshift_contract_negative_diff_detects_contract_mutation(self) -> None:
        negative = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "l3-signed-rshift-contract-negative-diff.json"
        )

        self.assertTrue(negative["mutation_detected"])
        self.assertIn("contract", negative["mutated_fields"])
        self.assertIn("contract", negative["compared_fields"])

    def test_signed_rshift_contract_records_fail_closed_refusal_evidence(self) -> None:
        refusal = self._load(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "demo"
            / "auto-translation"
            / "signed-rshift-contract"
            / "l3-signed-rshift-contract-refusal-evidence.json"
        )

        self.assertEqual(refusal["status"], "recorded")
        refusal_codes = {item["code"] for item in refusal["refusals"]}
        self.assertEqual(
            refusal_codes,
            {
                "missing_explicit_signed_right_shift_contract",
                "wrong_explicit_signed_right_shift_contract",
                "missing_scalar_input_domain",
            },
        )
        self.assertTrue(
            all(item["decision"] == "fail_closed" for item in refusal["refusals"])
        )

    def test_signed_rshift_contract_is_accepted_by_l2_summary_gate(self) -> None:
        report = validate_l2_evidence(REPO_ROOT / "validation" / "evidence")
        demo = next(
            item
            for item in report["slices"]
            if item["slice_id"] == "demo-signed-rshift-contract"
        )

        self.assertEqual(demo["level"], "L3")
        self.assertEqual(
            demo["evidence"]["negative_diff"],
            "validation/evidence/demo/l3-signed-rshift-contract-negative-diff.json",
        )

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
