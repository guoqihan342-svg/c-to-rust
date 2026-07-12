from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.context_scope import prompt_scope_for_context


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
                    "context_excerpt": {"types": []},
                    "failure_summary": [],
                },
                "unit-cfg.json": {
                    "status": "omitted_invalid_json",
                    "context_excerpt": {"blocks": []},
                },
                "unit-pointer-graph.json": {
                    "status": "loaded",
                    "failure_summary": [{"path": "$.status", "value": "blocked"}],
                },
            }
        }

        self.assertEqual(
            ["slice_spec", "source_spans", "type_map_excerpt", "root_cause_summary"],
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
            self.assertNotIn("C:/private/project", encoded)
            self.assertIn("direct_caller_callee_facts", prompt_scope_for_context(context))


if __name__ == "__main__":
    unittest.main()
