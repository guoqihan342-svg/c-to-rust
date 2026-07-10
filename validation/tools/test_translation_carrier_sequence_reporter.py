from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools._translation_carrier_reporter import emit_reports
from validation.tools._translation_carrier_reporter.contract import (
    ReporterError,
    parse_contract,
    validate_cases,
)
from validation.tools.sequence_replay_test_support import (
    FIELDS,
    build_sequence_spec,
    renamed_rust_draft,
    sha256_file,
    sha256_text,
    write_json,
)
from validation.tools.test_auto_migrate_sequence_replay import load_auto_migrate_module


REPO_ROOT = Path(__file__).resolve().parents[2]


class TranslationCarrierSequenceReporterTests(unittest.TestCase):
    def test_fully_renamed_sequence_reporter_executes_same_and_partition_negatives(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="sequence-reporter-", dir=target_root
        ) as tmp:
            layout = build_reporter_layout(Path(tmp))
            paths = emit_reports(**layout["emit_args"])
            reports = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}

            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["c_oracle"]["provenance"]["binding_mode"], "executed_harness")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["cases"][1]["probe_count"], 3)
            self.assertEqual(
                reports["rust_report"]["cases"][1]["probe_args"],
                [[7, 11, 13], [7, 11, 13], [7, 11, 13]],
            )

            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertEqual(
                negative["partition_detection"]["sequence_exhaustion_case_ids"],
                ["marker-first"],
            )
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["marker-later"],
            )
            self.assertIn(negative["first_mismatch"]["field"], FIELDS)
            self.assertEqual(negative["mismatches"][0]["field"], "scripted_return_sequence")
            execution = negative["actual_mutation_execution"]
            self.assertEqual(
                execution["same_generated_replay_harness"]["run"]["returncode"], 101
            )
            self.assertEqual(
                execution["partition_replay"]["compile"]["returncode"], 0
            )
            self.assertEqual(
                execution["mutation"]["operator_from"], "!="
            )
            self.assertEqual(execution["mutation"]["operator_to"], "==")

    def test_reporter_recomputes_and_rejects_sequence_contract_drift(self) -> None:
        spec, fixture = build_sequence_spec()
        contract = parse_contract(spec)
        cases = validate_cases(fixture["cases"], contract)
        self.assertEqual(cases[1]["expected_outputs"]["probe_count"], 3)

        drift = copy.deepcopy(spec)
        drift["c_boundary"]["pointer_contract"]["noalias_required"] = []
        with self.assertRaisesRegex(ReporterError, "noalias contract drifted"):
            parse_contract(drift)

        empty = copy.deepcopy(fixture["cases"])
        empty[0]["inputs"]["probe_sequence"] = []
        with self.assertRaisesRegex(ReporterError, "return sequence must be non-empty"):
            validate_cases(empty, contract)

        missing = copy.deepcopy(fixture["cases"])
        missing[1]["inputs"]["probe_sequence"] = [3, 4]
        with self.assertRaisesRegex(ReporterError, "does not reach sentinel"):
            validate_cases(missing, contract)

        count_drift = copy.deepcopy(fixture["cases"])
        count_drift[1]["expected_outputs"]["probe_count"] = 2
        with self.assertRaisesRegex(ReporterError, "row count drifted|sequence model"):
            validate_cases(count_drift, contract)


