from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import jsonschema

from validation.tools.replay_call_plan_v2 import (
    _plan_sha256,
    render_replay_call_plan_v2,
    validate_replay_call_plan_v2,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReplayCallPlanV2IdentityTests(unittest.TestCase):
    def test_mutable_identity_is_checked_before_binding_observation_and_compiles(self) -> None:
        cases = self.cases()
        plan = self.plan(cases, mutable=True)

        validate_replay_call_plan_v2(plan)
        source = render_replay_call_plan_v2(plan, cases)

        capture = "core::ptr::from_mut(&mut actual_nominal_0_state)"
        call = "let actual_return: &mut State = return_state(&mut actual_nominal_0_state);"
        compare = "core::ptr::eq(core::ptr::from_mut(actual_return), expected_identity_nominal_0)"
        observation = "let observed_nominal_0_0: u32 = actual_nominal_0_state.value;"
        self.assertLess(source.index(capture), source.index(call))
        self.assertLess(source.index(call), source.index(compare))
        self.assertLess(source.index(compare), source.index(observation))
        self.assertIn("core::ptr::null()", source)
        self.assertIn("core::ptr::null_mut()", source)
        self.compile_rendered(source, mutable=True)

    def test_shared_identity_uses_shared_pointer_capture(self) -> None:
        cases = self.cases()
        plan = self.plan(cases, mutable=False)

        validate_replay_call_plan_v2(plan)
        source = render_replay_call_plan_v2(plan, cases)

        self.assertIn("core::ptr::from_ref(&actual_nominal_0_state)", source)
        self.assertIn("let actual_return: &State = return_state(&actual_nominal_0_state);", source)
        self.assertIn(
            "core::ptr::eq(core::ptr::from_ref(actual_return), expected_identity_nominal_0)",
            source,
        )
        self.compile_rendered(source, mutable=False)

    def test_identity_contract_and_fixture_drift_fail_closed(self) -> None:
        cases = self.cases()
        base = self.plan(cases, mutable=True)

        mutations = (
            ("identity return type", lambda p: p.__setitem__("return_type", "&State")),
            (
                "identity binding mutability",
                lambda p: (
                    p["bindings"][0].__setitem__("mutable", False),
                    p["parameters"][0]["source"].__setitem__("kind", "binding_borrow"),
                    p["parameters"][0].__setitem__("rust_type", "&State"),
                ),
            ),
            ("identity borrow type", lambda p: p["parameters"][0].__setitem__("rust_type", "&mut Other")),
        )
        for message, mutate in mutations:
            with self.subTest(message=message):
                drifted = copy.deepcopy(base)
                mutate(drifted)
                if drifted["parameters"][0]["rust_type"] != drifted["c_parameter_mappings"][0]["rust_type"]:
                    drifted["c_parameter_mappings"][0]["rust_type"] = drifted["parameters"][0]["rust_type"]
                self.rehash(drifted)
                with self.assertRaisesRegex(ValueError, message):
                    validate_replay_call_plan_v2(drifted)

        borrow_drift = self.plan(cases, mutable=False)
        borrow_drift["parameters"][0]["source"]["kind"] = "binding_value"
        borrow_drift["parameters"][0]["rust_type"] = "State"
        borrow_drift["c_parameter_mappings"][0]["rust_type"] = "State"
        borrow_drift["call_args"][0]["source"]["kind"] = "binding_value"
        self.rehash(borrow_drift)
        with self.assertRaisesRegex(ValueError, "identity borrow"):
            validate_replay_call_plan_v2(borrow_drift)

        duplicate = copy.deepcopy(base)
        duplicate["identity_assertions"].append(copy.deepcopy(duplicate["identity_assertions"][0]))
        self.rehash(duplicate)
        with self.assertRaisesRegex(ValueError, "exactly one identity assertion"):
            validate_replay_call_plan_v2(duplicate)

        extra = copy.deepcopy(base)
        extra["identity_assertions"][0]["expression"] = "arbitrary_rust()"
        self.rehash(extra)
        with self.assertRaisesRegex(ValueError, "not canonical"):
            validate_replay_call_plan_v2(extra)

        actual_drift = copy.deepcopy(base)
        actual_drift["identity_assertions"][0]["actual"] = "binding.state"
        self.rehash(actual_drift)
        with self.assertRaisesRegex(ValueError, "identity assertion contract"):
            validate_replay_call_plan_v2(actual_drift)

        hash_drift = copy.deepcopy(base)
        hash_drift["identity_assertions"][0]["fixture_field"] = "renamed_identity"
        with self.assertRaisesRegex(ValueError, "sha256 drifted"):
            validate_replay_call_plan_v2(hash_drift)

        false_cases = copy.deepcopy(cases)
        false_cases[0]["expected"]["same_identity"] = False
        with self.assertRaisesRegex(ValueError, "identity fixture must be true"):
            render_replay_call_plan_v2(base, false_cases)

        missing_cases = copy.deepcopy(cases)
        del missing_cases[0]["expected"]["same_identity"]
        with self.assertRaisesRegex(ValueError, "identity fixture must be true"):
            render_replay_call_plan_v2(base, missing_cases)

    def test_constant_and_null_initializers_are_bounded_and_type_exact(self) -> None:
        base = self.plan(self.cases(), mutable=True)
        validate_replay_call_plan_v2(base)

        bad_leaves = (
            {"kind": "constant_scalar", "rust_type": "u32", "encoding": "i32", "value": 1},
            {"kind": "constant_scalar", "rust_type": "u32", "encoding": "u32", "value": -1},
            {"kind": "null_pointer", "rust_type": "*const u8", "mutability": "shared"},
            {"kind": "null_pointer", "rust_type": "*const core::ffi::c_void", "mutability": "mutable"},
            {"kind": "expression", "rust_type": "u32", "value": "danger()"},
        )
        for leaf in bad_leaves:
            with self.subTest(leaf=leaf):
                drifted = copy.deepcopy(base)
                drifted["bindings"][0]["initializer"]["fields"][1]["value"] = leaf
                self.rehash(drifted)
                with self.assertRaises(ValueError):
                    validate_replay_call_plan_v2(drifted)

        supporting_drift = copy.deepcopy(base)
        supporting_drift["supporting_types"][1]["fields"][1]["rust_type"] = "usize"
        self.rehash(supporting_drift)
        with self.assertRaisesRegex(ValueError, "supporting types drifted"):
            validate_replay_call_plan_v2(supporting_drift)

        binding_drift = copy.deepcopy(base)
        binding_drift["bindings"][0]["rust_type"] = "Other"
        self.rehash(binding_drift)
        with self.assertRaisesRegex(ValueError, "binding initializer type"):
            validate_replay_call_plan_v2(binding_drift)

    def test_schema_accepts_identity_and_rejects_open_or_unsafe_forms(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "validation/auto-translation-template/ai-context-pack.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft7Validator.check_schema(schema)
        validator = jsonschema.Draft7Validator(
            {"$ref": "#/definitions/boundReplayCallPlan", "definitions": schema["definitions"]}
        )
        plan = self.plan(self.cases(), mutable=True)
        validator.validate(plan)

        extra = copy.deepcopy(plan)
        extra["identity_assertions"][0]["address"] = 1234
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(extra)

        pointer = copy.deepcopy(plan)
        pointer["bindings"][0]["initializer"]["fields"][4]["value"]["rust_type"] = "*const u8"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(pointer)

        arbitrary = copy.deepcopy(plan)
        arbitrary["bindings"][0]["initializer"]["fields"][1]["value"] = {
            "kind": "expression",
            "rust_type": "u32",
            "value": "danger()",
        }
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(arbitrary)

        scalar_mismatch = copy.deepcopy(plan)
        scalar_mismatch["bindings"][0]["initializer"]["fields"][1]["value"][
            "encoding"
        ] = "i32"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(scalar_mismatch)

    def test_plan_and_rendered_evidence_contain_no_address_literal(self) -> None:
        cases = self.cases()
        plan = self.plan(cases, mutable=True)
        rendered = render_replay_call_plan_v2(plan, cases)

        self.assertIsNone(re.search(r"\b0x[0-9A-Fa-f]+\b", json.dumps(plan)))
        self.assertIsNone(re.search(r"\b0x[0-9A-Fa-f]+\b", rendered))
        self.assertNotIn("as usize", rendered)
        self.assertNotIn("{:p}", rendered)

    @staticmethod
    def cases() -> list[dict]:
        return [
            {
                "id": "nominal",
                "inputs": {"value": 7},
                "expected": {"same_identity": True, "value": 7},
            }
        ]

    @classmethod
    def plan(cls, cases: list[dict], *, mutable: bool) -> dict:
        borrow = "binding_borrow_mut" if mutable else "binding_borrow"
        reference = "&mut State" if mutable else "&State"
        mutability = "mutable" if mutable else "shared"
        initializer = {
            "kind": "struct",
            "rust_type": "State",
            "fields": [
                {
                    "name": "value",
                    "value": {"kind": "fixture_field", "field": "value", "encoding": "u32"},
                },
                {
                    "name": "count",
                    "value": {
                        "kind": "constant_scalar",
                        "rust_type": "u32",
                        "encoding": "u32",
                        "value": 3,
                    },
                },
                {
                    "name": "delta",
                    "value": {
                        "kind": "constant_scalar",
                        "rust_type": "i32",
                        "encoding": "i32",
                        "value": -2,
                    },
                },
                {
                    "name": "enabled",
                    "value": {
                        "kind": "constant_scalar",
                        "rust_type": "bool",
                        "encoding": "bool",
                        "value": True,
                    },
                },
                {
                    "name": "cookie",
                    "value": {
                        "kind": "null_pointer",
                        "rust_type": "*const core::ffi::c_void",
                        "mutability": "shared",
                    },
                },
                {
                    "name": "meta",
                    "value": {
                        "kind": "struct",
                        "rust_type": "Meta",
                        "fields": [
                            {
                                "name": "limit",
                                "value": {
                                    "kind": "constant_scalar",
                                    "rust_type": "usize",
                                    "encoding": "usize",
                                    "value": 8,
                                },
                            },
                            {
                                "name": "context",
                                "value": {
                                    "kind": "null_pointer",
                                    "rust_type": "*mut core::ffi::c_void",
                                    "mutability": "mutable",
                                },
                            },
                        ],
                    },
                },
            ],
        }
        source = {"kind": borrow, "binding": "state"}
        parameter = {
            "position": 0,
            "name": "state",
            "rust_type": reference,
            "c_parameter": "state",
            "length_retained": False,
            "source": source,
        }
        plan = {
            "schema_version": 2,
            "status": "bound",
            "source_function_name": "return_state",
            "api_name": "return_state",
            "visibility": "pub",
            "abi": "Rust",
            "unsafe": False,
            "parameters": [parameter],
            "c_parameter_mappings": [
                {
                    "position": 0,
                    "c_parameter": "state",
                    "c_type": "void *",
                    "direction": "inout" if mutable else "input",
                    "rust_parameter": "state",
                    "rust_type": reference,
                }
            ],
            "omitted_c_parameters": [],
            "length_parameters_retained": [],
            "return_type": reference,
            "supporting_types": [
                {
                    "kind": "struct",
                    "name": "Meta",
                    "visibility": "pub",
                    "fields": [
                        {"name": "limit", "rust_type": "usize"},
                        {"name": "context", "rust_type": "*mut core::ffi::c_void"},
                    ],
                },
                {
                    "kind": "struct",
                    "name": "State",
                    "visibility": "pub",
                    "fields": [
                        {"name": "value", "rust_type": "u32"},
                        {"name": "count", "rust_type": "u32"},
                        {"name": "delta", "rust_type": "i32"},
                        {"name": "enabled", "rust_type": "bool"},
                        {"name": "cookie", "rust_type": "*const core::ffi::c_void"},
                        {"name": "meta", "rust_type": "Meta"},
                    ],
                },
            ],
            "bindings": [
                {
                    "name": "state",
                    "rust_type": "State",
                    "mutable": mutable,
                    "initializer": initializer,
                }
            ],
            "distinct_mutable_bindings": [],
            "call_args": [{"position": 0, "parameter": "state", "source": source}],
            "assertions": [
                {
                    "actual": "binding.state.value",
                    "fixture_field": "value",
                    "rust_type": "u32",
                    "encoding": "u32",
                }
            ],
            "identity_assertions": [
                {
                    "kind": "reference_identity",
                    "actual": "return",
                    "expected_binding": "state",
                    "mutability": mutability,
                    "fixture_field": "same_identity",
                }
            ],
            "fixture": {
                "path": "validation/fixtures/identity.json",
                "sha256": "a" * 64,
                "case_count": len(cases),
                "case_ids": [case["id"] for case in cases],
            },
        }
        plan["plan_sha256"] = _plan_sha256(plan)
        return plan

    @staticmethod
    def rehash(plan: dict) -> None:
        plan["plan_sha256"] = _plan_sha256(plan)

    def compile_rendered(self, rendered: str, *, mutable: bool) -> None:
        rustc = shutil.which("rustc")
        if rustc is None:
            self.skipTest("rustc is unavailable")
        reference = "&mut State" if mutable else "&State"
        source = f"""
#![allow(dead_code)]
struct Meta {{ limit: usize, context: *mut core::ffi::c_void }}
struct State {{
    value: u32,
    count: u32,
    delta: i32,
    enabled: bool,
    cookie: *const core::ffi::c_void,
    meta: Meta,
}}
fn return_state(state: {reference}) -> {reference} {{ state }}
fn replay() {{
{rendered}}}
"""
        with tempfile.TemporaryDirectory(prefix="replay-v2-identity-") as tmp:
            root = Path(tmp)
            source_path = root / "identity.rs"
            source_path.write_text(source, encoding="utf-8")
            completed = subprocess.run(
                [rustc, "--crate-type", "lib", "--emit", "metadata", str(source_path)],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
