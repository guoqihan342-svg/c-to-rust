from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from validation.tools._translation_carrier_reporter import emit_reports
from validation.tools._translation_carrier_reporter.errors import ReporterError
from validation.tools._translation_carrier_reporter.sequence_contract import parse_contract
from validation.tools._translation_carrier_reporter.sequence_contract_validation import (
    validate_noalias,
)
from validation.tools._translation_carrier_reporter.sequence_model import (
    reference_outputs,
    validate_cases,
)
from validation.tools.test_translation_carrier_sequence_reporter import (
    REPO_ROOT,
    build_reporter_layout,
)


class SequenceOwnerInteriorAliasTests(unittest.TestCase):
    def test_emits_owner_alias_reports_and_precise_comparison_negative(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="sequence-owner-alias-reporter-", dir=target_root
        ) as tmp:
            layout = build_reporter_layout(Path(tmp), interior_alias=True)
            paths = emit_reports(**layout["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }
            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["negative_diff"]["status"], "expected_failed")
            claim = reports["rust_report"]["claim_boundary"]["sequence_replay"]
            self.assertEqual(claim["schema_version"], 2)
            self.assertEqual(
                claim["argument_modes"],
                ["record_ref", "record_ref", "owner_interior_alias"],
            )
            self.assertEqual(
                claim["interior_alias_bindings"][0]["alias_local"], "cursor"
            )
            mutation = reports["negative_diff"]["actual_mutation_execution"][
                "mutation"
            ]
            self.assertEqual(mutation["operator_from"], "!=")
            self.assertEqual(mutation["operator_to"], "==")

    def test_accepts_nested_owner_alias_and_tracks_combined_observation_path(self) -> None:
        spec, cases = build_spec()

        contract = parse_contract(spec)

        self.assertEqual(
            set(contract["external_callee"]["arguments"][0]),
            {
                "parameter",
                "mode",
                "entry_parameter",
                "projection_path",
                "alias_local",
                "field_path",
            },
        )
        self.assertEqual(
            set(contract["external_callee"]["arguments"][1]),
            {"parameter", "mode", "entry_parameter", "field_path"},
        )
        self.assertEqual(
            set(contract["external_callee"]["arguments"][2]),
            {"parameter", "mode", "entry_parameter", "field_path"},
        )
        self.assertEqual(validate_cases(cases, contract), cases)
        self.assertEqual(
            reference_outputs(cases[0], contract)["observed_arguments"],
            [[4, 12, 5], [9, 12, 5]],
        )

    def test_rejects_owner_alias_on_value_entry(self) -> None:
        spec, _ = build_spec()
        owner = entry(spec, "owner")
        owner["pass_mode"] = "value"
        owner["c_type"] = "struct Envelope"
        entry_signature_parameter(spec, "owner")["c_type"] = "struct Envelope"

        with self.assertRaisesRegex(ReporterError, "owner entry must use mutable_ref"):
            parse_contract(spec)

    def test_rejects_projection_that_does_not_resolve_to_a_record(self) -> None:
        spec, _ = build_spec()
        alias = spec["replay_contract"]["external_callee"]["arguments"][0]
        alias["projection_path"] = ["owner_tag"]

        with self.assertRaisesRegex(ReporterError, "projection_path does not resolve to a record"):
            parse_contract(spec)

    def test_rejects_alias_field_that_is_not_initialized(self) -> None:
        spec, _ = build_spec()
        alias = spec["replay_contract"]["external_callee"]["arguments"][0]
        alias["field_path"] = ["missing"]

        with self.assertRaisesRegex(ReporterError, "field path is not initialized"):
            parse_contract(spec)

    def test_rejects_state_output_that_does_not_match_alias_target(self) -> None:
        spec, _ = build_spec()
        spec["replay_contract"]["state_output"]["field_path"] = [
            "payload",
            "cursor",
            "stable",
        ]

        with self.assertRaisesRegex(ReporterError, "state_output does not match owner interior alias"):
            parse_contract(spec)

    def test_rejects_external_signature_using_owner_instead_of_nested_record(self) -> None:
        spec, _ = build_spec()
        external_signature_parameter(spec, "cursor_ref")["c_type"] = "struct Envelope *"

        with self.assertRaisesRegex(ReporterError, "external parameter types drifted"):
            parse_contract(spec)

    def test_preserves_legacy_argument_shapes(self) -> None:
        spec, _ = build_spec()
        legacy = spec["replay_contract"]["external_callee"]["arguments"][1]
        legacy["projection_path"] = ["unexpected"]

        with self.assertRaisesRegex(ReporterError, "shape drifted"):
            parse_contract(spec)

        missing, _ = build_spec()
        missing_alias = missing["replay_contract"]["external_callee"]["arguments"][0]
        missing_alias.pop("projection_path")
        with self.assertRaisesRegex(ReporterError, "shape drifted"):
            parse_contract(missing)

        legacy, _ = build_spec()
        legacy["replay_contract"]["schema_version"] = 1
        with self.assertRaisesRegex(ReporterError, "mode is unsupported"):
            parse_contract(legacy)

    def test_noalias_includes_owner_alias_entry_root(self) -> None:
        contract = {
            "external_callee": {
                "arguments": [
                    {
                        "mode": "owner_interior_alias",
                        "entry_parameter": "owner",
                    }
                ]
            },
            "state_output": {"parameter": "state"},
            "noalias_required": [["owner", "state"]],
        }
        spec = {
            "c_boundary": {
                "pointer_contract": {
                    "aliasing_proven": True,
                    "noalias_required": [["owner", "state"]],
                }
            }
        }
        entries = {
            "owner": {"pass_mode": "mutable_ref"},
            "state": {"pass_mode": "mutable_ref"},
        }

        validate_noalias(spec, contract, entries)


def build_spec() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fields = ["completed", "selected_value", "call_count", "observed_arguments"]
    owner_initializer = {
        "record_type": "Envelope",
        "fields": [
            {
                "name": "owner_tag",
                "fixture_field": "owner_tag_input",
                "rust_type": "u32",
            },
            {
                "name": "payload",
                "record": {
                    "record_type": "Payload",
                    "fields": [
                        {
                            "name": "cursor",
                            "record": {
                                "record_type": "Cursor",
                                "fields": [
                                    {
                                        "name": "value",
                                        "fixture_field": "cursor_value_input",
                                        "rust_type": "u32",
                                    },
                                    {
                                        "name": "stable",
                                        "fixture_field": "cursor_stable_input",
                                        "rust_type": "u32",
                                    },
                                ],
                            },
                        }
                    ],
                },
            },
        ],
    }
    peer_initializer = {
        "record_type": "Peer",
        "fields": [
            {
                "name": "token",
                "fixture_field": "peer_token_input",
                "rust_type": "u32",
            }
        ],
    }
    spec = {
        "function_name": "advance_envelope",
        "fixture_contract": {"observable_outputs": fields},
        "replay_contract": {
            "schema_version": 2,
            "kind": "scripted_external_record_u32_sequence_do_while_state",
            "external_callee": {
                "name": "inspect_cursor",
                "return_sequence_fixture_field": "scripted_values",
                "call_count_output": "call_count",
                "call_args_output": "observed_arguments",
                "arguments": [
                    {
                        "parameter": "cursor_ref",
                        "mode": "owner_interior_alias",
                        "entry_parameter": "owner",
                        "projection_path": ["payload", "cursor"],
                        "alias_local": "cursor",
                        "field_path": ["value"],
                    },
                    {
                        "parameter": "peer_ref",
                        "mode": "record_ref",
                        "entry_parameter": "peer",
                        "field_path": ["token"],
                    },
                    {
                        "parameter": "tag_value",
                        "mode": "scalar_field_value",
                        "entry_parameter": "owner",
                        "field_path": ["owner_tag"],
                    },
                ],
            },
            "entry_arguments": [
                {
                    "parameter": "owner",
                    "c_type": "struct Envelope *",
                    "rust_type": "Envelope",
                    "pass_mode": "mutable_ref",
                    "direction": "inout",
                    "initializer": owner_initializer,
                },
                {
                    "parameter": "peer",
                    "c_type": "struct Peer *",
                    "rust_type": "Peer",
                    "pass_mode": "mutable_ref",
                    "direction": "input",
                    "initializer": peer_initializer,
                },
            ],
            "state_output": {
                "parameter": "owner",
                "field_path": ["payload", "cursor", "value"],
                "fixture_field": "selected_value",
                "rust_type": "u32",
            },
            "loop": {"sentinel": 77, "comparison": "not_equal", "max_calls": 4},
            "return": {"fixture_field": "completed", "rust_type": "bool", "value": True},
            "noalias_required": [["owner", "peer"]],
        },
        "c_boundary": {
            "signatures": [
                {
                    "id": "entry-signature",
                    "function": "advance_envelope",
                    "return_type": "bool",
                    "parameters": [
                        {"name": "owner", "c_type": "struct Envelope *", "direction": "inout"},
                        {"name": "peer", "c_type": "struct Peer *", "direction": "input"},
                    ],
                },
                {
                    "id": "external-signature",
                    "function": "inspect_cursor",
                    "return_type": "uint32_t",
                    "parameters": [
                        {"name": "cursor_ref", "c_type": "struct Cursor *", "direction": "inout"},
                        {"name": "peer_ref", "c_type": "struct Peer *", "direction": "input"},
                        {"name": "tag_value", "c_type": "uint32_t", "direction": "input"},
                    ],
                },
            ],
            "external_direct_callees": [
                {"name": "inspect_cursor", "signature_ref": "external-signature"}
            ],
            "pointer_contract": {
                "aliasing_proven": True,
                "noalias_required": [["owner", "peer"]],
            },
        },
    }
    cases = [
        {
            "id": "state-evolves",
            "inputs": {
                "owner_tag_input": 5,
                "cursor_value_input": 4,
                "cursor_stable_input": 6,
                "peer_token_input": 12,
                "scripted_values": [9, 77],
            },
            "expected_outputs": {
                "completed": True,
                "selected_value": 77,
                "call_count": 2,
                "observed_arguments": [[4, 12, 5], [9, 12, 5]],
            },
        }
    ]
    return spec, cases


def entry(spec: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        item for item in spec["replay_contract"]["entry_arguments"] if item["parameter"] == name
    )


def entry_signature_parameter(spec: dict[str, Any], name: str) -> dict[str, Any]:
    signature = next(
        item for item in spec["c_boundary"]["signatures"] if item["function"] == spec["function_name"]
    )
    return next(item for item in signature["parameters"] if item["name"] == name)


def external_signature_parameter(spec: dict[str, Any], name: str) -> dict[str, Any]:
    external = spec["replay_contract"]["external_callee"]
    signature = next(
        item for item in spec["c_boundary"]["signatures"] if item["function"] == external["name"]
    )
    return next(item for item in signature["parameters"] if item["name"] == name)


if __name__ == "__main__":
    unittest.main()