def build_reporter_layout(workspace: Path) -> dict[str, object]:
    relative_prefix = workspace.relative_to(REPO_ROOT).as_posix() + "/"
    spec, fixture = build_sequence_spec(path_prefix=relative_prefix)
    fixture_path = workspace / "fixtures" / "window-tail-cases.json"
    source_root = workspace / "upstream"
    source_path = source_root / "tail.c"
    spec_path = workspace / "specs" / "window-tail.json"
    auto_dir = workspace / "evidence" / "auto"
    output_dir = workspace / "evidence" / "accepted"
    for directory in (fixture_path.parent, source_root, spec_path.parent, auto_dir):
        directory.mkdir(parents=True, exist_ok=True)
    write_json(fixture_path, fixture)
    source_path.write_bytes(spec["c_source"].encode("utf-8"))

    spec["fixture_hash"] = sha256_file(fixture_path)
    spec["fixture_contract"]["hash"] = spec["fixture_hash"]
    spec["source_root"] = source_root.relative_to(REPO_ROOT).as_posix()
    spec["source_file"] = source_path.name
    spec["source_file_hashes"] = {source_path.name: sha256_file(source_path)}
    spec["translation_carrier"] = translation_carrier(spec["c_source"], source_path.name)
    write_json(spec_path, spec)

    module = load_auto_migrate_module()
    oracle = module.generate_oracle_harness_draft(spec, auto_dir, False)
    if oracle["compile_execution"]["status"] != "compile_succeeded_not_oracle":
        raise AssertionError(oracle["compile_execution"])
    draft_path = auto_dir / "l3-advance-window-tail-rust-draft.rs"
    draft_path.write_text(renamed_rust_draft(), encoding="utf-8")
    plan = {
        "schema_version": 1,
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "fixture_hash": spec["fixture_hash"],
        "translation_carrier": spec["translation_carrier"],
        "status": "generated",
        "translation_source": {"selected": "clang-lowered-typed-ir"},
        "translation_summary": {
            "translation_rule_ids": ["clang-lowered-typed-ir"],
            "call_expressions": [{"callee": "probe_following_window"}],
        },
    }
    write_json(auto_dir / "l3-advance-window-tail-auto-translation-plan.json", plan)
    replay = module.generate_rust_replay_test_draft(spec, auto_dir, spec_path)
    rust_check, _ = module.run_rust_check(auto_dir, False, spec)
    if rust_check["status"] != "passed":
        raise AssertionError(rust_check)
    replay = module.run_generated_rust_replay(spec, auto_dir, replay, rust_check)
    if replay["status"] != "passed":
        raise AssertionError(replay)

    stable_source_hash = sha256_file(source_path)
    translator_input = {
        "schema_version": 1,
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "fixture_hash": spec["fixture_hash"],
        "translation_carrier": spec["translation_carrier"],
        "c_source": spec["c_source"],
        "function_name": spec["function_name"],
        "source_root": spec["source_root"],
        "source_file": spec["source_file"],
        "source_file_hashes": {source_path.name: stable_source_hash},
        "build_profile": {"clang_ast_fixture": None},
    }
    lowering = {
        "schema_version": 1,
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "fixture_hash": spec["fixture_hash"],
        "translation_carrier": spec["translation_carrier"],
        "status": "lowered",
        "function_name": spec["function_name"],
        "lowering_report": {"frontend": "clang_slice_source"},
        "metadata": {
            "source_root": spec["source_root"],
            "logical_source_file": spec["source_file"],
            "source_file_hashes": {source_path.name: stable_source_hash},
            "clang_ast_fixture": None,
        },
        "typed_ir_candidate": {
            "status": "generated",
            "rust_draft_generated": True,
            "semantic_pass": False,
            "rust_draft_sha256": sha256_file(draft_path),
        },
    }
    write_json(auto_dir / "l3-advance-window-tail-translator-input.json", translator_input)
    write_json(auto_dir / "l3-advance-window-tail-clang-lowering-report.json", lowering)
    return {
        "emit_args": {
            "slice_spec": spec_path,
            "auto_evidence_dir": auto_dir,
            "output_dir": output_dir,
            "repo_root": REPO_ROOT,
        }
    }


def translation_carrier(c_source: str, source_file: str) -> dict[str, object]:
    lines = c_source.splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines, start=1) if line.startswith("static bool"))
    fragment = "".join(lines[start - 1 :])
    return {
        "kind": "exact_source_fragment_wrapper",
        "embedding_mode": "verbatim_once",
        "frontend_contract": "live_clang_slice_source",
        "source_text_normalization": "utf8_universal_newlines",
        "source_file_hash_mode": "raw_bytes",
        "artifact_source_hash_mode": "lf_stable_text",
        "carrier_function": "advance_window_tail",
        "carrier_source_sha256": sha256_text(c_source),
        "claim_boundary": {
            "scope": "source_fragment_only",
            "whole_function_semantics_verified": False,
            "external_callee_semantics_verified": False,
            "excluded_semantics": ["real external storage semantics"],
        },
        "real_source": {
            "file": source_file,
            "containing_function": {
                "line_start": start,
                "line_end": len(lines),
                "hash_mode": "trimmed_normalized_span",
                "sha256": sha256_text(fragment.strip()),
                "declaration_text": "static bool advance_window_tail(",
            },
            "fragment": {
                "line_start": start,
                "line_end": len(lines),
                "hash_mode": "normalized_line_span_with_newline",
                "sha256": sha256_text(fragment),
                "text": fragment,
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
