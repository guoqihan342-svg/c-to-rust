from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.context_scope import prompt_scope_for_context
from validation.tools._ai_candidate_harness_parts.provider_readiness import (
    evaluate_provider_readiness,
)


class AiContextScopeTests(unittest.TestCase):
    def test_minimal_context_claims_only_always_present_inputs(self) -> None:
        self.assertEqual(
            ["slice_spec", "source_spans"],
            prompt_scope_for_context({}),
        )

    def test_artifact_scopes_require_loaded_excerpts_or_failure_facts(self) -> None:
        context = {
            "deterministic_artifacts": {
                "unit-type-map.json": {
                    "status": "loaded",
                    "context_excerpt": {"types": [{"name": "word_t"}]},
                    "failure_summary": [],
                },
                "unit-cfg.json": {
                    "status": "loaded",
                    "context_excerpt": {
                        "status": "omitted_too_large",
                        "sha256": "a" * 64,
                    },
                },
                "unit-pointer-graph.json": {
                    "status": "loaded",
                    "failure_summary": [
                        {"path": "$.status", "value": "ok"},
                        {"path": "$.diagnostics", "value": ["informational note"]},
                    ],
                },
                "unit-blocked-repairs.json": {
                    "status": "loaded",
                    "failure_summary": [{"path": "$.status", "value": "blocked"}],
                },
            }
        }

        self.assertEqual(
            ["slice_spec", "source_spans", "type_map_excerpt", "root_cause_summary"],
            prompt_scope_for_context(context),
        )

    def test_empty_callee_objects_do_not_claim_caller_callee_facts(self) -> None:
        context = {
            "c_boundary": {
                "payload": {
                    "external_direct_callees": [{}],
                    "signatures": [{"role": "external_direct_callee"}],
                    "direct_dependencies": [{"kind": "callee"}],
                    "call_expression_contract": {"unknown": True},
                }
            }
        }

        self.assertNotIn(
            "direct_caller_callee_facts",
            prompt_scope_for_context(context),
        )

    def test_external_direct_callee_metadata_is_bounded_and_declared(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        spec_path = repo_root / "validation" / "slice-specs" / "demo-external-direct-callee.json"

        context = ai_candidate_harness.build_context_pack(spec_path)
        payload = context["c_boundary"]["payload"]

        self.assertIn("external_direct_callees", payload)
        self.assertIn("call_expression_contract", payload)
        self.assertEqual(
            "real_source_bound",
            payload["external_direct_callees"][0]["definition_status"],
        )
        self.assertIn("direct_caller_callee_facts", prompt_scope_for_context(context))

    def test_external_callee_metadata_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-scope-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "target_id": "generic",
                        "slice_id": "callee",
                        "function_name": "caller",
                        "c_source": "int caller(int x) { return helper(x); }",
                        "c_boundary": {
                            "external_direct_callees": [
                                {
                                    "name": "helper",
                                    "source_ref": "C:/private/project/helper.c",
                                    "api_key": "must-not-leak",
                                    "notes": (
                                        'api_key="quoted-secret"; '
                                        "password: 'single-quoted-secret'; "
                                        '{"api_key":"json-secret"}; '
                                        r'{\"token\":\"escaped-json-secret\"}'
                                    ),
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            context = ai_candidate_harness.build_context_pack(spec_path)
            encoded = json.dumps(context["c_boundary"], sort_keys=True)

            self.assertNotIn("must-not-leak", encoded)
            self.assertNotIn("quoted-secret", encoded)
            self.assertNotIn("single-quoted-secret", encoded)
            self.assertNotIn("json-secret", encoded)
            self.assertNotIn("escaped-json-secret", encoded)
            self.assertNotIn("C:/private/project", encoded)
            self.assertIn("direct_caller_callee_facts", prompt_scope_for_context(context))

    def test_truncated_required_callee_boundary_blocks_provider(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-budget-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "target_id": "generic",
                        "slice_id": "large-callee",
                        "function_name": "caller",
                        "c_source": "int caller(int x) { return helper(x); }",
                        "c_boundary": {
                            "external_direct_callees": [
                                {
                                    "name": "helper",
                                    "definition_status": "real_source_bound",
                                }
                            ],
                            "call_expression_contract": {"direct_call_only": True},
                            "signatures": [
                                {"function": f"helper_{index}", "c_source": "x" * 600}
                                for index in range(40)
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            context = ai_candidate_harness.build_context_pack(spec_path)

            self.assertTrue(context["c_boundary"]["truncated"])
            self.assertIn(
                "c_boundary_truncated",
                context["c_boundary"]["missing_required_callee_sections"],
            )
            self.assertEqual(
                {
                    "status": "blocked",
                    "source_span_status": "inline_slice_spec",
                    "context_boundary_status": "required_callee_context_incomplete",
                },
                evaluate_provider_readiness(context),
            )
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=lambda _argv, _timeout: self.fail("truncated callee invoked provider"),
            )
            self.assertEqual("blocked", manifest["status"])
            self.assertEqual(0, manifest["provider_invocations"])

    def test_total_context_budget_omission_blocks_required_callee(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-total-budget-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "target_id": "generic",
                        "slice_id": "total-budget-callee",
                        "function_name": "caller",
                        "c_source": "int caller(int x) { return helper(x); }",
                        "c_boundary": {
                            "external_direct_callees": [
                                {
                                    "name": "helper",
                                    "definition_status": "real_source_bound",
                                }
                            ],
                            "signatures": [
                                {"function": "helper", "c_source": "x" * 3_500}
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "validation.tools._ai_candidate_harness_parts.context.MAX_CONTEXT_BYTES",
                5_000,
            ):
                context = ai_candidate_harness.build_context_pack(spec_path)

            self.assertEqual(
                "omitted_for_context_budget",
                context["c_boundary"]["payload"]["status"],
            )
            self.assertIn(
                "external_direct_callees",
                context["c_boundary"]["missing_required_callee_sections"],
            )
            self.assertEqual(
                "required_callee_context_incomplete",
                evaluate_provider_readiness(context)["context_boundary_status"],
            )


if __name__ == "__main__":
    unittest.main()
