from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import jsonschema

from validation.tools.replay_call_plan_v2 import (
    _encoded_literal,
    _plan_sha256,
    _value_matches,
    render_replay_call_plan_v2,
    validate_replay_call_plan_v2,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReplayCallPlanV2DynamicTests(unittest.TestCase):
    def test_canonical_dynamic_plan_validates_and_renders(self) -> None:
        cases = self.cases()
        plan = self.plan(cases)

        validate_replay_call_plan_v2(plan)
        source = render_replay_call_plan_v2(plan, cases)

        self.assertIn(
            "let mut actual_nominal_0_output: Vec<i32> = vec![0i32; 2usize];",
            source,
        )
        self.assertIn(
            "copy_values(&[4i32, -2i32], 2i32, &mut actual_nominal_0_output)",
            source,
        )
        self.assertIn(
            "let observed_nominal_0_1: Vec<i32> = actual_nominal_0_output;",
            source,
        )
        self.assertEqual(6, source.count("fixture relation"))

    def test_empty_vectors_render_without_weakening_the_bound(self) -> None:
        cases = [self.cases()[1]]
        source = render_replay_call_plan_v2(self.plan(cases), cases)

        self.assertIn("vec![0i32; 0usize]", source)
        self.assertIn("copy_values(&[], 0i32", source)
        self.assertIn("vec![0i32; 0usize].len()", source)

    def test_negative_and_over_limit_lengths_fail_closed(self) -> None:
        for length in (-1, 4):
            with self.subTest(length=length):
                cases = [copy.deepcopy(self.cases()[0])]
                cases[0]["inputs"]["len"] = length
                if length >= 0:
                    cases[0]["expected"]["out_values"] = [0] * length
                    cases[0]["expected"]["count"] = length
                with self.assertRaisesRegex(ValueError, "length fixture is out of bounds"):
                    render_replay_call_plan_v2(self.plan(cases), cases)

    def test_i32_slice_and_i32_vec_codecs_reject_more_than_4096_items(self) -> None:
        at_limit = [0] * 4096
        over_limit = [0] * 4097
        for codec in ("i32_slice", "i32_vec"):
            with self.subTest(codec=codec):
                self.assertTrue(_value_matches(at_limit, codec))
                self.assertFalse(_value_matches(over_limit, codec))
                self.assertTrue(_encoded_literal(at_limit, codec))
                with self.assertRaisesRegex(ValueError, f"encoding {codec}"):
                    _encoded_literal(over_limit, codec)

        slice_cases = [copy.deepcopy(self.cases()[0])]
        slice_cases[0]["inputs"]["values"] = [0] * 4097
        with self.assertRaisesRegex(ValueError, "encoding i32_slice"):
            render_replay_call_plan_v2(self.plan(slice_cases), slice_cases)

        vec_cases = [copy.deepcopy(self.cases()[0])]
        vec_cases[0]["expected"]["out_values"] = [0] * 4097
        vec_plan = self.plan(vec_cases)
        vec_plan["fixture_relations"] = [vec_plan["fixture_relations"][0]]
        self.rehash(vec_plan)
        with self.assertRaisesRegex(ValueError, "encoding i32_vec"):
            render_replay_call_plan_v2(vec_plan, vec_cases)

    def test_whole_binding_is_limited_to_well_typed_dynamic_vectors(self) -> None:
        base = self.plan(self.cases())
        initializers = (
            (
                "[i32; 1]",
                {
                    "kind": "array_repeat",
                    "rust_type": "[i32; 1]",
                    "element_type": "i32",
                    "length": 1,
                    "value": 0,
                },
            ),
            (
                "State",
                {
                    "kind": "struct",
                    "rust_type": "State",
                    "fields": [
                        {
                            "name": "value",
                            "value": {
                                "kind": "fixture_field",
                                "field": "len",
                                "encoding": "u32",
                            },
                        }
                    ],
                },
            ),
        )
        for rust_type, initializer in initializers:
            with self.subTest(rust_type=rust_type):
                drifted = copy.deepcopy(base)
                drifted["bindings"][0]["rust_type"] = rust_type
                drifted["bindings"][0]["initializer"] = initializer
                self.rehash(drifted)
                with self.assertRaisesRegex(ValueError, "assertion binding path"):
                    validate_replay_call_plan_v2(drifted)

        type_drift = copy.deepcopy(base)
        type_drift["assertions"][1]["rust_type"] = "i32"
        type_drift["assertions"][1]["encoding"] = "i32"
        self.rehash(type_drift)
        with self.assertRaisesRegex(ValueError, "whole binding assertion type"):
            validate_replay_call_plan_v2(type_drift)

        binding_type_drift = copy.deepcopy(base)
        binding_type_drift["bindings"][0]["rust_type"] = "[i32; 1]"
        self.rehash(binding_type_drift)
        with self.assertRaisesRegex(ValueError, "vector binding type"):
            validate_replay_call_plan_v2(binding_type_drift)

        slice_type_drift = copy.deepcopy(base)
        slice_type_drift["parameters"][0]["rust_type"] = "Vec<i32>"
        slice_type_drift["c_parameter_mappings"][0]["rust_type"] = "Vec<i32>"
        self.rehash(slice_type_drift)
        with self.assertRaisesRegex(ValueError, "i32 slice parameter type"):
            validate_replay_call_plan_v2(slice_type_drift)

    def test_relation_drift_and_noncanonical_relations_fail_closed(self) -> None:
        cases = self.cases()
        plan = self.plan(cases)
        drifted_cases = copy.deepcopy(cases)
        drifted_cases[0]["expected"]["echoed_values"] = [4, -1]
        with self.assertRaisesRegex(ValueError, "fixture relation drifted"):
            render_replay_call_plan_v2(plan, drifted_cases)

        encoding_drift = copy.deepcopy(plan)
        encoding_drift["fixture_relations"][0]["right"]["encoding"] = "usize"
        self.rehash(encoding_drift)
        with self.assertRaisesRegex(ValueError, "equal relation encodings"):
            validate_replay_call_plan_v2(encoding_drift)

        duplicate = copy.deepcopy(plan)
        duplicate["fixture_relations"].append(
            copy.deepcopy(duplicate["fixture_relations"][0])
        )
        self.rehash(duplicate)
        with self.assertRaisesRegex(ValueError, "relations must be unique"):
            validate_replay_call_plan_v2(duplicate)

        negative_numeric = copy.deepcopy(cases)
        negative_numeric[0]["inputs"]["len"] = -1
        negative_numeric[0]["expected"]["count"] = 0
        numeric_only = copy.deepcopy(plan)
        numeric_only["bindings"][0]["initializer"]["length"]["field"] = "safe_len"
        numeric_only["fixture_relations"] = [
            copy.deepcopy(numeric_only["fixture_relations"][2])
        ]
        for case in negative_numeric:
            case["inputs"]["safe_len"] = len(case["expected"]["out_values"])
        self.rehash(numeric_only)
        with self.assertRaisesRegex(ValueError, "numeric relation i32 must be non-negative"):
            render_replay_call_plan_v2(numeric_only, negative_numeric)

    def test_context_pack_schema_accepts_dynamic_plan_and_rejects_drift(self) -> None:
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
        validator = jsonschema.Draft7Validator(plan_schema)
        plan = self.plan(self.cases())

        validator.validate(plan)
        source_drift = copy.deepcopy(plan)
        source_drift["parameters"][0]["source"]["encoding"] = "i32_slice_bad"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(source_drift)

        initializer_drift = copy.deepcopy(plan)
        initializer_drift["bindings"][0]["initializer"]["length"]["maximum"] = 0
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(initializer_drift)

        relation_drift = copy.deepcopy(plan)
        relation_drift["fixture_relations"][0]["right"]["encoding"] = "usize"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(relation_drift)

    @staticmethod
    def cases() -> list[dict]:
        return [
            {
                "id": "nominal",
                "inputs": {"values": [4, -2], "len": 2},
                "expected": {
                    "return_code": 0,
                    "out_values": [0, 0],
                    "echoed_values": [4, -2],
                    "count": 2,
                },
            },
            {
                "id": "empty",
                "inputs": {"values": [], "len": 0},
                "expected": {
                    "return_code": 0,
                    "out_values": [],
                    "echoed_values": [],
                    "count": 0,
                },
            },
        ]

    @classmethod
    def plan(cls, cases: list[dict]) -> dict:
        plan = {
            "schema_version": 2,
            "status": "bound",
            "source_function_name": "copy_values",
            "api_name": "copy_values",
            "visibility": "pub",
            "abi": "Rust",
            "unsafe": False,
            "parameters": [
                {
                    "position": 0,
                    "name": "values",
                    "rust_type": "&[i32]",
                    "c_parameter": "values",
                    "length_retained": False,
                    "source": {
                        "kind": "fixture_field",
                        "field": "values",
                        "encoding": "i32_slice",
                    },
                },
                {
                    "position": 1,
                    "name": "len",
                    "rust_type": "i32",
                    "c_parameter": "len",
                    "length_retained": True,
                    "source": {
                        "kind": "fixture_field",
                        "field": "len",
                        "encoding": "i32",
                    },
                },
                {
                    "position": 2,
                    "name": "output",
                    "rust_type": "&mut Vec<i32>",
                    "c_parameter": "output",
                    "length_retained": False,
                    "source": {"kind": "binding_borrow_mut", "binding": "output"},
                },
            ],
            "c_parameter_mappings": [
                {
                    "position": 0,
                    "c_parameter": "values",
                    "c_type": "const int*",
                    "direction": "input",
                    "rust_parameter": "values",
                    "rust_type": "&[i32]",
                },
                {
                    "position": 1,
                    "c_parameter": "len",
                    "c_type": "int",
                    "direction": "input",
                    "rust_parameter": "len",
                    "rust_type": "i32",
                },
                {
                    "position": 2,
                    "c_parameter": "output",
                    "c_type": "int*",
                    "direction": "output",
                    "rust_parameter": "output",
                    "rust_type": "&mut Vec<i32>",
                },
            ],
            "omitted_c_parameters": [],
            "length_parameters_retained": ["len"],
            "return_type": "i32",
            "supporting_types": [],
            "bindings": [
                {
                    "name": "output",
                    "rust_type": "Vec<i32>",
                    "mutable": True,
                    "initializer": {
                        "kind": "vec_repeat",
                        "rust_type": "Vec<i32>",
                        "element_type": "i32",
                        "length": {
                            "kind": "fixture_field",
                            "field": "len",
                            "encoding": "i32",
                            "maximum": 3,
                        },
                        "value": 0,
                    },
                }
            ],
            "distinct_mutable_bindings": [],
            "call_args": [],
            "assertions": [
                {
                    "actual": "return",
                    "fixture_field": "return_code",
                    "rust_type": "i32",
                    "encoding": "i32",
                },
                {
                    "actual": "binding.output",
                    "fixture_field": "out_values",
                    "rust_type": "Vec<i32>",
                    "encoding": "i32_vec",
                },
            ],
            "fixture_relations": [
                {
                    "kind": "equal",
                    "left": {
                        "section": "inputs",
                        "field": "values",
                        "encoding": "i32_vec",
                    },
                    "right": {
                        "section": "expected",
                        "field": "echoed_values",
                        "encoding": "i32_vec",
                    },
                },
                {
                    "kind": "length_equals",
                    "collection": {
                        "section": "expected",
                        "field": "out_values",
                        "encoding": "i32_vec",
                    },
                    "length": {
                        "section": "inputs",
                        "field": "len",
                        "encoding": "i32",
                    },
                },
                {
                    "kind": "numeric_equal",
                    "left": {
                        "section": "inputs",
                        "field": "len",
                        "encoding": "i32",
                    },
                    "right": {
                        "section": "expected",
                        "field": "count",
                        "encoding": "usize",
                    },
                },
            ],
            "fixture": {
                "path": "validation/fixtures/dynamic-i32.json",
                "sha256": "0" * 64,
                "case_count": len(cases),
                "case_ids": [case["id"] for case in cases],
            },
        }
        plan["call_args"] = [
            {
                "position": item["position"],
                "parameter": item["name"],
                "source": item["source"],
            }
            for item in plan["parameters"]
        ]
        cls.rehash(plan)
        return plan

    @staticmethod
    def rehash(plan: dict) -> None:
        plan["plan_sha256"] = _plan_sha256(plan)


if __name__ == "__main__":
    unittest.main()
