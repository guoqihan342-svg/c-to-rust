from __future__ import annotations

import json
from pathlib import Path
import unittest

from validation.tools.c_oracle_call_plan import render_c_oracle_call_plan


REPO_ROOT = Path(__file__).resolve().parents[2]


class COracleOutputBindingPlanTests(unittest.TestCase):
    def test_libuv_contract_renders_all_declared_observations(self) -> None:
        rendered = render_c_oracle_call_plan(self.load_spec(), REPO_ROOT)

        self.assertEqual("generated", rendered["status"])
        self.assertEqual(
            [
                "return_code",
                "status",
                "family",
                "port_host",
                "port_bytes_hex",
                "addr_bytes_hex",
            ],
            rendered["compared_fields"],
        )
        self.assertIn("struct sockaddr_in case_loopback_0_addr_out = {0};", rendered["statements"])
        self.assertIn("uv_ip4_addr(case_loopback_0_ip", rendered["statements"])
        self.assertIn("sin_addr.s_addr", rendered["statements"])
        self.assertIn("_Static_assert(CHAR_BIT == 8", rendered["declarations"])
        self.assertEqual(12, len(rendered["protocol_records"]))

    def test_complete_identity_and_output_parameter_rename_stays_generic(self) -> None:
        spec = self.load_spec()
        spec["target_id"] = "unfamiliar-network-library"
        spec["slice_id"] = "unfamiliar-address-slice"
        spec["function_name"] = "convert_text_address"
        spec["c_boundary"]["functions"] = ["convert_text_address"]
        signature = spec["c_boundary"]["signatures"][0]
        signature["function"] = "convert_text_address"
        signature["parameters"][2]["name"] = "result"
        signature["parameters"][2]["c_type"] = "struct output_record*"
        spec["replay_contract"]["omitted_c_parameters"] = ["result"]
        spec["c_oracle_contract"]["output_bindings"][0]["c_parameter"] = "result"
        spec["c_boundary"]["files"][0]["path"] = "include/output_record.h"
        spec["c_oracle_contract"]["headers"] = ["output_record.h"]
        observations = spec["c_oracle_contract"]["observations"]
        observations[2]["source"]["path"] = ["family_code"]
        observations[3]["source"]["path"] = ["port_wire"]
        observations[4]["source"]["path"] = ["port_wire"]
        observations[5]["source"]["path"] = ["address", "wire"]

        rendered = render_c_oracle_call_plan(spec, REPO_ROOT)

        self.assertEqual("generated", rendered["status"])
        self.assertIn("convert_text_address(", rendered["statements"])
        self.assertNotIn("uv_ip4_addr(", rendered["statements"])
        self.assertIn('include "output_record.h"', rendered["declarations"])
        self.assertIn("address.wire", rendered["statements"])

    def test_missing_binding_and_non_writable_pointer_fail_closed(self) -> None:
        missing = self.load_spec()
        missing["c_oracle_contract"]["output_bindings"] = []
        rendered = render_c_oracle_call_plan(missing, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("bindings are missing", rendered["reason"])

        readonly = self.load_spec()
        parameter = readonly["c_boundary"]["signatures"][0]["parameters"][2]
        parameter["direction"] = "input"
        rendered = render_c_oracle_call_plan(readonly, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("not writable output", rendered["reason"])

    def test_raw_expression_and_unknown_transform_fail_closed(self) -> None:
        raw_expression = self.load_spec()
        source = raw_expression["c_oracle_contract"]["observations"][2]["source"]
        source["expression"] = "addr.sin_family"
        rendered = render_c_oracle_call_plan(raw_expression, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("fields are invalid", rendered["reason"])

        unknown = self.load_spec()
        unknown["c_oracle_contract"]["observations"][2]["source"] = {
            "kind": "project_specific_adapter",
            "binding": "addr_out",
            "path": ["sin_family"],
            "width_bytes": 2,
        }
        rendered = render_c_oracle_call_plan(unknown, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("source kind is unsupported", rendered["reason"])

    def test_observation_order_must_match_replay_and_fixture_contracts(self) -> None:
        spec = self.load_spec()
        observations = spec["c_oracle_contract"]["observations"]
        observations[0], observations[1] = observations[1], observations[0]

        rendered = render_c_oracle_call_plan(spec, REPO_ROOT)

        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("ReplayCallPlan assertions", rendered["reason"])

    def test_header_injection_and_scalar_width_drift_fail_closed(self) -> None:
        injected = self.load_spec()
        injected["c_oracle_contract"]["headers"] = ['uv.h\"\n#include "evil.h']
        rendered = render_c_oracle_call_plan(injected, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("safe header", rendered["reason"])

        wrong_width = self.load_spec()
        wrong_width["c_oracle_contract"]["observations"][2]["source"][
            "width_bytes"
        ] = 4
        rendered = render_c_oracle_call_plan(wrong_width, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("scalar field observation", rendered["reason"])

    @staticmethod
    def load_spec() -> dict:
        return json.loads(
            (REPO_ROOT / "validation/slice-specs/libuv-ip4-addr.json").read_text(
                encoding="utf-8"
            )
        )


if __name__ == "__main__":
    unittest.main()
