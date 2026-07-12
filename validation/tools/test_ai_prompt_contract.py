from __future__ import annotations

import json
import copy
import unittest

from validation.tools._ai_candidate_harness_parts.context_scope import prompt_scope_for_context
from validation.tools._ai_candidate_harness_parts.context_typed_ir import (
    typed_ir_context_status,
    typed_ir_summary,
)
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
                "model_input_policy": {
                    "replay_source_content": "withheld_oracle_bearing",
                    "oracle_values": "withheld",
                    "call_plan": "included",
                    "required_candidate_api": "included_when_bound",
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
        self.assertNotIn("translate(case.value, case.len)", prompt)
        self.assertIn("<withheld-oracle-bearing-replay-source>", prompt)
        self.assertIn("<presented-in-required-replay-api-contract>", prompt)
        self.assertIn("without dropping or reordering adjacent scalar parameters", prompt)
        self.assertEqual(1, prompt.count("Required replay discipline:"))
        self.assertIn("oracle values are intentionally withheld", prompt)
        self.assertIn("fixture lookup tables", prompt)
        self.assertLess(
            prompt.index("Required replay discipline:"),
            prompt.index("Required generated replay API contract:"),
        )

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
        self.assertLess(
            prompt.index("Required boundary facts:"),
            prompt.index("CurrentCandidate:"),
        )
        self.assertLess(
            prompt.index("Required generated replay API contract:"),
            prompt.index("ContextPack:"),
        )
        self.assertLess(
            prompt.index("Required generated replay API contract:"),
            prompt.index("CurrentCandidate:"),
        )
        self.assertNotIn("translate(case.value, case.len)", prompt)
        self.assertIn("<withheld-oracle-bearing-replay-source>", prompt)
        self.assertIn("internal_only forbids raw pointers", prompt)
        self.assertEqual(1, prompt.count("Required replay discipline:"))
        self.assertIn("oracle values are intentionally withheld", prompt)
        self.assertLess(
            prompt.index("Required replay discipline:"),
            prompt.index("Required generated replay API contract:"),
        )

    def test_repair_prompt_requests_only_one_full_candidate_shape(self) -> None:
        prompt = render_repair_prompt(
            self.context(),
            "pub fn translate(value: &[u8], len: usize) -> bool { value.len() == len }",
            {"gate": "rustc", "message": "supporting declaration missing"},
        )

        candidate_shape = (
            '{"schema_version":1,"repair":{"kind":"candidate","language":"rust",'
            '"source":"...full Rust source..."},"assumptions":[]}'
        )
        self.assertEqual(1, prompt.count(candidate_shape))
        self.assertIn("one full, self-contained Rust replacement candidate", prompt)
        self.assertIn("include all declarations needed by the generated replay API contract", prompt)
        self.assertNotIn('"kind":"patch"', prompt)
        self.assertNotIn("unified_diff", prompt)
        self.assertNotIn("Choose exactly one repair form", prompt)

    def test_source_typed_ir_semantics_are_high_salience_for_candidate_and_repair(self) -> None:
        context = self.context()
        summary = typed_ir_summary({
            "name": "translate",
            "return_type": {"canonical": "_Bool", "width_bits": 8},
            "params": [],
            "body": [
                {
                    "Assign": {
                        "target": {
                            "Member": {
                                "base": {"Var": {"name": "state"}},
                                "field": "count",
                                "is_arrow": False,
                            }
                        },
                        "value": {"LitInt": {"value": 1, "spelling": "1"}},
                    }
                },
                {"Return": {"value": {"LitInt": {"value": 0, "spelling": "0"}}}},
            ],
        })
        context["deterministic_artifacts"] = {
            "unit-clang-lowering-report.json": {
                "status": "loaded",
                "input": {"path": "unit-clang-lowering-report.json", "sha256": "d" * 64},
                "context_excerpt": {
                    "lowering_report": {
                        "function_ir_summary": summary,
                    }
                },
            }
        }

        prompt = render_prompt(context)
        repair_prompt = render_repair_prompt(
            context,
            "pub fn translate(value: &[u8], len: usize) -> bool { value.len() == len }",
            {"gate": "generated_replay", "kind": "replay_failed"},
        )

        for rendered in (prompt, repair_prompt):
            self.assertEqual(rendered.count("Source-derived C semantics contract:"), 1)
            self.assertIn('"artifact_sha256":"' + ("d" * 64) + '"', rendered)
            self.assertIn('"field":"count"', rendered)
            self.assertIn('"kind":"Return"', rendered)
            self.assertIn("Use structure-preserving lowering", rendered)
            self.assertIn("A DoWhile body must execute before its condition", rendered)
            self.assertIn("Preserve the exact required candidate API signature", rendered)
            self.assertLess(
                rendered.index("Source-derived C semantics contract:"),
                rendered.index("Required generated replay API contract:"),
            )
            self.assertIn("not oracle output and not semantic acceptance", rendered)

        self.assertEqual(typed_ir_context_status(context), "ready")
        self.assertIn("typed_ir_excerpt", prompt_scope_for_context(context))
        tampered = copy.deepcopy(context)
        tampered_summary = tampered["deterministic_artifacts"][
            "unit-clang-lowering-report.json"
        ]["context_excerpt"]["lowering_report"]["function_ir_summary"]
        tampered_summary["body"][0]["target"]["field"] = "drifted"
        self.assertEqual(typed_ir_context_status(tampered), "invalid")
        self.assertNotIn("Source-derived C semantics contract:", render_prompt(tampered))
        self.assertNotIn("typed_ir_excerpt", prompt_scope_for_context(tampered))

    def test_incomplete_typed_ir_projection_is_never_rendered_as_exact_semantics(self) -> None:
        for body, expected_issue in (
            ([{"UnknownStmt": {}}], "statement_unsupported:UnknownStmt"),
            (
                [
                    {"Expr": {"expr": {"LitInt": {"value": index, "spelling": str(index)}}}}
                    for index in range(65)
                ],
                "sequence_limit_exceeded",
            ),
        ):
            with self.subTest(expected_issue=expected_issue):
                context = self.context()
                summary = typed_ir_summary({"name": "translate", "params": [], "body": body})
                self.assertEqual(summary["projection_status"], "incomplete")
                self.assertIn(expected_issue, summary["unsupported_nodes"])
                context["deterministic_artifacts"] = {
                    "unit-clang-lowering-report.json": {
                        "status": "loaded",
                        "input": {
                            "path": "unit-clang-lowering-report.json",
                            "sha256": "d" * 64,
                        },
                        "context_excerpt": {
                            "lowering_report": {"function_ir_summary": summary}
                        },
                    }
                }

                self.assertEqual(typed_ir_context_status(context), "invalid")
                self.assertNotIn("Source-derived C semantics contract:", render_prompt(context))
                self.assertNotIn("typed_ir_excerpt", prompt_scope_for_context(context))

    def test_structured_call_plan_payload_appears_once_and_api_name_is_authoritative(self) -> None:
        context = self.context()
        context["replay_api_contract"]["schema_version"] = 3
        context["replay_api_contract"]["api_name"] = "translate_safe"
        context["replay_api_contract"]["call_plan"] = {
            "status": "bound",
            "source_function_name": "translate",
            "api_name": "translate_safe",
            "plan_sha256": "b" * 64,
            "c_parameter_mappings": [{"c_parameter": "value"}],
        }
        context["replay_api_contract"]["required_candidate_api"] = {
            "schema_version": 1,
            "status": "bound",
            "api_name": "translate_safe",
            "plan_sha256": "b" * 64,
            "signature": "pub fn translate_safe(value: &[u8], len: usize) -> bool",
            "supporting_types_source": "",
            "candidate_source_contract": {
                "mode": "self_contained",
                "type_environment": "closed",
                "supporting_types_source": "none",
                "harness_injects_missing_types": False,
            },
            "return_lifetime_from": None,
            "contract_sha256": "c" * 64,
        }

        prompt = render_prompt(context)

        self.assertEqual(1, prompt.count('"c_parameter_mappings"'))
        self.assertEqual(1, prompt.count("pub fn translate_safe(value: &[u8], len: usize) -> bool"))
        self.assertIn("Implement the exact api_name", prompt)
        self.assertLess(prompt.index("Required candidate API:"), prompt.index("ContextPack:"))
        self.assertLess(
            prompt.index("Required candidate API:"),
            prompt.index("Required generated replay API contract:"),
        )
        self.assertIn('"api_name":"translate_safe"', prompt)
        self.assertIn('"function_name":"translate"', prompt)
        self.assertEqual(1, prompt.count("Candidate source assembly:"))
        self.assertIn("The harness injects no missing types", prompt)

        repair_prompt = render_repair_prompt(
            context,
            "pub fn translate_safe(value: &[u8], len: usize) -> bool { value.len() == len }",
            {"gate": "generated_replay", "message": "exact API mismatch"},
        )
        self.assertIn('"api_name":"translate_safe"', repair_prompt)
        self.assertEqual(1, repair_prompt.count("Candidate source assembly:"))
        repair_contract_prefix = repair_prompt.split("CurrentCandidate:", 1)[0]
        self.assertEqual(
            1,
            repair_contract_prefix.count(
                "pub fn translate_safe(value: &[u8], len: usize) -> bool"
            ),
        )
        self.assertNotIn("translate(case.value, case.len)", repair_prompt)
        self.assertIn("<withheld-oracle-bearing-replay-source>", repair_prompt)
        for marker in ("ContextPack:", "CurrentCandidate:"):
            self.assertLess(repair_prompt.index("Required boundary facts:"), repair_prompt.index(marker))
            self.assertLess(repair_prompt.index("Required candidate API:"), repair_prompt.index(marker))
            self.assertLess(
                repair_prompt.index("Required generated replay API contract:"),
                repair_prompt.index(marker),
            )

    def test_scripted_callees_are_harness_owned_and_oracle_free(self) -> None:
        context = self.context()
        context["replay_api_contract"]["schema_version"] = 3
        context["replay_api_contract"]["call_plan"] = {
            "status": "bound",
            "source_function_name": "translate",
            "api_name": "translate",
            "plan_sha256": "b" * 64,
            "scripted_runtime": {
                "stimuli": [{"callee": "next_value", "expected": 999}],
                "probes": [
                    {"callee": "visit", "kind": "call_count", "expected": 17},
                    {"callee": "next_value", "kind": "call_order", "expected": [1, 2]},
                ],
            },
        }

        prompts = (
            render_prompt(context),
            render_repair_prompt(
                context,
                "pub fn translate(value: &[u8], len: usize) -> bool { value.len() == len }",
                {"gate": "generated_replay", "kind": "replay_failed"},
            ),
        )

        for prompt in prompts:
            self.assertEqual(prompt.count("Harness-owned scripted callee contract:"), 1)
            contract_line = next(
                line
                for line in prompt.splitlines()
                if line.startswith("Harness-owned scripted callee contract:")
            )
            self.assertIn('"name":"next_value"', contract_line)
            self.assertIn('"name":"visit"', contract_line)
            self.assertIn('"candidate_defines_functions":false', contract_line)
            self.assertNotIn("999", contract_line)
            self.assertNotIn("17", contract_line)
            self.assertIn("already in lexical scope", prompt)
            self.assertIn("do not add any fn, extern", prompt)


if __name__ == "__main__":
    unittest.main()
