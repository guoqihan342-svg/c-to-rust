from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from validation.tools import ai_candidate_harness, auto_migrate
from validation.tools.replay_call_plan import (
    build_replay_call_plan,
    render_declarative_replay_cases,
    validate_replay_call_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReplayCallPlanV2Tests(unittest.TestCase):
    RECORD_CASES = (
        ("flashdb-real-fdb-kv-iterate-kv-reset.json", ["binding_borrow_mut"]),
        (
            "flashdb-real-fdb-kv-iterate-traversed-len.json",
            ["binding_borrow", "binding_borrow_mut"],
        ),
        (
            "flashdb-real-fdb-kv-iterate-sector-start.json",
            ["binding_value", "fixture_field", "binding_borrow_mut"],
        ),
        ("flashdb-real-fdb-kv-iterate-iterated-count.json", ["binding_borrow_mut"]),
        (
            "flashdb-real-fdb-kv-iterate-interior-projection.json",
            ["binding_borrow_mut"],
        ),
        (
            "flashdb-real-fdb-kv-iterate-stats-sequence.json",
            ["binding_borrow_mut"],
        ),
        (
            "flashdb-real-fdb-kv-iterate-guarded-stats-sequence.json",
            ["binding_borrow_mut"],
        ),
        (
            "flashdb-real-fdb-kv-iterate-obj-bytes.json",
            ["binding_borrow_mut"],
        ),
        (
            "flashdb-real-fdb-kv-iterate-sector-advance-continue.json",
            ["binding_borrow", "binding_borrow_mut"],
        ),
    )

    def test_entry_record_state_kinds_share_one_plan_shape(self) -> None:
        for filename, expected_sources in self.RECORD_CASES:
            with self.subTest(filename=filename):
                plan = build_replay_call_plan(self.load_named_spec(filename), REPO_ROOT)
                self.assertEqual("bound", plan["status"])
                self.assertEqual(2, plan["schema_version"])
                self.assertEqual(
                    expected_sources,
                    [item["source"]["kind"] for item in plan["parameters"]],
                )

    def test_record_state_plan_binds_locals_borrows_and_post_state(self) -> None:
        spec = self.load_spec()
        spec["function_name"] = "renamed_source"
        spec["c_boundary"]["signatures"][0]["function"] = "renamed_source"
        spec["rust_boundary"]["public_api"][0]["name"] = "renamed_api"

        plan = build_replay_call_plan(spec, REPO_ROOT)

        self.assertEqual(2, plan["schema_version"])
        self.assertEqual("bound", plan["status"])
        self.assertEqual("renamed_source", plan["source_function_name"])
        self.assertEqual("renamed_api", plan["api_name"])
        self.assertEqual("binding_borrow_mut", plan["parameters"][0]["source"]["kind"])
        self.assertEqual("binding.kv.addr.start", plan["assertions"][1]["actual"])
        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)
        self.assertIn("let mut actual_already_zero_0_kv: Kv", source)
        self.assertIn("renamed_api(&mut actual_already_zero_0_kv)", source)
        self.assertNotIn("fdb_kv_iterate_kv_reset_probe(", source)

    def test_binding_and_observation_tampering_fail_closed(self) -> None:
        plan = build_replay_call_plan(self.load_spec(), REPO_ROOT)
        binding_drift = copy.deepcopy(plan)
        binding_drift["parameters"][0]["source"]["binding"] = "other"
        with self.assertRaisesRegex(ValueError, "binding source"):
            validate_replay_call_plan(binding_drift)

        observation_drift = copy.deepcopy(plan)
        observation_drift["assertions"][1]["actual"] = "binding.kv.addr.missing"
        with self.assertRaisesRegex(ValueError, "binding path"):
            validate_replay_call_plan(observation_drift)

    def test_contract_and_fixture_drift_are_blocked(self) -> None:
        noalias_drift = self.load_spec()
        noalias_drift["replay_contract"]["noalias_required"] = [["kv", "kv"]]
        self.assertEqual("blocked", build_replay_call_plan(noalias_drift, REPO_ROOT)["status"])

        output_drift = self.load_spec()
        output_drift["fixture_contract"]["cases"][0]["expected_outputs"]["kv_addr_start"] = 1
        self.assertEqual("blocked", build_replay_call_plan(output_drift, REPO_ROOT)["status"])

        with tempfile.TemporaryDirectory(prefix="replay-plan-v2-blocked-") as tmp:
            path = auto_migrate.write_rust_replay_test_draft_source(output_drift, Path(tmp))
            source = path.read_text(encoding="utf-8")
            self.assertIn("legacy replay fallback is disabled", source)
            self.assertNotIn("fdb_kv_iterate_kv_reset_probe(", source)

    def test_context_pack_schema_accepts_bound_plan_v2(self) -> None:
        schema = json.loads(
            (
                REPO_ROOT
                / "validation"
                / "auto-translation-template"
                / "ai-context-pack.schema.json"
            ).read_text(encoding="utf-8")
        )
        for filename in (
            "flashdb-real-fdb-kv-iterate-kv-reset.json",
            "flashdb-real-fdb-kv-iterate-sector-start.json",
            "flashdb-real-fdb-kv-iterate-traversed-len.json",
        ):
            with self.subTest(filename=filename):
                spec_path = REPO_ROOT / "validation" / "slice-specs" / filename
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                with tempfile.TemporaryDirectory(prefix="replay-plan-v2-context-") as tmp:
                    replay_root = Path(tmp)
                    replay_path = auto_migrate.write_rust_replay_test_draft_source(
                        spec, replay_root
                    )
                    context = ai_candidate_harness.build_context_pack(
                        spec_path,
                        source_root=REPO_ROOT / "sources" / "FlashDB",
                        replay_test_path=replay_path,
                        replay_root=replay_root,
                    )
                jsonschema.Draft7Validator(schema).validate(context)
                self.assertEqual(
                    2,
                    context["replay_api_contract"]["call_plan"]["schema_version"],
                )

    @staticmethod
    def load_spec() -> dict:
        return ReplayCallPlanV2Tests.load_named_spec(
            "flashdb-real-fdb-kv-iterate-kv-reset.json"
        )

    @staticmethod
    def load_named_spec(filename: str) -> dict:
        return json.loads(
            (
                REPO_ROOT
                / "validation"
                / "slice-specs"
                / filename
            ).read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
