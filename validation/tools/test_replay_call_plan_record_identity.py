from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import jsonschema

from validation.tools.replay_call_plan import _fixture_binding
from validation.tools.replay_call_plan_record_identity import (
    build_record_pointer_identity_plan,
    supports_record_pointer_identity_plan,
)
from validation.tools.replay_call_plan_v2 import (
    render_replay_call_plan_v2,
    validate_replay_call_plan_v2,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class RecordPointerIdentityPlanTests(unittest.TestCase):
    def test_real_tsl_to_blob_contract_produces_bound_v2_plan(self) -> None:
        spec = self.real_spec()
        plan = self.build(spec)

        self.assertTrue(supports_record_pointer_identity_plan(spec))
        self.assertEqual((2, "bound"), (plan["schema_version"], plan["status"]))
        self.assertEqual(["tsl", "blob"], [item["name"] for item in plan["parameters"]])
        self.assertEqual(
            ["binding_borrow", "binding_borrow_mut"],
            [item["source"]["kind"] for item in plan["parameters"]],
        )
        self.assertEqual("&mut FdbBlob", plan["return_type"])
        self.assertEqual([["blob", "tsl"]], plan["distinct_mutable_bindings"])
        self.assertEqual(
            [
                {
                    "kind": "reference_identity",
                    "actual": "return",
                    "expected_binding": "blob",
                    "mutability": "mutable",
                    "fixture_field": "return_same_blob",
                }
            ],
            plan["identity_assertions"],
        )
        self.assertEqual(
            ["blob.saved.addr", "blob.saved.meta_addr", "blob.saved.len"],
            [item["fixture_field"] for item in plan["assertions"]],
        )
        self.assertEqual(
            ["FdbTslAddr", "FdbTsl", "FdbBlobSaved", "FdbBlob"],
            [item["name"] for item in plan["supporting_types"]],
        )
        output = next(item for item in plan["bindings"] if item["name"] == "blob")
        leaves = self.initializer_leaves(output["initializer"])
        self.assertEqual("usize", leaves[("saved", "len")]["encoding"])
        self.assertEqual("constant_scalar", leaves[("size",)]["kind"])
        self.assertEqual("null_pointer", leaves[("buf",)]["kind"])
        self.assertEqual("mutable", leaves[("buf",)]["mutability"])
        self.assertEqual(3, plan["fixture"]["case_count"])
        self.assertEqual(64, len(plan["plan_sha256"]))

    def test_real_kv_to_blob_contract_uses_the_generic_v2_renderer(self) -> None:
        spec = json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-to-blob.json")
            .read_text(encoding="utf-8")
        )
        plan = self.build(spec)

        validate_replay_call_plan_v2(plan)
        source = render_replay_call_plan_v2(
            plan, _fixture_binding(spec, REPO_ROOT)["cases"]
        )

        self.assertEqual((2, "bound"), (plan["schema_version"], plan["status"]))
        self.assertEqual("fdb_kv_to_blob", plan["api_name"])
        self.assertEqual([["blob", "kv"]], plan["distinct_mutable_bindings"])
        self.assertIn("fdb_kv_to_blob(", source)
        self.assertNotIn("record_projection_identity_return", source)

    def test_neutral_inline_contract_survives_complete_symbol_and_field_rename(self) -> None:
        spec = self.neutral_spec()
        plan = self.build(spec)

        self.assertEqual("remap_record", plan["source_function_name"])
        self.assertEqual("apply_record", plan["api_name"])
        self.assertEqual(["destination", "source"], [item["name"] for item in plan["parameters"]])
        self.assertEqual(
            ["binding_borrow_mut", "binding_borrow"],
            [item["source"]["kind"] for item in plan["parameters"]],
        )
        self.assertEqual("binding.destination.payload.value", plan["assertions"][0]["actual"])
        self.assertEqual("result.payload.value", plan["assertions"][0]["fixture_field"])
        self.assertEqual("return_same_destination", plan["identity_assertions"][0]["fixture_field"])
        source = next(item for item in plan["bindings"] if item["name"] == "source")
        leaves = self.initializer_leaves(source["initializer"])
        self.assertEqual(["source_case", "nested.value"], leaves[("header", "amount")]["path"])
        self.assertNotIn("fdb", json.dumps(plan).lower())
        self.assertNotIn("tsl", json.dumps(plan).lower())

    def test_fixture_and_observable_drift_fail_closed(self) -> None:
        cases: list[tuple[str, dict, str]] = []

        missing_nested = self.neutral_spec()
        del missing_nested["fixture_contract"]["cases"][0]["inputs"]["source_case"]["nested.value"]
        cases.append(("nested", missing_nested, "input fixture shape drifted"))

        wrong_identity = self.neutral_spec()
        wrong_identity["fixture_contract"]["cases"][0]["expected_outputs"][
            "return_same_destination"
        ] = False
        cases.append(("identity", wrong_identity, "expected outputs drifted"))

        extra_observable = self.neutral_spec()
        extra_observable["fixture_contract"]["observable_outputs"].append("extra")
        extra_observable["fixture_contract"]["behavior_fields"].append("extra")
        cases.append(("observable", extra_observable, "observable outputs are not closed"))

        duplicate_case = self.neutral_spec()
        duplicate_case["fixture_contract"]["cases"].append(
            copy.deepcopy(duplicate_case["fixture_contract"]["cases"][0])
        )
        cases.append(("case-id", duplicate_case, "fixture case ids are invalid"))

        for label, spec, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    self.build(spec)

    def test_contract_type_path_duplicate_and_prefix_drift_fail_closed(self) -> None:
        cases: list[tuple[str, dict, str]] = []

        conversion = self.neutral_spec()
        conversion["replay_contract"]["output"]["fields"][0]["conversion"] = "identity"
        cases.append(("conversion", conversion, "scalar conversion is inconsistent"))

        duplicate = self.neutral_spec()
        duplicate["replay_contract"]["input"]["fields"].append(
            copy.deepcopy(duplicate["replay_contract"]["input"]["fields"][0])
        )
        cases.append(("duplicate", duplicate, "duplicate input fixture path"))

        prefix = self.neutral_spec()
        prefix["replay_contract"]["output"]["defaults"].append(
            {
                "rust_field_path": ["payload"],
                "rust_type_path": [],
                "rust_scalar_type": "usize",
                "value": {"kind": "zero"},
            }
        )
        cases.append(("prefix", prefix, "prefix conflict"))

        type_path = self.neutral_spec()
        type_path["replay_contract"]["output"]["fields"][0]["rust_type_path"] = []
        cases.append(("type-path", type_path, "type path length drifted"))

        output_mapping = self.neutral_spec()
        output_mapping["replay_contract"]["output"]["fields"][0]["expected_output"] = (
            "result.payload.renamed"
        )
        cases.append(("output", output_mapping, "observable outputs are not closed"))

        for label, spec, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    self.build(spec)

    def test_signature_and_noalias_proof_drift_fail_closed(self) -> None:
        cases: list[tuple[str, dict, str]] = []

        order_closed = self.neutral_spec()
        order_closed["c_boundary"]["signatures"][0]["parameters"].reverse()
        plan = self.build(order_closed)
        self.assertEqual(["source", "destination"], [item["name"] for item in plan["parameters"]])

        unknown_parameter = self.neutral_spec()
        unknown_parameter["c_boundary"]["signatures"][0]["parameters"][0]["name"] = "other"
        cases.append(("parameter", unknown_parameter, "do not close the C signature"))

        noalias_ref = self.neutral_spec()
        noalias_ref["replay_contract"]["noalias_refs"] = [["output", "input"]]
        cases.append(("contract-noalias", noalias_ref, "must close input/output exactly"))

        noalias_pair = self.neutral_spec()
        noalias_pair["c_boundary"]["pointer_contract"]["noalias_required"] = []
        cases.append(("pointer-noalias", noalias_pair, "noalias proof is not closed"))

        proof = self.neutral_spec()
        proof["c_boundary"]["pointer_contract"]["actual_argument_noalias_proof"]["proven"] = False
        cases.append(("proof", proof, "noalias proof is incomplete"))

        role = self.neutral_spec()
        role["c_boundary"]["pointer_contract"]["output_pointers"][0]["name"] = "other"
        cases.append(("role", role, "pointer roles do not close"))

        for label, spec, message in cases:
            with self.subTest(label=label):
                self.assertFalse(supports_record_pointer_identity_plan(spec))
                with self.assertRaisesRegex(ValueError, message):
                    self.build(spec)

    def test_schema_accepts_real_record_identity_plan(self) -> None:
        plan = self.build(self.real_spec())
        schema = json.loads(
            (REPO_ROOT / "validation" / "auto-translation-template" / "ai-context-pack.schema.json")
            .read_text(encoding="utf-8")
        )
        plan_schema = {"$ref": "#/definitions/boundReplayCallPlan", "definitions": schema["definitions"]}
        jsonschema.Draft7Validator(plan_schema).validate(plan)
        validate_replay_call_plan_v2(plan)

    def test_renderer_is_declarative(self) -> None:
        spec = self.neutral_spec()
        plan = self.build(spec)
        validate_replay_call_plan_v2(plan)
        fixture = _fixture_binding(spec, REPO_ROOT)
        source = render_replay_call_plan_v2(plan, fixture["cases"])
        self.assertIn("apply_record(", source)
        self.assertNotIn("struct FixtureCase", source)
        self.assertNotIn("fdb_tsl_to_blob", source)
        self.assertNotIn("record_pointer_identity_return", source)

    @staticmethod
    def initializer_leaves(initializer: dict, prefix: tuple[str, ...] = ()) -> dict:
        result = {}
        for field in initializer["fields"]:
            path = (*prefix, field["name"])
            value = field["value"]
            if value["kind"] == "struct":
                result.update(RecordPointerIdentityPlanTests.initializer_leaves(value, path))
            else:
                result[path] = value
        return result

    @staticmethod
    def real_spec() -> dict:
        return json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-tsl-to-blob.json")
            .read_text(encoding="utf-8")
        )

    @staticmethod
    def build(spec: dict) -> dict:
        return build_record_pointer_identity_plan(
            spec,
            spec["replay_contract"],
            _fixture_binding(spec, REPO_ROOT),
        )

    @staticmethod
    def neutral_spec() -> dict:
        expected = {"return_same_destination": True, "result.payload.value": 7}
        return {
            "schema_version": 1,
            "function_name": "remap_record",
            "c_boundary": {
                "signatures": [
                    {
                        "function": "remap_record",
                        "return_type": "destination_handle",
                        "parameters": [
                            {"name": "destination", "c_type": "destination_handle", "direction": "inout"},
                            {"name": "source", "c_type": "source_handle", "direction": "input"},
                        ],
                        "c_source": (
                            "destination_handle remap_record(destination_handle destination, "
                            "source_handle source) { destination->payload.value = source->nested.value; "
                            "return destination; }"
                        ),
                    }
                ],
                "pointer_contract": {
                    "input_buffers": [{"name": "source", "read_effects": ["source->nested.value"]}],
                    "output_pointers": [
                        {"name": "destination", "write_effects": ["destination->payload.value"]}
                    ],
                    "aliasing_proven": True,
                    "noalias_required": [["source", "destination"]],
                    "actual_argument_noalias_proof": {
                        "parameter_pair": ["source", "destination"],
                        "actual_arguments": [
                            {"parameter": "source", "object": "distinct source object"},
                            {"parameter": "destination", "object": "distinct destination object"},
                        ],
                        "proven": True,
                    },
                    "alias_contract": {"requires_noalias": True, "proven": True},
                },
            },
            "rust_boundary": {"public_api": [{"name": "apply_record"}]},
            "fixture_contract": {
                "cases": [
                    {
                        "id": "renamed-case",
                        "input_ref": "inline",
                        "inputs": {
                            "source_case": {"nested.value": 7},
                            "destination_case": {"old_value": 3},
                        },
                        "expected_outputs": expected,
                    }
                ],
                "observable_outputs": list(expected),
                "behavior_fields": list(expected),
            },
            "replay_contract": {
                "schema_version": 1,
                "kind": "record_pointer_identity_return",
                "input": {
                    "parameter": "source",
                    "fixture_root": ["source_case"],
                    "rust_type": "SourceRecord",
                    "fields": [
                        {
                            "fixture_path": ["nested.value"],
                            "rust_field_path": ["header", "amount"],
                            "rust_type_path": ["SourceHeader"],
                            "fixture_scalar_type": "u32",
                            "rust_scalar_type": "u32",
                            "conversion": "identity",
                        }
                    ],
                    "defaults": [],
                },
                "output": {
                    "parameter": "destination",
                    "fixture_root": ["destination_case"],
                    "rust_type": "DestinationRecord",
                    "fields": [
                        {
                            "initial_fixture_path": ["old_value"],
                            "expected_output": "result.payload.value",
                            "rust_field_path": ["payload", "value"],
                            "rust_type_path": ["DestinationPayload"],
                            "fixture_scalar_type": "u32",
                            "rust_scalar_type": "usize",
                            "conversion": "u32_to_usize",
                        }
                    ],
                    "defaults": [
                        {
                            "rust_field_path": ["opaque"],
                            "rust_type_path": [],
                            "rust_scalar_type": "raw_const_ptr",
                            "value": {"kind": "null"},
                        },
                        {
                            "rust_field_path": ["capacity"],
                            "rust_type_path": [],
                            "rust_scalar_type": "u32",
                            "value": {"kind": "zero"},
                        },
                    ],
                },
                "return": {"kind": "identity", "parameter_ref": "output"},
                "noalias_refs": [["input", "output"]],
            },
        }


if __name__ == "__main__":
    unittest.main()
