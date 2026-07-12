from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import jsonschema

from validation.tools.replay_call_plan import (
    build_replay_call_plan,
    render_declarative_replay_cases,
    validate_replay_call_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReplayCallPlanOutTests(unittest.TestCase):
    def test_real_single_i32_output_spec_binds_v2_plan(self) -> None:
        spec = self.load_spec()

        plan = build_replay_call_plan(spec, REPO_ROOT)

        self.assertEqual(2, plan["schema_version"])
        self.assertEqual("bound", plan["status"])
        self.assertEqual(["fixture_field", "binding_borrow_mut"], [
            item["source"]["kind"] for item in plan["parameters"]
        ])
        self.assertEqual("i32", plan["bindings"][0]["initializer"]["element_type"])
        self.assertEqual("binding.out.0", plan["assertions"][1]["actual"])
        self.assertEqual(
            [{"fixture_field": "status", "encoding": "string", "expected": "ok"}],
            plan["fixture_assertions"],
        )

    def test_structural_match_survives_full_symbol_and_field_rename(self) -> None:
        spec = self.inline_renamed_spec()

        plan = build_replay_call_plan(spec, REPO_ROOT)
        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)

        self.assertEqual("transform_scalar", plan["source_function_name"])
        self.assertEqual("apply_scalar", plan["api_name"])
        self.assertEqual(["seed", "destination"], [item["name"] for item in plan["parameters"]])
        self.assertEqual("binding.destination.0", plan["assertions"][1]["actual"])
        self.assertEqual("result_value", plan["assertions"][1]["fixture_field"])
        self.assertIn("apply_scalar(4i32, &mut actual_nominal_0_destination)", source)
        self.assertNotIn("store_add_one", source)
        self.assertNotIn("struct FixtureCase", source)

    def test_fixture_and_observable_drift_fail_closed(self) -> None:
        status_drift = self.inline_renamed_spec()
        status_drift["fixture_contract"]["cases"][0]["expected_outputs"]["status"] = "failed"
        self.assertEqual("blocked", build_replay_call_plan(status_drift, REPO_ROOT)["status"])

        type_drift = self.inline_renamed_spec()
        type_drift["fixture_contract"]["cases"][0]["expected_outputs"]["result_value"] = 2**31
        self.assertEqual("blocked", build_replay_call_plan(type_drift, REPO_ROOT)["status"])

        output_drift = self.inline_renamed_spec()
        output_drift["fixture_contract"]["observable_outputs"].append("unbound_output")
        self.assertEqual("unavailable", build_replay_call_plan(output_drift, REPO_ROOT)["status"])

    def test_plan_tampering_and_schema_validation_fail_closed(self) -> None:
        plan = build_replay_call_plan(self.load_spec(), REPO_ROOT)
        schema = json.loads(
            (
                REPO_ROOT
                / "validation"
                / "auto-translation-template"
                / "ai-context-pack.schema.json"
            ).read_text(encoding="utf-8")
        )
        plan_schema = {"$ref": "#/definitions/boundReplayCallPlan", "definitions": schema["definitions"]}
        jsonschema.Draft7Validator(plan_schema).validate(plan)

        tampered = copy.deepcopy(plan)
        tampered["fixture_assertions"][0]["expected"] = 1
        with self.assertRaisesRegex(ValueError, "encoding string"):
            validate_replay_call_plan(tampered)

    @staticmethod
    def load_spec() -> dict:
        return json.loads(
            (
                REPO_ROOT
                / "validation"
                / "slice-specs"
                / "demo-store-add-one.json"
            ).read_text(encoding="utf-8")
        )

    @classmethod
    def inline_renamed_spec(cls) -> dict:
        spec = cls.load_spec()
        spec["function_name"] = "transform_scalar"
        signature = spec["c_boundary"]["signatures"][0]
        signature["function"] = "transform_scalar"
        signature["parameters"][0]["name"] = "seed"
        signature["parameters"][1]["name"] = "destination"
        spec["rust_boundary"]["public_api"][0]["name"] = "apply_scalar"
        spec["fixture_contract"] = {
            "cases": [
                {
                    "id": "nominal",
                    "input_ref": "inline",
                    "inputs": {"seed": 4},
                    "expected_outputs": {
                        "return_code": 0,
                        "status": "ok",
                        "result_value": 5,
                    },
                }
            ],
            "observable_outputs": ["return_code", "status", "result_value"],
        }
        return spec


if __name__ == "__main__":
    unittest.main()
