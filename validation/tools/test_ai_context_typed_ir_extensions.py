from __future__ import annotations

import copy
import unittest

from validation.tools._ai_candidate_harness_parts.context_typed_ir import (
    typed_ir_summary,
    typed_ir_summary_is_valid,
)


SHA = "a" * 64


def integer_type(name: str, width: int = 32) -> dict[str, object]:
    return {
        "spelled": name,
        "canonical": name,
        "is_const": False,
        "kind": {"Integer": {"signed": False, "width": width}},
        "width_bits": width,
    }


def pointer_type(pointee: dict[str, object], name: str) -> dict[str, object]:
    return {
        "spelled": f"{name} *",
        "canonical": f"{name} *",
        "is_const": False,
        "kind": {"Pointer": {"pointee": pointee}},
    }


def void_pointer() -> dict[str, object]:
    return pointer_type(
        {
            "spelled": "void",
            "canonical": "void",
            "is_const": False,
            "kind": "Void",
        },
        "void",
    )


def function_ir(root: str, field: str) -> dict[str, object]:
    scalar = integer_type("renamed_uint")
    scalar_pointer = pointer_type(scalar, "renamed_uint")
    record = {
        "spelled": "struct renamed_record",
        "canonical": "struct renamed_record",
        "is_const": False,
        "kind": {"Record": {"name": "renamed_record", "fields": []}},
    }
    root_var = {"Var": {"name": root, "ty": pointer_type(record, "struct renamed_record")}}
    member = {
        "Member": {
            "base": root_var,
            "field": field,
            "is_arrow": True,
            "ty": scalar,
        }
    }
    layout = {
        "record_type": "struct renamed_record",
        "size_bytes": 16,
        "align_bytes": 4,
        "compile_arguments_sha256": SHA,
        "compile_database_sha256": SHA,
        "diagnostics_sha256": SHA,
        "dump_sha256": SHA,
        "target_abi": {
            "triple_or_abi": "x86_64-unknown-linux-gnu",
            "endianness": "little",
            "char_width": 8,
            "short_width": 16,
            "pointer_width": 64,
            "int_width": 32,
            "long_width": 64,
            "long_long_width": 64,
            "char_align": 8,
            "short_align": 16,
            "int_align": 32,
            "long_align": 64,
            "long_long_align": 64,
            "pointer_align": 64,
            "plain_char_signed": True,
        },
    }
    return {
        "name": "renamed_entry",
        "params": [],
        "body": [
            {
                "RecordMemset": {
                    "destination": root_var,
                    "byte": 0,
                    "write_len_bytes": 16,
                    "layout": layout,
                }
            },
            {
                "Return": {
                    "value": {
                        "Call": {
                            "callee": "renamed_external",
                            "args": [
                                {
                                    "MutableVoidPointerAddress": {
                                        "operand": member,
                                        "source_pointer": scalar_pointer,
                                        "target": void_pointer(),
                                    }
                                }
                            ],
                        }
                    }
                }
            },
        ],
    }


class AiContextTypedIrExtensionTests(unittest.TestCase):
    def test_extended_nodes_form_complete_hash_bound_projection(self) -> None:
        summary = typed_ir_summary(function_ir("owner_alpha", "slot_beta"))

        self.assertTrue(typed_ir_summary_is_valid(summary), summary["unsupported_nodes"])
        self.assertEqual(summary["statement_kinds"], ["RecordMemset", "Return"])
        memset = summary["body"][0]
        self.assertEqual(memset["byte"], 0)
        self.assertEqual(memset["layout"]["size_bytes"], 16)
        address = summary["body"][1]["value"]["args"][0]
        self.assertEqual(address["kind"], "mutable_void_pointer_address")
        self.assertEqual(address["source_pointer"]["pointee"]["kind"], "integer")
        self.assertEqual(address["target_pointer"]["pointee"]["kind"], "void")

    def test_extended_projection_is_identifier_independent(self) -> None:
        for root, field in (("owner_alpha", "slot_beta"), ("ctx_gamma", "word_delta")):
            with self.subTest(root=root, field=field):
                summary = typed_ir_summary(function_ir(root, field))
                self.assertTrue(typed_ir_summary_is_valid(summary))
                self.assertEqual(summary["body"][0]["destination"]["name"], root)
                self.assertEqual(
                    summary["body"][1]["value"]["args"][0]["operand"]["field"],
                    field,
                )

    def test_layout_and_pointer_contract_drift_remain_fail_closed(self) -> None:
        cases = {}
        size_drift = function_ir("owner", "slot")
        size_drift["body"][0]["RecordMemset"]["write_len_bytes"] = 8
        cases["layout-size"] = size_drift
        const_target = function_ir("owner", "slot")
        const_target["body"][1]["Return"]["value"]["Call"]["args"][0][
            "MutableVoidPointerAddress"
        ]["target"]["is_const"] = True
        cases["const-target"] = const_target
        width_drift = function_ir("owner", "slot")
        width_drift["body"][1]["Return"]["value"]["Call"]["args"][0][
            "MutableVoidPointerAddress"
        ]["source_pointer"]["kind"]["Pointer"]["pointee"]["width_bits"] = 64
        cases["integer-width"] = width_drift
        unknown = function_ir("owner", "slot")
        unknown["body"].append({"UnknownFutureStatement": {}})
        cases["unknown-node"] = unknown

        for label, ir in cases.items():
            with self.subTest(label=label):
                summary = typed_ir_summary(ir)
                self.assertFalse(typed_ir_summary_is_valid(summary))
                self.assertEqual(summary["projection_status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
