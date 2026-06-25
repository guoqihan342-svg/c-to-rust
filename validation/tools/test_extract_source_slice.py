import hashlib
import importlib.util
import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR = REPO_ROOT / "validation" / "tools" / "extract_source_slice.py"


def load_extractor_module():
    spec = importlib.util.spec_from_file_location("extract_source_slice_under_test", EXTRACTOR)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load extract_source_slice module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtractSourceSliceTests(unittest.TestCase):
    def test_generates_slice_spec_from_real_c_source_span(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-slice-test-") as tmp:
            root = Path(tmp)
            src = root / "src" / "sample.c"
            src.parent.mkdir()
            src.write_text(
                textwrap.dedent(
                    """
                    /* fake ignored body: int add_one(int value) { return 99; } */
                    static const char *ignored = "{ not a function brace }";

                    int helper(int value) {
                        return value - 1;
                    }

                    int add_one(int value) {
                        return value + 1;
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            module = load_extractor_module()
            spec = module.generate_slice_spec(
                repo_root=root,
                source_file=Path("src/sample.c"),
                function_name="add_one",
                target_id="unit",
                slice_id="real-add-one",
                source_commit="unit-commit",
                compiler_command_source="compile_commands.json",
                include_paths=["include"],
                defines=["UNIT=1"],
            )

            self.assertEqual(spec["target_id"], "unit")
            self.assertEqual(spec["slice_id"], "real-add-one")
            self.assertEqual(spec["status"], "draft")
            self.assertEqual(spec["function_name"], "add_one")
            self.assertEqual(spec["source"]["source_root"], str(root.resolve()))
            self.assertEqual(spec["source"]["source_commit"], "unit-commit")
            self.assertEqual(spec["source"]["source_file_hashes"]["src/sample.c"], hashlib.sha256(src.read_bytes()).hexdigest())
            self.assertEqual(spec["c_boundary"]["files"][0]["path"], "src/sample.c")
            self.assertEqual(spec["c_boundary"]["files"][0]["role"], "source")
            self.assertEqual(spec["c_boundary"]["signatures"][0]["function"], "add_one")
            self.assertEqual(spec["c_boundary"]["signatures"][0]["source_span"]["file"], "src/sample.c")
            self.assertEqual(spec["c_boundary"]["signatures"][0]["source_span"]["line_start"], 8)
            self.assertEqual(spec["c_boundary"]["signatures"][0]["source_span"]["line_end"], 10)
            self.assertIn("int add_one(int value)", spec["c_source"])
            self.assertNotIn("return 99", spec["c_source"])
            self.assertEqual(spec["build_profile"]["compiler_command_source"], "compile_commands.json")
            self.assertEqual(spec["build_profile"]["include_paths"], ["include"])
            self.assertEqual(spec["build_profile"]["defines"], ["UNIT=1"])
            self.assertEqual(spec["build_profile"]["preprocessing_mode"], "manual_flags")
            self.assertEqual(spec["build_profile"]["clang_type_extraction"]["available"], False)
            self.assertIn("syntax-indexed", spec["build_profile"]["clang_type_extraction"]["diagnostics"][0])
            self.assertEqual(spec["rust_boundary"]["public_api"][0]["boundary_kind"], "internal_ffi")

    def test_cli_writes_generated_slice_spec_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-slice-cli-test-") as tmp:
            root = Path(tmp)
            src = root / "math.c"
            out = root / "slice.json"
            src.write_text("int add_one(int value) { return value + 1; }\n", encoding="utf-8")

            subprocess.run(
                [
                    "python",
                    str(EXTRACTOR),
                    "--repo-root",
                    str(root),
                    "--source-file",
                    "math.c",
                    "--function",
                    "add_one",
                    "--target-id",
                    "unit",
                    "--slice-id",
                    "real-add-one",
                    "--source-commit",
                    "unit-commit",
                    "--compiler-command-source",
                    "compile_commands.json",
                    "--out",
                    str(out),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            spec = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(spec["function_name"], "add_one")
            self.assertEqual(spec["c_boundary"]["signatures"][0]["source_span"]["line_start"], 1)
            self.assertEqual(spec["c_boundary"]["signatures"][0]["source_span"]["line_end"], 1)
            self.assertEqual(spec["source"]["source_file_hashes"]["math.c"], hashlib.sha256(src.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
