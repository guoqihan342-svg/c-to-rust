from __future__ import annotations
from copy import deepcopy
import hashlib
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.context_contracts import canonical
from validation.tools._project_migration_harness.context_frontier_wave import (
    WAVE_INPUT_POLICY, build_context_expansion_query,
)
from validation.tools._project_migration_harness.context_frontier_wave_selection import (
    CLAIM_BOUNDARY, derive_context_frontier_wave_selection,
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
RUN_ID = "wave-selection-run"
TARGET = "scc-target"
DEPENDENCY = "scc-dependency"
def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()
def add_fact(facts: dict[str, dict], kind: str, payload: dict) -> str:
    fact = {"kind": kind, "payload": payload}
    fact_sha = hashlib.sha256(canonical(fact)).hexdigest()
    facts[fact_sha] = fact
    return fact_sha
def evidence(sequence: int = 7, *, unit_id: str = DEPENDENCY) -> dict:
    payload = candidate_verdict_payload(
        run_id=RUN_ID,
        unit_id=unit_id,
        candidate_artifact_id=f"candidate-{sequence}",
        candidate_sha256=digest(f"candidate-{sequence}"),
        gate_family="compile",
        status="failed",
        diagnostics=[{
            "code": "rustc-type-error", "stage": "compile",
            "message": "type mismatch", "file": "src/dependency.rs",
            "line": 3, "column": 9,
        }],
    )
    return {"sequence": sequence, "sha256": content_sha256(payload), "evidence": payload}
def unit_input(failure_sha: str, query_sha: str) -> dict:
    failure_hashes = [failure_sha]
    query_hashes = [query_sha]
    seed = {
        "policy": WAVE_INPUT_POLICY,
        "run_id": RUN_ID,
        "unit_id": TARGET,
        "wave_index": 1,
        "dag_sha256": digest("dag"),
        "group_sha256": digest("target-group"),
        "dependency_closure_sha256": digest("dependency-closure"),
        "failure_fact_set_sha256": content_sha256(failure_hashes),
        "expansion_query_set_sha256": content_sha256(query_hashes),
    }
    return {
        **seed,
        "failure_evidence_sha256s": failure_hashes,
        "expansion_query_sha256s": query_hashes,
        "selection_seed_sha256": content_sha256(seed),
    }


def context_fixture() -> tuple[dict, dict[str, str]]:
    facts: dict[str, dict] = {}
    dependency_function = add_fact(facts, "function", {
        "node_id": "dependency-node", "unit_id": "dependency-unit",
        "node_kind": "function", "symbol": "dependency_step", "linkage": "external",
    })
    dependency_binding = add_fact(facts, "source_binding", {
        "node_id": "dependency-node", "source": {
            "path": "src/dependency.c", "sha256": digest("dependency-source"),
            "span": {"byte_start": 0, "byte_end": 32, "sha256": digest("dependency-span")},
        },
    })
    dependency_signature = add_fact(facts, "function_signature", {
        "node_id": "dependency-node", "chunk_index": 0, "chunk_count": 1,
        "content": "int dependency_step(void);",
    })
    dependency_source = add_fact(facts, "function_source", {
        "node_id": "dependency-node", "chunk_index": 0, "chunk_count": 1,
        "content": "int dependency_step(void) { return 1; }",
    })
    dependency_edge = add_fact(facts, "scc_dependency", {
        "scc_id": TARGET, "dependency_scc_id": DEPENDENCY,
    })
    own_function = add_fact(facts, "function", {
        "node_id": "target-node", "unit_id": "target-unit",
        "node_kind": "function", "symbol": "target_step", "linkage": "external",
    })
    own_source = add_fact(facts, "function_source", {
        "node_id": "target-node", "chunk_index": 0, "chunk_count": 1,
        "content": "int target_step(void) { return dependency_step(); }",
    })
    include_anchor = add_fact(facts, "include_binding", {
        "unit_id": "target-unit", "kind": "include", "body": '"extra.h"',
        "sha256": digest("include-line"), "byte_offset": 0,
        "from_path": "src/target.c", "target": "extra.h", "style": "quote",
        "status": "bound", "path": "include/extra.h",
    })
    header_binding = add_fact(facts, "header_source_binding", {
        "owner_id": "header-extra", "source": {
            "path": "include/extra.h", "sha256": digest("header-source"),
            "span": {"byte_start": 0, "byte_end": 24, "sha256": digest("header-span")},
        },
    })
    header_source = add_fact(facts, "header_source", {
        "owner_id": "header-extra", "chunk_index": 0, "chunk_count": 1,
        "content": "#define EXTRA_LIMIT 8\n",
    })
    required = [
        dependency_edge, own_function, own_source, dependency_function,
        dependency_binding, dependency_signature,
    ]

    def adder(kind: str, payload: dict) -> str:
        return add_fact(facts, kind, payload)

    visible, binding, retrieval_set, segments = partition_context_refs(
        TARGET, [*required, include_anchor, header_binding, header_source],
        facts, adder, max_selected_bytes=8_192, identifier_cache={},
        selection_index=ContextSelectionIndex(facts),
    )
    assert binding is not None and retrieval_set is not None
    bundle = {
        "schema_version": 1,
        "shared_facts": {key: facts[key] for key in sorted(facts)},
        "pages": [
            {"scc_id": DEPENDENCY, "fact_refs": [
                dependency_function, dependency_binding,
                dependency_signature, dependency_source,
            ]},
            {"scc_id": TARGET, "fact_refs": visible},
        ],
        "retrieval_bindings": [binding],
        "retrieval_sets": {binding["retrieval_set_sha256"]: retrieval_set},
        "retrieval_segments": segments,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    refs = {
        "include": include_anchor, "header_binding": header_binding,
        "header_source": header_source, "dependency_function": dependency_function,
        "dependency_binding": dependency_binding,
        "dependency_signature": dependency_signature,
        "dependency_source": dependency_source,
    }
    return bundle, refs


def query(failure_sha: str, requests: list[dict] | None = None) -> dict:
    return build_context_expansion_query(
        run_id=RUN_ID, unit_id=TARGET, query_epoch=2,
        requests=requests or [
            {"family": "include-adjacency", "anchor_fact_sha256": context_fixture()[1]["include"]},
            {"family": "dependency-scc-interface", "dependency_scc_id": DEPENDENCY},
            {"family": "verified-failure-fact", "failure_evidence_sha256": failure_sha},
        ],
    )


class ProjectMigrationContextFrontierWaveSelectionTests(unittest.TestCase):
    def test_derives_deterministic_bounded_directives_without_ready_claim(self) -> None:
        bundle, refs = context_fixture()
        failed = evidence()
        expansion = build_context_expansion_query(
            run_id=RUN_ID, unit_id=TARGET, query_epoch=2,
            requests=[
                {"family": "include-adjacency", "anchor_fact_sha256": refs["include"]},
                {"family": "dependency-scc-interface", "dependency_scc_id": DEPENDENCY},
                {"family": "verified-failure-fact",
                 "failure_evidence_sha256": failed["sha256"]},
            ],
        )
        wave = unit_input(failed["sha256"], expansion["sha256"])
        first = derive_context_frontier_wave_selection(
            wave, expansion_query=expansion,
            failed_verifier_evidence=[failed], context_bundle=bundle,
        )
        second = derive_context_frontier_wave_selection(
            deepcopy(wave), expansion_query=deepcopy(expansion),
            failed_verifier_evidence=[deepcopy(failed)], context_bundle=deepcopy(bundle),
        )

        self.assertEqual(first, second)
        self.assertEqual("bounded_selection_directives", first["status"])
        self.assertFalse(first["selection_ready"])
        self.assertTrue(first["requires_host_recompute"])
        self.assertEqual(CLAIM_BOUNDARY, first["claim_boundary"])
        self.assertEqual(
            sorted([refs["include"], refs["header_binding"], refs["header_source"]]),
            first["allowed_deferred_fact_refs"],
        )
        self.assertEqual(
            sorted([refs["dependency_function"], refs["dependency_binding"],
                    refs["dependency_signature"]]),
            first["required_interface_fact_refs"],
        )
        failure_fact = first["host_failure_facts"][0]
        self.assertEqual("host_verifier_failure", failure_fact["fact"]["kind"])
        self.assertTrue(failure_fact["fact"]["payload"]["model_input_safe"])
        self.assertEqual(
            hashlib.sha256(canonical(failure_fact["fact"])).hexdigest(),
            failure_fact["sha256"],
        )
        payload = {key: value for key, value in first.items() if key != "sha256"}
        self.assertEqual(content_sha256(payload), first["sha256"])

    def test_rejects_non_direct_dependency_and_out_of_scope_failure(self) -> None:
        bundle, _refs = context_fixture()
        failed = evidence()
        requests = [
            ({"family": "dependency-scc-interface", "dependency_scc_id": "scc-other"},
             "not a direct SCC dependency"),
            ({"family": "verified-failure-fact",
              "failure_evidence_sha256": digest("unbound-failure")},
             "outside the wave unit scope"),
        ]
        for request, message in requests:
            with self.subTest(message=message):
                expansion = query(failed["sha256"], [request])
                with self.assertRaisesRegex(ValueError, message):
                    derive_context_frontier_wave_selection(
                        unit_input(failed["sha256"], expansion["sha256"]),
                        expansion_query=expansion, failed_verifier_evidence=[failed],
                        context_bundle=bundle,
                    )

    def test_rejects_unknown_or_out_of_scope_include_anchor(self) -> None:
        bundle, refs = context_fixture()
        failed = evidence()
        for anchor in (digest("unknown-fact"), refs["dependency_source"]):
            with self.subTest(anchor=anchor):
                expansion = query(failed["sha256"], [
                    {"family": "include-adjacency", "anchor_fact_sha256": anchor},
                ])
                with self.assertRaisesRegex(ValueError, "outside the target SCC"):
                    derive_context_frontier_wave_selection(
                        unit_input(failed["sha256"], expansion["sha256"]),
                        expansion_query=expansion, failed_verifier_evidence=[failed],
                        context_bundle=bundle,
                    )

    def test_rejects_query_and_context_fact_tampering(self) -> None:
        bundle, refs = context_fixture()
        failed = evidence()
        expansion = query(failed["sha256"], [
            {"family": "include-adjacency", "anchor_fact_sha256": refs["include"]},
        ])
        wave = unit_input(failed["sha256"], expansion["sha256"])
        drifted_query = deepcopy(expansion)
        drifted_query["requests"][0]["anchor_fact_sha256"] = digest("changed")
        with self.assertRaisesRegex(ValueError, "binding drifted"):
            derive_context_frontier_wave_selection(
                wave, expansion_query=drifted_query,
                failed_verifier_evidence=[failed], context_bundle=bundle,
            )

        drifted_bundle = deepcopy(bundle)
        drifted_bundle["shared_facts"][refs["include"]]["payload"]["path"] = "include/changed.h"
        with self.assertRaisesRegex(ValueError, "fact SHA-256 drifted"):
            derive_context_frontier_wave_selection(
                wave, expansion_query=expansion,
                failed_verifier_evidence=[failed], context_bundle=drifted_bundle,
            )

    def test_requires_exact_hash_bound_failed_evidence_scope(self) -> None:
        bundle, refs = context_fixture()
        failed = evidence()
        expansion = query(failed["sha256"], [
            {"family": "include-adjacency", "anchor_fact_sha256": refs["include"]},
        ])
        wave = unit_input(failed["sha256"], expansion["sha256"])
        drifted = deepcopy(failed)
        drifted["evidence"]["diagnostics"][0]["code"] = "changed-code"
        with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
            derive_context_frontier_wave_selection(
                wave, expansion_query=expansion,
                failed_verifier_evidence=[drifted], context_bundle=bundle,
            )

        other = evidence(8, unit_id="scc-unrelated")
        with self.assertRaisesRegex(ValueError, "outside the wave unit scope"):
            derive_context_frontier_wave_selection(
                wave, expansion_query=expansion,
                failed_verifier_evidence=[other], context_bundle=bundle,
            )


if __name__ == "__main__":
    unittest.main()
