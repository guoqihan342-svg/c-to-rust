from __future__ import annotations

import json
import unittest

from validation.tools._project_migration_harness.artifacts import (
    content_sha256,
    write_json_artifact,
)
from validation.tools._project_migration_harness.project_knowledge import (
    build_project_knowledge,
    knowledge_entry,
    validate_project_knowledge,
)
from validation.tools._project_migration_harness.project_prompt import (
    render_project_worker_prompt,
)
from validation.tools.project_migration_runtime_test_support import RuntimeHarnessCase


class ProjectMigrationKnowledgeTests(RuntimeHarnessCase):
    def test_retrieval_is_relevant_deduplicated_and_content_bound(self) -> None:
        relevant = entry("api-fact", ["unit:a"], {"symbol": "parse", "arity": 2})
        unrelated = entry("type-fact", ["unit:b"], {"name": "Header", "size_bytes": 8})
        bundle = build_project_knowledge(
            [unrelated, relevant, relevant],
            subject_refs=["unit:a"],
            max_entries=4,
            max_bytes=8_192,
        )

        validated = validate_project_knowledge(bundle)

        self.assertEqual(1, validated["entry_count"])
        self.assertEqual(relevant["sha256"], validated["entries"][0]["sha256"])

        drifted = json.loads(json.dumps(bundle))
        drifted["entries"][0]["payload"]["arity"] = 3
        with self.assertRaisesRegex(ValueError, "canonical or hash-bound"):
            validate_project_knowledge(drifted)

    def test_oracle_values_and_raw_repository_source_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            entry("failure-class", ["unit:a"], {"expected": "secret answer"})
        with self.assertRaisesRegex(ValueError, "raw repository/source"):
            entry("build-fact", ["unit:a"], {"source_content": "entire tree"})
        with self.assertRaisesRegex(ValueError, "semantic acceptance"):
            entry("candidate-decision", ["unit:a"], {"decision": "accepted"})

    def test_hash_bound_bundle_is_loaded_into_the_prompt(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        bundle = build_project_knowledge(
            [entry("build-fact", [request["group_id"]], {"target_kind": "static"})],
            subject_refs=[request["group_id"]],
            max_bytes=8_192,
        )
        reference = write_json_artifact(
            self.harness,
            "target/run/harness/knowledge/current.json",
            bundle,
        )
        request["input_facts"]["project_knowledge"] = reference
        base = {
            key: value for key, value in request.items()
            if key not in {"effective_input_sha256", "execution_binding"}
        }
        request["effective_input_sha256"] = content_sha256(base)

        prompt = json.loads(render_project_worker_prompt(
            request, harness_root=self.harness,
        ))

        knowledge = prompt["bound_inputs"]["project_knowledge"]
        self.assertEqual(bundle["bundle_sha256"], knowledge["bundle_sha256"])
        self.assertEqual(1, knowledge["entry_count"])


def entry(kind: str, subjects: list[str], payload: dict) -> dict:
    return knowledge_entry(
        kind=kind,
        authority="host-extractor",
        subjects=subjects,
        payload=payload,
        evidence_sha256s=["a" * 64],
    )


if __name__ == "__main__":
    unittest.main()
