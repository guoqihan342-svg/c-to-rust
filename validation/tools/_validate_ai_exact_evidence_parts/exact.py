from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import EvidenceStore, fail, reject_accepted_proof, require_sha, sha256_file


GATES = (
    "rustc",
    "generated_replay",
    "schema_diff",
    "negative_mutation",
    "unsafe_scan",
    "unsafe_ledger",
    "alias_contract",
    "abi_contract",
    "oracle_contract",
    "final_verification",
)
EXPECTED_PASS_STATUS = {
    **{name: "passed" for name in GATES},
    "negative_mutation": "expected_failed",
}
ROUTER_GATE_SOURCES = {
    "compile": ("rustc",),
    "oracle": ("oracle_contract",),
    "replay": ("generated_replay",),
    "schema_diff": ("schema_diff",),
    "negative_diff": ("negative_mutation",),
    "unsafe": ("unsafe_scan", "unsafe_ledger"),
    "alias_abi": ("alias_contract", "abi_contract"),
    "final_verification": ("final_verification",),
}


def _router_gates(gates: dict[str, dict[str, Any]], candidate_sha: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for name, sources in ROUTER_GATE_SOURCES.items():
        passed = all(
            gates[source].get("candidate_sha256") == candidate_sha
            and gates[source].get("status") == EXPECTED_PASS_STATUS[source]
            for source in sources
        )
        output[name] = {
            "status": "passed" if passed else "failed",
            "candidate_sha256": candidate_sha,
            "source_gates": list(sources),
        }
    return output


def validate_exact_summary(
    store: EvidenceStore,
    ref: Any,
    label: str,
) -> dict[str, Any]:
    summary_path, summary = store.read_bound_json(ref, label)
    reject_accepted_proof(summary, label)
    if summary.get("schema_version") != 1:
        fail("summary_schema", f"{label}.schema_version must be 1", path=label)
    candidate_sha = require_sha(summary.get("candidate_sha256"), f"{label}.candidate_sha256")

    index_path, gate_index = store.read_bound_json(
        summary.get("gate_index"),
        f"{label}.gate_index",
        parent=summary_path.parent,
    )
    reject_accepted_proof(gate_index, f"{label}.gate_index")
    if gate_index.get("schema_version") != 1 or gate_index.get("candidate_sha256") != candidate_sha:
        fail("gate_index_binding", f"{label} gate-index candidate binding drift", path=label)
    refs = gate_index.get("gates")
    if not isinstance(refs, dict) or set(refs) != set(GATES):
        fail("gate_set_drift", f"{label} gate-index must contain the exact ten-gate set", path=label)

    frozen = store.resolve("candidate.rs", f"{label}.candidate", parent=index_path.parent)
    store.checked_artifacts += 1
    if sha256_file(frozen) != candidate_sha:
        fail("candidate_hash_drift", f"{label} frozen candidate SHA-256 drift", path=label)

    gates: dict[str, dict[str, Any]] = {}
    for name in GATES:
        _, payload = store.read_bound_json(
            refs.get(name),
            f"{label}.gates.{name}",
            parent=index_path.parent,
        )
        reject_accepted_proof(payload, f"{label}.gates.{name}")
        if payload.get("candidate_sha256") != candidate_sha:
            fail("gate_candidate_drift", f"{label}.{name} candidate SHA-256 drift", path=label)
        gates[name] = payload

    if summary.get("gates") != gates:
        fail("summary_gate_drift", f"{label} inline gates differ from gate files", path=label)
    required_passed = all(
        gates[name].get("status") == EXPECTED_PASS_STATUS[name]
        for name in GATES[:-1]
    )
    final = gates["final_verification"]
    semantic_pass = (
        required_passed
        and final.get("status") == "passed"
        and final.get("semantic_pass") is True
        and final.get("required_gates") == list(GATES[:-1])
    )
    if final.get("semantic_pass") is True and not semantic_pass:
        fail("false_semantic_pass", f"{label} final gate claims an invalid semantic pass", path=label)
    expected_status = "passed" if semantic_pass else "failed"
    if summary.get("status") != expected_status or summary.get("semantic_pass") is not semantic_pass:
        fail("summary_status_drift", f"{label} status does not match its exact gates", path=label)

    router_gates = _router_gates(gates, candidate_sha)
    if summary.get("router_gate_results") != router_gates:
        fail("router_gate_drift", f"{label} router gate projection drift", path=label)
    if ref.get("status") != expected_status:
        fail("summary_ref_status_drift", f"{label} reference status drift", path=label)
    return {
        "path": summary_path,
        "candidate_sha256": candidate_sha,
        "semantic_pass": semantic_pass,
        "status": expected_status,
        "router_gate_results": router_gates,
    }
