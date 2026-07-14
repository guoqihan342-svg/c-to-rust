from __future__ import annotations

import hashlib

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.context_contracts import canonical
from validation.tools._project_migration_harness.context_frontier_wave import (
    WAVE_INPUT_POLICY,
)
from validation.tools._project_migration_harness.context_frontier_wave_selection import (
    CLAIM_BOUNDARY,
    derive_context_frontier_wave_selection,
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


RUN_ID = "wave-materialization-run"
TARGET = "scc-target"
DEPENDENCY = "scc-dependency"
DIRECTIVE_KIND = "context-frontier-wave-selection-directives"


def derive_directives(
    bundle: dict, query: dict, failures: list[dict],
) -> dict:
    return derive_context_frontier_wave_selection(
        _wave_unit(query, failures),
        expansion_query=query,
        failed_verifier_evidence=failures,
        context_bundle=bundle,
    )


def _wave_unit(query: dict, failures: list[dict]) -> dict:
    failure_refs = sorted(item["sha256"] for item in failures)
    query_refs = [query["sha256"]]
    seed = {
        "policy": WAVE_INPUT_POLICY,
        "run_id": RUN_ID,
        "unit_id": TARGET,
        "wave_index": 1,
        "dag_sha256": digest("dag"),
        "group_sha256": digest("target-group"),
        "dependency_closure_sha256": digest("dependency-closure"),
        "failure_fact_set_sha256": content_sha256(failure_refs),
        "expansion_query_set_sha256": content_sha256(query_refs),
    }
    return {
        **seed,
        "failure_evidence_sha256s": failure_refs,
        "expansion_query_sha256s": query_refs,
        "selection_seed_sha256": content_sha256(seed),
    }


def failure_evidence() -> dict:
    payload = candidate_verdict_payload(
        run_id=RUN_ID,
        unit_id=DEPENDENCY,
        candidate_artifact_id="candidate-failed",
        candidate_sha256=digest("candidate-failed"),
        gate_family="compile",
        status="failed",
        diagnostics=[{
            "code": "rustc-type-error",
            "stage": "compile",
            "message": "type mismatch",
            "file": "src/dependency.rs",
            "line": 3,
            "column": 9,
        }],
    )
    return {
        "sequence": 7,
        "sha256": content_sha256(payload),
        "evidence": payload,
    }


def context_fixture(
    *, blocked: bool = False,
) -> tuple[dict, dict[str, str], list[dict], dict]:
    facts: dict[str, dict] = {}

    def add_fact(kind: str, payload: dict) -> str:
        fact = {"kind": kind, "payload": payload}
        fact_sha = hashlib.sha256(canonical(fact)).hexdigest()
        facts[fact_sha] = fact
        return fact_sha

    include = add_fact("include_binding", {
        "unit_id": "target-unit",
        "kind": "include",
        "body": '"extra.h"',
        "sha256": digest("include-line"),
        "byte_offset": 0,
        "from_path": "src/target.c",
        "target": "extra.h",
        "style": "quote",
        "status": "bound",
        "path": "include/extra.h",
    })
    header_binding = add_fact("header_source_binding", {
        "owner_id": "header-extra",
        "source": {
            "path": "include/extra.h",
            "sha256": digest("header-source"),
            "span": {
                "byte_start": 0,
                "byte_end": 24,
                "sha256": digest("header-span"),
            },
        },
    })
    header_source = add_fact("header_source", {
        "owner_id": "header-extra",
        "chunk_index": 0,
        "chunk_count": 1,
        "content": "#define EXTRA_LIMIT 8\n",
    })
    refs = [include, header_binding, header_source]
    if blocked:
        refs = [
            add_fact("function", {
                "node_id": "target-node",
                "unit_id": "target-unit",
                "node_kind": "function",
                "symbol": "target_step",
                "linkage": "external",
            }),
            add_fact("function_source", {
                "node_id": "target-node",
                "chunk_index": 0,
                "chunk_count": 1,
                "content": "int target_step(void) { return remote_step(1); }",
            }),
            add_fact("external_call", {
                "caller_node_id": "target-node",
                "symbol": "remote_step",
                "status": "unresolved_external",
                "candidate_node_ids": [],
            }),
            *refs,
        ]

    visible, binding, retrieval_set, segments = partition_context_refs(
        TARGET,
        refs,
        facts,
        add_fact,
        max_selected_bytes=8_192,
        identifier_cache={},
        selection_index=ContextSelectionIndex(facts),
    )
    if binding is None or retrieval_set is None:
        raise AssertionError("fixture must produce a retrieval binding")
    bundle = {
        "schema_version": 1,
        "shared_facts": {key: facts[key] for key in sorted(facts)},
        "pages": [{"scc_id": TARGET, "fact_refs": visible}],
        "retrieval_bindings": [binding],
        "retrieval_sets": {binding["retrieval_set_sha256"]: retrieval_set},
        "retrieval_segments": segments,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    entries = [{
        "scc_id": TARGET,
        "page_id": "page-base-target",
        "fact_refs": list(visible),
        "payload": b"base-page",
        "page_metadata": {"part_index": 0},
    }]
    return bundle, {
        "include": include,
        "header_binding": header_binding,
        "header_source": header_source,
    }, entries, binding


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


__all__ = [
    "DIRECTIVE_KIND",
    "RUN_ID",
    "TARGET",
    "context_fixture",
    "derive_directives",
    "digest",
    "failure_evidence",
]
