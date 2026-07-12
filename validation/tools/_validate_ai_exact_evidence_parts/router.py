from __future__ import annotations

from typing import Any

from validation.tools._ai_candidate_harness_parts.router import (
    MODEL_IDENTITY_FIELDS,
    REQUIRED_GATES,
    build_selection_policy,
    route_candidates,
    selection_policy_sha256,
)

from .exact import validate_exact_summary
from .io import EvidenceStore, fail, reject_accepted_proof, require_sha
from .repair import validate_c2rust_repair_audit


SOURCE_REF_KEYS = {
    "opencode-ai": "ai",
    "typed-ir": "typed_ir",
    "c2rust-repair": "c2rust_repair",
    "c2rust-baseline": "c2rust_baseline",
}
ROUTER_FIELDS = (
    "selection_policy",
    "selection_policy_sha256",
    "provider_invocations",
    "selected_candidate_id",
    "candidate_set",
    "deduplicated_candidates",
    "metrics",
)


def validate_router(store: EvidenceStore, router: dict[str, Any]) -> dict[str, Any]:
    reject_accepted_proof(router, "router")
    if router.get("schema_version") != 1:
        fail("router_schema", "router.schema_version must be 1", path="router")
    policy = router.get("selection_policy")
    if not isinstance(policy, dict):
        fail("policy_missing", "router selection_policy must be an object", path="router")
    budget_record = policy.get("provider_invocation_budget")
    effective = budget_record.get("effective") if isinstance(budget_record, dict) else None
    if isinstance(effective, bool) or not isinstance(effective, int):
        fail("policy_budget", "router policy effective budget is invalid", path="router")
    try:
        expected_policy = build_selection_policy(provider_invocation_budget=effective)
    except ValueError as error:
        fail("policy_budget", str(error), path="router")
        raise AssertionError from error
    if policy != expected_policy:
        fail("policy_drift", "router selection policy differs from the canonical policy", path="router")
    policy_sha = selection_policy_sha256(policy)
    if require_sha(router.get("selection_policy_sha256"), "router.selection_policy_sha256") != policy_sha:
        fail("policy_hash_drift", "router selection policy SHA-256 drift", path="router")

    candidate_set = router.get("candidate_set")
    duplicates = router.get("deduplicated_candidates")
    evidence = router.get("candidate_evidence")
    if not isinstance(candidate_set, list) or not isinstance(duplicates, list):
        fail("candidate_set_invalid", "router candidate arrays are required", path="router")
    if not isinstance(evidence, dict):
        fail("candidate_evidence_invalid", "router candidate_evidence must be an object", path="router")

    summaries: dict[str, dict[str, Any]] = {}
    inputs: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    by_sha: dict[str, dict[str, Any]] = {}
    expected_ref_keys: set[str] = set()
    for candidate in candidate_set:
        if not isinstance(candidate, dict):
            fail("candidate_invalid", "router candidate must be an object", path="router")
        source = candidate.get("source")
        if not isinstance(source, str):
            fail("candidate_source_invalid", "router candidate source must be a string", path="router")
        ref_key = SOURCE_REF_KEYS.get(source)
        if ref_key is None or source in seen_sources:
            fail("candidate_source_invalid", "router requires one exact candidate per supported source", path="router")
        seen_sources.add(source)
        expected_ref_keys.add(ref_key)
        if ref_key not in evidence:
            fail("candidate_evidence_missing", f"router candidate evidence missing for {source}", path="router")
        summary = validate_exact_summary(store, evidence[ref_key], f"router.candidate_evidence.{ref_key}")
        artifact_sha = require_sha(candidate.get("artifact_sha256"), f"router.{ref_key}.artifact_sha256")
        if summary["candidate_sha256"] != artifact_sha:
            fail("candidate_artifact_drift", f"router {source} artifact binding drift", path="router")
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            fail("candidate_id_invalid", "router candidate_id must be a non-empty string", path="router")
        summaries[candidate_id] = summary
        by_sha[artifact_sha] = summary
        inputs.append(
            {
                "candidate_id": candidate_id,
                "source": source,
                "artifact_sha256": artifact_sha,
                "gate_results": summary["router_gate_results"],
                **{
                    field: candidate[field]
                    for field in MODEL_IDENTITY_FIELDS
                    if field in candidate
                },
            }
        )
    if set(evidence) != expected_ref_keys:
        fail("candidate_evidence_drift", "router candidate_evidence keys drift from candidate_set", path="router")

    repair_rounds = validate_c2rust_repair_audit(store, router)

    for duplicate in duplicates:
        if not isinstance(duplicate, dict):
            fail("duplicate_invalid", "router duplicate candidate must be an object", path="router")
        digest = require_sha(duplicate.get("artifact_sha256"), "router.duplicate.artifact_sha256")
        summary = by_sha.get(digest)
        if summary is None:
            fail("duplicate_binding", "router duplicate has no exact candidate artifact", path="router")
        inputs.append(
            {
                "candidate_id": duplicate.get("candidate_id"),
                "source": duplicate.get("source"),
                "artifact_sha256": digest,
                "gate_results": summary["router_gate_results"],
            }
        )

    try:
        expected = route_candidates(
            inputs,
            provider_invocation_budget=effective,
            provider_invocations=router.get("provider_invocations"),
        )
    except ValueError as error:
        fail("router_contract", str(error), path="router")
        raise AssertionError from error
    for field in ROUTER_FIELDS:
        if router.get(field) != expected.get(field):
            fail("router_recompute_drift", f"router.{field} differs from recomputed route", path="router")

    selected_id = expected.get("selected_candidate_id")
    semantic_pass = selected_id is not None
    if router.get("semantic_pass") is not semantic_pass:
        fail("router_semantic_drift", "router semantic_pass differs from selection", path="router")
    selected = summaries.get(selected_id)
    if selected_id is not None:
        if selected is None or not selected["semantic_pass"]:
            fail("selected_candidate_invalid", "selected candidate lacks exact semantic evidence", path="router")
        if set(selected["router_gate_results"]) != set(REQUIRED_GATES) or not all(
            gate.get("status") == "passed" for gate in selected["router_gate_results"].values()
        ):
            fail("selected_gate_failure", "selected candidate did not pass all eight router gates", path="router")
    return {
        "selected_candidate_id": selected_id,
        "selected_candidate_sha256": selected["candidate_sha256"] if selected else None,
        "semantic_pass": semantic_pass,
        "candidate_count": len(candidate_set) + len(duplicates),
        "metrics": expected["metrics"],
        "repair_rounds": repair_rounds,
    }
