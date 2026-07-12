from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from validation.tools import auto_migrate
from validation.tools.auto_migrate_call_continue_test_support import (
    EXPECTED_V2_PARTITIONS,
    partition_reports,
    schema_v2_spec_with_five_partitions,
)
from validation.tools._translation_carrier_reporter.call_continue_contract import (
    parse_contract,
)
from validation.tools._translation_carrier_reporter.call_continue_model import (
    reference_outputs,
)
from validation.tools.call_continue_test_support import (
    REPO_ROOT,
    renamed_spec,
    renamed_zero_start_rust_draft,
)


class AutoMigrateCallContinueTests(unittest.TestCase):
    def setUp(self) -> None:
        (REPO_ROOT / "target").mkdir(exist_ok=True)

    def test_schema_v2_generates_scalar_offset_and_executes_rust_replay(self) -> None:
        spec, cases = schema_v2_spec_with_five_partitions()
        fixture = auto_migrate.oracle_fixture_binding(spec)
        contract = auto_migrate.call_continue_state_replay_contract(spec, fixture)
        self.assertIsNotNone(contract)

        oracle = auto_migrate.oracle_fixture_execution_source(spec, fixture)
        self.assertIn(
            "uint32_t actual_zero_start_plain_header_span = (uint32_t)25u;",
            oracle["statements"],
        )
        self.assertNotIn("struct u32", oracle["statements"])
        self.assertIn(
            "advance_window(&actual_zero_start_plain_source, "
            "actual_zero_start_plain_window_seed, "
            "actual_zero_start_plain_header_span, &actual_zero_start_plain_owner)",
            oracle["statements"],
        )
        self.assertIn("if (c2r_call_count != 0u)", oracle["statements"])
        self.assertIn("if (c2r_call_count != 1u)", oracle["statements"])

        replay = auto_migrate.rust_replay_fixture_cases_source(spec, fixture)
        self.assertIn(
            "let actual_zero_start_plain_header_span = 25u32;",
            replay,
        )
        self.assertNotIn("u32 {", replay)
        self.assertIn(
            "advance_window(&mut actual_zero_start_plain_source, "
            "actual_zero_start_plain_window_seed, "
            "actual_zero_start_plain_header_span, &mut actual_zero_start_plain_owner)",
            replay,
        )
        self.assertIn("__c2r_scripted_external_call_count(), 0usize", replay)
        self.assertIn("__c2r_scripted_external_call_count(), 1usize", replay)

        rustc = shutil.which("rustc")
        self.assertIsNotNone(rustc)
        with tempfile.TemporaryDirectory(
            prefix="auto-call-continue-v2-", dir=REPO_ROOT / "target"
        ) as tmp:
            root = Path(tmp)
            combined = root / "combined.rs"
            combined.write_text(
                renamed_zero_start_rust_draft()
                + "\n#[test]\nfn generated_auto_migrate_replay() {\n"
                + replay
                + "}\n",
                encoding="utf-8",
                newline="\n",
            )
            executable = root / "replay.exe"
            compiled = subprocess.run(
                [rustc, "--edition=2021", "--test", str(combined), "-o", str(executable)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run(
                [str(executable)], capture_output=True, text=True, check=False
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)

    def test_schema_v2_state_model_and_safety_declare_five_partitions(self) -> None:
        spec, _cases = schema_v2_spec_with_five_partitions()
        contract = parse_contract(spec)
        state_model = auto_migrate.call_continue_fixture_state_model(contract)
        self.assertEqual(state_model["schema_version"], 2)
        self.assertEqual(
            state_model["entry_argument_kinds"], ["record", "record", "u32", "record"]
        )
        self.assertEqual(state_model["fixture_partitions"], EXPECTED_V2_PARTITIONS)
        self.assertEqual(state_model["external_call_count_values"], [0, 1])

        with tempfile.TemporaryDirectory(
            prefix="auto-call-continue-safety-", dir=REPO_ROOT / "target"
        ) as tmp:
            draft = Path(tmp) / "draft.rs"
            draft.write_text(
                renamed_zero_start_rust_draft(), encoding="utf-8", newline="\n"
            )
            safety = auto_migrate.call_continue_generated_rust_safety(spec, draft)
        self.assertIsNotNone(safety)
        self.assertEqual(safety["schema_version"], 2)
        self.assertEqual(safety["fixture_partitions"], EXPECTED_V2_PARTITIONS)
        self.assertEqual(safety["external_call_count_values"], [0, 1])
        self.assertTrue(safety["zero_start_external_call_skipped"])

    def test_generated_replay_safety_rejection_is_structured_not_exception(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="auto-call-continue-replay-safety-", dir=REPO_ROOT / "target"
        ) as tmp:
            evidence_dir = Path(tmp)
            slice_id = "renamed-zero-start"
            (evidence_dir / f"l3-{slice_id}-rust-draft.rs").write_text(
                "pub fn candidate() {}\n",
                encoding="utf-8",
            )
            (evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs").write_text(
                "#[test] fn replay() {}\n",
                encoding="utf-8",
            )
            replay = {"translation_mappings": [{"status": "candidate"}]}
            with (
                mock.patch.object(
                    auto_migrate,
                    "generated_rust_replay_supported",
                    return_value=True,
                ),
                mock.patch.object(
                    auto_migrate,
                    "call_continue_generated_rust_safety",
                    side_effect=ValueError(
                        "carrier must contain exactly one declared safe owner interior alias"
                    ),
                ),
                mock.patch.object(auto_migrate, "run_generated_rust_replay_once") as execute,
            ):
                result = auto_migrate.run_generated_rust_replay(
                    {"slice_id": slice_id},
                    evidence_dir,
                    replay,
                    {"status": "passed"},
                )

            execute.assert_not_called()
            self.assertEqual("failed", result["status"])
            self.assertEqual("safety", result["replay_execution"]["phase"])
            self.assertFalse(result["generated_draft_replay_pass"])
            self.assertFalse(result["generated_draft_semantic_pass"])
            self.assertFalse(result["replay_safety"]["semantic_gate"])
            self.assertEqual(
                "generated_rust_safety_contract_failed",
                result["replay_safety"]["kind"],
            )
            self.assertEqual("failed", result["translation_mappings"][0]["status"])
            persisted = json.loads(
                (
                    evidence_dir
                    / f"l3-{slice_id}-test-translation-generated.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(result, persisted)

    def test_schema_v2_identity_partition_recomputation_checks_call_counts(self) -> None:
        spec, cases = schema_v2_spec_with_five_partitions()
        execution, negative = partition_reports(spec, cases)
        with tempfile.TemporaryDirectory(
            prefix="auto-call-continue-partitions-", dir=REPO_ROOT / "target"
        ) as tmp:
            fixture = Path(tmp) / "fixture.json"
            fixture.write_text(
                json.dumps({"cases": cases}), encoding="utf-8", newline="\n"
            )
            auto_migrate._verify_call_continue_partitions(
                spec, fixture, negative, execution
            )

            bad_count = copy.deepcopy(cases)
            bad_count[0]["expected_outputs"]["call_count"] = 1
            fixture.write_text(
                json.dumps({"cases": bad_count}), encoding="utf-8", newline="\n"
            )
            with self.assertRaisesRegex(SystemExit, "fixture call count mismatch"):
                auto_migrate._verify_call_continue_partitions(
                    spec, fixture, negative, execution
                )

            missing_plain = copy.deepcopy(cases)
            missing_plain[0]["inputs"]["alias_start_initial"] = 1
            missing_plain[0]["expected_outputs"] = reference_outputs(
                missing_plain[0], parse_contract(spec)
            )
            fixture.write_text(
                json.dumps({"cases": missing_plain}), encoding="utf-8", newline="\n"
            )
            with self.assertRaisesRegex(SystemExit, "fixture partition mismatch"):
                auto_migrate._verify_call_continue_partitions(
                    spec, fixture, negative, execution
                )

    def test_schema_v2_requires_one_wrapping_sentinel_hit(self) -> None:
        spec, cases = schema_v2_spec_with_five_partitions()
        second_hit = copy.deepcopy(cases[2])
        second_hit["id"] = "second-hit"
        cases.append(second_hit)
        spec["fixture_contract"]["cases"] = copy.deepcopy(cases)
        fixture = auto_migrate.oracle_fixture_binding(spec)
        with self.assertRaisesRegex(ValueError, "exactly one sentinel hit"):
            auto_migrate.call_continue_state_replay_contract(spec, fixture)

        spec, cases = schema_v2_spec_with_five_partitions()
        hit = next(case for case in cases if case["id"] == "hit-wrap")
        hit["inputs"]["owner_traversed_initial"] = 100
        hit["expected_outputs"] = reference_outputs(hit, parse_contract(spec))
        spec["fixture_contract"]["cases"] = copy.deepcopy(cases)
        fixture = auto_migrate.oracle_fixture_binding(spec)
        with self.assertRaisesRegex(ValueError, "traversed u32 wrap"):
            auto_migrate.call_continue_state_replay_contract(spec, fixture)

    def test_schema_v1_generator_shape_is_unchanged(self) -> None:
        spec, cases = renamed_spec()
        fixture = auto_migrate.oracle_fixture_binding(spec)
        contract = auto_migrate.call_continue_state_replay_contract(spec, fixture)
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract["entry_arguments"]), 3)

        state_model = auto_migrate.call_continue_fixture_state_model(contract)
        self.assertNotIn("schema_version", state_model)
        self.assertNotIn("fixture_partitions", state_model)
        oracle = auto_migrate.oracle_fixture_execution_source(spec, fixture)
        replay = auto_migrate.rust_replay_fixture_cases_source(spec, fixture)
        self.assertNotIn("struct u32", oracle["statements"])
        self.assertNotIn("u32 {", replay)
        for case in cases:
            self.assertEqual(case["expected_outputs"]["call_count"], 1)

if __name__ == "__main__":
    unittest.main()
