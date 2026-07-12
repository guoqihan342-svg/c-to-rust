from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import jsonschema

from validation.tools.replay_call_plan import (
    _fixture_binding,
    build_replay_call_plan,
    render_declarative_replay_cases,
)
from validation.tools.replay_call_plan_record_buffer_identity import (
    build_record_buffer_identity_plan,
    supports_record_buffer_identity_plan,
)
from validation.tools.replay_call_plan_v2 import validate_replay_call_plan_v2


REPO_ROOT = Path(__file__).resolve().parents[2]


class RecordBufferIdentityPlanTests(unittest.TestCase):
    def test_real_blob_make_builds_routes_renders_and_compiles(self) -> None:
        spec = self.real_spec()
        self.assertTrue(supports_record_buffer_identity_plan(spec))

        plan = build_replay_call_plan(spec, REPO_ROOT)
        validate_replay_call_plan_v2(plan)
        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)

        self.assertEqual((2, "bound"), (plan["schema_version"], plan["status"]))
        self.assertEqual(["blob", "value_buf", "buf_len"], [item["name"] for item in plan["parameters"]])
        self.assertEqual(["buf_len"], plan["length_parameters_retained"])
        self.assertEqual("nullable_byte_buffer_const_ptr", plan["parameters"][1]["source"]["kind"])
        self.assertEqual("raw_pointer_identity", plan["pointer_identity_assertions"][0]["kind"])
        self.assertIn("core::ptr::null::<core::ffi::c_void>()", source)
        self.assertIn("vec![16u8, 32u8, 48u8]", source)
        self.assertIn(".as_ptr().cast::<core::ffi::c_void>()", source)
        self.assertNotIn("zeroed", source)
        self.assertNotIn("0x", source)
        self.compile_rendered(source)

    def test_neutral_symbols_use_the_same_producer(self) -> None:
        spec = self.neutral_spec()
        plan = self.build(spec)
        rendered = render_declarative_replay_cases(spec, plan, REPO_ROOT)

        self.assertEqual("remap_payload", plan["source_function_name"])
        self.assertEqual("apply_payload", plan["api_name"])
        self.assertEqual(["target", "bytes", "count"], [item["name"] for item in plan["parameters"]])
        self.assertIn("binding.target.data", plan["pointer_identity_assertions"][0]["actual"])
        self.assertNotIn("fdb", json.dumps(plan).lower())
        self.assertNotIn("blob", json.dumps(plan).lower())
        self.assertIn("apply_payload", rendered)

    def test_nullable_and_length_contract_fail_closed(self) -> None:
        too_short = self.neutral_spec()
        too_short["fixture_contract"]["cases"][0]["inputs"]["bytes"] = [1]
        with self.assertRaisesRegex(ValueError, "exceeds buffer"):
            self.build(too_short)

        implicit_null = self.neutral_spec()
        implicit_null["fixture_contract"]["cases"][0]["inputs"]["bytes"] = "null"
        with self.assertRaisesRegex(ValueError, "nullable byte fixture"):
            self.build(implicit_null)

        expression = self.neutral_spec()
        expression["replay_contract"]["buffer"]["expression"] = "danger()"
        self.assertFalse(supports_record_buffer_identity_plan(expression))
        with self.assertRaisesRegex(ValueError, "shape drifted"):
            self.build(expression)

    def test_schema_accepts_closed_plan_and_rejects_address_or_expression(self) -> None:
        plan = self.build(self.neutral_spec())
        schema = json.loads(
            (REPO_ROOT / "validation/auto-translation-template/ai-context-pack.schema.json")
            .read_text(encoding="utf-8")
        )
        jsonschema.Draft7Validator.check_schema(schema)
        validator = jsonschema.Draft7Validator(
            {"$ref": "#/definitions/boundReplayCallPlan", "definitions": schema["definitions"]}
        )
        validator.validate(plan)

        for key, value in (("address", 4096), ("expression", "danger()")):
            drifted = copy.deepcopy(plan)
            drifted["pointer_identity_assertions"][0][key] = value
            with self.subTest(key=key), self.assertRaises(jsonschema.ValidationError):
                validator.validate(drifted)

    @staticmethod
    def real_spec() -> dict:
        return json.loads(
            (REPO_ROOT / "validation/slice-specs/flashdb-real-fdb-blob-make.json")
            .read_text(encoding="utf-8")
        )

    @staticmethod
    def build(spec: dict) -> dict:
        return build_record_buffer_identity_plan(
            spec, spec["replay_contract"], _fixture_binding(spec, REPO_ROOT)
        )

    @staticmethod
    def neutral_spec() -> dict:
        expected = {"return_same_target": True, "target.data": "bytes", "target.length": 2}
        return {
            "schema_version": 1,
            "function_name": "remap_payload",
            "c_boundary": {
                "signatures": [{
                    "function": "remap_payload",
                    "return_type": "payload_handle",
                    "parameters": [
                        {"name": "target", "c_type": "payload_handle", "direction": "inout"},
                        {"name": "bytes", "c_type": "const void*", "direction": "input"},
                        {"name": "count", "c_type": "size_t", "direction": "input"},
                    ],
                    "c_source": (
                        "payload_handle remap_payload(payload_handle target, const void *bytes, size_t count) "
                        "{ target->data = (void *)bytes; target->length = count; return target; }"
                    ),
                }],
                "pointer_contract": {
                    "input_buffers": [{
                        "name": "bytes", "length_companion": "count", "nullability": "nullable",
                        "read_effects": [], "write_effects": [],
                    }],
                    "inout_pointers": [{"name": "target"}],
                    "aliasing_proven": False,
                    "noalias_required": [],
                },
            },
            "rust_boundary": {"public_api": [{"name": "apply_payload"}]},
            "fixture_contract": {
                "cases": [{
                    "id": "renamed",
                    "input_ref": "inline",
                    "inputs": {"seed_length": 7, "bytes": [10, 20, 30], "count": 2},
                    "expected_outputs": expected,
                }],
                "observable_outputs": list(expected),
                "behavior_fields": list(expected),
            },
            "replay_contract": {
                "schema_version": 1,
                "kind": "record_buffer_length_identity_return",
                "record": {
                    "parameter": "target", "fixture_root": [], "rust_type": "PayloadBox",
                    "fields": [{
                        "initial_fixture_path": ["seed_length"], "expected_output": "target.length",
                        "expected_from_ref": "length", "rust_field_path": ["length"],
                        "rust_type_path": [], "fixture_scalar_type": "usize",
                        "rust_scalar_type": "usize", "conversion": "identity",
                    }],
                    "defaults": [{
                        "rust_field_path": ["data"], "rust_type_path": [],
                        "rust_scalar_type": "raw_mut_ptr", "value": {"kind": "null_mut"},
                    }],
                },
                "buffer": {
                    "parameter": "bytes", "fixture_path": ["bytes"], "maximum_bytes": 64,
                    "nullability": "fixture_nullable", "pointer_rust_type": "*const core::ffi::c_void",
                },
                "length": {
                    "parameter": "count", "fixture_path": ["count"], "rust_type": "usize",
                    "retained": True,
                    "relation": {"kind": "within_buffer_when_nonnull", "buffer_ref": "buffer"},
                },
                "pointer_identity": {
                    "record_field_path": ["data"], "record_type_path": [],
                    "record_pointer_type": "raw_mut_ptr", "buffer_ref": "buffer",
                    "expected_output": "target.data",
                },
                "return": {"kind": "identity", "parameter_ref": "record"},
                "noalias_refs": [],
            },
        }

    def compile_rendered(self, body: str) -> None:
        rustc = shutil.which("rustc")
        if rustc is None:
            self.skipTest("rustc is unavailable")
        source = """
pub struct FdbBlob { pub buf: *mut core::ffi::c_void, pub size: usize }
pub fn fdb_blob_make(blob: &mut FdbBlob, value_buf: *const core::ffi::c_void, buf_len: usize) -> &mut FdbBlob {
    blob.buf = value_buf as *mut core::ffi::c_void; blob.size = buf_len; blob
}
fn main() {
""" + body + "\n}\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.rs"
            path.write_text(source, encoding="utf-8")
            completed = subprocess.run(
                [rustc, "--edition=2021", str(path), "-o", str(Path(directory) / "replay")],
                text=True, capture_output=True, check=False,
            )
        self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
