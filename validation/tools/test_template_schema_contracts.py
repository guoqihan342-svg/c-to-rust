import json
import unittest
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_schema_ref(schema: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if not ref:
        return node
    prefix = "#/definitions/"
    if not ref.startswith(prefix):
        raise AssertionError(f"unsupported local schema ref: {ref}")
    return schema["definitions"][ref[len(prefix):]]


class TemplateSchemaContractTests(unittest.TestCase):
    def test_auto_translation_template_documents_five_repair_round_default(self) -> None:
        readme_path = REPO_ROOT / "validation" / "auto-translation-template" / "README.md"
        text = readme_path.read_text(encoding="utf-8")

        self.assertIn("Default repair retry limit is five repair rounds.", text)
        self.assertNotIn("Default repair retry limit is three rounds.", text)

    def test_patch_event_schema_allows_five_repair_rounds(self) -> None:
        template_dir = REPO_ROOT / "validation" / "auto-translation-template"
        schema = load_json(template_dir / "patch-event.schema.json")
        example = load_json(template_dir / "patch-event.example.json")

        self.assertEqual(5, schema["properties"]["round"]["maximum"])

        fifth_round = json.loads(json.dumps(example))
        fifth_round["round"] = 5
        jsonschema.validate(fifth_round, schema)

        sixth_round = json.loads(json.dumps(example))
        sixth_round["round"] = 6
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(sixth_round, schema)

    def test_pointer_graph_template_exposes_alias_and_effect_contract(self) -> None:
        schema_path = REPO_ROOT / "validation" / "pointer-graph-template" / "pointer-graph.schema.json"
        example_path = REPO_ROOT / "validation" / "pointer-graph-template" / "pointer-graph.example.json"
        schema = load_json(schema_path)
        example = load_json(example_path)

        self.assertEqual(example["schema_version"], 2)
        for field in [
            "alias_contract",
            "alias_risks",
            "safe_boundary_preconditions",
            "effect_graph",
        ]:
            self.assertIn(field, schema["properties"])
            self.assertIn(field, example)

        definitions = schema["definitions"]
        for definition in [
            "aliasContract",
            "aliasRisk",
            "safeBoundaryPrecondition",
            "effectGraph",
            "pointerEffect",
        ]:
            self.assertIn(definition, definitions)

        pointer_node_props = definitions["pointerNode"]["properties"]
        self.assertIn("read_effects", pointer_node_props)
        self.assertIn("write_effects", pointer_node_props)

        jsonschema.validate(example, schema)

    def test_slice_spec_template_exposes_memory_model_contract(self) -> None:
        schema_path = REPO_ROOT / "validation" / "slice-spec-template" / "slice-spec.schema.json"
        example_path = REPO_ROOT / "validation" / "slice-spec-template" / "slice-spec.example.json"
        schema = load_json(schema_path)
        example = load_json(example_path)

        self.assertIn("memory_model", schema["properties"])
        self.assertIn("memory_model", example)
        c_boundary_props = schema["properties"]["c_boundary"]["properties"]
        self.assertIn("pointer_contract", c_boundary_props)
        self.assertIn("scalar_arithmetic_contract", c_boundary_props)
        self.assertIn("pointer_contract", example["c_boundary"])
        self.assertIn("scalar_arithmetic_contract", example["c_boundary"])

        pointer_contract_schema = resolve_schema_ref(schema, c_boundary_props["pointer_contract"])
        pointer_contract_props = pointer_contract_schema["properties"]
        for field in [
            "input_buffers",
            "output_pointers",
            "inout_pointers",
            "aliasing_proven",
            "read_read_alias_allowed",
            "noalias_required",
        ]:
            self.assertIn(field, pointer_contract_props)

        scalar_contract_schema = resolve_schema_ref(schema, c_boundary_props["scalar_arithmetic_contract"])
        scalar_contract_props = scalar_contract_schema["properties"]
        for field in [
            "wrapping_profile",
            "signed_overflow",
            "division_by_zero",
            "signed_division_overflow",
            "shift_count",
            "signed_right_shift",
        ]:
            self.assertIn(field, scalar_contract_props)

        fixture_props = schema["properties"]["fixture_contract"]["properties"]
        self.assertIn("scalar_input_domain", fixture_props)
        self.assertIn("scalar_input_domain", example["fixture_contract"])
        scalar_domain_schema = resolve_schema_ref(schema, fixture_props["scalar_input_domain"])
        scalar_domain_props = scalar_domain_schema["properties"]
        for field in ["case_source", "parameters", "covers_overflow_boundaries"]:
            self.assertIn(field, scalar_domain_props)

        memory_schema = resolve_schema_ref(schema, schema["properties"]["memory_model"])
        memory_props = memory_schema["properties"]
        for field in [
            "alias_contract",
            "ownership_contract",
            "length_companions",
            "effect_graph",
        ]:
            self.assertIn(field, memory_props)
            self.assertIn(field, example["memory_model"])

        self.assertIn("c_boundary.scalar_arithmetic_contract", example["cache_invalidation_keys"])
        self.assertIn("fixture_contract.scalar_input_domain", example["cache_invalidation_keys"])

        jsonschema.validate(example, schema)

    def test_auto_translation_and_l3_manifest_templates_expose_alias_gate_summary(self) -> None:
        plan_schema_path = (
            REPO_ROOT
            / "validation"
            / "auto-translation-template"
            / "auto-translation-plan.schema.json"
        )
        plan_example_path = (
            REPO_ROOT
            / "validation"
            / "auto-translation-template"
            / "auto-translation-plan.example.json"
        )
        manifest_schema_path = REPO_ROOT / "validation" / "l3-template" / "evidence-manifest.schema.json"
        manifest_example_path = REPO_ROOT / "validation" / "l3-template" / "evidence-manifest.example.json"

        plan_schema = load_json(plan_schema_path)
        plan_example = load_json(plan_example_path)
        translation_summary_props = plan_schema["properties"]["translation_summary"]["properties"]
        self.assertIn("alias_gate", translation_summary_props)
        self.assertIn("alias_gate", plan_example["translation_summary"])
        jsonschema.validate(plan_example, plan_schema)

        manifest_schema = load_json(manifest_schema_path)
        manifest_example = load_json(manifest_example_path)
        claim_boundary_props = manifest_schema["properties"]["claim_boundary"]["properties"]
        self.assertIn("alias_gate", claim_boundary_props)
        self.assertIn("alias_gate", manifest_example["claim_boundary"])
        jsonschema.validate(manifest_example, manifest_schema)

    def test_validation_profile_template_exposes_competition_environment_contract(self) -> None:
        schema_path = (
            REPO_ROOT
            / "validation"
            / "auto-translation-template"
            / "validation-profile.schema.json"
        )
        schema = load_json(schema_path)

        self.assertIn("competition_environment", schema["properties"])
        self.assertIn("competitionEnvironment", schema["definitions"])
        environment_schema = resolve_schema_ref(schema, schema["properties"]["competition_environment"])
        for field in ["profile_id", "path", "sha256"]:
            self.assertIn(field, environment_schema["required"])
            self.assertIn(field, environment_schema["properties"])

    def test_passed_validation_profile_requires_oracle_boundary_contract(self) -> None:
        schema_path = (
            REPO_ROOT
            / "validation"
            / "auto-translation-template"
            / "validation-profile.schema.json"
        )
        schema = load_json(schema_path)

        self.assertIn("oracle_boundary_contract", schema["properties"])
        self.assertIn("oracleBoundaryContract", schema["definitions"])
        contract_schema = resolve_schema_ref(schema, schema["properties"]["oracle_boundary_contract"])
        for field in [
            "status",
            "observable_outputs",
            "fixture_representativeness",
            "compiler",
            "target",
            "sanitizer_diagnostics",
            "ub_and_implementation_defined",
            "platform_model",
        ]:
            self.assertIn(field, contract_schema["required"])
            self.assertIn(field, contract_schema["properties"])

        minimal_passed_profile = {
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "slice",
            "status": "passed",
            "profile": "L3-dev",
            "route_level": "L3",
            "goal": "dev",
            "required_gates": ["compile", "c_oracle_diff"],
            "optional_gates": [],
            "skipped_gates": [],
            "required_gate_status": {"compile": "passed", "c_oracle_diff": "C_ORACLE_GENERATED"},
            "loop_policy": {"source": "run_policy", "fixed_project_loop_count_required": False},
            "tool_boundaries": {"c_ub": [], "rust_ub": []},
        }
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(minimal_passed_profile, schema)

        minimal_passed_profile["oracle_boundary_contract"] = {
            "schema_version": 1,
            "status": "sufficient_for_semantic_pass",
            "observable_outputs": ["return_code"],
            "fixture_representativeness": {
                "fixture_path": "fixtures/demo.json",
                "fixture_hash": "fixture-hash",
                "declared_case_count": 1,
                "accepted_oracle_case_count": 1,
                "representativeness": "bounded_fixture_contract",
                "limitations": [],
            },
            "compiler": {
                "command_source": "unit-test",
                "include_paths": [],
                "defines": [],
                "flags": [],
                "tool_versions": {},
            },
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "long_width": 64,
                "pointer_width": 64,
                "word_size_bits": 64,
            },
            "sanitizer_diagnostics": {
                "sanitizer_status": "not_run",
                "diagnostic_status": "none_recorded",
                "diagnostics": [],
            },
            "ub_and_implementation_defined": {
                "known_ub": [],
                "implementation_defined_behavior": [],
                "scalar_arithmetic_contract": {},
            },
            "platform_model": {
                "hardware_dependencies": [],
                "rtos_dependencies": [],
                "volatile_dependencies": [],
                "hardware_dependency_status": "not_applicable",
                "rtos_dependency_status": "not_applicable",
                "volatile_dependency_status": "not_applicable",
            },
        }
        jsonschema.validate(minimal_passed_profile, schema)

    def test_route_and_profile_candidate_set_schema_bind_c2rust_baseline_refs(self) -> None:
        for schema_name in ["route-decision.schema.json", "validation-profile.schema.json"]:
            schema_path = REPO_ROOT / "validation" / "auto-translation-template" / schema_name
            schema = load_json(schema_path)
            generation_schema = schema["definitions"]["candidateGenerationEvidence"]
            candidate_schema = schema["definitions"]["candidateSetItem"]

            self.assertIn("generated_draft_semantic_pass", generation_schema["required"])
            self.assertIn("baseline_manifest", candidate_schema["properties"])
            self.assertIn("output_ref", candidate_schema["properties"])
            self.assertIn(
                "baseline_or_repair_candidate_context",
                candidate_schema["properties"]["role"]["enum"],
            )
            self.assertIn(
                "typed_ir_candidate_signal",
                candidate_schema["properties"]["role"]["enum"],
            )

            baseline_manifest_schema = candidate_schema["properties"]["baseline_manifest"]
            self.assertEqual(baseline_manifest_schema["$ref"], "#/definitions/artifactRef")
            output_ref_schema = candidate_schema["properties"]["output_ref"]
            self.assertEqual(output_ref_schema["anyOf"][0]["type"], "null")
            self.assertIn("path", output_ref_schema["anyOf"][1]["required"])
            self.assertIn("sha256", output_ref_schema["anyOf"][1]["required"])

    def test_c2rust_baseline_manifest_schema_rejects_compile_only_spoof_shapes(self) -> None:
        schema = load_json(REPO_ROOT / "validation" / "auto-translation-template" / "c2rust-baseline-manifest.schema.json")
        generated = {
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "c2rust-generated",
            "status": "generated",
            "reason": "generated_by_c2rust",
            "correctness_role": "candidate_context_only",
            "fallback_oracle": "original_c_oracle_required",
            "validation_impact": "candidate context only",
            "source_commit": "1234567",
            "slice_spec": {"path": "slice.json", "sha256": "slice-sha"},
            "build_profile_hash": "profile-sha",
            "commands": [
                {
                    "name": "c2rust",
                    "path": "fake-c2rust",
                    "available": True,
                    "version_status": "OK",
                    "version": "c2rust 0.18.0",
                }
            ],
            "selected_command": {"name": "c2rust", "path": "fake-c2rust"},
            "reference_tree": {
                "path": "tools/c2rust-reference",
                "status": "missing",
                "cargo_toml": "",
                "diagnostic_only": True,
            },
            "generation": {
                "enabled": True,
                "enabled_by": "C2RUST_BASELINE_GENERATION",
                "compile_commands": {"path": "compile_commands.json", "sha256": "compile-db-sha"},
                "command": {
                    "argv": ["c2rust", "transpile", "--emit-build-files", "compile_commands.json"],
                    "working_directory": "validation/evidence/demo",
                    "stdout_log": "baseline.stdout.log",
                    "stderr_log": "baseline.stderr.log",
                    "timeout_seconds": 120,
                    "exit_status": "passed",
                    "returncode": 0,
                },
                "generated_files": [{"path": "src/lib.rs", "sha256": "lib-sha"}],
            },
            "output": {"path": "baseline.rs", "status": "generated", "sha256": "output-sha"},
            "compile": {
                "status": "passed",
                "attempted": True,
                "semantic_pass": False,
                "candidate_output": {"path": "baseline.rs", "status": "generated", "sha256": "output-sha"},
                "command": {
                    "argv": ["rustc", "--crate-type", "lib", "baseline.rs"],
                    "working_directory": "validation/evidence/demo",
                    "stdout_log": "baseline.stdout.log",
                    "stderr_log": "baseline.stderr.log",
                    "timeout_seconds": 60,
                    "exit_status": "passed",
                    "returncode": 0,
                },
                "artifact": {"path": "baseline.rlib", "status": "compiled", "sha256": "artifact-sha"},
                "diagnostics": [],
            },
            "diagnostics": [],
            "must_not_claim": ["C2Rust output proves semantic equivalence"],
        }
        jsonschema.validate(generated, schema)

        generated_without_compile = json.loads(json.dumps(generated))
        generated_without_compile.pop("compile")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(generated_without_compile, schema)

        generated_semantic_spoof = json.loads(json.dumps(generated))
        generated_semantic_spoof["compile"]["semantic_pass"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(generated_semantic_spoof, schema)

        skipped_with_output = json.loads(json.dumps(generated))
        skipped_with_output.update(
            {
                "status": "skipped",
                "reason": "blocked_by_missing_tools",
                "selected_command": None,
                "compile": None,
            }
        )
        skipped_with_output.pop("generation")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(skipped_with_output, schema)

        blocked_with_compile = json.loads(json.dumps(generated))
        blocked_with_compile.update(
            {
                "status": "blocked",
                "reason": "blocked_by_missing_compile_commands",
                "selected_command": None,
                "output": None,
            }
        )
        blocked_with_compile.pop("generation")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(blocked_with_compile, schema)

    def test_route_and_profile_schema_allow_p0_route_governance_summary(self) -> None:
        for schema_name in ["route-decision.schema.json", "validation-profile.schema.json"]:
            schema_path = REPO_ROOT / "validation" / "auto-translation-template" / schema_name
            schema = load_json(schema_path)
            generation_schema = schema["definitions"]["candidateGenerationEvidence"]
            policy_schema = schema["definitions"]["candidateSelectionPolicy"]

            self.assertIn("governance_summary", generation_schema["properties"])
            self.assertIn("p0_route_governance", policy_schema["properties"]["stage"]["enum"])
            self.assertIn("routeGovernanceSummary", schema["definitions"])

    def test_route_and_profile_candidate_set_schema_allows_legacy_compatibility_only(self) -> None:
        for schema_name in ["route-decision.schema.json", "validation-profile.schema.json"]:
            schema_path = REPO_ROOT / "validation" / "auto-translation-template" / schema_name
            schema = load_json(schema_path)
            generation_schema = schema["definitions"]["candidateGenerationEvidence"]
            candidate_schema = schema["definitions"]["candidateSetItem"]
            primary_schema = schema["definitions"]["primaryCandidateEvidence"]

            self.assertIn("compatibility_sources", generation_schema["properties"])
            self.assertNotIn(
                "legacy-string-translator",
                primary_schema["properties"]["selected"]["enum"],
            )
            self.assertIn("compatibility_rust_draft", candidate_schema["properties"]["role"]["enum"])
            self.assertIn(
                "compatibility_only",
                candidate_schema["properties"]["correctness_role"]["enum"],
            )
            self.assertEqual(candidate_schema["properties"]["compatibility_only"]["const"], True)

            jsonschema.validate(
                {
                    "candidate_id": "compat:legacy-string-translator",
                    "kind": "legacy-string-translator",
                    "status": "generated",
                    "role": "compatibility_rust_draft",
                    "semantic_pass": False,
                    "correctness_role": "compatibility_only",
                    "compatibility_only": True,
                },
                candidate_schema,
            )

    def test_blocked_repairs_schema_requires_repair_playbook_fields(self) -> None:
        schema_path = REPO_ROOT / "validation" / "auto-translation-template" / "blocked-repairs.schema.json"
        example_path = REPO_ROOT / "validation" / "auto-translation-template" / "blocked-repairs.example.json"
        schema = load_json(schema_path)
        example = load_json(example_path)

        repair_schema = schema["definitions"]["blockedRepair"]
        for field in [
            "ir_feature_gap",
            "oracle_fixture_gap",
            "candidate_routes",
            "smallest_next_test",
            "human_intervention_point",
        ]:
            self.assertIn(field, repair_schema["required"])
            self.assertIn(field, repair_schema["properties"])

        jsonschema.validate(example, schema)
        incomplete = json.loads(json.dumps(example))
        incomplete["blocked_repairs"][0].pop("ir_feature_gap")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(incomplete, schema)

    def test_c2rust_verified_unsafe_baseline_schema_requires_semantic_gate_boundaries(self) -> None:
        schema_path = (
            REPO_ROOT
            / "validation"
            / "auto-translation-template"
            / "c2rust-verified-unsafe-baseline.schema.json"
        )
        schema = load_json(schema_path)
        artifact_ref = {"path": "validation/evidence/demo/artifact.json", "status": "passed", "sha256": "artifact-sha"}
        output_ref = {
            "path": "validation/evidence/demo/c2rust-baseline-output.rs",
            "status": "generated",
            "sha256": "output-sha",
        }
        compile_ref = {
            "path": "validation/evidence/demo/c2rust-baseline-output.rlib",
            "status": "compiled",
            "sha256": "compile-sha",
        }
        gate_ref = {
            "path": "validation/evidence/demo/gate.json",
            "status": "passed",
            "sha256": "gate-sha",
            "binding": "same_c2rust_output",
            "c2rust_output": output_ref,
            "compile_artifact": compile_ref,
        }
        baseline = {
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "demo-slice",
            "source_commit": "1234567",
            "entry_function": "demo_slice",
            "status": "passed",
            "semantic_pass": True,
            "semantic_claim_source": "verified_unsafe_baseline_gates",
            "generated_draft_semantic_pass": False,
            "fixture": {"path": "validation/l2_slices/fixtures/demo.json", "hash": "fixture-sha"},
            "validation_profile": dict(artifact_ref),
            "route_decision": dict(artifact_ref),
            "c2rust_baseline": {
                "path": "validation/evidence/demo/c2rust-baseline-manifest.json",
                "status": "generated",
                "sha256": "baseline-sha",
            },
            "c2rust_output": output_ref,
            "compile_artifact": compile_ref,
            "direct_c2rust_replay": {
                "status": "passed",
                "semantic_pass": False,
                "observable_replay_pass": True,
                "artifact": {
                    "path": "validation/evidence/demo/c2rust-direct-replay.json",
                    "status": "passed",
                    "sha256": "direct-replay-sha",
                },
                "c2rust_output": output_ref,
                "compile_artifact": compile_ref,
            },
            "gate_refs": {"rust_replay": dict(artifact_ref)},
            "same_output_gate_refs": {
                "c_oracle": dict(gate_ref),
                "rust_replay": {
                    **gate_ref,
                    "path": "validation/evidence/demo/c2rust-direct-replay.json",
                    "replay_kind": "direct_c2rust_output_replay",
                    "correctness_role": "direct_replay_evidence",
                },
                "schema_diff": dict(gate_ref),
                "negative_diff": dict(gate_ref),
                "unsafe_scan": dict(gate_ref),
                "unsafe_ledger": dict(gate_ref),
                "final_verification": dict(gate_ref),
            },
            "accepted_evidence_binding": {
                "status": "accepted",
                "generated_draft_semantic_pass": False,
            },
            "blocked_reasons": [],
            "claim_boundary": {
                "semantic_pass": True,
                "generated_draft_semantic_pass": False,
                "compile_only_is_semantic_pass": False,
            },
        }

        jsonschema.validate(baseline, schema)

        semantic_spoof = json.loads(json.dumps(baseline))
        semantic_spoof["semantic_claim_source"] = "c2rust_compile_only"
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(semantic_spoof, schema)

        generated_draft_spoof = json.loads(json.dumps(baseline))
        generated_draft_spoof["generated_draft_semantic_pass"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(generated_draft_spoof, schema)

        missing_gate = json.loads(json.dumps(baseline))
        missing_gate["same_output_gate_refs"].pop("unsafe_ledger")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_gate, schema)

        rust_replay_not_direct = json.loads(json.dumps(baseline))
        rust_replay_not_direct["same_output_gate_refs"]["rust_replay"].pop("replay_kind")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(rust_replay_not_direct, schema)

        missing_claim_boundary = json.loads(json.dumps(baseline))
        missing_claim_boundary.pop("claim_boundary")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_claim_boundary, schema)

    def test_real_fdb_calc_crc32_verified_unsafe_baseline_matches_schema(self) -> None:
        schema = load_json(
            REPO_ROOT
            / "validation"
            / "auto-translation-template"
            / "c2rust-verified-unsafe-baseline.schema.json"
        )
        artifact = load_json(
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-calc-crc32"
            / "l3-real-fdb-calc-crc32-c2rust-verified-unsafe-baseline.json"
        )

        jsonschema.validate(artifact, schema)

    def test_cfg_template_schema_pins_control_flow_refusal_kinds(self) -> None:
        schema_path = REPO_ROOT / "validation" / "cfg-template" / "cfg.schema.json"
        schema = load_json(schema_path)

        kind_enum = set(
            schema["definitions"]["unsupportedControlFlow"]["properties"]["kind"]["enum"]
        )
        self.assertTrue(
            {
                "goto",
                "switch",
                "label",
                "case",
                "default",
                "setjmp",
                "longjmp",
                "inline_assembly",
                "relooper_refusal",
            }.issubset(kind_enum)
        )


if __name__ == "__main__":
    unittest.main()
