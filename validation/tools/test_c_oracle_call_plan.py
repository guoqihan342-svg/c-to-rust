from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from validation.tools.c_oracle_call_plan import (
    render_c_oracle_call_plan,
    validate_c_oracle_call_plan_harness,
)
from validation.tools.replay_call_plan import build_replay_call_plan


REPO_ROOT = Path(__file__).resolve().parents[2]


class COracleCallPlanTests(unittest.TestCase):
    def test_zlib_plan_renders_scalar_hex_buffer_length_and_empty_sentinel(self) -> None:
        spec = self.load_spec("zlib-adler32-step.json")

        rendered = render_c_oracle_call_plan(spec, REPO_ROOT)

        self.assertEqual("generated", rendered["status"])
        self.assertEqual(2, rendered["case_count"])
        self.assertEqual(["value"], rendered["compared_fields"])
        self.assertIn(
            "static const uint8_t case_empty_0_buf[] = { 0 };",
            rendered["declarations"],
        )
        self.assertIn(
            "adler32_z(((uint32_t)1ULL), case_empty_0_buf, ((size_t)0ULL))",
            rendered["statements"],
        )
        self.assertIn("fixture case ascii value matched", rendered["statements"])
        self.assertRegex(rendered["replay_call_plan_sha256"], r"^[0-9a-f]{64}$")

    def test_auto_migrate_dispatches_zlib_through_generic_call_plan(self) -> None:
        from validation.tools import auto_migrate

        spec = self.load_spec("zlib-adler32-step.json")
        fixture = auto_migrate.oracle_fixture_binding(spec)

        rendered = auto_migrate.oracle_fixture_execution_source(spec, fixture)

        self.assertEqual("generated", rendered["call_plan"]["status"])
        self.assertEqual(2, rendered["call_plan"]["case_count"])
        self.assertIn("COracleCallPlan-SHA256", rendered["declarations"])
        self.assertIn("adler32_z(", rendered["statements"])

    def test_complete_rename_does_not_select_by_known_identity(self) -> None:
        spec = self.load_spec("zlib-adler32-step.json")
        spec["target_id"] = "unfamiliar-target"
        spec["slice_id"] = "unfamiliar-slice"
        spec["function_name"] = "renamed_checksum"
        spec["c_boundary"]["functions"] = ["renamed_checksum"]
        spec["c_boundary"]["signatures"][0]["function"] = "renamed_checksum"
        spec["rust_boundary"]["public_api"][0]["name"] = "renamed_safe_api"

        rendered = render_c_oracle_call_plan(spec, REPO_ROOT)

        self.assertEqual("generated", rendered["status"])
        self.assertIn("renamed_checksum(", rendered["statements"])
        self.assertNotIn("adler32_z(", rendered["statements"])

    def test_harness_validation_rejects_marker_without_target_invocation(self) -> None:
        spec = self.load_spec("zlib-adler32-step.json")
        rendered = render_c_oracle_call_plan(spec, REPO_ROOT)
        contract = {
            "status": "generated",
            "replay_call_plan_sha256": rendered["replay_call_plan_sha256"],
            "case_count": rendered["case_count"],
            "compared_fields": rendered["compared_fields"],
        }
        harness = (
            rendered["declarations"]
            + "uint32_t adler32_z(uint32_t, const unsigned char *, size_t);\n"
            + "int main(void) {\n"
            + rendered["statements"]
            + "  return 0;\n}\n"
        )
        validate_c_oracle_call_plan_harness(spec, contract, harness, REPO_ROOT)

        with self.assertRaisesRegex(ValueError, "contract is missing"):
            validate_c_oracle_call_plan_harness(
                spec, {"status": "not_used"}, harness, REPO_ROOT
            )

        spoofed = harness.replace(
            rendered["statements"],
            '  puts("fixture case empty value matched");\n',
        )
        with self.assertRaisesRegex(ValueError, "target invocation"):
            validate_c_oracle_call_plan_harness(
                spec, contract, spoofed, REPO_ROOT
            )

    def test_omitted_parameter_and_record_return_stay_unavailable(self) -> None:
        rendered = render_c_oracle_call_plan(
            self.load_spec("libuv-ip4-addr.json"), REPO_ROOT
        )

        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("every C parameter", rendered["reason"])

    def test_type_drift_and_fixture_metadata_stay_unavailable(self) -> None:
        type_drift = self.load_spec("zlib-adler32-step.json")
        type_drift["c_boundary"]["signatures"][0]["parameters"][0]["c_type"] = "uint64_t"
        rendered = render_c_oracle_call_plan(type_drift, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("incompatible", rendered["reason"])

        metadata = self.load_spec("zlib-adler32-step.json")
        metadata["replay_contract"]["fixture_assertions"] = [
            {"fixture_field": "status", "encoding": "string", "expected": "ok"}
        ]
        metadata["fixture_contract"]["observable_outputs"].append("status")
        for case in metadata["fixture_contract"]["cases"]:
            case["expected_outputs"]["status"] = "ok"
        rendered = render_c_oracle_call_plan(metadata, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("fixture metadata", rendered["reason"])

    def test_case_identifier_collisions_do_not_collide_in_c_storage(self) -> None:
        spec = self.load_spec("zlib-adler32-step.json")
        cases = spec["fixture_contract"]["cases"]
        cases[0]["id"] = "same-id"
        cases[1]["id"] = "same_id"

        rendered = render_c_oracle_call_plan(spec, REPO_ROOT)

        self.assertEqual("generated", rendered["status"])
        self.assertIn("case_same_id_0_buf", rendered["declarations"])
        self.assertIn("case_same_id_1_buf", rendered["declarations"])

    def test_unsafe_c_string_and_oversized_buffer_fail_closed(self) -> None:
        spec = self.load_spec("zlib-adler32-step.json")
        plan = build_replay_call_plan(spec, REPO_ROOT)
        plan["parameters"][1]["source"] = {
            "kind": "fixture_field",
            "field": "input_hex",
            "encoding": "string",
        }
        signature_parameter = spec["c_boundary"]["signatures"][0]["parameters"][1]
        signature_parameter["c_type"] = "const char *"
        spec["fixture_contract"]["cases"][0]["inputs"]["input_hex"] = "bad\u0000text"
        with patch(
            "validation.tools.c_oracle_call_plan.build_replay_call_plan",
            return_value=plan,
        ):
            rendered = render_c_oracle_call_plan(spec, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("printable ASCII", rendered["reason"])

        oversized = self.load_spec("zlib-adler32-step.json")
        oversized["fixture_contract"]["cases"][0]["inputs"]["input_hex"] = (
            "00" * (1024 * 1024 + 1)
        )
        rendered = render_c_oracle_call_plan(oversized, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("hex fixture field", rendered["reason"])

    def test_usize_literal_obeys_target_pointer_width(self) -> None:
        spec = self.load_spec("zlib-adler32-step.json")
        plan = build_replay_call_plan(spec, REPO_ROOT)
        plan["parameters"][0]["source"]["encoding"] = "usize"
        spec["c_boundary"]["signatures"][0]["parameters"][0]["c_type"] = "size_t"
        spec["build_profile"]["target"]["pointer_width"] = 32
        spec["fixture_contract"]["cases"][0]["inputs"]["seed"] = 2**32

        with patch(
            "validation.tools.c_oracle_call_plan.build_replay_call_plan",
            return_value=plan,
        ):
            rendered = render_c_oracle_call_plan(spec, REPO_ROOT)

        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("usize fixture value", rendered["reason"])

    def test_duplicate_parameter_and_unknown_source_kind_fail_closed(self) -> None:
        spec = self.load_spec("zlib-adler32-step.json")
        plan = build_replay_call_plan(spec, REPO_ROOT)
        plan["parameters"][1]["c_parameter"] = "adler"
        with patch(
            "validation.tools.c_oracle_call_plan.build_replay_call_plan",
            return_value=plan,
        ):
            rendered = render_c_oracle_call_plan(spec, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("mapping is not closed", rendered["reason"])

        plan = build_replay_call_plan(spec, REPO_ROOT)
        plan["parameters"][0]["source"]["kind"] = "guessed_value"
        with patch(
            "validation.tools.c_oracle_call_plan.build_replay_call_plan",
            return_value=plan,
        ):
            rendered = render_c_oracle_call_plan(spec, REPO_ROOT)
        self.assertEqual("unavailable", rendered["status"])
        self.assertIn("source kind is unsupported", rendered["reason"])

    @staticmethod
    def load_spec(filename: str) -> dict:
        return json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / filename).read_text(
                encoding="utf-8"
            )
        )


if __name__ == "__main__":
    unittest.main()
