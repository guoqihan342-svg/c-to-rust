from __future__ import annotations
import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any
from .artifacts import content_sha256
from .context_contracts import canonical
from .context_frontier_wave import WAVE_INPUT_POLICY, validate_context_expansion_query
from .context_retrieval import DEFERRED_FACT_KINDS, validate_retrieval_bundle
from .gate_authority import candidate_kind, validate_candidate_verdict
from .gate_diagnostics import normalize_gate_evidence
WAVE_SELECTION_POLICY = "host-context-frontier-wave-selection-v1"
CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UNIT_KEYS = {
    "policy", "run_id", "unit_id", "wave_index", "dag_sha256", "group_sha256",
    "dependency_closure_sha256", "failure_fact_set_sha256",
    "expansion_query_set_sha256", "failure_evidence_sha256s",
    "expansion_query_sha256s", "selection_seed_sha256",
}
_SEED_KEYS = (
    "policy", "run_id", "unit_id", "wave_index", "dag_sha256", "group_sha256",
    "dependency_closure_sha256", "failure_fact_set_sha256",
    "expansion_query_set_sha256",
)
_INTERFACE_KINDS = {"function", "source_binding", "function_signature", "parser_boundary"}
_MAX_FACTS, _MAX_PAGES, _MAX_FAILURES = 100_000, 10_000, 4_096
def derive_context_frontier_wave_selection(
    wave_unit_input: Mapping[str, Any], *, expansion_query: Mapping[str, Any] | None,
    failed_verifier_evidence: Sequence[Mapping[str, Any]],
    context_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive bounded host directives; never publish a recomputed ready bundle."""
    unit = _unit(wave_unit_input)
    query = _query(expansion_query, unit)
    failures = _failures(failed_verifier_evidence, unit)
    facts, pages, retrieval = _bundle(context_bundle)
    visible = pages.get(unit["unit_id"])
    _require(bool(visible), "wave selection unit has no context pages")
    omitted = set(retrieval.get(unit["unit_id"], {}).get("fact_refs", []))
    constraints, allowed, interfaces, host_facts = [], set(), set(), {}
    for request in [] if query is None else query["requests"]:
        family, request_sha = request["family"], content_sha256(request)
        if family == "include-adjacency":
            refs = _include(request["anchor_fact_sha256"], facts, visible | omitted, omitted)
            allowed.update(refs)
            constraint = {
                "family": family, "request_sha256": request_sha,
                "anchor_fact_sha256": request["anchor_fact_sha256"],
                "allowed_deferred_fact_refs": refs,
            }
        elif family == "dependency-scc-interface":
            refs = _interface(unit["unit_id"], request["dependency_scc_id"], facts, pages, visible)
            interfaces.update(refs)
            constraint = {
                "family": family, "request_sha256": request_sha,
                "dependency_scc_id": request["dependency_scc_id"],
                "required_interface_fact_refs": refs,
            }
        else:
            evidence_sha = request["failure_evidence_sha256"]
            _require(evidence_sha in failures, "failure request is outside the wave unit scope")
            fact_sha, fact = _failure_fact(unit["unit_id"], evidence_sha, failures[evidence_sha])
            host_facts[fact_sha] = fact
            constraint = {
                "family": family, "request_sha256": request_sha,
                "failure_evidence_sha256": evidence_sha,
                "host_failure_fact_sha256": fact_sha,
            }
        constraints.append(constraint)
    constraints.sort(key=lambda item: (item["family"], item["request_sha256"]))
    host_records = [{"sha256": digest, "fact": host_facts[digest]} for digest in sorted(host_facts)]
    evidence_index = [
        {"sequence": record["sequence"], "sha256": digest}
        for digest, record in sorted(failures.items())
    ]
    allowed_refs, interface_refs = sorted(allowed), sorted(interfaces)
    payload = {
        "schema_version": 1, "artifact_kind": "context-frontier-wave-selection-directives",
        "policy": WAVE_SELECTION_POLICY, "run_id": unit["run_id"],
        "unit_id": unit["unit_id"], "wave_index": unit["wave_index"],
        "status": "bounded_selection_directives", "selection_ready": False,
        "requires_host_recompute": True,
        "input_bindings": {
            "wave_selection_seed_sha256": unit["selection_seed_sha256"],
            "context_bundle_sha256": content_sha256(context_bundle),
            "expansion_query_sha256": None if query is None else query["sha256"],
            "failure_evidence_set_sha256": unit["failure_fact_set_sha256"],
            "failed_verifier_evidence_index_sha256": content_sha256(evidence_index),
        },
        "selection_constraints": constraints,
        "selection_constraint_set_sha256": content_sha256(constraints),
        "allowed_deferred_fact_refs": allowed_refs,
        "allowed_deferred_fact_set_sha256": content_sha256(allowed_refs),
        "required_interface_fact_refs": interface_refs,
        "required_interface_fact_set_sha256": content_sha256(interface_refs),
        "host_failure_facts": host_records,
        "host_failure_fact_set_sha256": content_sha256(host_records),
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    return {**payload, "sha256": content_sha256(payload)}
def _unit(value: Any) -> dict[str, Any]:
    _require(isinstance(value, Mapping) and set(value) == _UNIT_KEYS, "wave unit input shape is invalid")
    result = dict(value)
    _require(result.get("policy") == WAVE_INPUT_POLICY, "wave unit input policy is invalid")
    _text(result.get("run_id"), "wave unit run_id")
    _text(result.get("unit_id"), "wave unit unit_id")
    _count(result.get("wave_index"), "wave unit wave_index")
    for key in (*_SEED_KEYS[4:], "selection_seed_sha256"):
        _digest(result.get(key), f"wave unit {key}")
    failures = _sha_list(result.get("failure_evidence_sha256s"), _MAX_FAILURES)
    queries = _sha_list(result.get("expansion_query_sha256s"), 1)
    _require(content_sha256(failures) == result["failure_fact_set_sha256"],
             "wave unit failure evidence set drifted")
    _require(content_sha256(queries) == result["expansion_query_set_sha256"],
             "wave unit expansion query set drifted")
    seed = {key: result[key] for key in _SEED_KEYS}
    _require(content_sha256(seed) == result["selection_seed_sha256"],
             "wave unit selection seed drifted")
    result["failure_evidence_sha256s"], result["expansion_query_sha256s"] = failures, queries
    return result
def _query(value: Mapping[str, Any] | None, unit: Mapping[str, Any]) -> dict[str, Any] | None:
    expected = unit["expansion_query_sha256s"]
    if not expected:
        _require(value is None, "wave unit does not bind an expansion query")
        return None
    _require(value is not None, "wave unit expansion query is missing")
    query = validate_context_expansion_query(value)
    _require(
        query["run_id"] == unit["run_id"] and query["unit_id"] == unit["unit_id"]
        and [query["sha256"]] == expected,
        "expansion query is outside the wave unit scope",
    )
    return query
def _bundle(value: Any) -> tuple[
    dict[str, Mapping[str, Any]], dict[str, set[str]], dict[str, dict[str, Any]],
]:
    _require(isinstance(value, Mapping) and value.get("claim_boundary") == CLAIM_BOUNDARY,
             "context bundle claim boundary is invalid")
    raw_facts = value.get("shared_facts")
    _require(isinstance(raw_facts, Mapping) and len(raw_facts) <= _MAX_FACTS,
             "context bundle shared facts are invalid")
    raw_pages = _items(value.get("pages"), "context bundle pages", _MAX_PAGES)
    for key, expected, default, limit in (
        ("retrieval_bindings", list, [], _MAX_PAGES), ("retrieval_sets", Mapping, {}, _MAX_FACTS),
        ("retrieval_segments", Mapping, {}, _MAX_FACTS),
    ):
        raw_index = value.get(key, default)
        _require(isinstance(raw_index, expected) and len(raw_index) <= limit, f"context bundle {key} is unbounded")
    facts: dict[str, Mapping[str, Any]] = {}
    for digest, fact in raw_facts.items():
        valid = (
            isinstance(digest, str) and _SHA.fullmatch(digest) is not None
            and isinstance(fact, Mapping) and set(fact) == {"kind", "payload"}
            and isinstance(fact.get("kind"), str) and bool(fact["kind"])
            and isinstance(fact.get("payload"), Mapping)
            and hashlib.sha256(canonical(fact)).hexdigest() == digest
        )
        _require(valid, "context bundle fact SHA-256 drifted")
        facts[digest] = fact
    pages: dict[str, set[str]] = {}
    for page in raw_pages:
        _require(isinstance(page, Mapping), "context bundle page is invalid")
        scc_id = _text(page.get("scc_id"), "context page SCC")
        refs = _sha_list(page.get("fact_refs"), _MAX_FACTS, canonical_order=False)
        _require(all(ref in facts for ref in refs), "context page references an unknown fact")
        pages.setdefault(scc_id, set()).update(refs)
    return facts, pages, validate_retrieval_bundle(value, facts, raw_pages)

def _include(
    anchor: str, facts: Mapping[str, Mapping[str, Any]], scoped: set[str], omitted: set[str],
) -> list[str]:
    _require(anchor in scoped and anchor in facts,
             "include adjacency anchor is outside the target SCC")
    fact, payload = facts[anchor], facts[anchor].get("payload")
    _require(fact.get("kind") == "include_binding" and isinstance(payload, Mapping),
             "include adjacency anchor is not an include binding")
    path = payload.get("path")
    _require(
        payload.get("status") == "bound" and isinstance(path, str) and bool(path)
        and isinstance(payload.get("unit_id"), str) and isinstance(payload.get("from_path"), str),
        "include adjacency anchor is not a bound include",
    )
    owners = set()
    for ref in scoped:
        item, body = facts[ref], facts[ref].get("payload")
        if item.get("kind") == "header_source_binding" and isinstance(body, Mapping):
            source = body.get("source")
            if isinstance(body.get("owner_id"), str) and isinstance(source, Mapping) \
                    and source.get("path") == path:
                owners.add(body["owner_id"])
    allowed = {
        ref for ref in omitted if ref == anchor or (
            facts[ref].get("kind") in {"header_source_binding", "header_source"}
            and facts[ref].get("payload", {}).get("owner_id") in owners
        )
    }
    _require(
        bool(owners) and bool(allowed)
        and all(facts[ref].get("kind") in DEFERRED_FACT_KINDS for ref in allowed),
        "include adjacency has no bounded deferred facts",
    )
    return sorted(allowed)

def _interface(
    unit_id: str, dependency_id: str, facts: Mapping[str, Mapping[str, Any]],
    pages: Mapping[str, set[str]], visible: set[str],
) -> list[str]:
    direct = {
        facts[ref]["payload"].get("dependency_scc_id") for ref in visible
        if facts[ref].get("kind") == "scc_dependency"
        and facts[ref]["payload"].get("scc_id") == unit_id
    }
    _require(dependency_id in direct, "dependency interface is not a direct SCC dependency")
    dependency_refs = pages.get(dependency_id)
    _require(bool(dependency_refs), "dependency interface SCC has no context pages")
    nodes = {
        facts[ref]["payload"].get("node_id") for ref in dependency_refs
        if facts[ref].get("kind") == "function_source"
    }
    refs = sorted(
        ref for ref in visible if facts[ref].get("kind") in _INTERFACE_KINDS
        and facts[ref]["payload"].get("node_id") in nodes
    )
    _require(nodes and refs and any(facts[ref].get("kind") == "function" for ref in refs),
             "direct dependency SCC interface is incomplete")
    return refs

def _failures(values: Any, unit: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    wrappers = _items(values, "failed verifier evidence", _MAX_FAILURES)
    result, sequences = {}, set()
    for wrapper in wrappers:
        _require(isinstance(wrapper, Mapping) and set(wrapper) == {"sequence", "sha256", "evidence"},
                 "failed verifier evidence wrapper shape is invalid")
        sequence = _count(wrapper.get("sequence"), "failed verifier sequence")
        digest, evidence = _digest(wrapper.get("sha256"), "failed verifier SHA-256"), wrapper.get("evidence")
        _require(sequence not in sequences and digest not in result,
                 "failed verifier evidence identity is duplicated")
        _require(isinstance(evidence, Mapping) and content_sha256(evidence) == digest,
                 "failed verifier evidence SHA-256 drifted")
        _require(evidence.get("run_id") == unit["run_id"] and evidence.get("status") == "failed",
                 "failed verifier evidence is outside the wave run")
        family = evidence.get("gate_family")
        validate_candidate_verdict(
            evidence, run_id=unit["run_id"], unit_id=evidence.get("unit_id"),
            candidate_artifact_id=evidence.get("candidate_artifact_id"),
            candidate_sha256=evidence.get("candidate_sha256"), gate_family=family,
            candidate_set_sha256=evidence.get("candidate_set_sha256"), status="failed",
            verifier_id=evidence.get("authority_id"), kind=candidate_kind(family),
        )
        safe = normalize_gate_evidence(
            gate_family=family, status="failed", candidate_artifact_id=evidence["candidate_artifact_id"],
            candidate_sha256=evidence["candidate_sha256"], diagnostics=evidence["diagnostics"],
        )
        _require(safe["diagnostics"] == evidence["diagnostics"],
                 "failed verifier diagnostics are not model-safe")
        sequences.add(sequence)
        result[digest] = {"sequence": sequence, "evidence": dict(evidence), "safe": safe}
    _require(set(result) == set(unit["failure_evidence_sha256s"]),
             "failed verifier evidence is outside the wave unit scope")
    return result

def _failure_fact(consumer: str, digest: str, record: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    evidence, safe = record["evidence"], record["safe"]
    fact = {"kind": "host_verifier_failure", "payload": {
        "consumer_unit_id": consumer, "source_unit_id": evidence["unit_id"],
        "gate_family": evidence["gate_family"], "candidate_artifact_id": evidence["candidate_artifact_id"],
        "candidate_sha256": evidence["candidate_sha256"],
        "candidate_set_sha256": evidence["candidate_set_sha256"],
        "failure_evidence_sha256": digest, "diagnostics": safe["diagnostics"],
        "withheld_fields": safe["withheld_fields"], "model_input_safe": True,
    }}
    return hashlib.sha256(canonical(fact)).hexdigest(), fact

def _items(value: Any, label: str, limit: int) -> list[Any]:
    _require(isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
             and len(value) <= limit, f"{label} must be a bounded array")
    return list(value)

def _sha_list(value: Any, limit: int, *, canonical_order: bool = True) -> list[str]:
    result = _items(value, "SHA-256 list", limit)
    _require(all(isinstance(item, str) and _SHA.fullmatch(item) for item in result),
             "SHA-256 list contains an invalid value")
    _require(len(result) == len(set(result)) and (not canonical_order or result == sorted(result)),
             "SHA-256 list is not canonical")
    return result

def _digest(value: Any, label: str) -> str:
    _require(isinstance(value, str) and _SHA.fullmatch(value) is not None, f"{label} is invalid")
    return value
def _count(value: Any, label: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{label} is invalid")
    return value
def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and 0 < len(value) <= 256, f"{label} is invalid")
    return value
def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)
__all__ = ["WAVE_SELECTION_POLICY", "derive_context_frontier_wave_selection"]
