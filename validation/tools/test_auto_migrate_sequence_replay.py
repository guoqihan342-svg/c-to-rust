from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.sequence_replay_test_support import (
    build_interior_sequence_spec,
    build_sequence_spec,
    renamed_interior_rust_draft,
    renamed_rust_draft,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("sequence_auto_migrate_under_test", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoMigrateSequenceReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_auto_migrate_module()
        self.spec, _ = build_sequence_spec()
        self.spec["fixture_hash"] = "synthetic-renamed-sequence-fixture"

    def test_fully_renamed_mixed_mode_sequence_compiles_and_replays(self) -> None:
        fixture_binding = self.module.oracle_fixture_binding(self.spec)
        contract = (
            self.module.scripted_external_record_u32_sequence_do_while_state_replay_contract(
                self.spec, fixture_binding
            )
        )
        self.assertEqual(
            [item["mode"] for item in contract["external_callee"]["arguments"]],
            ["record_ref", "record_ref", "scalar_field_value"],
        )
        oracle_source = self.module.oracle_fixture_execution_source(self.spec, fixture_binding)
        self.assertIn("struct Ledger *ledger_ref", oracle_source["definitions_after_target"])
        self.assertIn("struct Window *window_ref", oracle_source["definitions_after_target"])
        self.assertIn("uint32_t walked_copy", oracle_source["definitions_after_target"])
        self.assertIn("c2r_scripted_external_call_args[", oracle_source["definitions_after_target"])

        with tempfile.TemporaryDirectory(prefix="auto-migrate-sequence-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "advance-window-tail.json"
            spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
            oracle = self.module.generate_oracle_harness_draft(self.spec, evidence_dir, False)
            compile_execution = oracle["compile_execution"]
            self.assertEqual(compile_execution["status"], "compile_succeeded_not_oracle")
            self.assertEqual(
                compile_execution["harness_execution"]["status"], "exited_zero_not_oracle"
            )

            draft_path = evidence_dir / "l3-advance-window-tail-rust-draft.rs"
            draft_path.write_text(renamed_rust_draft(), encoding="utf-8")
            plan_path = evidence_dir / "l3-advance-window-tail-auto-translation-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "translation_summary": {
                            "translation_rule_ids": ["clang-lowered-typed-ir"],
                            "call_expressions": [{"callee": "probe_following_window"}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            replay = self.module.generate_rust_replay_test_draft(
                self.spec, evidence_dir, spec_path
            )
            rust_check, _ = self.module.run_rust_check(evidence_dir, False, self.spec)
            self.assertEqual(rust_check["status"], "passed")
            checked_draft = draft_path.read_text(encoding="utf-8")
            self.assertIn("walked_copy: u32", checked_draft)
            self.assertIn("Vec<[u32; 3]>", checked_draft)
            replay = self.module.run_generated_rust_replay(
                self.spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")
            self.assertEqual(
                replay["fixture_external_stub"]["kind"],
                "scripted_external_record_u32_sequence_do_while_state",
            )

    def test_noalias_empty_and_boundary_drift_fail_closed(self) -> None:
        drift = copy.deepcopy(self.spec)
        drift["c_boundary"]["pointer_contract"]["noalias_required"] = []
        with self.assertRaisesRegex(ValueError, "noalias contract drifted"):
            self._parse(drift)

        empty = copy.deepcopy(self.spec)
        empty["replay_contract"]["noalias_required"] = []
        empty["c_boundary"]["pointer_contract"]["noalias_required"] = []
        with self.assertRaisesRegex(ValueError, "complete mutable root pair set"):
            self._parse(empty)

    def test_empty_sequence_missing_sentinel_and_expected_count_drift_fail_closed(self) -> None:
        empty = copy.deepcopy(self.spec)
        empty["fixture_contract"]["cases"][0]["inputs"]["probe_sequence"] = []
        with self.assertRaisesRegex(ValueError, "return sequence must be non-empty"):
            self._parse(empty)

        missing = copy.deepcopy(self.spec)
        missing["fixture_contract"]["cases"][1]["inputs"]["probe_sequence"] = [4, 7]
        with self.assertRaisesRegex(ValueError, "does not reach sentinel"):
            self._parse(missing)

        count_drift = copy.deepcopy(self.spec)
        count_drift["fixture_contract"]["cases"][1]["expected_outputs"]["probe_count"] = 2
        with self.assertRaisesRegex(ValueError, "expected outputs drifted"):
            self._parse(count_drift)

    def test_scalar_mode_signature_drift_is_rejected(self) -> None:
        drift = copy.deepcopy(self.spec)
        drift["c_boundary"]["signatures"][1]["parameters"][2]["c_type"] = (
            "struct Progress *"
        )
        with self.assertRaisesRegex(ValueError, "external parameter types drifted"):
            self._parse(drift)

    def test_renamed_owner_interior_alias_sequence_compiles_and_replays(self) -> None:
        self.spec, _ = build_interior_sequence_spec()
        self.spec["fixture_hash"] = "synthetic-renamed-interior-sequence-fixture"
        fixture_binding = self.module.oracle_fixture_binding(self.spec)
        contract = self.module.scripted_external_record_u32_sequence_do_while_state_replay_contract(
            self.spec, fixture_binding
        )
        alias = contract["external_callee"]["arguments"][2]
        self.assertEqual(alias["mode"], "owner_interior_alias")
        self.assertEqual(
            self.module.scripted_sequence_external_rust_type(
                alias,
                {item["parameter"]: item for item in contract["entry_arguments"]},
            ),
            "&mut Cursor",
        )
        oracle_source = self.module.oracle_fixture_execution_source(
            self.spec, fixture_binding
        )
        self.assertIn(
            "struct Cursor *cursor_ref",
            oracle_source["definitions_after_target"],
        )

        with tempfile.TemporaryDirectory(prefix="auto-migrate-interior-sequence-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "advance-window-tail.json"
            spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
            oracle = self.module.generate_oracle_harness_draft(
                self.spec, evidence_dir, False
            )
            self.assertEqual(
                oracle["compile_execution"]["status"],
                "compile_succeeded_not_oracle",
            )
            draft_path = evidence_dir / "l3-advance-window-tail-rust-draft.rs"
            draft_path.write_text(renamed_interior_rust_draft(), encoding="utf-8")
            plan_path = evidence_dir / "l3-advance-window-tail-auto-translation-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "translation_summary": {
                            "translation_rule_ids": ["clang-lowered-typed-ir"],
                            "call_expressions": [{"callee": "probe_following_window"}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            replay = self.module.generate_rust_replay_test_draft(
                self.spec, evidence_dir, spec_path
            )
            rust_check, _ = self.module.run_rust_check(
                evidence_dir, False, self.spec
            )
            self.assertEqual(rust_check["status"], "passed")
            replay = self.module.run_generated_rust_replay(
                self.spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")

    def test_owner_interior_alias_projection_and_signature_drift_fail_closed(self) -> None:
        self.spec, _ = build_interior_sequence_spec()
        self.spec["fixture_hash"] = "synthetic-renamed-interior-sequence-fixture"
        projection_drift = copy.deepcopy(self.spec)
        projection_drift["replay_contract"]["external_callee"]["arguments"][2][
            "projection_path"
        ] = ["missing"]
        with self.assertRaisesRegex(ValueError, "projection must resolve"):
            self._parse(projection_drift)

        signature_drift = copy.deepcopy(self.spec)
        signature_drift["c_boundary"]["signatures"][1]["parameters"][2][
            "c_type"
        ] = "struct Progress *"
        with self.assertRaisesRegex(ValueError, "external parameter types drifted"):
            self._parse(signature_drift)

        legacy_drift = copy.deepcopy(self.spec)
        legacy_drift["replay_contract"]["schema_version"] = 1
        with self.assertRaisesRegex(ValueError, "mode is unsupported"):
            self._parse(legacy_drift)

    def _parse(self, spec: dict[str, object]) -> dict[str, object]:
        return self.module.scripted_external_record_u32_sequence_do_while_state_replay_contract(
            spec, self.module.oracle_fixture_binding(spec)
        )


if __name__ == "__main__":
    unittest.main()
