from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools.interior_projection_syntax import validate_rust_interior_projection_draft
from validation.tools.interior_projection_test_support import (
    build_projection_spec,
    load_auto_migrate_module,
    renamed_rust_draft,
    unsafe_rust_draft,
)


class AutoMigrateInteriorProjectionReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_auto_migrate_module()
        self.spec, _ = build_projection_spec()
        self.spec["fixture_hash"] = "synthetic-renamed-projection-fixture"

    def test_contract_c_oracle_and_safe_generated_replay(self) -> None:
        fixture = self.module.oracle_fixture_binding(self.spec)
        contract = self._parse(self.spec)
        self.assertEqual(contract["owner"]["parameter"], "owner")
        self.assertEqual(contract["projection_path"], ["current"])
        self.assertEqual(contract["state_output"]["alias_field_path"], ["telemetry", "phase"])
        oracle_source = self.module.oracle_fixture_execution_source(self.spec, fixture)
        self.assertIn("actual_ordinary_owner.current.telemetry.phase", oracle_source["statements"])
        self.assertNotIn("scripted_external", oracle_source["statements"])

        with tempfile.TemporaryDirectory(prefix="auto-migrate-projection-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "reset-current-phase.json"
            spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
            oracle = self.module.generate_oracle_harness_draft(self.spec, evidence_dir, False)
            self.assertEqual(oracle["compile_execution"]["status"], "compile_succeeded_not_oracle")
            draft = evidence_dir / "l3-reset-current-phase-rust-draft.rs"
            draft.write_text(renamed_rust_draft(), encoding="utf-8")
            (evidence_dir / "l3-reset-current-phase-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "translation_summary": {
                            "translation_rule_ids": ["clang-lowered-typed-ir"],
                            "call_expressions": [],
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
            replay = self.module.run_generated_rust_replay(
                self.spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")
            self.assertEqual(replay["safe_mutable_projection"]["unsafe_count"], 0)
            self.assertEqual(replay["safe_mutable_projection"]["raw_pointer_count"], 0)
            self.assertEqual(replay["fixture_state_model"]["pointer_root_count"], 1)

    def test_inferred_and_explicit_safe_projection_are_accepted(self) -> None:
        contract = self._parse(self.spec)
        drafts = [renamed_rust_draft(explicit_type=value) for value in (False, True)]
        for draft in drafts:
            report = validate_rust_interior_projection_draft(
                draft, contract
            )
            self.assertEqual(report["projection_mode"], "safe_mutable_reference")

    def test_owner_state_equality_return_fails_closed_in_c_and_rust(self) -> None:
        c_equality = copy.deepcopy(self.spec)
        c_equality["c_source"] = c_equality["c_source"].replace(
            "return true;", "return owner->current.telemetry.phase == 0;"
        )
        with self.assertRaisesRegex(ValueError, "bool return"):
            self._parse(c_equality)

        contract = self._parse(self.spec)
        rust_equality = renamed_rust_draft().replace(
            "    true\n", "    owner.current.telemetry.phase == 0\n"
        )
        with self.assertRaisesRegex(ValueError, "fixed bool return"):
            validate_rust_interior_projection_draft(rust_equality, contract)

    def test_unsafe_raw_pointer_and_direct_owner_update_fail_closed(self) -> None:
        contract = self._parse(self.spec)
        with self.assertRaisesRegex(ValueError, "unsafe, raw_pointer"):
            validate_rust_interior_projection_draft(unsafe_rust_draft(), contract)
        direct = renamed_rust_draft().replace(
            "cursor.telemetry.phase = (0i32 as u32);",
            "owner.current.telemetry.phase = (0i32 as u32);",
        )
        with self.assertRaisesRegex(ValueError, "projected alias state assignment"):
            validate_rust_interior_projection_draft(direct, contract)

    def test_projection_alias_root_and_noalias_drift_fail_closed(self) -> None:
        alias = copy.deepcopy(self.spec)
        alias["replay_contract"]["alias"]["rust_type"] = "Telemetry"
        with self.assertRaisesRegex(ValueError, "alias type"):
            self._parse(alias)

        path = copy.deepcopy(self.spec)
        path["replay_contract"]["state_output"]["owner_field_path"] = ["current", "phase"]
        with self.assertRaisesRegex(ValueError, "extend projection_path"):
            self._parse(path)

        root = copy.deepcopy(self.spec)
        root["c_boundary"]["signatures"][0]["parameters"].append(
            {"name": "other", "c_type": "struct Node *", "direction": "inout"}
        )
        with self.assertRaisesRegex(ValueError, "exactly one proven owner pointer root"):
            self._parse(root)

        noalias = copy.deepcopy(self.spec)
        noalias["replay_contract"]["noalias_required"] = [["owner", "other"]]
        with self.assertRaisesRegex(ValueError, "must be empty"):
            self._parse(noalias)

    def _parse(self, spec: dict[str, object]) -> dict[str, object]:
        return self.module.record_interior_projection_u32_constant_state_replay_contract(
            spec, self.module.oracle_fixture_binding(spec)
        )


if __name__ == "__main__":
    unittest.main()
