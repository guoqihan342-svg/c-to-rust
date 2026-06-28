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
        self.assertIn("pointer_contract", example["c_boundary"])

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

    def test_route_and_profile_candidate_set_schema_bind_c2rust_baseline_refs(self) -> None:
        for schema_name in ["route-decision.schema.json", "validation-profile.schema.json"]:
            schema_path = REPO_ROOT / "validation" / "auto-translation-template" / schema_name
            schema = load_json(schema_path)
            generation_schema = schema["definitions"]["candidateGenerationEvidence"]
            candidate_schema = schema["definitions"]["candidateSetItem"]

            self.assertIn("generated_draft_semantic_pass", generation_schema["required"])
            self.assertIn("baseline_manifest", candidate_schema["properties"])
            self.assertIn("output_ref", candidate_schema["properties"])

            baseline_manifest_schema = candidate_schema["properties"]["baseline_manifest"]
            self.assertEqual(baseline_manifest_schema["$ref"], "#/definitions/artifactRef")
            output_ref_schema = candidate_schema["properties"]["output_ref"]
            self.assertEqual(output_ref_schema["anyOf"][0]["type"], "null")
            self.assertIn("path", output_ref_schema["anyOf"][1]["required"])
            self.assertIn("sha256", output_ref_schema["anyOf"][1]["required"])


if __name__ == "__main__":
    unittest.main()
