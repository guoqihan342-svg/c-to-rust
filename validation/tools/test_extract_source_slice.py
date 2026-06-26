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

    def test_records_same_file_global_object_dependency_from_function_body(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-slice-global-test-") as tmp:
            root = Path(tmp)
            src = root / "src" / "crc.c"
            src.parent.mkdir()
            src.write_text(
                textwrap.dedent(
                    """
                    #include <stdint.h>

                    static const uint32_t table[2] = { 0U, 1U };
                    static const uint32_t comment_only[1] = { 9U };
                    static const uint32_t string_only[1] = { 7U };

                    uint32_t calc(uint32_t value) {
                        /* comment_only[value & 0x1U] must not be a dependency */
                        const char *debug = "string_only[value & 0x1U]";
                        return table[value & 0x1U] ^ (uint32_t)debug[0];
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            module = load_extractor_module()
            spec = module.generate_slice_spec(
                repo_root=root,
                source_file=Path("src/crc.c"),
                function_name="calc",
                target_id="unit",
                slice_id="real-calc",
                source_commit="unit-commit",
            )

            dependencies = spec["c_boundary"]["direct_dependencies"]
            globals_by_name = {
                dependency["name"]: dependency
                for dependency in dependencies
                if dependency["kind"] == "global"
            }
            self.assertIn("table", globals_by_name)
            self.assertNotIn("comment_only", globals_by_name)
            self.assertNotIn("string_only", globals_by_name)
            table = globals_by_name["table"]
            self.assertEqual(table["source"], "extracted_function_body_reference")
            self.assertEqual(table["definition_status"], "same_file_top_level_declared")
            self.assertEqual(table["source_span"]["file"], "src/crc.c")
            self.assertEqual(table["source_span"]["line_start"], 3)
            self.assertEqual(table["source_span"]["line_end"], 3)
            self.assertIn("sha256", table)

    def test_does_not_record_global_dependency_when_parameter_shadows_name(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-slice-shadow-test-") as tmp:
            root = Path(tmp)
            src = root / "src" / "shadow.c"
            src.parent.mkdir()
            src.write_text(
                textwrap.dedent(
                    """
                    #include <stdint.h>

                    static const uint32_t table[2] = { 0U, 1U };

                    uint32_t calc(uint32_t table) {
                        return table + 1U;
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            module = load_extractor_module()
            spec = module.generate_slice_spec(
                repo_root=root,
                source_file=Path("src/shadow.c"),
                function_name="calc",
                target_id="unit",
                slice_id="real-shadow",
                source_commit="unit-commit",
            )

            self.assertFalse(
                any(
                    dependency["kind"] == "global" and dependency["name"] == "table"
                    for dependency in spec["c_boundary"]["direct_dependencies"]
                )
            )

    def test_does_not_record_global_dependency_when_local_variable_shadows_name(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-slice-local-shadow-test-") as tmp:
            root = Path(tmp)
            src = root / "src" / "local_shadow.c"
            src.parent.mkdir()
            src.write_text(
                textwrap.dedent(
                    """
                    #include <stdint.h>

                    static const uint32_t table[2] = { 0U, 1U };

                    uint32_t calc(uint32_t value) {
                        uint32_t table = value + 1U;
                        return table;
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            module = load_extractor_module()
            spec = module.generate_slice_spec(
                repo_root=root,
                source_file=Path("src/local_shadow.c"),
                function_name="calc",
                target_id="unit",
                slice_id="real-local-shadow",
                source_commit="unit-commit",
            )

            self.assertFalse(
                any(
                    dependency["kind"] == "global" and dependency["name"] == "table"
                    for dependency in spec["c_boundary"]["direct_dependencies"]
                )
            )

    def test_does_not_treat_ternary_colon_as_label_for_local_shadow(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-slice-ternary-shadow-test-") as tmp:
            root = Path(tmp)
            src = root / "src" / "ternary_shadow.c"
            src.parent.mkdir()
            src.write_text(
                textwrap.dedent(
                    """
                    #include <stdint.h>

                    static const uint32_t table[2] = { 0U, 1U };

                    uint32_t calc(uint32_t value) {
                        uint32_t table = value ? 1U : 2U;
                        return table;
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            module = load_extractor_module()
            spec = module.generate_slice_spec(
                repo_root=root,
                source_file=Path("src/ternary_shadow.c"),
                function_name="calc",
                target_id="unit",
                slice_id="real-ternary-shadow",
                source_commit="unit-commit",
            )

            self.assertFalse(
                any(
                    dependency["kind"] == "global" and dependency["name"] == "table"
                    for dependency in spec["c_boundary"]["direct_dependencies"]
                )
            )

    def test_records_global_dependency_when_reference_precedes_nested_local_shadow(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-slice-scoped-shadow-test-") as tmp:
            root = Path(tmp)
            src = root / "src" / "scoped_shadow.c"
            src.parent.mkdir()
            src.write_text(
                textwrap.dedent(
                    """
                    #include <stdint.h>

                    static const uint32_t table[2] = { 0U, 1U };

                    uint32_t calc(uint32_t value) {
                        uint32_t out = table[value & 0x1U];
                        if (value != 0U) {
                            uint32_t table = value + 1U;
                            out ^= table;
                        }
                        return out;
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            module = load_extractor_module()
            spec = module.generate_slice_spec(
                repo_root=root,
                source_file=Path("src/scoped_shadow.c"),
                function_name="calc",
                target_id="unit",
                slice_id="real-scoped-shadow",
                source_commit="unit-commit",
            )

            self.assertTrue(
                any(
                    dependency["kind"] == "global" and dependency["name"] == "table"
                    for dependency in spec["c_boundary"]["direct_dependencies"]
                )
            )


if __name__ == "__main__":
    unittest.main()
