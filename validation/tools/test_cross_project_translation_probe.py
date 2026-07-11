import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from validation.tools import cross_project_translation_probe as probe


REPO_ROOT = Path(__file__).resolve().parents[2]


class CrossProjectTranslationProbeTest(unittest.TestCase):
    def test_catalog_is_bounded_and_generic(self) -> None:
        catalog, cases = probe.load_cases(probe.DEFAULT_FIXTURES, REPO_ROOT)

        self.assertEqual(catalog["schema_version"], 1)
        self.assertGreaterEqual(len(cases), 2)
        self.assertLessEqual(len(cases), probe.MAX_CASES)
        self.assertNotIn("flashdb", probe.DEFAULT_FIXTURES.read_text(encoding="utf-8").lower())
        self.assertEqual(len({case["id"] for case in cases}), len(cases))

    def test_catalog_rejects_more_than_twenty_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            source_file = probe.DEFAULT_FIXTURES.parent / "probe_fixtures.c"
            case = {
                "id": "case-a",
                "project": "unit",
                "syntax_family": "scalar",
                "naming_variant": "value",
                "function_name": "value",
                "c_source": "int value(void) { return 0; }",
                "clang_ast_fixture": "crates/c2r-translator/fixtures/clang_ast/add_one_ast.json",
                "expected_classification": "success",
            }
            path.write_text(
                json.dumps({"schema_version": 1, "source_file": source_file.relative_to(REPO_ROOT).as_posix(), "cases": [case] * 21}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "1 to 20"):
                probe.load_cases(path, REPO_ROOT)

    def test_probe_reports_success_refusal_and_execution_failure(self) -> None:
        catalog, cases = probe.load_cases(probe.DEFAULT_FIXTURES, REPO_ROOT)
        selected = [cases[0], cases[-2], cases[-1]]
        fixtures_path = Path(self._tmpdir()) / "selected-cases.json"
        fixtures_path.write_text(
            json.dumps({"schema_version": 1, "source_file": catalog["source_file"], "cases": selected}),
            encoding="utf-8",
        )

        def fake_runner(argv, _cwd):
            case_dir = Path(argv[argv.index("--out-dir") + 1])
            spec = json.loads(Path(argv[argv.index("--slice-spec") + 1]).read_text(encoding="utf-8"))
            case_id = spec["slice_id"]
            if case_id == selected[-1]["id"]:
                return subprocess.CompletedProcess(argv, 9, "", "translator unavailable")
            prefix = f"l3-{case_id}"
            generated = case_id == selected[0]["id"]
            route = {
                "route_id": "generic-typed-ir" if generated else "unsupported",
                "reasons": [] if generated else [{"code": "outside_typed_ir_emitter_subset"}],
            }
            (case_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "generated" if generated else "blocked"}), encoding="utf-8"
            )
            (case_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps({"typed_ir_candidate": {"rust_draft_generated": generated, "candidate_route": route}}),
                encoding="utf-8",
            )
            (case_dir / f"{prefix}-blocked-repairs.json").write_text(
                json.dumps({"blocked": [] if generated else [{"kind": "unsupported_syntax"}]}), encoding="utf-8"
            )
            return subprocess.CompletedProcess(argv, 0, "{}", "")

        report = probe.run_probe(REPO_ROOT, fixtures_path, fixtures_path.parent / "out", fake_runner)

        self.assertEqual(report["outcome_counts"], {"success": 1, "refusal": 1, "execution_failure": 1})
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["cases"][0]["route"], "generic-typed-ir")
        self.assertEqual(report["cases"][1]["refusal"]["codes"], ["outside_typed_ir_emitter_subset", "unsupported_syntax"])
        self.assertEqual(report["cases"][2]["refusal"]["codes"], ["translator_process_failed"])

    def _tmpdir(self) -> str:
        if not hasattr(self, "_temporary_directory"):
            self._temporary_directory = tempfile.TemporaryDirectory()
            self.addCleanup(self._temporary_directory.cleanup)
        return self._temporary_directory.name


if __name__ == "__main__":
    unittest.main()
