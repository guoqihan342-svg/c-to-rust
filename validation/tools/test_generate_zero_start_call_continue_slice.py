from __future__ import annotations

import copy
import json
import os
import unittest
from pathlib import Path

import jsonschema

from validation.tools._translation_carrier_reporter.call_continue_contract import (
    KIND,
    parse_contract,
)
from validation.tools.call_continue_syntax import validate_c_call_continue_source
from validation.tools._zero_start_call_continue_slice_generator import (
    DEFAULT_FIXTURE,
    DEFAULT_INPUT,
    DEFAULT_SPEC,
    SLICE_ID,
    build_documents,
    load_generator_input,
    sha256_text,
    stable_json_bytes,
    validate_source_checkout,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class GenerateZeroStartCallContinueSliceTests(unittest.TestCase):
    def test_checked_in_spec_and_fixture_are_reproducible(self) -> None:
        generator_input = load_generator_input(DEFAULT_INPUT)
        spec, fixture = build_documents(generator_input)

        self.assertEqual(DEFAULT_SPEC.read_bytes(), stable_json_bytes(spec))
        self.assertEqual(DEFAULT_FIXTURE.read_bytes(), stable_json_bytes(fixture))
        schema = json.loads(
            (REPO_ROOT / "validation/slice-spec-template/slice-spec.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(spec, schema)

    def test_real_source_binding_and_normalized_fragment_sha_are_exact(self) -> None:
        generator_input = load_generator_input(DEFAULT_INPUT)
        source = generator_input["source"]
        fragment = source["fragment"]

        self.assertEqual(source["source_branch"], "competition")
        self.assertEqual(
            source["source_commit"],
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        )
        self.assertEqual((fragment["line_start"], fragment["line_end"]), (1868, 1874))
        self.assertEqual(fragment["sha256"], sha256_text(fragment["text"]))
        self.assertEqual(
            fragment["sha256"],
            "5ecb3553be0af447e9cba4bc822c8e1da5ea7d9efd1fc9f7876d802b81224cf7",
        )

    def test_schema_v2_contract_has_four_entries_and_five_discriminating_cases(self) -> None:
        spec, fixture = build_documents(load_generator_input(DEFAULT_INPUT))
        contract = parse_contract(spec)

        self.assertEqual(contract["schema_version"], 2)
        self.assertEqual(contract["kind"], KIND)
        self.assertEqual(len(contract["entry_arguments"]), 4)
        validate_c_call_continue_source(spec["c_source"], contract)
        self.assertEqual(contract["zero_start"]["external_call"], "skip")
        self.assertEqual(
            [case["id"] for case in fixture["cases"]],
            [
                "zero-start-ordinary",
                "zero-start-u32-wrap",
                "sentinel-hit",
                "zero-miss",
                "ordinary-miss",
            ],
        )
        ordinary, wrapped, hit, zero_miss, ordinary_miss = fixture["cases"]
        self.assertEqual(ordinary["expected_outputs"]["call_count"], 0)
        self.assertEqual(ordinary["expected_outputs"]["alias_start_after"], 124)
        self.assertEqual(wrapped["expected_outputs"]["call_count"], 0)
        self.assertEqual(wrapped["expected_outputs"]["alias_start_after"], 8)
        self.assertTrue(hit["expected_outputs"]["return_value"])
        self.assertEqual(hit["expected_outputs"]["owner_traversed_after"], 5)
        self.assertEqual(zero_miss["expected_outputs"]["alias_start_after"], 0)
        self.assertEqual(ordinary_miss["expected_outputs"]["alias_start_after"], 7)

    def test_target_identity_does_not_select_translation_contract(self) -> None:
        generator_input = load_generator_input(DEFAULT_INPUT)
        flashdb_spec, _ = build_documents(generator_input)
        renamed_spec, _ = build_documents(
            copy.deepcopy(generator_input),
            target_id="renamed-target",
            slice_id="renamed-slice",
        )

        self.assertEqual(flashdb_spec["replay_contract"], renamed_spec["replay_contract"])
        self.assertEqual(parse_contract(renamed_spec), renamed_spec["replay_contract"])

    @unittest.skipUnless(os.environ.get("FLASHDB_SOURCE_ROOT"), "FLASHDB_SOURCE_ROOT not set")
    def test_generator_input_matches_live_competition_checkout(self) -> None:
        validate_source_checkout(
            Path(os.environ["FLASHDB_SOURCE_ROOT"]),
            load_generator_input(DEFAULT_INPUT),
        )


if __name__ == "__main__":
    unittest.main()
