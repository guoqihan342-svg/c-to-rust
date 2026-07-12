from __future__ import annotations

import hashlib
import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.context_callees import (
    build_external_callee_source_context,
    callee_source_input_bindings,
)
from validation.tools._ai_candidate_harness_parts.context_scope import (
    prompt_scope_for_context,
)
from validation.tools._ai_candidate_harness_parts.gate_feedback import (
    REQUIRED_GATES,
    extract_gate_failure_facts,
)
from validation.tools._ai_candidate_harness_parts.provider_readiness import (
    external_callee_source_context_status,
)
from validation.tools._ai_candidate_harness_parts.provider_response import render_prompt


class AiExternalCalleeSourceContextTests(unittest.TestCase):
    def write_fixture(self, root: Path) -> tuple[Path, dict[str, object]]:
        source = root / "src" / "unit.c"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "int helper(int value) {\n"
            "    if (value < 0) { return 17; }\n"
            "    return value + 1;\n"
            "}\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        spec: dict[str, object] = {
            "schema_version": 1,
            "target_id": "generic-target",
            "slice_id": "generic-caller",
            "function_name": "caller",
            "c_source": "int caller(int value) { return helper(value); }",
            "c_boundary": {
                "external_direct_callees": [
                    {
                        "name": "helper",
                        "source_ref": "src/unit.c#helper",
                        "source_files": [{"path": "src/unit.c", "sha256": digest}],
                        "definition_status": "real_source_bound",
                    }
                ],
                "signatures": [
                    {
                        "id": "sig-helper",
                        "role": "external_direct_callee",
                        "function": "helper",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int"}],
                    }
                ],
            },
            "rust_boundary": {
                "public_api": [{"name": "caller", "visibility": "public"}],
                "raw_pointer_policy": "internal_only",
                "unsafe_policy": {"ledger_required": True},
            },
        }
        return source, spec

    def test_binds_generic_hash_checked_callee_definition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-source-") as tmp:
            root = Path(tmp)
            source, spec = self.write_fixture(root)

            context = build_external_callee_source_context(
                spec,
                source_root=root,
                known_roots=(str(root),),
            )

            self.assertEqual(context["status"], "bound")
            self.assertFalse(context["semantics_verified"])
            self.assertEqual(context["blocked"], [])
            block = context["blocks"][0]
            self.assertEqual(block["callee"], "helper")
            self.assertEqual(block["source_file"]["path"], "<source-root>/src/unit.c")
            self.assertEqual(block["source_file"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertIn("return value + 1", block["source_span"]["content"])
            self.assertEqual(block["allowed_use"], "candidate_context_only")
            bindings = callee_source_input_bindings(context)
            self.assertEqual(bindings[0]["kind"], "external_callee_source")
            self.assertEqual(bindings[0]["callee"], "helper")

    def test_hash_and_source_ref_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-source-drift-") as tmp:
            root = Path(tmp)
            _source, spec = self.write_fixture(root)
            callee = spec["c_boundary"]["external_direct_callees"][0]
            callee["source_files"][0]["sha256"] = "0" * 64

            hash_context = build_external_callee_source_context(
                spec,
                source_root=root,
                known_roots=(str(root),),
            )
            self.assertEqual(hash_context["status"], "unavailable")
            self.assertEqual(hash_context["blocked"][0]["reason"], "source_file_sha256_mismatch")

            _source, spec = self.write_fixture(root)
            spec["c_boundary"]["external_direct_callees"][0]["source_ref"] = "src/unit.c#other"
            symbol_context = build_external_callee_source_context(
                spec,
                source_root=root,
                known_roots=(str(root),),
            )
            self.assertEqual(symbol_context["status"], "unavailable")
            self.assertEqual(symbol_context["blocked"][0]["reason"], "source_ref_symbol_mismatch")

    def test_missing_real_source_bound_callee_is_not_provider_ready(self) -> None:
        context_pack = {
            "c_boundary": {
                "required_callee_sections": ["external_direct_callees"],
                "payload": {
                    "external_direct_callees": [
                        {"name": "bound_helper", "definition_status": "real_source_bound"},
                        {"name": "missing_helper", "definition_status": "real_source_bound"},
                        {"name": "strlen", "definition_status": "stdlib_model_pending"},
                    ]
                },
            },
            "external_callee_source_context": {
                "status": "partial",
                "blocks": [{"callee": "bound_helper"}],
                "blocked": [{"callee": "missing_helper", "reason": "source_file_missing"}],
                "source_backed_behavior": {"semantics_verified": False},
            },
        }

        self.assertEqual(external_callee_source_context_status(context_pack), "incomplete")

    def test_context_pack_and_prompt_expose_source_without_duplicate_body(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-context-pack-") as tmp:
            root = Path(tmp)
            _source, spec = self.write_fixture(root)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            context = ai_candidate_harness.build_context_pack(
                spec_path,
                source_root=root,
            )
            prompt = render_prompt(context)

            self.assertEqual(context["external_callee_source_context"]["status"], "bound")
            self.assertIn("external_callee_source_blocks", prompt_scope_for_context(context))
            self.assertIn("Source-backed external callees:", prompt)
            self.assertEqual(prompt.count("return value + 1"), 1)
            self.assertIn(
                "external_callee_source",
                {item["kind"] for item in context["bindings"]["inputs"]},
            )
            self.assertFalse(context["claim_boundary"]["semantic_gate"])

    def test_real_source_guard_constant_is_independent_of_fixture_expected_output(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        spec_path = repo_root / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        source_root = repo_root / "sources" / "FlashDB"

        context = build_external_callee_source_context(
            spec,
            source_root=source_root,
            known_roots=(str(source_root),),
        )
        rules = context["source_backed_behavior"]["rules"]

        self.assertEqual(context["status"], "partial")
        self.assertEqual(
            {rule["callee"] for rule in rules},
            {"fdb_kv_del", "fdb_kv_set_blob"},
        )
        self.assertEqual({rule["effect"]["resolved_integer"] for rule in rules}, {7})
        self.assertEqual(
            {tuple(rule["when"]["field_path"]) for rule in rules},
            {("init_ok",)},
        )
        behavior_sha = context["source_backed_behavior"]["behavior_sha256"]

        drifted = copy.deepcopy(spec)
        for case in drifted["fixture_contract"]["cases"]:
            case["expected_outputs"]["return_code"] = 99
        drifted_context = build_external_callee_source_context(
            drifted,
            source_root=source_root,
            known_roots=(str(source_root),),
        )
        self.assertEqual(
            drifted_context["source_backed_behavior"]["behavior_sha256"],
            behavior_sha,
        )
        self.assertEqual(
            {rule["effect"]["resolved_integer"] for rule in drifted_context["source_backed_behavior"]["rules"]},
            {7},
        )
        self.assertIn(
            "source_behavior_expected_output_mismatch",
            {item["reason"] for item in drifted_context["blocked"]},
        )

    def test_candidate_prompt_withholds_replay_oracle_but_keeps_source_rule(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        spec_path = repo_root / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        context = ai_candidate_harness.build_context_pack(
            spec_path,
            source_root=repo_root / "sources" / "FlashDB",
        )
        replay_source = "fn replay() { assert_eq!(fdb_kv_set(&db, \"boot_count\", None), 7); }\n"
        context["replay_api_contract"] = {
            "schema_version": 1,
            "contract_kind": "generated_replay_rust_source",
            "function_name": "fdb_kv_set",
            "status": "bound",
            "call_count": 1,
            "source": {
                "path": "l3-real-fdb-kv-set-rust-replay-test-draft.rs",
                "sha256": hashlib.sha256(replay_source.encode("utf-8")).hexdigest(),
                "size_bytes": len(replay_source.encode("utf-8")),
                "content": replay_source,
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
        }

        prompt = render_prompt(context)

        self.assertIn("<withheld-oracle-bearing-replay-source>", prompt)
        self.assertIn("Source-backed external-callee behavior contract:", prompt)
        self.assertIn('"resolved_integer":7', prompt)
        behavior_line = next(
            line
            for line in prompt.splitlines()
            if line.startswith("Source-backed external-callee behavior contract:")
        )
        self.assertEqual(behavior_line.count('"resolved_integer":7'), 2)
        self.assertIn(
            '"status":"presented-in-source-backed-external-callee-behavior-contract"',
            prompt,
        )
        self.assertLess(
            prompt.index("Source-backed external-callee behavior contract:"),
            prompt.index("Required generated replay API contract:"),
        )
        self.assertNotIn("assert_eq!", prompt)
        self.assertNotIn('"expected_outputs":{"return_code":7}', prompt)
        self.assertNotIn("every assertion, expected value", prompt)

    def test_repair_feedback_withholds_semantic_expected_and_actual_values(self) -> None:
        digest = "a" * 64
        payloads = {
            gate: {"candidate_sha256": digest, "status": "passed"}
            for gate in REQUIRED_GATES
        }
        payloads["schema_diff"]["first_mismatch"] = None
        payloads["negative_mutation"]["detected"] = True
        payloads["final_verification"]["semantic_pass"] = True
        payloads["generated_replay"] = {
            "candidate_sha256": digest,
            "status": "failed",
            "failures": [
                {
                    "kind": "assertion_failed",
                    "message": "left -1 did not equal right 7",
                    "details": {
                        "expected": 7,
                        "actual": -1,
                        "diagnostic": "expected 7 but observed -1",
                    },
                }
            ],
        }

        result = extract_gate_failure_facts(
            payloads,
            selected_candidate_sha256=digest,
        )
        encoded = json.dumps(result, sort_keys=True)

        self.assertEqual(result["status"], "failed")
        self.assertNotIn("left -1", encoded)
        self.assertNotIn('"expected": 7', encoded)
        self.assertNotIn('"actual": -1', encoded)
        self.assertNotIn("expected 7 but observed -1", encoded)
        self.assertIn('"oracle_values": "withheld"', encoded)


if __name__ == "__main__":
    unittest.main()
