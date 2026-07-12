from __future__ import annotations

import json
import unittest

from validation.tools._ai_candidate_harness_parts.provider_response import render_prompt
from validation.tools._ai_candidate_harness_parts.repair import render_repair_prompt


class AiPromptContractTests(unittest.TestCase):
    def context(self) -> dict[str, object]:
        return {
            "function_name": "translate",
            "c_boundary": {
                "payload": {
                    "signatures": [
                        {"function": "other", "parameters": []},
                        {
                            "function": "translate",
                            "return_type": "bool",
                            "parameters": [
                                {"name": "value", "c_type": "uint8_t *"},
                                {"name": "len", "c_type": "size_t"},
                            ],
                        },
                    ]
                }
            },
            "rust_boundary": {
                "payload": {
                    "public_api": [
                        {"name": "translate", "boundary_kind": "validated_buffer"}
                    ],
                    "raw_pointer_policy": "internal_only",
                    "unsafe_policy": {"ledger_required": True},
                }
            },
        }

    def test_generation_prompt_leads_with_exact_generic_boundary_contract(self) -> None:
        prompt = render_prompt(self.context())
        boundary_line = next(
            line for line in prompt.splitlines() if line.startswith("Required boundary facts: ")
        )
        boundary = json.loads(boundary_line.removeprefix("Required boundary facts: "))

        self.assertEqual("translate", boundary["function_name"])
        self.assertEqual("translate", boundary["c_signature"]["function"])
        self.assertEqual(
            ["value", "len"],
            [item["name"] for item in boundary["c_signature"]["parameters"]],
        )
        self.assertEqual("internal_only", boundary["raw_pointer_policy"])
        self.assertLess(prompt.index("Required boundary facts:"), prompt.index("ContextPack:"))
        self.assertIn("without dropping or reordering adjacent scalar parameters", prompt)

    def test_repair_prompt_repeats_the_same_boundary_before_failure_payload(self) -> None:
        prompt = render_repair_prompt(
            self.context(),
            "pub fn translate(value: *const u8, len: usize) -> bool { false }",
            {"gate": "generated_replay", "message": "raw pointer mismatch"},
        )

        self.assertIn('\"raw_pointer_policy\":\"internal_only\"', prompt)
        self.assertLess(prompt.index("Required boundary facts:"), prompt.index("ContextPack:"))
        self.assertIn("internal_only forbids raw pointers", prompt)


if __name__ == "__main__":
    unittest.main()
