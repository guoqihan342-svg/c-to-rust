from __future__ import annotations

import json
import unittest

from validation.tools._ai_candidate_harness_parts.provider_response import render_prompt
from validation.tools._ai_candidate_harness_parts.repair import render_repair_prompt


class AiPromptContractTests(unittest.TestCase):
    def context(self) -> dict[str, object]:
        return {
            "slice_id": "translate-slice",
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
            "replay_api_contract": {
                "schema_version": 1,
                "contract_kind": "generated_replay_rust_source",
                "function_name": "translate",
                "status": "bound",
                "call_count": 1,
                "source": {
                    "path": "l3-translate-slice-rust-replay-test-draft.rs",
                    "sha256": "a" * 64,
                    "size_bytes": 119,
                    "content": "struct Case { value: &'static [u8], len: usize }\nfn replay(case: Case) { let _ = translate(case.value, case.len); }\n",
                },
                "requirements": {
                    "candidate_defines_function": True,
                    "all_call_sites_typecheck": True,
                    "parameter_count_and_order": "as_invoked_by_generated_replay",
                    "return_type": "as_constrained_by_generated_replay",
                },
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
        self.assertLess(
            prompt.index("Required generated replay API contract:"),
            prompt.index("ContextPack:"),
        )
        self.assertIn("translate(case.value, case.len)", prompt)
        self.assertIn("<presented-in-required-replay-api-contract>", prompt)
        self.assertIn("without dropping or reordering adjacent scalar parameters", prompt)

    def test_repair_prompt_repeats_the_same_boundary_before_failure_payload(self) -> None:
        prompt = render_repair_prompt(
            self.context(),
            "pub fn translate(value: *const u8, len: usize) -> bool { false }",
            {"gate": "generated_replay", "message": "raw pointer mismatch"},
        )

        self.assertIn('\"raw_pointer_policy\":\"internal_only\"', prompt)
        self.assertLess(prompt.index("Required boundary facts:"), prompt.index("ContextPack:"))
        self.assertLess(
            prompt.index("Required generated replay API contract:"),
            prompt.index("FailureFacts:"),
        )
        self.assertIn("translate(case.value, case.len)", prompt)
        self.assertIn("internal_only forbids raw pointers", prompt)

    def test_structured_call_plan_payload_appears_once_and_api_name_is_authoritative(self) -> None:
        context = self.context()
        context["replay_api_contract"]["schema_version"] = 2
        context["replay_api_contract"]["api_name"] = "translate_safe"
        context["replay_api_contract"]["call_plan"] = {
            "status": "bound",
            "source_function_name": "translate",
            "api_name": "translate_safe",
            "plan_sha256": "b" * 64,
            "c_parameter_mappings": [{"c_parameter": "value"}],
        }

        prompt = render_prompt(context)

        self.assertEqual(1, prompt.count('"c_parameter_mappings"'))
        self.assertIn("Implement the exact api_name", prompt)
        self.assertIn('"api_name":"translate_safe"', prompt)
        self.assertIn('"function_name":"translate"', prompt)


if __name__ == "__main__":
    unittest.main()
