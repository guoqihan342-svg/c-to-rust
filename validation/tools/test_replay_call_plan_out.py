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

    def test_real_i32_slice_output_spec_binds_dynamic_plan(self) -> None:
        spec = self.load_slice_spec()

        plan = build_replay_call_plan(spec, REPO_ROOT)

        self.assertEqual(2, plan["schema_version"])
        self.assertEqual("bound", plan["status"])
        self.assertEqual(
            ["fixture_field", "fixture_field", "binding_borrow_mut"],
            [item["source"]["kind"] for item in plan["parameters"]],
        )
        self.assertEqual("vec_repeat", plan["bindings"][0]["initializer"]["kind"])
        self.assertEqual("binding.out", plan["assertions"][1]["actual"])
        self.assertEqual("i32_vec", plan["assertions"][1]["encoding"])
        self.assertEqual(5, len(plan["fixture_relations"]))

        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)
        self.assertIn("let mut actual_empty_0_out: Vec<i32> = vec![0i32; 0usize];", source)
        self.assertIn("copy_i32_ptr_arith(&[], 0i32, &mut actual_empty_0_out)", source)
        self.assertIn("vec![-5i32, 2i32, -3i32, 6i32]", source)
        self.assertNotIn("struct FixtureCase", source)

    def test_slice_output_match_survives_symbol_and_observable_rename(self) -> None:
        spec = self.inline_renamed_slice_spec()

        plan = build_replay_call_plan(spec, REPO_ROOT)
        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)

        self.assertEqual("apply_buffer", plan["api_name"])
        self.assertEqual("binding.destination", plan["assertions"][1]["actual"])
        self.assertEqual("result_items", plan["assertions"][1]["fixture_field"])
        self.assertIn("apply_buffer(&[3i32, -2i32], 2i32, &mut actual_nominal_0_destination)", source)
        self.assertNotIn("copy_i32_ptr_arith", source)

    def test_slice_output_fixture_drift_fails_closed(self) -> None:
        length_drift = self.inline_renamed_slice_spec()
        length_drift["fixture_contract"]["cases"][0]["expected_outputs"]["result_items"] = [3]
        self.assertEqual("blocked", build_replay_call_plan(length_drift, REPO_ROOT)["status"])

        negative_length = self.inline_renamed_slice_spec()
        case = negative_length["fixture_contract"]["cases"][0]
        case["inputs"]["count"] = -1
        case["expected_outputs"]["count"] = -1
        case["expected_outputs"]["changed_items"] = -1
        self.assertEqual("blocked", build_replay_call_plan(negative_length, REPO_ROOT)["status"])

        metadata_drift = self.inline_renamed_slice_spec()
        second = copy.deepcopy(metadata_drift["fixture_contract"]["cases"][0])
        second["id"] = "drifted"
        second["expected_outputs"]["source_note"] = "different"
        metadata_drift["fixture_contract"]["cases"].append(second)
        self.assertEqual("blocked", build_replay_call_plan(metadata_drift, REPO_ROOT)["status"])

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

    @staticmethod
    def load_slice_spec() -> dict:
        return json.loads(
            (
                REPO_ROOT
                / "validation"
                / "slice-specs"
                / "demo-copy-i32-ptr-arith.json"
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

    @classmethod
    def inline_renamed_slice_spec(cls) -> dict:
        spec = cls.load_slice_spec()
        spec["function_name"] = "transform_buffer"
        signature = spec["c_boundary"]["signatures"][0]
        signature["function"] = "transform_buffer"
        signature["parameters"][0].update(
            {"name": "source_items", "buffer_length_parameter": "count"}
        )
        signature["parameters"][1]["name"] = "count"
        signature["parameters"][2].update(
            {"name": "destination", "buffer_length_parameter": "count"}
        )
        spec["rust_boundary"]["public_api"][0]["name"] = "apply_buffer"
        expected = {
            "return_code": 0,
            "status": "ok",
            "source_items": [3, -2],
            "count": 2,
            "result_items": [3, -2],
            "source_note": "source projection",
            "canonical_note": "canonical projection",
            "write_note": "destination projection",
            "canonical_write_note": "canonical destination projection",
            "changed_items": 2,
        }
        spec["fixture_contract"] = {
            "cases": [
                {
                    "id": "nominal",
                    "input_ref": "inline",
                    "inputs": {"source_items": [3, -2], "count": 2},
                    "expected_outputs": expected,
                }
            ],
            "observable_outputs": list(expected),
        }
        return spec


if __name__ == "__main__":
    unittest.main()
