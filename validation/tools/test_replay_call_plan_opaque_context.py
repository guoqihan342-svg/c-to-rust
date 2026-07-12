from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import jsonschema

from validation.tools.replay_call_plan import _fixture_binding
from validation.tools.replay_call_plan_opaque_context import (
    build_opaque_context_plan,
    supports_opaque_context_plan,
)
from validation.tools.replay_call_plan_v2 import (
    _plan_sha256,
    render_replay_call_plan_v2,
    validate_replay_call_plan_v2,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class OpaqueContextPlanTests(unittest.TestCase):
    def test_real_delete_contract_produces_safe_v2_candidate_shape(self) -> None:
        spec = self.real_spec("flashdb-real-fdb-kv-del.json")
        plan = self.build(spec)

        self.assertTrue(supports_opaque_context_plan(spec))
        self.assertEqual((2, "bound"), (plan["schema_version"], plan["status"]))
        self.assertEqual(["db", "key"], [item["name"] for item in plan["parameters"]])
        self.assertEqual(
            ["binding_borrow", "string_ref"],
            [plan["parameters"][0]["source"]["kind"], plan["parameters"][1]["source"]["encoding"]],
        )
        self.assertEqual("&KvDbFixture", plan["parameters"][0]["rust_type"])
        self.assertEqual("&str", plan["parameters"][1]["rust_type"])
        self.assertEqual("i32", plan["return_type"])
        self.assertEqual("return_code", plan["assertions"][0]["fixture_field"])
        self.assertEqual(plan["plan_sha256"], _plan_sha256(plan))
        self.assert_safe_plan(plan)

    def test_real_set_contract_closes_nullable_string_without_raw_pointer(self) -> None:
        spec = self.real_spec("flashdb-real-fdb-kv-set.json")
        plan = self.build(spec)

        self.assertEqual(["db", "key", "value"], [item["name"] for item in plan["parameters"]])
        self.assertEqual(
            ["binding_borrow", "string_ref", "optional_string_ref"],
            [
                plan["parameters"][0]["source"]["kind"],
                plan["parameters"][1]["source"]["encoding"],
                plan["parameters"][2]["source"]["encoding"],
            ],
        )
        self.assertEqual("Option<&str>", plan["parameters"][2]["rust_type"])
        self.assertEqual(2, plan["fixture"]["case_count"])
        initializer = plan["bindings"][0]["initializer"]
        self.assertEqual("fixture_enum_constant", initializer["fields"][0]["value"]["kind"])
        self.assertEqual("db_state", initializer["fields"][0]["value"]["field"])
        self.assertIs(initializer["fields"][0]["value"]["value"], False)
        self.assertEqual("owned_string", initializer["fields"][1]["value"]["kind"])
        self.assert_safe_plan(plan)

    def test_real_contracts_validate_render_and_compile(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "validation/auto-translation-template/ai-context-pack.schema.json")
            .read_text(encoding="utf-8")
        )
        plan_schema = {
            "$ref": "#/definitions/boundReplayCallPlan",
            "definitions": schema["definitions"],
        }
        for filename in (
            "flashdb-real-fdb-kv-del.json",
            "flashdb-real-fdb-kv-set.json",
        ):
            with self.subTest(filename=filename):
                spec = self.real_spec(filename)
                fixture = _fixture_binding(spec, REPO_ROOT)
                plan = self.build(spec)
                jsonschema.Draft7Validator(plan_schema).validate(plan)
                validate_replay_call_plan_v2(plan)
                rendered = render_replay_call_plan_v2(plan, fixture["cases"])
                self.compile_rendered(plan, rendered)

                drifted = copy.deepcopy(fixture["cases"])
                drifted[0]["inputs"]["db_state"] = "initialized"
                with self.assertRaisesRegex(ValueError, "fixture enum value drifted"):
                    render_replay_call_plan_v2(plan, drifted)

    def test_complete_symbol_and_fixture_rename_is_project_independent(self) -> None:
        spec, fixture = self.neutral_spec()
        plan = build_opaque_context_plan(spec, spec["replay_contract"], fixture)

        self.assertEqual("remove_entry", plan["source_function_name"])
        self.assertEqual("remove_model", plan["api_name"])
        self.assertEqual(["store", "label"], [item["name"] for item in plan["parameters"]])
        self.assertEqual("StoreFixture", plan["bindings"][0]["rust_type"])
        self.assertEqual(
            ["ready", "title"],
            [item["name"] for item in plan["supporting_types"][0]["fields"]],
        )
        self.assertEqual("result", plan["assertions"][0]["fixture_field"])
        serialized = json.dumps(plan).lower()
        for forbidden in ("flashdb", "fdb", "kvdbfixture", "return_code", "db_name"):
            self.assertNotIn(forbidden, serialized)
        self.assert_safe_plan(plan)

    def test_invalid_state_nullable_type_and_parameter_mapping_fail_closed(self) -> None:
        cases: list[tuple[str, dict, dict, str]] = []

        state_spec, state_fixture = self.neutral_spec()
        state_fixture["cases"][0]["inputs"]["lifecycle"] = "initialized"
        cases.append(("state", state_spec, state_fixture, "fixture state is unsupported"))

        state_contract, state_contract_fixture = self.neutral_spec()
        state_contract["replay_contract"]["context"]["state"]["required_value"] = "initialized"
        cases.append(("state-contract", state_contract, state_contract_fixture, "must close uninitialized_named"))

        nullable, nullable_fixture = self.neutral_spec(optional=True)
        nullable["replay_contract"]["inputs"][1]["nullable"] = False
        cases.append(("nullable", nullable, nullable_fixture, "nullability or Rust type drifted"))

        fixture_nullable, fixture_nullable_binding = self.neutral_spec()
        fixture_nullable_binding["cases"][0]["inputs"]["label"] = None
        cases.append(("fixture-nullable", fixture_nullable, fixture_nullable_binding, "fixture string nullability"))

        rust_type, rust_type_fixture = self.neutral_spec()
        rust_type["replay_contract"]["inputs"][0]["rust_type"] = "String"
        cases.append(("rust-type", rust_type, rust_type_fixture, "nullability or Rust type drifted"))

        c_type, c_type_fixture = self.neutral_spec()
        c_type["c_boundary"]["signatures"][0]["parameters"][1]["c_type"] = "const unsigned char *"
        cases.append(("c-type", c_type, c_type_fixture, "C parameter type drifted"))

        mapping, mapping_fixture = self.neutral_spec()
        mapping["c_boundary"]["signatures"][0]["parameters"].reverse()
        cases.append(("mapping", mapping, mapping_fixture, "do not close the C signature"))

        for label, spec, fixture, message in cases:
            with self.subTest(label=label):
                if label not in {"state", "fixture-nullable"}:
                    self.assertFalse(supports_opaque_context_plan(spec))
                with self.assertRaisesRegex(ValueError, message):
                    build_opaque_context_plan(spec, spec["replay_contract"], fixture)

    def test_arbitrary_expression_and_unknown_codec_fail_closed(self) -> None:
        expression, expression_fixture = self.neutral_spec()
        expression["replay_contract"]["context"]["rust_expression"] = "unsafe { zeroed() }"
        with self.assertRaisesRegex(ValueError, "context shape drifted"):
            build_opaque_context_plan(expression, expression["replay_contract"], expression_fixture)

        codec, codec_fixture = self.neutral_spec()
        codec["replay_contract"]["inputs"][0]["codec"] = "raw_pointer"
        with self.assertRaisesRegex(ValueError, "codec is unsupported"):
            build_opaque_context_plan(codec, codec["replay_contract"], codec_fixture)

    @staticmethod
    def assert_safe_plan(plan: dict) -> None:
        serialized = json.dumps(plan).lower()
        for forbidden in (
            "*mut", "*const", "core::ptr", "marker", "zeroed", "transmute",
            "address_literal", "rust_expression",
        ):
            if forbidden in serialized:
                raise AssertionError(f"unsafe opaque-context token leaked into plan: {forbidden}")

    def compile_rendered(self, plan: dict, rendered: str) -> None:
        rustc = shutil.which("rustc")
        if rustc is None:
            self.skipTest("rustc is unavailable")
        definitions = []
        for item in plan["supporting_types"]:
            fields = ", ".join(
                f"{field['name']}: {field['rust_type']}" for field in item["fields"]
            )
            definitions.append(f"struct {item['name']} {{ {fields} }}")
        parameters = ", ".join(
            f"{item['name']}: {item['rust_type']}" for item in plan["parameters"]
        )
        source = (
            "#![allow(dead_code, unused_variables)]\n"
            + "\n".join(definitions)
            + f"\nfn {plan['api_name']}({parameters}) -> i32 {{ 7i32 }}\n"
            + f"fn replay() {{\n{rendered}}}\n"
        )
        with tempfile.TemporaryDirectory(prefix="opaque-context-plan-") as tmp:
            path = Path(tmp) / "opaque.rs"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [rustc, "--crate-type", "lib", "--emit", "metadata", str(path)],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)

    @staticmethod
    def real_spec(filename: str) -> dict:
        return json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / filename).read_text(encoding="utf-8")
        )

    @staticmethod
    def build(spec: dict) -> dict:
        return build_opaque_context_plan(
            spec,
            spec["replay_contract"],
            _fixture_binding(spec, REPO_ROOT),
        )

    @staticmethod
    def neutral_spec(*, optional: bool = False) -> tuple[dict, dict]:
        inputs = [
            {
                "parameter": "label",
                "c_type": "const char *",
                "rust_type": "&str",
                "fixture_field": "label",
                "codec": "string_ref",
                "nullable": False,
            }
        ]
        signature_parameters = [
            {"name": "store", "c_type": "opaque_store_t", "direction": "input"},
            {"name": "label", "c_type": "const char *", "direction": "input"},
        ]
        case_inputs = {
            "lifecycle": "uninitialized_named",
            "store_title": "unit-store",
            "label": "counter",
        }
        if optional:
            inputs.append(
                {
                    "parameter": "payload",
                    "c_type": "const char *",
                    "rust_type": "Option<&str>",
                    "fixture_field": "payload",
                    "codec": "optional_string_ref",
                    "nullable": True,
                }
            )
            signature_parameters.append(
                {"name": "payload", "c_type": "const char *", "direction": "input"}
            )
            case_inputs["payload"] = None
        expected = {"result": 9}
        spec = {
            "function_name": "remove_entry",
            "c_boundary": {
                "signatures": [
                    {
                        "function": "remove_entry",
                        "return_type": "store_status_t",
                        "parameters": signature_parameters,
                    }
                ]
            },
            "rust_boundary": {
                "public_api": [{"name": "remove_model", "visibility": "public"}]
            },
            "fixture_contract": {
                "cases": [{"id": "cold", "expected_outputs": expected}],
                "observable_outputs": ["result"],
                "behavior_fields": ["result"],
            },
            "replay_contract": {
                "schema_version": 1,
                "kind": "opaque_context_return_code",
                "context": {
                    "parameter": "store",
                    "c_type": "opaque_store_t",
                    "rust_type": "StoreFixture",
                    "state": {
                        "fixture_field": "lifecycle",
                        "required_value": "uninitialized_named",
                        "rust_field": "ready",
                        "rust_type": "bool",
                        "constant": False,
                    },
                    "name": {
                        "fixture_field": "store_title",
                        "rust_field": "title",
                        "rust_type": "String",
                        "initializer": "owned_string",
                    },
                    "source": "binding_borrow",
                },
                "inputs": inputs,
                "return": {
                    "c_type": "store_status_t",
                    "rust_type": "i32",
                    "fixture_field": "result",
                    "codec": "i32",
                },
            },
        }
        fixture = {
            "path": "inline-neutral-fixture.json",
            "sha256": "a" * 64,
            "cases": [{"id": "cold", "inputs": case_inputs, "expected": expected}],
        }
        return spec, fixture


if __name__ == "__main__":
    unittest.main()
