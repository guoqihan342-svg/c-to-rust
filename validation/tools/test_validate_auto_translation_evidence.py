import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"


class ValidateAutoTranslationEvidenceTests(unittest.TestCase):
    def test_rejects_semantic_pass_missing_external_callee_context_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"
            source_dir = REPO_ROOT / "validation" / "evidence" / "demo" / "auto-translation" / "call-expression"
            evidence_dir = out_root / "demo" / "auto-translation" / "call-expression"
            shutil.copytree(source_dir, evidence_dir)

            spec = json.loads((REPO_ROOT / "validation" / "slice-specs" / "demo-call-expression.json").read_text())
            spec["c_boundary"]["signatures"].append(
                {
                    "id": "sig-helper-add-one",
                    "role": "external_direct_callee",
                    "function": "helper_add_one",
                    "return_type": "int",
                    "parameters": [{"name": "value", "c_type": "int"}],
                    "source_ref": "unit/helper.c#helper_add_one",
                    "signature_sha256": "helper-signature-sha",
                    "definition_status": "real_source_bound",
                    "c_source": "int helper_add_one(int value) { return value + 1; }",
                }
            )
            spec["c_boundary"]["external_direct_callees"] = [
                {
                    "name": "helper_add_one",
                    "signature_ref": "sig-helper-add-one",
                    "source_files": [{"path": "unit/helper.c", "sha256": "helper-sha"}],
                    "definition_status": "real_source_bound",
                    "stub_boundary": "compile_only",
                }
            ]
            spec_path = tmp_path / "demo-call-expression-external-callee.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("external callee", result.stderr + result.stdout)

    def test_rejects_read_write_pointer_graph_missing_alias_gate_fields(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            for key in ["alias_sets", "alias_risks", "alias_contract", "safe_boundary_preconditions"]:
                pointer_graph.pop(key, None)
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)

    def test_rejects_missing_alias_gate_in_manifest_and_final_verification(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "demo" / "auto-translation" / "copy-i32-ptr-arith"
            for file_name in [
                "l3-copy-i32-ptr-arith-evidence-manifest.json",
                "l3-copy-i32-ptr-arith-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload.get("claim_boundary", {}).pop("alias_gate", None)
                payload.pop("alias_gate", None)
                path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)

    def test_rejects_empty_alias_risk_and_noalias_precondition_for_unknown_alias(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            pointer_graph["alias_risks"] = []
            pointer_graph["safe_boundary_preconditions"] = []
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
