from __future__ import annotations

import json
from pathlib import Path
import unittest

from validation.tools.c_oracle_call_plan import render_c_oracle_call_plan
from validation.tools.c_oracle_output_protocol import (
    c_oracle_call_plan_output_gate,
    validate_c_oracle_call_plan_output_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class COracleOutputProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        spec_path = REPO_ROOT / "validation/slice-specs/zlib-adler32-step.json"
        self.spec = json.loads(spec_path.read_text(encoding="utf-8"))
        self.rendered = render_c_oracle_call_plan(self.spec, REPO_ROOT)
        self.assertEqual("generated", self.rendered["status"])

    def test_exact_records_allow_unrelated_diagnostics(self) -> None:
        run = self.run_with_records(self.rendered["protocol_records"])

        gate = c_oracle_call_plan_output_gate(self.rendered, None, run)

        self.assertEqual("matched_not_oracle", gate["status"])
        self.assertEqual([], gate["missing_stdout_fragments"])
        self.assertEqual([], gate["unexpected_protocol_records"])
        self.assertEqual([], gate["invalid_protocol_records"])

    def test_missing_duplicate_extra_reordered_and_wrong_value_fail(self) -> None:
        records = self.rendered["protocol_records"]
        mutations = [
            records[:1],
            [records[0], records[0], records[1]],
            [*records, records[0].replace("case_result", "extra_result")],
            list(reversed(records)),
            [records[0].replace('"value":"1"', '"value":"2"'), records[1]],
            [records[0].replace("975b48", "000000"), records[1]],
        ]

        for observed in mutations:
            with self.subTest(observed=observed):
                gate = c_oracle_call_plan_output_gate(
                    self.rendered, None, self.run_with_records(observed)
                )
                self.assertEqual("mismatch_not_oracle", gate["status"])

    def test_malformed_and_duplicate_json_keys_fail(self) -> None:
        records = self.rendered["protocol_records"]
        malformed = "C2R_C_ORACLE_JSON {not-json}"
        duplicate = records[0].replace(
            '"schema_version":1}', '"schema_version":1,"schema_version":1}'
        )

        for first in (malformed, duplicate):
            gate = c_oracle_call_plan_output_gate(
                self.rendered, None, self.run_with_records([first, records[1]])
            )
            self.assertEqual("mismatch_not_oracle", gate["status"])
            self.assertTrue(gate["invalid_protocol_records"])

    def test_validator_recomputes_gate_from_persisted_stdout(self) -> None:
        run = self.run_with_records(self.rendered["protocol_records"])
        run["output_gate"] = c_oracle_call_plan_output_gate(
            self.rendered, None, run
        )
        contract = {
            "status": "generated",
            "replay_call_plan_sha256": self.rendered["replay_call_plan_sha256"],
            "case_count": self.rendered["case_count"],
            "compared_fields": self.rendered["compared_fields"],
            "output_protocol": self.rendered["output_protocol"],
            "protocol_record_count": len(self.rendered["protocol_records"]),
        }
        validate_c_oracle_call_plan_output_gate(
            self.spec, contract, run, REPO_ROOT
        )

        run["stdout"] = run["stdout"].replace('"value":"1"', '"value":"2"')
        with self.assertRaisesRegex(ValueError, "drifted from captured stdout"):
            validate_c_oracle_call_plan_output_gate(
                self.spec, contract, run, REPO_ROOT
            )

    @staticmethod
    def run_with_records(records: list[str]) -> dict[str, object]:
        return {
            "status": "exited_zero_not_oracle",
            "returncode": 0,
            "stdout": "diagnostic before\n" + "\n".join(records) + "\ndiagnostic after\n",
        }


if __name__ == "__main__":
    unittest.main()
