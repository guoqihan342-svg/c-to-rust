import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validation.tools import c2rust_verifier_mcp


REPO_ROOT = Path(__file__).resolve().parents[2]


class C2RustVerifierMcpTests(unittest.TestCase):
    def test_registers_thin_scaffold_tool_metadata(self) -> None:
        tools = c2rust_verifier_mcp.tool_metadata()
        names = {tool["name"] for tool in tools}

        self.assertEqual(
            names,
            {
                "translate_slice",
                "run_oracle",
                "read_evidence",
                "coverage_matrix",
            },
        )
        for tool in tools:
            self.assertIn("description", tool)
            self.assertIn("input_schema", tool)
            self.assertIn("repo-confined", tool["description"])

    def test_read_evidence_rejects_paths_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-verifier-mcp-") as tmp:
            root = Path(tmp)
            outside = root.parent / "outside.json"
            outside.write_text("{}", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                c2rust_verifier_mcp.read_evidence(
                    {"path": "../outside.json"},
                    repo_root=root,
                )

        self.assertIn("path must not escape repository", str(raised.exception))

    def test_read_evidence_loads_repo_relative_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-verifier-mcp-") as tmp:
            root = Path(tmp)
            evidence = root / "validation/evidence/demo/result.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text(json.dumps({"status": "recorded"}), encoding="utf-8")

            result = c2rust_verifier_mcp.read_evidence(
                {"path": "validation/evidence/demo/result.json"},
                repo_root=root,
            )

        self.assertEqual(result["status"], "recorded")
        self.assertEqual(result["path"], "validation/evidence/demo/result.json")
        self.assertEqual(result["payload"], {"status": "recorded"})

    def test_translate_slice_returns_existing_migrator_command_without_running(self) -> None:
        result = c2rust_verifier_mcp.translate_slice(
            {
                "slice_spec": "validation/slice-specs/demo-store-add-one.json",
                "out_root": "target/c2rust-verifier",
                "reuse_accepted_evidence": True,
                "accepted_evidence_root": "validation/evidence",
            }
        )

        self.assertEqual(result["status"], "planned")
        self.assertFalse(result["executed"])
        self.assertIn("not a full verifier/runtime completion", result["claim_boundary"])
        self.assertIn("validation/tools/run_competition.py", result["argv"])
        self.assertIn("--slice-spec", result["argv"])
        self.assertIn("validation/slice-specs/demo-store-add-one.json", result["argv"])

    def test_run_oracle_plans_verify_phase_and_confines_paths(self) -> None:
        result = c2rust_verifier_mcp.run_oracle(
            {
                "slice_spec": "validation/slice-specs/demo-store-add-one.json",
                "out_root": "target/c2rust-verifier",
            }
        )

        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["phase"], "verify")
        self.assertFalse(result["executed"])
        self.assertIn("--proof-class", result["argv"])

        with self.assertRaises(SystemExit):
            c2rust_verifier_mcp.run_oracle({"slice_spec": "../escape.json"})

    def test_coverage_matrix_delegates_to_existing_report_builder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-verifier-mcp-") as tmp:
            root = Path(tmp)
            self._write(root / "cases/ok.rs", "// case\n")
            matrix = {
                "schema_version": 1,
                "status": "recorded",
                "claim_boundary": "unit test translator coverage matrix",
                "required_dimensions": c2rust_verifier_mcp.translator_coverage_matrix.REQUIRED_DIMENSIONS,
                "capabilities": [
                    {
                        "id": "scalar-add",
                        "status": "covered",
                        "ir_constructs": ["IrExpr::Binary"],
                        "positive_cases": [{"name": "ok", "path": "cases/ok.rs"}],
                        "negative_cases": [
                            {
                                "name": "bad",
                                "path": "cases/ok.rs",
                                "fail_closed_reason": "unit test",
                            }
                        ],
                        "dimension_status": {
                            dimension: {"status": "not_applicable", "reason": "unit test"}
                            for dimension in c2rust_verifier_mcp.translator_coverage_matrix.REQUIRED_DIMENSIONS
                        },
                    }
                ],
            }
            matrix_path = root / "validation/translator-coverage-matrix.json"
            matrix_path.parent.mkdir(parents=True)
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

            result = c2rust_verifier_mcp.coverage_matrix(
                {"matrix": "validation/translator-coverage-matrix.json"},
                repo_root=root,
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["capability_count"], 1)
        self.assertIn("not semantic acceptance evidence", result["claim_boundary"])

    def test_script_entrypoint_lists_tools_from_repo_root(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", "validation/tools/c2rust_verifier_mcp.py", "--list-tools"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("translate_slice", completed.stdout)
        self.assertIn("coverage_matrix", completed.stdout)

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
