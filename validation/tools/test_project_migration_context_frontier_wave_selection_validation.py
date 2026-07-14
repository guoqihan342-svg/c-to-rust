from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, content_sha256,
)
from validation.tools._project_migration_harness.context_contracts import canonical
from validation.tools._project_migration_harness.context_frontier_wave import (
    WAVE_INPUT_POLICY, build_context_expansion_query,
)
from validation.tools._project_migration_harness.context_frontier_wave_selection import (
    derive_context_frontier_wave_selection,
)
from validation.tools._project_migration_harness.context_frontier_wave_selection_validation import (
    validate_context_frontier_wave_selection,
)
from validation.tools._project_migration_harness.context_retrieval import (
    partition_context_refs,
)
from validation.tools._project_migration_harness.context_selection_index import (
    ContextSelectionIndex,
)
from validation.tools._project_migration_harness.gate_authority import (
    candidate_verdict_payload,
)


RUN_ID = "wave-selection-validation-run"
TARGET = "scc-target"
DEPENDENCY = "scc-dependency"
KIND = "context-frontier-wave-selection-directives"
CLAIM = {"semantic_gate": False, "translation_coverage_numerator": 0}


class ProjectMigrationContextFrontierWaveSelectionValidationTests(unittest.TestCase):
    def test_accepts_normal_host_derivation(self) -> None:
        bundle, _refs, directives = directive_fixture()
        reference = cas_reference(directives)

        validated = validate_context_frontier_wave_selection(
            directives, directives_reference=reference, context_bundle=bundle,
        )

        self.assertEqual(directives, validated)

    def test_rejects_cross_scc_deferred_fact_injection(self) -> None:
        bundle, refs, directives = directive_fixture()
        forged = deepcopy(directives)
        include = next(
            item for item in forged["selection_constraints"]
            if item["family"] == "include-adjacency"
        )
        include["allowed_deferred_fact_refs"] = sorted([
            *include["allowed_deferred_fact_refs"], refs["cross_deferred"],
        ])
        forged["allowed_deferred_fact_refs"] = include[
            "allowed_deferred_fact_refs"
        ]
        forged["selection_constraint_set_sha256"] = content_sha256(
            forged["selection_constraints"]
        )
        forged["allowed_deferred_fact_set_sha256"] = content_sha256(
            forged["allowed_deferred_fact_refs"]
        )
        forged = rebind(forged)

        with self.assertRaisesRegex(ValueError, "allowed ref scope drifted"):
            validate_context_frontier_wave_selection(
                forged, directives_reference=cas_reference(forged),
                context_bundle=bundle,
            )

    def test_rejects_wrong_internal_set_hash(self) -> None:
        bundle, _refs, directives = directive_fixture()
        drifted = deepcopy(directives)
        drifted["allowed_deferred_fact_set_sha256"] = digest("wrong-set")
        drifted = rebind(drifted)

        with self.assertRaisesRegex(ValueError, "allowed ref set hash drifted"):
            validate_context_frontier_wave_selection(
                drifted, directives_reference=cas_reference(drifted),
                context_bundle=bundle,
            )

    def test_rejects_cas_triple_tampering(self) -> None:
        bundle, _refs, directives = directive_fixture()
        reference = {**cas_reference(directives), "sha256": digest("tampered")}

        with self.assertRaisesRegex(ValueError, "CAS reference binding drifted"):
            validate_context_frontier_wave_selection(
                directives, directives_reference=reference,
                context_bundle=bundle,
            )


def directive_fixture() -> tuple[dict, dict[str, str], dict]:
    bundle, refs = context_fixture()
    failed = failure_evidence()
    query = build_context_expansion_query(
        run_id=RUN_ID, unit_id=TARGET, query_epoch=2,
        requests=[
            {"family": "include-adjacency",
             "anchor_fact_sha256": refs["include"]},
            {"family": "dependency-scc-interface",
             "dependency_scc_id": DEPENDENCY},
            {"family": "verified-failure-fact",
             "failure_evidence_sha256": failed["sha256"]},
        ],
    )
    failures = [failed]
    failure_refs = [failed["sha256"]]
    query_refs = [query["sha256"]]
    seed = {
        "policy": WAVE_INPUT_POLICY, "run_id": RUN_ID, "unit_id": TARGET,
        "wave_index": 1, "dag_sha256": digest("dag"),
        "group_sha256": digest("group"),
        "dependency_closure_sha256": digest("closure"),
        "failure_fact_set_sha256": content_sha256(failure_refs),
        "expansion_query_set_sha256": content_sha256(query_refs),
    }
    unit = {
        **seed, "failure_evidence_sha256s": failure_refs,
        "expansion_query_sha256s": query_refs,
        "selection_seed_sha256": content_sha256(seed),
    }
    directives = derive_context_frontier_wave_selection(
        unit, expansion_query=query, failed_verifier_evidence=failures,
        context_bundle=bundle,
    )
    return bundle, refs, directives


