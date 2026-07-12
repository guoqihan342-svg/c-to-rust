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


class ReplayCallPlanScalarTests(unittest.TestCase):
    SCALAR_SPECS = (
        "demo-add-one.json",
        "demo-enum-constant.json",
        "demo-implicit-integer-noop-cast.json",
        "demo-scalar-div-rem-contract.json",
        "demo-signed-rshift-contract.json",
        "demo-sparse-designated-array-lookup.json",
        "demo-target-abi-ulong-identity.json",
        "demo-while-countdown-positive.json",
    )

    def test_scalar_legacy_shapes_share_declarative_plan(self) -> None:
        for filename in self.SCALAR_SPECS:
            with self.subTest(filename=filename):
                spec = self.load_spec(filename)
                plan = build_replay_call_plan(spec, REPO_ROOT)
                self.assertEqual("bound", plan["status"])
                self.assertEqual(1, plan["schema_version"])
                source = render_declarative_replay_cases(spec, plan, REPO_ROOT)
                self.assertIn(f"{plan['api_name']}(", source)
                self.assertNotIn("struct FixtureCase", source)

    def test_scalar_plan_uses_declared_api_after_complete_rename(self) -> None:
        spec = self.load_spec("demo-add-one.json")
        old_name = spec["function_name"]
        spec["function_name"] = "renamed_scalar_source"
        signature = next(
            item for item in spec["c_boundary"]["signatures"] if item["function"] == old_name
        )
        signature["function"] = "renamed_scalar_source"
        spec["rust_boundary"]["public_api"][0]["name"] = "renamed_scalar_api"
        plan = build_replay_call_plan(spec, REPO_ROOT)
        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)
        self.assertIn("renamed_scalar_api(", source)
        self.assertNotIn(f"{old_name}(", source)

    def test_scalar_fixture_metadata_and_u64_are_bound(self) -> None:
        signed = build_replay_call_plan(
            self.load_spec("demo-signed-rshift-contract.json"), REPO_ROOT
        )
        self.assertEqual(
            ["status", "contract"],
            [item["fixture_field"] for item in signed["fixture_assertions"]],
        )
        unsigned = build_replay_call_plan(
            self.load_spec("demo-target-abi-ulong-identity.json"), REPO_ROOT
        )
        self.assertEqual("u64", unsigned["return_type"])
        self.assertEqual("u64", unsigned["parameters"][0]["source"]["encoding"])

    def test_scalar_metadata_and_plan_tampering_fail_closed(self) -> None:
        plan = build_replay_call_plan(self.load_spec("demo-add-one.json"), REPO_ROOT)
        drift = copy.deepcopy(plan)
        drift["fixture_assertions"][0]["expected"] = "failed"
        with self.assertRaisesRegex(ValueError, "sha256 drifted"):
            validate_replay_call_plan(drift)

        spec = self.load_spec("demo-add-one.json")
        spec["fixture_contract"]["cases"] = [
            {
                "id": "metadata-drift",
                "input_ref": "inline",
                "inputs": {"value": 0},
                "expected_outputs": {"return_value": 1, "status": "failed"},
            }
        ]
        blocked = build_replay_call_plan(spec, REPO_ROOT)
        self.assertEqual("blocked", blocked["status"])
        self.assertIn("metadata field status drifted", blocked["reason"])

    def test_context_schema_accepts_scalar_fixture_assertions(self) -> None:
        schema = json.loads(
            (
                REPO_ROOT
                / "validation"
                / "auto-translation-template"
                / "ai-context-pack.schema.json"
            ).read_text(encoding="utf-8")
        )
        plan_schema = {
            "$ref": "#/definitions/boundReplayCallPlan",
            "definitions": schema["definitions"],
        }
        for filename in self.SCALAR_SPECS:
            with self.subTest(filename=filename):
                plan = build_replay_call_plan(self.load_spec(filename), REPO_ROOT)
                jsonschema.Draft7Validator(plan_schema).validate(plan)

    @staticmethod
    def load_spec(filename: str) -> dict:
        return json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / filename).read_text(
                encoding="utf-8"
            )
        )


if __name__ == "__main__":
    unittest.main()