def context_fixture() -> tuple[dict, dict[str, str]]:
    facts: dict[str, dict] = {}

    def add(kind: str, payload: dict) -> str:
        fact = {"kind": kind, "payload": payload}
        fact_sha = hashlib.sha256(canonical(fact)).hexdigest()
        facts[fact_sha] = fact
        return fact_sha

    dependency_function = add("function", {
        "node_id": "dependency-node", "unit_id": "dependency-unit",
        "node_kind": "function", "symbol": "dependency_step",
        "linkage": "external",
    })
    dependency_binding = add("source_binding", {
        "node_id": "dependency-node", "source": {
            "path": "src/dependency.c", "sha256": digest("dependency-source"),
            "span": {"byte_start": 0, "byte_end": 32,
                     "sha256": digest("dependency-span")},
        },
    })
    dependency_signature = add("function_signature", {
        "node_id": "dependency-node", "chunk_index": 0, "chunk_count": 1,
        "content": "int dependency_step(void);",
    })
    dependency_source = add("function_source", {
        "node_id": "dependency-node", "chunk_index": 0, "chunk_count": 1,
        "content": "int dependency_step(void) { return 1; }",
    })
    cross_deferred = add("header_source", {
        "owner_id": "dependency-header", "chunk_index": 0, "chunk_count": 1,
        "content": "#define DEPENDENCY_ONLY 1\n",
    })
    dependency_edge = add("scc_dependency", {
        "scc_id": TARGET, "dependency_scc_id": DEPENDENCY,
    })
    own_function = add("function", {
        "node_id": "target-node", "unit_id": "target-unit",
        "node_kind": "function", "symbol": "target_step", "linkage": "external",
    })
    own_source = add("function_source", {
        "node_id": "target-node", "chunk_index": 0, "chunk_count": 1,
        "content": "int target_step(void) { return dependency_step(); }",
    })
    include = add("include_binding", {
        "unit_id": "target-unit", "kind": "include", "body": "\"extra.h\"",
        "sha256": digest("include-line"), "byte_offset": 0,
        "from_path": "src/target.c", "target": "extra.h", "style": "quote",
        "status": "bound", "path": "include/extra.h",
    })
    header_binding = add("header_source_binding", {
        "owner_id": "header-extra", "source": {
            "path": "include/extra.h", "sha256": digest("header-source"),
            "span": {"byte_start": 0, "byte_end": 24,
                     "sha256": digest("header-span")},
        },
    })
    header_source = add("header_source", {
        "owner_id": "header-extra", "chunk_index": 0, "chunk_count": 1,
        "content": "#define EXTRA_LIMIT 8\n",
    })
    required = [
        dependency_edge, own_function, own_source, dependency_function,
        dependency_binding, dependency_signature,
    ]
    visible, binding, retrieval_set, segments = partition_context_refs(
        TARGET, [*required, include, header_binding, header_source], facts, add,
        max_selected_bytes=8_192, identifier_cache={},
        selection_index=ContextSelectionIndex(facts),
    )
    if binding is None or retrieval_set is None:
        raise AssertionError("fixture must produce a retrieval binding")
    bundle = {
        "schema_version": 1,
        "shared_facts": {key: facts[key] for key in sorted(facts)},
        "pages": [
            {"scc_id": DEPENDENCY, "fact_refs": [
                dependency_function, dependency_binding, dependency_signature,
                dependency_source, cross_deferred,
            ]},
            {"scc_id": TARGET, "fact_refs": visible},
        ],
        "retrieval_bindings": [binding],
        "retrieval_sets": {binding["retrieval_set_sha256"]: retrieval_set},
        "retrieval_segments": segments,
        "claim_boundary": dict(CLAIM),
    }
    return bundle, {"include": include, "cross_deferred": cross_deferred}


def failure_evidence() -> dict:
    payload = candidate_verdict_payload(
        run_id=RUN_ID, unit_id=DEPENDENCY,
        candidate_artifact_id="candidate-failed",
        candidate_sha256=digest("candidate-failed"), gate_family="compile",
        status="failed", diagnostics=[{
            "code": "rustc-type-error", "stage": "compile",
            "message": "type mismatch", "file": "src/dependency.rs",
            "line": 3, "column": 9,
        }],
    )
    return {"sequence": 7, "sha256": content_sha256(payload), "evidence": payload}


def rebind(value: dict) -> dict:
    result = deepcopy(value)
    result["sha256"] = content_sha256({
        key: item for key, item in result.items() if key != "sha256"
    })
    return result


def cas_reference(value: dict) -> dict:
    encoded = canonical_json_bytes(value)
    digest_value = hashlib.sha256(encoded).hexdigest()
    return {
        "path": f"target/run/context/frontier-cas/{KIND}/sha256/"
                f"{digest_value[:2]}/{digest_value}.json",
        "sha256": digest_value, "size_bytes": len(encoded),
    }


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
